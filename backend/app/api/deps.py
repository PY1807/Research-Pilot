from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from app.config import get_settings
from app.db.models import User
from app.db.session import SessionDep


async def get_current_user(session: SessionDep) -> User:
    """Until auth lands in M8, every request acts as the seeded dev user.
    Routes depend on this, so swapping in real auth later changes only this function."""
    email = get_settings().dev_user_email
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The development user doesn't exist yet. Run `make seed`.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
