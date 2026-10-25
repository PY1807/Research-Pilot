import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.db.session import SessionDep
from app.projects.router import get_owned_project
from app.retrieval.service import SearchMode, search

router = APIRouter(tags=["search"])


class SearchResultOut(BaseModel):
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    page_number: int | None
    text: str
    score: float
    semantic_rank: int | None
    keyword_rank: int | None


@router.get("/projects/{project_id}/search/", response_model=list[SearchResultOut])
async def search_project(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    q: Annotated[str, Query(min_length=1, max_length=1000, description="The question")],
    k: Annotated[int, Query(ge=1, le=20, description="How many passages to return")] = 5,
    mode: Annotated[
        SearchMode, Query(description="hybrid (meaning + keywords), semantic, or keyword")
    ] = "hybrid",
):
    project = await get_owned_project(session, project_id, user)
    return await search(session, project.id, q, k, mode)
