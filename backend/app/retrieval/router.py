import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.db.session import SessionDep
from app.projects.router import get_owned_project
from app.retrieval.service import semantic_search

router = APIRouter(tags=["search"])


class SearchResultOut(BaseModel):
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    page_number: int | None
    text: str
    score: float


@router.get("/projects/{project_id}/search/", response_model=list[SearchResultOut])
async def search(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=1000, description="The question or search text"),
    k: int = Query(default=5, ge=1, le=20, description="How many passages to return"),
):
    project = await get_owned_project(session, project_id, user)
    return await semantic_search(session, project.id, q, k)
