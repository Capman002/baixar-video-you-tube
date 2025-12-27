"""
Gerenciador de Fila de Downloads.
Processa downloads sequencialmente para evitar sobrecarga.
"""
import asyncio
import uuid
import logging
from typing import Dict, Optional, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.models import (
    DownloadRequest, 
    DownloadStatus, 
    QueueItem, 
    QueueResponse,
    detect_platform
)

logger = logging.getLogger("uvicorn")


@dataclass
class QueuedDownload:
    """Representa um download na fila."""
    job_id: str
    url: str
    format: str
    video_quality: str
    audio_quality: str
    playlist_items: Optional[List[int]]
    title: Optional[str] = None
    platform: str = "unknown"
    status: DownloadStatus = DownloadStatus.QUEUED
    progress: float = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    sid: Optional[str] = None  # Socket ID para notificações


class QueueManager:
    """
    Gerenciador singleton da fila de downloads.
    Processa um download por vez para evitar sobrecarga.
    """
    
    _instance: Optional['QueueManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._queue: asyncio.Queue[QueuedDownload] = asyncio.Queue()
        self._items: Dict[str, QueuedDownload] = {}  # job_id -> item
        self._current: Optional[str] = None  # job_id sendo processado
        self._processing = False
        self._download_callback: Optional[Callable] = None
        self._initialized = True
        
        logger.info("QueueManager inicializado")
    
    def set_download_callback(self, callback: Callable):
        """Define o callback que será chamado para processar downloads."""
        self._download_callback = callback
    
    async def add(
        self, 
        request: DownloadRequest, 
        sid: Optional[str] = None,
        title: Optional[str] = None,
        thumbnail: Optional[str] = None
    ) -> QueuedDownload:
        """
        Adiciona um novo download à fila.
        
        Returns:
            QueuedDownload com o job_id gerado
        """
        job_id = str(uuid.uuid4())
        platform = detect_platform(request.url)
        
        item = QueuedDownload(
            job_id=job_id,
            url=request.url,
            format=request.format.value,
            video_quality=request.video_quality.value,
            audio_quality=request.audio_quality.value,
            playlist_items=request.playlist_items,
            title=title,
            platform=platform.value,
            sid=sid
        )
        
        self._items[job_id] = item
        await self._queue.put(item)
        
        logger.info(f"Download adicionado à fila: {job_id} ({request.url})")
        
        # Inicia processamento se não estiver rodando
        if not self._processing:
            asyncio.create_task(self._process_queue())
        
        return item
    
    async def _process_queue(self):
        """Loop principal de processamento da fila."""
        if self._processing:
            return
            
        self._processing = True
        logger.info("Iniciando processamento da fila")
        
        try:
            while True:
                try:
                    # Timeout de 1 segundo para verificar se deve parar
                    item = await asyncio.wait_for(
                        self._queue.get(), 
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # Fila vazia, verifica se deve continuar
                    if self._queue.empty():
                        break
                    continue
                
                self._current = item.job_id
                item.status = DownloadStatus.DOWNLOADING
                
                logger.info(f"Processando download: {item.job_id}")
                
                try:
                    if self._download_callback:
                        await self._download_callback(item)
                    else:
                        logger.error("Callback de download não configurado!")
                except Exception as e:
                    logger.error(f"Erro no download {item.job_id}: {e}")
                    item.status = DownloadStatus.FAILED
                finally:
                    self._current = None
                    self._queue.task_done()
                    
        finally:
            self._processing = False
            logger.info("Processamento da fila finalizado")
    
    def get_position(self, job_id: str) -> int:
        """Retorna a posição do item na fila (0 = sendo processado)."""
        if job_id == self._current:
            return 0
        
        position = 1
        for item in list(self._items.values()):
            if item.status == DownloadStatus.QUEUED:
                if item.job_id == job_id:
                    return position
                position += 1
        
        return -1  # Não está na fila
    
    def get_item(self, job_id: str) -> Optional[QueuedDownload]:
        """Retorna um item pelo job_id."""
        return self._items.get(job_id)
    
    def update_progress(self, job_id: str, progress: float, status: DownloadStatus = None):
        """Atualiza o progresso de um download."""
        if job_id in self._items:
            self._items[job_id].progress = progress
            if status:
                self._items[job_id].status = status
    
    def update_title(self, job_id: str, title: str):
        """Atualiza o título de um download."""
        if job_id in self._items:
            self._items[job_id].title = title
    
    def mark_completed(self, job_id: str):
        """Marca um download como completo."""
        if job_id in self._items:
            self._items[job_id].status = DownloadStatus.COMPLETED
            self._items[job_id].progress = 100
    
    def mark_failed(self, job_id: str):
        """Marca um download como falho."""
        if job_id in self._items:
            self._items[job_id].status = DownloadStatus.FAILED
    
    async def cancel(self, job_id: str) -> bool:
        """
        Cancela um download da fila.
        Note: Não cancela downloads em andamento.
        """
        if job_id not in self._items:
            return False
        
        item = self._items[job_id]
        
        if item.status == DownloadStatus.QUEUED:
            item.status = DownloadStatus.FAILED
            # Remove da fila interna (não do asyncio.Queue diretamente)
            del self._items[job_id]
            return True
        
        return False
    
    def get_queue_status(self) -> QueueResponse:
        """Retorna o estado atual da fila."""
        items = []
        position = 1
        
        # Primeiro o item atual
        if self._current and self._current in self._items:
            current_item = self._items[self._current]
            items.append(QueueItem(
                job_id=current_item.job_id,
                url=current_item.url,
                title=current_item.title,
                platform=current_item.platform,
                format=current_item.format,
                quality=current_item.video_quality,
                status=current_item.status,
                position=0,
                progress=current_item.progress
            ))
        
        # Depois os itens na fila
        for job_id, item in self._items.items():
            if item.status == DownloadStatus.QUEUED:
                items.append(QueueItem(
                    job_id=item.job_id,
                    url=item.url,
                    title=item.title,
                    platform=item.platform,
                    format=item.format,
                    quality=item.video_quality,
                    status=item.status,
                    position=position,
                    progress=0
                ))
                position += 1
        
        return QueueResponse(
            items=items,
            total=len(items),
            processing=self._current
        )
    
    def clear_completed(self):
        """Remove itens completados/falhos da memória."""
        to_remove = [
            job_id for job_id, item in self._items.items()
            if item.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]
        ]
        for job_id in to_remove:
            del self._items[job_id]


# Singleton global
queue_manager = QueueManager()
