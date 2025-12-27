"""
Serviço de Download refatorado.
Suporta múltiplos formatos, qualidades, playlists e sistema de fila.
"""
import yt_dlp
import asyncio
import os
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from src.settings import settings
from src.models import (
    DownloadFormat,
    VideoQuality,
    AudioQuality,
    DownloadStatus,
    get_format_string,
    detect_platform
)
from src.queue_manager import QueuedDownload, queue_manager
from src.database import (
    get_db_session,
    create_download_record,
    update_download_status
)

logger = logging.getLogger("uvicorn")


class DownloadService:
    """
    Serviço de download com suporte a:
    - Múltiplos formatos (vídeo MP4, áudio MP3)
    - Múltiplas qualidades
    - Playlists
    - Progress em tempo real via SocketIO
    - Persistência no banco de dados
    """
    
    def __init__(self, sio):
        self.sio = sio
    
    async def _emit(self, event: str, data: Dict[str, Any], sid: str):
        """Emite evento via SocketIO."""
        if sid:
            await self.sio.emit(event, data, room=sid)
    
    def _get_cookies_path(self) -> Optional[str]:
        """Retorna path dos cookies se disponível."""
        if settings.COOKIES_FILE.exists() and settings.COOKIES_FILE.stat().st_size > 200:
            return str(settings.COOKIES_FILE)
        return None
    
    def _build_ydl_opts(
        self,
        output_template: str,
        format_type: DownloadFormat,
        video_quality: VideoQuality,
        audio_quality: AudioQuality,
        playlist_items: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Constrói as opções do yt-dlp."""
        
        format_string = get_format_string(format_type, video_quality, audio_quality)
        
        opts = {
            'format': format_string,
            'outtmpl': output_template,
            'noplaylist': False,  # Permite playlists
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'logger': logger,
            'ignoreerrors': True,  # Continua em erros de itens individuais
        }
        
        # Merge para MP4
        if format_type == DownloadFormat.VIDEO:
            opts['merge_output_format'] = 'mp4'
            opts['postprocessor_args'] = {
                'merger': ['-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k']
            }
        
        # Extração de áudio
        if format_type == DownloadFormat.AUDIO:
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': audio_quality.value,
            }]
        
        # Seleção de itens da playlist
        if playlist_items:
            opts['playlist_items'] = ','.join(str(i) for i in playlist_items)
        
        # Cookies
        cookies_path = self._get_cookies_path()
        if cookies_path:
            opts['cookiefile'] = cookies_path
            logger.info("Usando cookies de autenticação")
        
        # POT Provider
        if settings.POT_PROVIDER_URL:
            opts['extractor_args'] = {
                'youtubepot-bgutilhttp': {
                    'base_url': settings.POT_PROVIDER_URL
                }
            }
            logger.info(f"POT Provider: {settings.POT_PROVIDER_URL}")
        
        return opts
    
    async def process_download(self, item: QueuedDownload):
        """
        Processa um download da fila.
        Este método é chamado pelo QueueManager.
        """
        job_id = item.job_id
        sid = item.sid
        
        # Parse enums
        format_type = DownloadFormat(item.format)
        video_quality = VideoQuality(item.video_quality)
        audio_quality = AudioQuality(item.audio_quality)
        
        # Template de saída
        ext = "mp3" if format_type == DownloadFormat.AUDIO else "mp4"
        output_template = str(settings.DOWNLOAD_DIR / f"{job_id}_%(playlist_index)s.%(ext)s")
        
        # Cria registro no banco
        async with get_db_session() as session:
            await create_download_record(
                session=session,
                job_id=job_id,
                url=item.url,
                platform=item.platform,
                format=item.format,
                quality=item.video_quality,
                title=item.title
            )
        
        # Notifica início
        await self._emit('download_status', {
            'job_id': job_id,
            'status': 'fetching_info',
            'message': 'Obtendo informações...'
        }, sid)
        
        # Opções do yt-dlp
        ydl_opts = self._build_ydl_opts(
            output_template=output_template,
            format_type=format_type,
            video_quality=video_quality,
            audio_quality=audio_quality,
            playlist_items=item.playlist_items
        )
        
        loop = asyncio.get_running_loop()
        
        def run_download():
            """Executa o download em thread separada."""
            downloaded_files = []
            total_items = 1
            current_item = 0
            
            def progress_hook(d):
                nonlocal current_item
                
                if d['status'] == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    percentage = (downloaded / total * 100) if total else 0
                    speed = d.get('speed') or 0
                    eta = d.get('eta')
                    
                    payload = {
                        'job_id': job_id,
                        'status': 'downloading',
                        'percentage': round(percentage, 1),
                        'speed': f"{speed/1024/1024:.1f} MB/s" if speed else "...",
                        'eta': f"{eta}s" if eta else None,
                        'current_item': current_item + 1,
                        'total_items': total_items
                    }
                    
                    # Atualiza fila
                    queue_manager.update_progress(job_id, percentage, DownloadStatus.DOWNLOADING)
                    
                    # Emite via thread-safe
                    asyncio.run_coroutine_threadsafe(
                        self._emit('download_progress', payload, sid),
                        loop
                    )
                
                elif d['status'] == 'finished':
                    filename = d.get('filename')
                    if filename:
                        downloaded_files.append(filename)
                    current_item += 1
            
            # Adiciona hook
            ydl_opts['progress_hooks'] = [progress_hook]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Primeiro extrai info para saber quantidade
                info = ydl.extract_info(item.url, download=False)
                
                if info.get('_type') == 'playlist':
                    entries = info.get('entries', [])
                    total_items = len([e for e in entries if e])
                    title = info.get('title', 'Playlist')
                else:
                    title = info.get('title', 'video')
                
                # Atualiza título na fila
                queue_manager.update_title(job_id, title)
                
                # Faz o download
                ydl.download([item.url])
            
            return {
                'title': title,
                'files': downloaded_files,
                'total_items': total_items
            }
        
        try:
            # Executa download em thread pool
            result = await loop.run_in_executor(None, run_download)
            
            # Processa arquivos baixados
            files = list(settings.DOWNLOAD_DIR.glob(f"{job_id}_*"))
            
            if not files:
                raise FileNotFoundError("Nenhum arquivo foi baixado")
            
            # Se for um único arquivo, renomeia
            if len(files) == 1:
                original = files[0]
                safe_title = "".join(
                    c for c in result['title'] 
                    if c.isalnum() or c in (' ', '-', '_')
                ).strip()[:100]
                
                final_name = f"{safe_title}{original.suffix}"
                final_path = settings.DOWNLOAD_DIR / final_name
                
                # Remove se existir
                if final_path.exists():
                    final_path.unlink()
                
                original.rename(final_path)
                
                # Atualiza banco
                async with get_db_session() as session:
                    await update_download_status(
                        session=session,
                        job_id=job_id,
                        status=DownloadStatus.COMPLETED,
                        progress=100,
                        file_path=str(final_path),
                        file_size=final_path.stat().st_size,
                        title=result['title']
                    )
                
                # Notifica conclusão
                queue_manager.mark_completed(job_id)
                
                await self._emit('download_complete', {
                    'job_id': job_id,
                    'url': f"/api/files/{final_path.name}",
                    'filename': final_path.name,
                    'file_size': final_path.stat().st_size
                }, sid)
            
            else:
                # Múltiplos arquivos (playlist)
                # Cria um ZIP ou notifica individualmente
                file_list = []
                
                for f in files:
                    file_list.append({
                        'url': f"/api/files/{f.name}",
                        'filename': f.name
                    })
                
                async with get_db_session() as session:
                    await update_download_status(
                        session=session,
                        job_id=job_id,
                        status=DownloadStatus.COMPLETED,
                        progress=100,
                        title=result['title']
                    )
                
                queue_manager.mark_completed(job_id)
                
                await self._emit('download_complete', {
                    'job_id': job_id,
                    'is_playlist': True,
                    'files': file_list,
                    'total': len(file_list)
                }, sid)
            
            logger.info(f"Download completo: {job_id}")
            
        except Exception as e:
            logger.error(f"Erro no download {job_id}: {e}")
            
            queue_manager.mark_failed(job_id)
            
            async with get_db_session() as session:
                await update_download_status(
                    session=session,
                    job_id=job_id,
                    status=DownloadStatus.FAILED,
                    error_message=str(e)
                )
            
            await self._emit('download_error', {
                'job_id': job_id,
                'error': str(e)
            }, sid)


# ============================================================
# LEGACY SUPPORT - Mantém compatibilidade com código antigo
# ============================================================

class LegacyDownloadService:
    """Wrapper para manter compatibilidade com a versão antiga."""
    
    def __init__(self, sio):
        self.sio = sio
        self.service = DownloadService(sio)
    
    async def download_video(self, url: str, sid: str):
        """Método legado - cria um download com opções padrão."""
        from src.models import DownloadRequest
        
        request = DownloadRequest(
            url=url,
            format=DownloadFormat.VIDEO,
            video_quality=VideoQuality.BEST,
            audio_quality=AudioQuality.Q_192K
        )
        
        # Adiciona à fila
        item = await queue_manager.add(request, sid=sid)
        
        # A fila processará automaticamente
        return item.job_id
