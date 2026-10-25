import asyncio
import os
import tempfile
from pathlib import Path

# Point the app at the test database and a throwaway storage folder before anything
# imports app settings.
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://researchpilot:researchpilot@localhost:5433/researchpilot_test",
)
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="researchpilot-test-storage-")
# A fast keyword-hash embedder instead of the real model: no download, deterministic.
os.environ["EMBEDDING_PROVIDER"] = "hash"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from alembic import command  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.scripts.seed_dev_user import main as seed_dev_user  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


async def _reset_schema() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    """Start every test session from an empty schema, built only by our migrations.

    This also proves the migrations themselves work, not just the models.
    """
    asyncio.run(_reset_schema())
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    asyncio.run(seed_dev_user())


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def session():
    async with SessionLocal() as s:
        yield s


@pytest.fixture
async def dev_user(session) -> User:
    return await session.scalar(select(User).where(User.email == get_settings().dev_user_email))


@pytest.fixture(autouse=True)
def queued_tasks(monkeypatch) -> list[str]:
    """Capture ingestion jobs instead of sending them to Redis. Tests run the
    ingestion function directly when they need its effects."""
    queued: list[str] = []
    monkeypatch.setattr(
        "app.sources.router.ingest_source_task.delay", lambda source_id: queued.append(source_id)
    )
    return queued
