"""
Configurações centralizadas do projeto.
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional
import os


class Settings(BaseSettings):
    # Projeto
    PROJECT_NAME: str = "Baixar Vídeo"
    VERSION: str = "2.0.0"
    DEBUG: bool = False
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DOWNLOAD_DIR: Path = BASE_DIR / "downloads"
    DATABASE_FILE: Path = BASE_DIR / "data" / "downloads.db"
    COOKIES_FILE: Path = BASE_DIR / "cookies.txt"
    
    # FFmpeg
    FFMPEG_BINARY: str = "ffmpeg"
    
    # Download Settings
    MAX_CONCURRENT_DOWNLOADS: int = 1  # Processa um por vez
    MAX_PLAYLIST_ITEMS: int = 50  # Máximo de itens de playlist
    CLEANUP_HOURS: int = 24  # Limpa arquivos após X horas
    
    # POT Provider (anti-bot)
    POT_PROVIDER_URL: Optional[str] = None
    
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Cria diretórios necessários
settings.DOWNLOAD_DIR.mkdir(exist_ok=True)
settings.DATABASE_FILE.parent.mkdir(exist_ok=True)

# Verifica POT Provider via env var
if os.environ.get('POT_PROVIDER_URL'):
    settings.POT_PROVIDER_URL = os.environ.get('POT_PROVIDER_URL')
