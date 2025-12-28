"""
API Principal - Baixar Vídeo v2.0
FastAPI + SocketIO com suporte a múltiplos formatos, playlists e fila.
"""
from fastapi import FastAPI, BackgroundTasks, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import socketio
import asyncio
import os
import logging

from src.settings import settings
from src.models import (
    DownloadRequest,
    PreviewRequest,
    DownloadFormat,
    VideoQuality,
    AudioQuality,
    DownloadStatus,
    HistoryResponse,
    HistoryItem,
    QueueResponse,
    detect_platform
)
from src.database import (
    init_db,
    get_db_session,
    get_history,
    delete_download_record,
    cleanup_old_records,
    get_download_by_job_id
)
from src.preview import preview_service
from src.queue_manager import queue_manager
from src.downloader import DownloadService

logger = logging.getLogger("uvicorn")


# ============================================================
# LIFESPAN - Startup/Shutdown
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    # Startup
    logger.info(f"Iniciando {settings.PROJECT_NAME} v{settings.VERSION}")
    
    # Inicializa banco de dados
    await init_db()
    logger.info("Banco de dados inicializado")
    
    # Configura callback do queue manager
    download_service = DownloadService(sio)
    queue_manager.set_download_callback(download_service.process_download)
    logger.info("Sistema de fila configurado")
    
    # Task de cleanup periódico
    cleanup_task = asyncio.create_task(periodic_cleanup())
    
    yield
    
    # Shutdown
    cleanup_task.cancel()
    logger.info("Aplicação encerrada")


# ============================================================
# APP SETUP
# ============================================================

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# SocketIO
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio, app)

# Templates
templates = Jinja2Templates(directory=str(settings.BASE_DIR / "src" / "templates"))

# Static files (CSS, JS)
app.mount("/static", StaticFiles(directory=str(settings.BASE_DIR / "src" / "static")), name="static")


# ============================================================
# BACKGROUND TASKS
# ============================================================

async def periodic_cleanup():
    """Limpa arquivos antigos periodicamente."""
    while True:
        try:
            await asyncio.sleep(3600)  # A cada hora
            
            async with get_db_session() as session:
                deleted = await cleanup_old_records(session, settings.CLEANUP_HOURS)
                if deleted > 0:
                    logger.info(f"Cleanup: {deleted} registros antigos removidos")
            
            # Remove arquivos órfãos
            for file in settings.DOWNLOAD_DIR.iterdir():
                if file.is_file():
                    age_hours = (asyncio.get_event_loop().time() - file.stat().st_mtime) / 3600
                    if age_hours > settings.CLEANUP_HOURS:
                        file.unlink()
                        logger.info(f"Arquivo removido: {file.name}")
                        
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no cleanup: {e}")


# ============================================================
# ROUTES - Pages
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Página principal."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/favicon.ico")
async def favicon():
    """Favicon."""
    return ""


# ============================================================
# ROUTES - API Preview
# ============================================================

@app.get("/api/preview")
async def get_preview(url: str = Query(..., description="URL do vídeo")):
    """
    Obtém informações de um vídeo ou playlist sem baixar.
    Retorna título, thumbnail, duração, qualidades disponíveis, etc.
    """
    try:
        preview = await preview_service.get_preview(url)
        return preview.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro no preview: {e}")
        raise HTTPException(status_code=500, detail="Erro ao obter informações")


# ============================================================
# ROUTES - API Download
# ============================================================

@app.post("/api/download")
async def start_download(request: DownloadRequest):
    """
    Inicia um novo download.
    O download é adicionado à fila e processado sequencialmente.
    """
    try:
        # Obtém preview para título/thumbnail
        try:
            preview = await preview_service.get_preview(request.url)
            title = preview.videos[0].title if preview.videos else None
            thumbnail = preview.videos[0].thumbnail if preview.videos else None
        except Exception:
            title = None
            thumbnail = None
        
        # Adiciona à fila
        item = await queue_manager.add(request, title=title)
        
        return {
            "success": True,
            "job_id": item.job_id,
            "position": queue_manager.get_position(item.job_id),
            "message": "Download adicionado à fila"
        }
    except Exception as e:
        logger.error(f"Erro ao iniciar download: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download/{job_id}")
async def get_download_status(job_id: str):
    """Obtém o status de um download específico."""
    item = queue_manager.get_item(job_id)
    
    if item:
        return {
            "job_id": item.job_id,
            "status": item.status.value,
            "progress": item.progress,
            "position": queue_manager.get_position(job_id),
            "title": item.title
        }
    
    # Verifica no banco
    async with get_db_session() as session:
        record = await get_download_by_job_id(session, job_id)
        if record:
            return {
                "job_id": record.job_id,
                "status": record.status,
                "progress": record.progress,
                "title": record.title,
                "file_path": record.file_path
            }
    
    raise HTTPException(status_code=404, detail="Download não encontrado")


@app.delete("/api/download/{job_id}")
async def cancel_download(job_id: str):
    """Cancela um download da fila (apenas se ainda não iniciou)."""
    cancelled = await queue_manager.cancel(job_id)
    
    if cancelled:
        return {"success": True, "message": "Download cancelado"}
    
    raise HTTPException(
        status_code=400, 
        detail="Não é possível cancelar (já iniciado ou não encontrado)"
    )


