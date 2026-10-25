from fastapi import FastAPI

from app.api import health

app = FastAPI(
    title="ResearchPilot API",
    version="0.1.0",
    description="Evidence-first agentic research workspace.",
)

app.include_router(health.router, prefix="/api")
