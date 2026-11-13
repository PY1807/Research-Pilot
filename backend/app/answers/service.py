"""Cited answers (baseline RAG): retrieve passages, ask the LLM to answer only from them,
check every citation, and save the run. No HTTP here, so the API and the evaluation
harness share it (and the M6 agent will reuse its pieces).

Saved as a `research_run` (config.kind = "answer") with its retrieved passages as
`evidence_items`, the claims and citations in a `report`, and each step in `run_events`.
"""

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.answers.prompts import (
    ANSWER_SYSTEM,
    AnswerDraft,
    build_answer_prompt,
    passage_label,
)
from app.db.models import EvidenceItem, Report, ResearchRun, RunEvent, RunStatus
from app.llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse
from app.llm.structured import cost_usd, generate_structured
from app.retrieval.service import SearchMode, SearchResult, search

_LABEL = re.compile(r"^\[?\s*S\s*(\d+)\s*\]?$", re.IGNORECASE)


@dataclass(frozen=True)
class Passage:
    label: str  # "S1", "S2", ... as shown to the LLM
    result: SearchResult
    cited: bool


@dataclass(frozen=True)
class Claim:
    text: str
    citations: list[str]  # labels of passages that exist; invented ones are dropped

    @property
    def cited(self) -> bool:
        return bool(self.citations)


@dataclass(frozen=True)
class LLMUsage:
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float

    @classmethod
    def from_responses(cls, responses: list[LLMResponse]) -> "LLMUsage":
        last = responses[-1]
        return cls(
            provider=last.provider,
            model=last.model,
            calls=len(responses),
            input_tokens=sum(r.usage.input_tokens for r in responses),
            output_tokens=sum(r.usage.output_tokens for r in responses),
            cost_usd=round(sum(cost_usd(r) for r in responses), 6),
            latency_ms=round(sum(r.latency_ms for r in responses), 1),
        )


@dataclass
class AnswerResult:
    question: str
    answerable: bool
    claims: list[Claim]
    passages: list[Passage]
    missing_information: str | None
    # Citations the LLM made to passages it was never shown (a hallucination signal).
    dropped_citations: list[str] = field(default_factory=list)
    usage: LLMUsage | None = None  # None when no LLM call was needed
    retrieval_mode: SearchMode = "hybrid"
    retrieval_ms: float = 0.0
    run_id: uuid.UUID | None = None


def _normalise(label: str) -> str | None:
    match = _LABEL.match(label.strip())
    return f"S{int(match.group(1))}" if match else None


def resolve_citations(
    draft: AnswerDraft, passage_count: int
) -> tuple[list[Claim], set[str], list[str]]:
    """Keep citations that point at real passages; collect the rest as dropped."""
    valid = {passage_label(i) for i in range(passage_count)}
    claims, used, dropped = [], set(), []
    for draft_claim in draft.claims:
        kept: list[str] = []
        for raw in draft_claim.citations:
            label = _normalise(raw)
            if label in valid:
                if label not in kept:
                    kept.append(label)
            else:
                dropped.append(raw)
        used.update(kept)
        claims.append(Claim(draft_claim.text.strip(), kept))
    return claims, used, dropped


async def answer_question(
    session: AsyncSession,
    llm: LLMProvider,
    project_id: uuid.UUID,
    question: str,
    *,
    user_id: uuid.UUID | None = None,
    k: int = 8,
    mode: SearchMode = "hybrid",
    persist: bool = True,
) -> AnswerResult:
    """Answer from the project's sources. Saves a run when `persist` (needs `user_id`).
    LLM failures are recorded on the run and re-raised for the caller to report."""
    started_at = datetime.now(UTC)
    t0 = time.perf_counter()
    results = await search(session, project_id, question, k, mode)
    retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)
    await session.rollback()  # end the read transaction so SET LOCAL search settings end

    answer = AnswerResult(
        question=question,
        answerable=False,
        claims=[],
        passages=[],
        missing_information=None,
        retrieval_mode=mode,
        retrieval_ms=retrieval_ms,
    )

    if not results:
        # Nothing to ground an answer in, so don't spend an LLM call guessing.
        answer.missing_information = "No passages were found. Are any sources ready yet?"
    else:
        request = LLMRequest(system=ANSWER_SYSTEM, prompt=build_answer_prompt(question, results))
        try:
            structured = await generate_structured(llm, request, AnswerDraft)
        except LLMError as exc:
            if persist:
                await _save_failed_run(session, project_id, user_id, question, mode, k, exc)
            raise
        draft = structured.value
        claims, used, dropped = resolve_citations(draft, len(results))
        answer.answerable = draft.answerable and bool(claims)
        answer.claims = claims if draft.answerable else []
        answer.missing_information = draft.missing_information
        answer.dropped_citations = dropped
        answer.usage = LLMUsage.from_responses(structured.responses)
        answer.passages = [
            Passage(passage_label(i), r, passage_label(i) in used) for i, r in enumerate(results)
        ]

    if persist:
        answer.run_id = await _save_run(session, project_id, user_id, answer, k, started_at)
    return answer


