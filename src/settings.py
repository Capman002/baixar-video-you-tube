from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "Baixar Vídeo"
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DOWNLOAD_DIR: Path = BASE_DIR / "downloads"
    COOKIES_FILE: Path = BASE_DIR / "cookies.txt"
    FFMPEG_BINARY: str = "ffmpeg"
    
    class Config:
        case_sensitive = True

settings = Settings()
settings.DOWNLOAD_DIR.mkdir(exist_ok=True)
