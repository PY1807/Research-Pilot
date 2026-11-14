import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.answers.service import AnswerResult, answer_question
from app.api.deps import CurrentUser
from app.config import get_settings
from app.db.session import SessionDep
from app.llm.base import LLMError, LLMNotConfigured, LLMProvider, LLMRetryableError
from app.llm.factory import get_answer_llm
from app.projects.router import get_owned_project
from app.retrieval.service import SearchMode

router = APIRouter(tags=["answers"])


def answer_llm() -> LLMProvider:
    """Dependency so tests can swap in a FakeProvider. A missing key is a clear 503."""
    try:
        return get_answer_llm()
    except LLMNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


AnswerLLM = Annotated[LLMProvider, Depends(answer_llm)]


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    k: int | None = Field(default=None, ge=1, le=20, description="Passages shown to the LLM")
    mode: SearchMode | None = Field(default=None, description="Default: answer_retrieval_mode")


class ClaimOut(BaseModel):
    text: str
    citations: list[str]  # passage labels, e.g. ["S1", "S3"]


class PassageOut(BaseModel):
    label: str
    cited: bool
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    page_number: int | None
    text: str
    score: float


class UsageOut(BaseModel):
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float


class AnswerOut(BaseModel):
    run_id: uuid.UUID | None
    question: str
    answerable: bool
    claims: list[ClaimOut]
    passages: list[PassageOut]
    missing_information: str | None
    dropped_citations: list[str]
    retrieval_mode: SearchMode
    retrieval_ms: float
    usage: UsageOut | None


def to_out(answer: AnswerResult) -> AnswerOut:
    return AnswerOut(
        run_id=answer.run_id,
        question=answer.question,
        answerable=answer.answerable,
        claims=[ClaimOut(text=c.text, citations=c.citations) for c in answer.claims],
        passages=[
            PassageOut(
                label=p.label,
                cited=p.cited,
                chunk_id=p.result.chunk_id,
                source_id=p.result.source_id,
                source_title=p.result.source_title,
                page_number=p.result.page_number,
                text=p.result.text,
                score=p.result.score,
            )
            for p in answer.passages
        ],
        missing_information=answer.missing_information,
        dropped_citations=answer.dropped_citations,
        retrieval_mode=answer.retrieval_mode,
        retrieval_ms=answer.retrieval_ms,
        usage=UsageOut(**vars(answer.usage)) if answer.usage else None,
    )


@router.post("/projects/{project_id}/answers/", response_model=AnswerOut)
async def ask(
    project_id: uuid.UUID,
    body: AnswerRequest,
    session: SessionDep,
    user: CurrentUser,
    llm: AnswerLLM,
):
    project = await get_owned_project(session, project_id, user)
    try:
        answer = await answer_question(
            session,
            llm,
            project.id,
            body.question,
            user_id=user.id,
            k=body.k or get_settings().answer_top_k,
            mode=body.mode or get_settings().answer_retrieval_mode,
        )
    except LLMRetryableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The language model is busy or rate-limited. Try again in a minute.",
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"The language model failed: {exc}"
        ) from exc
    return to_out(answer)
