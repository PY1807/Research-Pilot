import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.config import get_settings
from app.embeddings import get_embedder
from app.projects import router as projects
from app.retrieval import router as retrieval
from app.sources import router as sources


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model at startup (a few seconds) instead of on the first search,
    # so no user waits for it. Skipped in tests, which use the instant hash embedder.
    if get_settings().env != "test":
        await asyncio.to_thread(get_embedder)
    yield


app = FastAPI(
    title="ResearchPilot API",
    version="0.1.0",
    description="Evidence-first agentic research workspace.",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(retrieval.router, prefix="/api")
