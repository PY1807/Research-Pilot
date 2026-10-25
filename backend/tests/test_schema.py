from sqlalchemy import text

from app.db.session import SessionLocal

EXPECTED_TABLES = {
    "users",
    "research_projects",
    "source_documents",
    "document_chunks",
    "research_runs",
    "evidence_items",
    "reports",
    "run_events",
}


async def test_migrations_create_all_tables():
    async with SessionLocal() as session:
        rows = await session.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        tables = {r[0] for r in rows}

    assert EXPECTED_TABLES <= tables


async def test_pgvector_extension_is_installed():
    async with SessionLocal() as session:
        installed = await session.scalar(
            text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
        )

    assert installed == 1


async def test_top_level_tables_have_owner_column():
    async with SessionLocal() as session:
        rows = await session.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'user_id'"
            )
        )
        owned = {r[0] for r in rows}

    assert {"research_projects", "source_documents", "research_runs"} <= owned
