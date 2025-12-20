from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import socketio
import asyncio
from src.settings import settings
from src.downloader import DownloadService
import os

# --- App Setup ---
app = FastAPI(title=settings.PROJECT_NAME)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

# --- SocketIO Setup ---
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio, app)

# --- Templates ---
templates = Jinja2Templates(directory=str(settings.BASE_DIR / "src" / "templates"))


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/favicon.ico")
async def favicon():
    return "" # No content

@app.get("/api/files/{filename}")
async def get_file(filename: str, background_tasks: BackgroundTasks):
    file_path = settings.DOWNLOAD_DIR / filename
    if not file_path.exists():
        return {"error": "File not found"}
    
    # Clean up after sending
    # background_tasks.add_task(lambda: file_path.unlink(missing_ok=True)) 
    # Warning: Removing immediately might break download managers. 
    # Professional way: Cron job cleanup. Here we leave it for now or implement delayed cleanup.
    
    return FileResponse(file_path, filename=filename)

# --- SocketIO Events ---

@sio.on('connect')
async def connect(sid, environ):
    await sio.emit('session_id', {'sid': sid}, room=sid)

@sio.on('start_download')
async def start_download(sid, data):
    url = data.get('url')
    if not url:
        return
    
    # Dependency Injection of Service
    service = DownloadService(sio)
    # Start async
    asyncio.create_task(service.download_video(url, sid))

# --- Entry Point (Managed by Uvicorn via UV) ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("src.main:socket_app", host="0.0.0.0", port=port, reload=True)
