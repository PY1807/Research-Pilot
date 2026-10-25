"""Create the single development user that owns everything until auth lands in M8.

Safe to run repeatedly: it does nothing if the user already exists.
Run with: python -m app.scripts.seed_dev_user
"""

import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.db.models import User
from app.db.session import SessionLocal, engine


async def main() -> None:
    email = get_settings().dev_user_email
    async with SessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            print(f"Dev user already exists: {email} ({existing.id})")
        else:
            user = User(email=email, is_verified=True)
            session.add(user)
            await session.commit()
            print(f"Created dev user: {email} ({user.id})")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
