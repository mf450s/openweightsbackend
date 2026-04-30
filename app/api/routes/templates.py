from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.template import WorkoutTemplate, WorkoutTemplateCreate, WorkoutTemplateRead

router = APIRouter()


@router.get("/", response_model=list[WorkoutTemplateRead])
def list_templates(session: Session = Depends(get_session)) -> list[WorkoutTemplate]:
    statement = select(WorkoutTemplate).order_by(WorkoutTemplate.id)
    return list(session.exec(statement).all())


@router.post("/", response_model=WorkoutTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: WorkoutTemplateCreate, session: Session = Depends(get_session)
) -> WorkoutTemplate:
    template = WorkoutTemplate.model_validate(payload)
    session.add(template)
    session.commit()
    session.refresh(template)
    return template
