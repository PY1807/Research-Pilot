import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import IngestionStatus, SourceType


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    source_type: SourceType
    status: IngestionStatus
    error: str | None
    checksum: str | None
    metadata: dict[str, Any] = Field(validation_alias="meta")
    created_at: datetime


class SourceStatusOut(BaseModel):
    id: uuid.UUID
    status: IngestionStatus
    error: str | None
    page_count: int | None
    chunk_count: int | None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page_number: int | None
    text: str
