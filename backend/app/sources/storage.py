"""Where uploaded files live on disk. Paths stored in the database are relative to
`settings.storage_dir`, so the storage root can move without rewriting rows."""

import uuid
from pathlib import Path

from app.config import get_settings


def storage_root() -> Path:
    return Path(get_settings().storage_dir).resolve()


def upload_relpath(user_id: uuid.UUID, source_id: uuid.UUID) -> str:
    return f"uploads/{user_id}/{source_id}.pdf"


def absolute_path(relpath: str) -> Path:
    return storage_root() / relpath
