from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# Tests run each case in its own event loop; pooled asyncpg connections are tied to the
# loop that opened them, so tests use NullPool (a fresh connection per checkout).
engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool if settings.env == "test" else None,
    pool_pre_ping=settings.env != "test",
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed afterwards."""
    async with SessionLocal() as session:
        yield session


# Use as a parameter type in route functions: `async def route(session: SessionDep)`.
SessionDep = Annotated[AsyncSession, Depends(get_session)]
