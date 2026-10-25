from fastapi import FastAPI

from app.api import health
from app.projects import router as projects
from app.sources import router as sources

app = FastAPI(
    title="ResearchPilot API",
    version="0.1.0",
    description="Evidence-first agentic research workspace.",
)

app.include_router(health.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
