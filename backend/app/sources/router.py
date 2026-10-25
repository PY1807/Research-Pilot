import hashlib
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.config import get_settings
from app.db.models import DocumentChunk, IngestionStatus, SourceDocument, SourceType, User
from app.db.session import SessionDep
from app.projects.router import get_owned_project
from app.sources.schemas import ChunkOut, SourceOut, SourceStatusOut
from app.sources.storage import absolute_path, storage_root, upload_relpath
from app.sources.tasks import ingest_source_task

router = APIRouter(tags=["sources"])

PDF_MAGIC = b"%PDF-"
READ_BLOCK = 1024 * 1024


def _save_upload(upload: BinaryIO) -> tuple[Path, str]:
    """Copy the upload to a temp file block by block, checking the PDF header, enforcing
    the size limit, and hashing as we go, so a large file never sits in memory.

    Synchronous on purpose: callers run it in a thread so disk I/O doesn't block the
    event loop. (Starlette has already buffered the request body by this point; a hard
    cap on request size belongs in the reverse proxy at deployment, M10.)
    """
    limit = get_settings().max_upload_bytes
    digest = hashlib.sha256()
    size = 0
    tmp_dir = storage_root() / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".pdf", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with tmp_path.open("wb") as out:
            while block := upload.read(READ_BLOCK):
                # The PDF spec allows a few bytes of junk before the header.
                if size == 0 and PDF_MAGIC not in block[:1024]:
                    raise HTTPException(
                        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are supported."
                    )
                size += len(block)
                if size > limit:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"File is larger than the {limit // (1024 * 1024)} MB limit.",
                    )
                digest.update(block)
                out.write(block)
        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path, digest.hexdigest()


def _move_into_place(tmp_path: Path, final_path: Path) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp_path, final_path)


async def _get_owned_source(
    session: AsyncSession, source_id: uuid.UUID, user: User
) -> SourceDocument:
    source = await session.get(SourceDocument, source_id)
    if source is None or source.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")
    return source


@router.post(
    "/projects/{project_id}/sources/",
    response_model=SourceOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_source(
    project_id: uuid.UUID,
    file: UploadFile,
    session: SessionDep,
    user: CurrentUser,
    title: str | None = Form(default=None, max_length=500),
):
    """Save the PDF and queue it for ingestion. Returns immediately with status
    `pending`; poll the status endpoint until it's `ready` or `failed`."""
    project = await get_owned_project(session, project_id, user)
    tmp_path, checksum = await run_in_threadpool(_save_upload, file.file)

    duplicate = await session.scalar(
        select(SourceDocument).where(
            SourceDocument.project_id == project.id, SourceDocument.checksum == checksum
        )
    )
    if duplicate is not None:
        await run_in_threadpool(tmp_path.unlink, missing_ok=True)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This file is already in the project (source {duplicate.id}).",
        )

    source = SourceDocument(
        id=uuid.uuid4(),
        user_id=user.id,
        project_id=project.id,
        title=title or Path(file.filename or "Untitled").stem,
        source_type=SourceType.UPLOADED,
        checksum=checksum,
        status=IngestionStatus.PENDING,
        meta={"original_filename": file.filename},
    )
    source.file_path = upload_relpath(user.id, source.id)
    await run_in_threadpool(_move_into_place, tmp_path, absolute_path(source.file_path))

    session.add(source)
    await session.commit()
    await session.refresh(source)
    # Enqueue only after the commit, so the worker can already see the row.
    ingest_source_task.delay(str(source.id))
    return source


@router.get("/projects/{project_id}/sources/", response_model=list[SourceOut])
async def list_sources(project_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    project = await get_owned_project(session, project_id, user)
    rows = await session.scalars(
        select(SourceDocument)
        .where(SourceDocument.project_id == project.id)
        .order_by(SourceDocument.created_at)
    )
    return rows.all()


@router.get("/sources/{source_id}/status/", response_model=SourceStatusOut)
async def source_status(source_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    source = await _get_owned_source(session, source_id, user)
    return SourceStatusOut(
        id=source.id,
        status=source.status,
        error=source.error,
        page_count=source.meta.get("page_count"),
        chunk_count=source.meta.get("chunk_count"),
    )


@router.get("/sources/{source_id}/chunks/", response_model=list[ChunkOut])
async def list_chunks(
    source_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    source = await _get_owned_source(session, source_id, user)
    rows = await session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.source_id == source.id)
        .order_by(DocumentChunk.chunk_index)
        .limit(limit)
        .offset(offset)
    )
    return rows.all()