# ============================================================
# ROUTES - API Queue
# ============================================================

@app.get("/api/queue", response_model=QueueResponse)
async def get_queue():
    """Retorna o estado atual da fila de downloads."""
    return queue_manager.get_queue_status()


# ============================================================
# ROUTES - API History
# ============================================================

@app.get("/api/history")
async def get_download_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str = Query(None)
):
    """Retorna o histórico de downloads paginado."""
    async with get_db_session() as session:
        items, total = await get_history(session, page, per_page, status)
        
        return {
            "items": [
                {
                    "id": item.id,
                    "job_id": item.job_id,
                    "url": item.url,
                    "title": item.title,
                    "platform": item.platform,
                    "format": item.format,
                    "quality": item.quality,
                    "status": item.status,
                    "progress": item.progress,
                    "file_path": item.file_path,
                    "file_size": item.file_size,
                    "thumbnail": item.thumbnail,
                    "duration": item.duration,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "completed_at": item.completed_at.isoformat() if item.completed_at else None
                }
                for item in items
            ],
            "total": total,
            "page": page,
            "per_page": per_page
        }


@app.delete("/api/history/{job_id}")
async def delete_history_item(job_id: str):
    """Remove um item do histórico."""
    async with get_db_session() as session:
        deleted = await delete_download_record(session, job_id)
        
        if deleted:
            return {"success": True, "message": "Registro removido"}
        
        raise HTTPException(status_code=404, detail="Registro não encontrado")


@app.delete("/api/history")
async def clear_history():
    """Limpa todo o histórico de downloads concluídos."""
    async with get_db_session() as session:
        deleted = await cleanup_old_records(session, hours=0)
        return {"success": True, "deleted": deleted}


# ============================================================
# ROUTES - API Files
# ============================================================

@app.get("/api/files/{filename}")
async def get_file(filename: str, background_tasks: BackgroundTasks):
    """Retorna um arquivo para download."""
    file_path = settings.DOWNLOAD_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    return FileResponse(
        file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


# ============================================================
# ROUTES - API Info
# ============================================================

@app.get("/api/info")
async def get_app_info():
    """Retorna informações da aplicação."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "supported_platforms": [
            {"id": "youtube", "name": "YouTube", "icon": "🎬"},
            {"id": "instagram", "name": "Instagram", "icon": "📸"},
            {"id": "tiktok", "name": "TikTok", "icon": "🎵"},
            {"id": "twitter", "name": "X (Twitter)", "icon": "🐦"},
            {"id": "facebook", "name": "Facebook", "icon": "👤"},
            {"id": "vimeo", "name": "Vimeo", "icon": "🎥"},
            {"id": "twitch", "name": "Twitch", "icon": "🎮"},
            {"id": "reddit", "name": "Reddit", "icon": "🤖"}
        ],
        "formats": ["video", "audio"],
        "video_qualities": ["360p", "480p", "720p", "1080p", "1440p", "2160p", "best"],
        "audio_qualities": ["128", "192", "320"]
    }


# ============================================================
# SOCKETIO EVENTS
# ============================================================

@sio.on('connect')
async def socket_connect(sid, environ):
    """Cliente conectou."""
    logger.info(f"Cliente conectado: {sid}")
    await sio.emit('session_id', {'sid': sid}, room=sid)
    
    # Envia estado atual da fila
    queue_status = queue_manager.get_queue_status()
    await sio.emit('queue_update', queue_status.model_dump(), room=sid)


@sio.on('disconnect')
async def socket_disconnect(sid):
    """Cliente desconectou."""
    logger.info(f"Cliente desconectado: {sid}")


@sio.on('start_download')
async def socket_start_download(sid, data):
    """
    Evento legado - inicia download com opções padrão.
    Mantido para compatibilidade com interface antiga.
    """
    url = data.get('url')
    if not url:
        await sio.emit('download_error', {'error': 'URL não fornecida'}, room=sid)
        return
    
    format_type = DownloadFormat(data.get('format', 'video'))
    video_quality = VideoQuality(data.get('video_quality', 'best'))
    audio_quality = AudioQuality(data.get('audio_quality', '192'))
    
    request = DownloadRequest(
        url=url,
        format=format_type,
        video_quality=video_quality,
        audio_quality=audio_quality,
        playlist_items=data.get('playlist_items')
    )
    
    # Obtém preview
    try:
        preview = await preview_service.get_preview(url)
        title = preview.videos[0].title if preview.videos else None
    except Exception:
        title = None
    
    # Adiciona à fila
    item = await queue_manager.add(request, sid=sid, title=title)
    
    await sio.emit('download_queued', {
        'job_id': item.job_id,
        'position': queue_manager.get_position(item.job_id)
    }, room=sid)


@sio.on('cancel_download')
async def socket_cancel_download(sid, data):
    """Cancela um download."""
    job_id = data.get('job_id')
    if job_id:
        cancelled = await queue_manager.cancel(job_id)
        await sio.emit('download_cancelled', {
            'job_id': job_id,
            'success': cancelled
        }, room=sid)


@sio.on('get_queue')
async def socket_get_queue(sid):
    """Retorna estado da fila."""
    queue_status = queue_manager.get_queue_status()
    await sio.emit('queue_update', queue_status.model_dump(), room=sid)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "src.main:socket_app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