def _run_config(mode: SearchMode, k: int, usage: LLMUsage | None = None) -> dict:
    config: dict = {"kind": "answer", "retrieval_mode": mode, "k": k}
    if usage:
        config |= {"provider": usage.provider, "model": usage.model}
    return config


async def _save_run(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID | None,
    answer: AnswerResult,
    k: int,
    started_at: datetime,
) -> uuid.UUID:
    if user_id is None:
        raise ValueError("user_id is required to save a run")
    run = ResearchRun(
        user_id=user_id,
        project_id=project_id,
        status=RunStatus.SUCCEEDED,
        plan={"question": answer.question},
        config=_run_config(answer.retrieval_mode, k, answer.usage),
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()  # assigns run.id

    for i, passage in enumerate(answer.passages, start=1):
        session.add(
            EvidenceItem(
                run_id=run.id,
                source_id=passage.result.source_id,
                chunk_id=passage.result.chunk_id,
                query=answer.question,
                rank=i,
                score=passage.result.score,
                excerpt=passage.result.text,
            )
        )
    by_label = {p.label: p for p in answer.passages}
    session.add(
        Report(
            run_id=run.id,
            sections=[{"type": "answer", "answerable": answer.answerable}],
            claims=[{"text": c.text, "citations": c.citations} for c in answer.claims],
            citations=[
                {
                    "label": p.label,
                    "chunk_id": str(p.result.chunk_id),
                    "source_id": str(p.result.source_id),
                    "page_number": p.result.page_number,
                }
                for p in by_label.values()
                if p.cited
            ],
            limitations=[answer.missing_information] if answer.missing_information else [],
        )
    )
    # Events hold counts and timings only, never document text (they're for tracing/costs).
    session.add(
        RunEvent(
            run_id=run.id,
            event_type="retrieval",
            tool="search",
            summary={
                "mode": answer.retrieval_mode,
                "k": k,
                "results": len(answer.passages),
                "latency_ms": answer.retrieval_ms,
            },
        )
    )
    if answer.usage:
        session.add(
            RunEvent(
                run_id=run.id,
                event_type="llm_call",
                tool="answer",
                summary={
                    "provider": answer.usage.provider,
                    "model": answer.usage.model,
                    "calls": answer.usage.calls,
                    "input_tokens": answer.usage.input_tokens,
                    "output_tokens": answer.usage.output_tokens,
                    "cost_usd": answer.usage.cost_usd,
                    "latency_ms": answer.usage.latency_ms,
                },
            )
        )
    session.add(
        RunEvent(
            run_id=run.id,
            event_type="completed",
            summary={
                "answerable": answer.answerable,
                "claims": len(answer.claims),
                "uncited_claims": sum(not c.cited for c in answer.claims),
                "dropped_citations": len(answer.dropped_citations),
            },
        )
    )
    await session.commit()
    return run.id


async def _save_failed_run(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID | None,
    question: str,
    mode: SearchMode,
    k: int,
    error: LLMError,
) -> None:
    if user_id is None:
        return
    now = datetime.now(UTC)
    run = ResearchRun(
        user_id=user_id,
        project_id=project_id,
        status=RunStatus.FAILED,
        plan={"question": question},
        config=_run_config(mode, k),
        error=str(error)[:500],
        started_at=now,
        finished_at=now,
    )
    session.add(run)
    await session.flush()
    session.add(
        RunEvent(run_id=run.id, event_type="failed", summary={"error": type(error).__name__})
    )
    await session.commit()
