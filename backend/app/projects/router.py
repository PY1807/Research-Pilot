import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.models import ResearchProject, User
from app.db.session import SessionDep
from app.projects.schemas import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


async def get_owned_project(
    session: AsyncSession, project_id: uuid.UUID, user: User
) -> ResearchProject:
    """Fetch a project only if it belongs to the user. Someone else's project gets the
    same 404 as a missing one, so IDs can't be probed for existence."""
    project = await session.get(ResearchProject, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    return project


@router.post("/", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, session: SessionDep, user: CurrentUser):
    project = ResearchProject(user_id=user.id, **body.model_dump())
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/", response_model=list[ProjectOut])
async def list_projects(session: SessionDep, user: CurrentUser):
    rows = await session.scalars(
        select(ResearchProject)
        .where(ResearchProject.user_id == user.id)
        .order_by(ResearchProject.created_at.desc())
    )
    return rows.all()


@router.get("/{project_id}/", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    return await get_owned_project(session, project_id, user)
