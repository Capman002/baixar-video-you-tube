import yt_dlp
import asyncio
import uuid
import os
from typing import Optional, Dict, Any
from pathlib import Path
from src.settings import settings
import logging

logger = logging.getLogger("uvicorn")

class DownloadService:
    def __init__(self, sio):
        self.sio = sio

    async def _emit(self, event: str, data: Dict[str, Any], sid: str):
        # SocketIO emit is async-friendly in python-socketio
        await self.sio.emit(event, data, room=sid)

    def _get_cookies_path(self) -> Optional[str]:
        if settings.COOKIES_FILE.exists() and settings.COOKIES_FILE.stat().st_size > 200:
            return str(settings.COOKIES_FILE)
        return None

    def _progress_hook_factory(self, sid: str):
        # We need a closure to capture sid, but the hook is sync
        # We can't await inside the hook directly unless we use an event loop helper
        # Usually python-socketio background tasks handle this, or we use call_soon_threadsafe
        # For simplicity in thread, we can use a sync emit if supported or run_coroutine_threadsafe
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        def hook(d):
            if d['status'] == 'downloading':
                try:
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    percentage = (downloaded / total * 100) if total else 0
                    
                    # Hack: running async emit from sync thread
                    # Simplification: In production, use redis queue for status updates
                    # Here we just print log or try to bridge
                    # Actually, python-socketio 'emit' is often thread-safe if using 'server.emit'
                    # But since we passed 'sio' which is AsyncServer, we need loop.
                    pass # Handled by outer thread wrapper if possible, or just skip granular progress for now to keep code clean?
                    # NO, user wants progress.
                    
                    # Valid Modern Python Approach:
                    # Capture data, put in Queue, Consume Queue in Main Async Loop.
                    # Too complex for this snippet?
                    # Let's use the 'external' sync emit method if available or just ignore strict async purity for the hook.
                    
                    # Simpler: The hook runs in the thread. 
                    # We can use `asyncio.run_coroutine_threadsafe` against the MAIN loop.
                    pass
                except Exception:
                    pass

        return hook

    async def download_video(self, url: str, sid: str):
        job_id = str(uuid.uuid4())
        output_tmpl = settings.DOWNLOAD_DIR / f"{job_id}.%(ext)s"
        
        cookies_path = self._get_cookies_path()
        
        # Modern: Define options clearly
        ydl_opts = {
            # Prefer MP4/M4A native formats, fallback to any and convert
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': str(output_tmpl),
            'noplaylist': True,
            'quiet': True,
            'nocheckcertificate': True,
            'logger': logger,
            # Force audio re-encoding to AAC during merge (fixes Opus/WebM audio issues)
            'postprocessor_args': {
                'merger': ['-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k']
            },
        }

        # Professional Auth handling
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path
            logger.info("Using auth cookies.")
        
        # POT Provider Integration
        # The bgutil-ytdlp-pot-provider plugin auto-detects the POT server at localhost:4416
        # For custom POT server URL, we can use extractor_args
        pot_url = os.environ.get('POT_PROVIDER_URL')
        if pot_url:
            logger.info(f"POT Provider configured: {pot_url}")
            ydl_opts['extractor_args'] = {
                'youtubepot-bgutilhttp': {
                    'base_url': pot_url
                }
            }
        else:
            # Local development: Plugin will auto-detect localhost:4416
            logger.info("Using default POT Provider (localhost:4416 if available)")


        loop = asyncio.get_running_loop()

        def run_thread():
            # Sync wrapper for YT-DLP
            # We enforce MP4
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # We can inject a custom progress hook here that calls loop.call_soon_threadsafe
                def progress(d):
                    if d['status'] == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                        down = d.get('downloaded_bytes', 0)
                        pct = (down / total * 100) if total else 0
                        speed = d.get('speed') or 0
                        
                        payload = {
                            "percentage": round(pct, 2),
                            "speed": f"{speed/1024/1024:.1f} MB/s",
                            "status": "downloading"
                        }
                        
                        future = asyncio.run_coroutine_threadsafe(
                            self.sio.emit('download_progress', payload, room=sid), 
                            loop
                        )
                
                ydl_opts['progress_hooks'] = [progress]
                # Re-init with hooks
                with yt_dlp.YoutubeDL(ydl_opts) as ydl_with_hooks:
                    info = ydl_with_hooks.extract_info(url, download=True)
                    return info

        try:
            # Run blocking code in thread pool
            info = await loop.run_in_executor(None, run_thread)
            
            # Post-processing
            title = info.get('title', 'video')
            ext = 'mp4' # Forced above
            
            # Locate file (since yt-dlp might merge keys)
            # We look for the file starting with job_id
            possible_files = list(settings.DOWNLOAD_DIR.glob(f"{job_id}*"))
            if not possible_files:
                raise FileNotFoundError("Processing failed to create file.")
            
            actual_file = possible_files[0]
            # Rename to safe title
            # Pydantic/Strict approach:
            safe_title = "".join([c for c in title if c.isalnum() or c in (' ','-','_')]).strip()
            final_path = settings.DOWNLOAD_DIR / f"{safe_title}.{actual_file.suffix}"
            
            if final_path.exists():
                final_path.unlink()
            
            actual_file.rename(final_path)
            
            await self.sio.emit('download_complete', {
                "url": f"/api/files/{final_path.name}",
                "filename": final_path.name
            }, room=sid)

        except Exception as e:
            logger.error(f"Download invalid: {e}")
            await self.sio.emit('download_error', {"error": str(e)}, room=sid)
