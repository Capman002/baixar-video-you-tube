"""
Serviço de Preview - Extrai informações de vídeos/playlists sem baixar.
"""
import yt_dlp
import asyncio
import logging
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from src.models import (
    PreviewResponse, 
    VideoInfo, 
    Platform, 
    detect_platform
)
from src.settings import settings

logger = logging.getLogger("uvicorn")

# Thread pool para operações bloqueantes
executor = ThreadPoolExecutor(max_workers=3)


class PreviewService:
    """Serviço para extrair informações de vídeos sem baixar."""
    
    def __init__(self):
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,  # False para obter info completa
            'nocheckcertificate': True,
        }
        
        # Adiciona cookies se disponível
        if settings.COOKIES_FILE.exists() and settings.COOKIES_FILE.stat().st_size > 200:
            self.base_opts['cookiefile'] = str(settings.COOKIES_FILE)
    
    def _extract_available_qualities(self, formats: List[Dict]) -> List[str]:
        """Extrai as qualidades disponíveis dos formatos."""
        qualities = set()
        
        for fmt in formats:
            height = fmt.get('height')
            if height:
                if height >= 2160:
                    qualities.add("2160p")
                elif height >= 1440:
                    qualities.add("1440p")
                elif height >= 1080:
                    qualities.add("1080p")
                elif height >= 720:
                    qualities.add("720p")
                elif height >= 480:
                    qualities.add("480p")
                elif height >= 360:
                    qualities.add("360p")
        
        # Ordenar do maior para menor
        order = ["2160p", "1440p", "1080p", "720p", "480p", "360p"]
        return [q for q in order if q in qualities]
    
    def _parse_video_info(self, info: Dict[str, Any]) -> VideoInfo:
        """Converte info do yt-dlp para VideoInfo."""
        formats = info.get('formats', [])
        
        return VideoInfo(
            id=info.get('id', ''),
            title=info.get('title', 'Sem título'),
            thumbnail=info.get('thumbnail'),
            duration=info.get('duration'),
            uploader=info.get('uploader') or info.get('channel'),
            view_count=info.get('view_count'),
            upload_date=info.get('upload_date'),
            description=info.get('description', '')[:500] if info.get('description') else None,
            available_qualities=self._extract_available_qualities(formats)
        )
    
    def _sync_extract(self, url: str, flat: bool = False) -> Dict[str, Any]:
        """Extrai informações de forma síncrona (para rodar em thread)."""
        opts = {**self.base_opts}
        
        if flat:
            opts['extract_flat'] = 'in_playlist'
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    
    async def get_preview(self, url: str) -> PreviewResponse:
        """
        Obtém preview de um vídeo ou playlist.
        
        Args:
            url: URL do vídeo ou playlist
            
        Returns:
            PreviewResponse com informações do conteúdo
        """
        loop = asyncio.get_running_loop()
        platform = detect_platform(url)
        
        try:
            # Primeiro, tenta extrair com flat=True para detectar playlists
            info = await loop.run_in_executor(
                executor, 
                lambda: self._sync_extract(url, flat=True)
            )
            
            is_playlist = info.get('_type') == 'playlist'
            
            if is_playlist:
                # É uma playlist
                entries = info.get('entries', [])
                videos = []
                
                # Limita a 50 vídeos para não sobrecarregar
                for entry in entries[:50]:
                    if entry:
                        videos.append(VideoInfo(
                            id=entry.get('id', ''),
                            title=entry.get('title', 'Sem título'),
                            thumbnail=entry.get('thumbnails', [{}])[0].get('url') if entry.get('thumbnails') else None,
                            duration=entry.get('duration'),
                            uploader=entry.get('uploader'),
                            available_qualities=[]  # Não disponível no flat mode
                        ))
                
                return PreviewResponse(
                    url=url,
                    platform=platform,
                    is_playlist=True,
                    playlist_title=info.get('title'),
                    playlist_count=len(entries),
                    videos=videos,
                    available_qualities=["2160p", "1440p", "1080p", "720p", "480p", "360p"],
                    supports_audio=True
                )
            else:
                # Vídeo único - extrai info completa
                full_info = await loop.run_in_executor(
                    executor,
                    lambda: self._sync_extract(url, flat=False)
                )
                
                video_info = self._parse_video_info(full_info)
                
                return PreviewResponse(
                    url=url,
                    platform=platform,
                    is_playlist=False,
                    videos=[video_info],
                    available_qualities=video_info.available_qualities or ["best"],
                    supports_audio=True
                )
                
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Erro ao extrair preview: {e}")
            raise ValueError(f"Não foi possível obter informações: {str(e)}")
        except Exception as e:
            logger.error(f"Erro inesperado no preview: {e}")
            raise ValueError(f"Erro ao processar URL: {str(e)}")
    
    async def validate_url(self, url: str) -> bool:
        """Verifica se a URL é válida e suportada."""
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                extractors = ydl.list_extractors()
                for ie in extractors:
                    if ie.suitable(url):
                        return True
            return False
        except Exception:
            return False


# Singleton
preview_service = PreviewService()
