"""
Configuração do banco de dados SQLite com suporte assíncrono.
"""
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional, List
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import selectinload

from src.models import Base, DownloadRecord, DownloadStatus
from src.settings import settings

# Engine assíncrono
DATABASE_URL = f"sqlite+aiosqlite:///{settings.DATABASE_FILE}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set True for SQL debugging
    future=True
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Inicializa o banco de dados, criando as tabelas se necessário."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para obter uma sessão do banco."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session():
    """Context manager para sessões do banco."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ============================================================
# CRUD OPERATIONS
# ============================================================

async def create_download_record(
    session: AsyncSession,
    job_id: str,
    url: str,
    platform: str,
    format: str,
    quality: str,
    title: Optional[str] = None,
    thumbnail: Optional[str] = None,
    duration: Optional[int] = None
) -> DownloadRecord:
    """Cria um novo registro de download."""
    record = DownloadRecord(
        job_id=job_id,
        url=url,
        platform=platform,
        format=format,
        quality=quality,
        title=title,
        thumbnail=thumbnail,
        duration=duration,
        status=DownloadStatus.QUEUED.value
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def get_download_by_job_id(
    session: AsyncSession,
    job_id: str
) -> Optional[DownloadRecord]:
    """Busca um download pelo job_id."""
    result = await session.execute(
        select(DownloadRecord).where(DownloadRecord.job_id == job_id)
    )
    return result.scalar_one_or_none()


async def update_download_status(
    session: AsyncSession,
    job_id: str,
    status: DownloadStatus,
    progress: int = None,
    error_message: str = None,
    file_path: str = None,
    file_size: int = None,
    title: str = None
):
    """Atualiza o status de um download."""
    update_data = {"status": status.value}
    
    if progress is not None:
        update_data["progress"] = progress
    if error_message is not None:
        update_data["error_message"] = error_message
    if file_path is not None:
        update_data["file_path"] = file_path
    if file_size is not None:
        update_data["file_size"] = file_size
    if title is not None:
        update_data["title"] = title
    
    if status == DownloadStatus.COMPLETED:
        update_data["completed_at"] = datetime.utcnow()
    
    await session.execute(
        update(DownloadRecord)
        .where(DownloadRecord.job_id == job_id)
        .values(**update_data)
    )
    await session.commit()


async def get_history(
    session: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    status_filter: Optional[str] = None
) -> tuple[List[DownloadRecord], int]:
    """Retorna o histórico de downloads paginado."""
    query = select(DownloadRecord).order_by(DownloadRecord.created_at.desc())
    
    if status_filter:
        query = query.where(DownloadRecord.status == status_filter)
    
    # Count total
    count_query = select(func.count(DownloadRecord.id))
    if status_filter:
        count_query = count_query.where(DownloadRecord.status == status_filter)
    
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()
    
    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    
    result = await session.execute(query)
    items = result.scalars().all()
    
    return list(items), total


async def delete_download_record(
    session: AsyncSession,
    job_id: str
) -> bool:
    """Deleta um registro de download."""
    result = await session.execute(
        delete(DownloadRecord).where(DownloadRecord.job_id == job_id)
    )
    await session.commit()
    return result.rowcount > 0


async def cleanup_old_records(
    session: AsyncSession,
    hours: int = 24
) -> int:
    """Remove registros antigos (completados há mais de X horas)."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    result = await session.execute(
        delete(DownloadRecord)
        .where(DownloadRecord.completed_at < cutoff)
        .where(DownloadRecord.status == DownloadStatus.COMPLETED.value)
    )
    await session.commit()
    return result.rowcount


async def get_pending_downloads(
    session: AsyncSession
) -> List[DownloadRecord]:
    """Retorna downloads pendentes (para recuperação após restart)."""
    result = await session.execute(
        select(DownloadRecord)
        .where(DownloadRecord.status.in_([
            DownloadStatus.QUEUED.value,
            DownloadStatus.DOWNLOADING.value,
            DownloadStatus.FETCHING_INFO.value
        ]))
        .order_by(DownloadRecord.created_at.asc())
    )
    return list(result.scalars().all())
