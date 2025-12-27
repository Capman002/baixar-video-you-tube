"""
Models e Schemas para o sistema de download.
Inclui modelos Pydantic para validação e SQLAlchemy para persistência.
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Literal
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ============================================================
# ENUMS
# ============================================================

class DownloadFormat(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class VideoQuality(str, Enum):
    Q_360P = "360p"
    Q_480P = "480p"
    Q_720P = "720p"
    Q_1080P = "1080p"
    Q_1440P = "1440p"
    Q_4K = "2160p"
    BEST = "best"


class AudioQuality(str, Enum):
    Q_128K = "128"
    Q_192K = "192"
    Q_320K = "320"


class DownloadStatus(str, Enum):
    QUEUED = "queued"
    FETCHING_INFO = "fetching_info"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Platform(str, Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    TWITTER = "twitter"
    FACEBOOK = "facebook"
    VIMEO = "vimeo"
    TWITCH = "twitch"
    REDDIT = "reddit"
    UNKNOWN = "unknown"


# ============================================================
# DATABASE MODELS (SQLAlchemy)
# ============================================================

class DownloadRecord(Base):
    """Registro de download no banco de dados."""
    __tablename__ = "downloads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), unique=True, nullable=False, index=True)
    url = Column(Text, nullable=False)
    title = Column(String(500), nullable=True)
    platform = Column(String(50), default="unknown")
    format = Column(String(20), default="video")
    quality = Column(String(20), default="best")
    status = Column(String(20), default="queued")
    progress = Column(Integer, default=0)
    file_path = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    thumbnail = Column(Text, nullable=True)
    duration = Column(Integer, nullable=True)  # segundos
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# ============================================================
# PYDANTIC SCHEMAS - Requests
# ============================================================

class PreviewRequest(BaseModel):
    """Request para obter preview de um vídeo/playlist."""
    url: str = Field(..., description="URL do vídeo ou playlist")


class DownloadRequest(BaseModel):
    """Request para iniciar um download."""
    url: str = Field(..., description="URL do vídeo")
    format: DownloadFormat = Field(default=DownloadFormat.VIDEO)
    video_quality: VideoQuality = Field(default=VideoQuality.BEST)
    audio_quality: AudioQuality = Field(default=AudioQuality.Q_192K)
    playlist_items: Optional[List[int]] = Field(
        default=None, 
        description="Índices dos itens da playlist para baixar (None = todos)"
    )


class QueueActionRequest(BaseModel):
    """Request para ações na fila."""
    job_id: str


# ============================================================
# PYDANTIC SCHEMAS - Responses
# ============================================================

class FormatInfo(BaseModel):
    """Informações de um formato disponível."""
    format_id: str
    ext: str
    quality: Optional[str] = None
    filesize: Optional[int] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None


class VideoInfo(BaseModel):
    """Informações de um vídeo individual."""
    id: str
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[int] = None  # segundos
    uploader: Optional[str] = None
    view_count: Optional[int] = None
    upload_date: Optional[str] = None
    description: Optional[str] = None
    available_qualities: List[str] = []


class PreviewResponse(BaseModel):
    """Response com preview do conteúdo."""
    url: str
    platform: Platform
    is_playlist: bool = False
    playlist_title: Optional[str] = None
    playlist_count: Optional[int] = None
    videos: List[VideoInfo] = []
    available_qualities: List[str] = []
    supports_audio: bool = True


class DownloadProgress(BaseModel):
    """Progresso de um download."""
    job_id: str
    status: DownloadStatus
    progress: float = 0
    speed: Optional[str] = None
    eta: Optional[str] = None
    current_item: Optional[int] = None
    total_items: Optional[int] = None


class DownloadComplete(BaseModel):
    """Notificação de download completo."""
    job_id: str
    url: str
    filename: str
    file_size: Optional[int] = None


class DownloadError(BaseModel):
    """Notificação de erro no download."""
    job_id: str
    error: str


class HistoryItem(BaseModel):
    """Item do histórico de downloads."""
    id: int
    job_id: str
    url: str
    title: Optional[str]
    platform: str
    format: str
    quality: str
    status: str
    progress: int
    file_path: Optional[str]
    file_size: Optional[int]
    thumbnail: Optional[str]
    duration: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class HistoryResponse(BaseModel):
    """Response com histórico de downloads."""
    items: List[HistoryItem]
    total: int
    page: int
    per_page: int


class QueueItem(BaseModel):
    """Item na fila de downloads."""
    job_id: str
    url: str
    title: Optional[str]
    platform: str
    format: str
    quality: str
    status: DownloadStatus
    position: int
    progress: float = 0


class QueueResponse(BaseModel):
    """Response com estado da fila."""
    items: List[QueueItem]
    total: int
    processing: Optional[str] = None  # job_id do item sendo processado


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def detect_platform(url: str) -> Platform:
    """Detecta a plataforma baseado na URL."""
    url_lower = url.lower()
    
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return Platform.YOUTUBE
    elif "instagram.com" in url_lower:
        return Platform.INSTAGRAM
    elif "tiktok.com" in url_lower:
        return Platform.TIKTOK
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return Platform.TWITTER
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return Platform.FACEBOOK
    elif "vimeo.com" in url_lower:
        return Platform.VIMEO
    elif "twitch.tv" in url_lower:
        return Platform.TWITCH
    elif "reddit.com" in url_lower:
        return Platform.REDDIT
    else:
        return Platform.UNKNOWN


def get_format_string(
    format_type: DownloadFormat,
    video_quality: VideoQuality,
    audio_quality: AudioQuality
) -> str:
    """Gera a string de formato para o yt-dlp."""
    if format_type == DownloadFormat.AUDIO:
        return "bestaudio[ext=m4a]/bestaudio/best"
    
    # Vídeo
    if video_quality == VideoQuality.BEST:
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    
    height = video_quality.value.replace("p", "")
    return f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best[height<={height}]"
