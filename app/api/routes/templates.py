from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, delete, select

from app.api.deps import get_optional_current_user
from app.db.session import get_session
from app.models.common import utcnow
from app.models.template import (
    TemplateExercise,
    TemplateExerciseCreate,
    TemplateExerciseRead,
    TemplateExerciseUpdate,
    WorkoutTemplate,
    WorkoutTemplateCreate,
    WorkoutTemplateRead,
    WorkoutTemplateUpdate,
)
from app.models.user import User
from app.services.exercise_access import ensure_accessible_exercise_or_400

router = APIRouter()


def _get_template_or_404(session: Session, template_id: int) -> WorkoutTemplate:
    template = session.get(WorkoutTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    return template


def _get_template_exercise_or_404(
    session: Session, template_id: int, template_exercise_id: int
) -> TemplateExercise:
    template_exercise = session.get(TemplateExercise, template_exercise_id)
    if template_exercise is None or template_exercise.template_id != template_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template exercise not found.",
        )
    return template_exercise


@router.get("/", response_model=list[WorkoutTemplateRead])
def list_templates(session: Session = Depends(get_session)) -> list[WorkoutTemplate]:
    statement = select(WorkoutTemplate).order_by(WorkoutTemplate.id)
    return list(session.exec(statement).all())


@router.get("/{template_id}", response_model=WorkoutTemplateRead)
def read_template(template_id: int, session: Session = Depends(get_session)) -> WorkoutTemplate:
    return _get_template_or_404(session, template_id)


@router.post("/", response_model=WorkoutTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: WorkoutTemplateCreate, session: Session = Depends(get_session)
) -> WorkoutTemplate:
    template = WorkoutTemplate.model_validate(payload)
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


@router.patch("/{template_id}", response_model=WorkoutTemplateRead)
def update_template(
    template_id: int,
    payload: WorkoutTemplateUpdate,
    session: Session = Depends(get_session),
) -> WorkoutTemplate:
    template = _get_template_or_404(session, template_id)
    updates = payload.model_dump(exclude_unset=True)
    template.sqlmodel_update(updates)

    session.add(template)
    session.commit()
    session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, session: Session = Depends(get_session)) -> Response:
    template = _get_template_or_404(session, template_id)

    session.exec(delete(TemplateExercise).where(TemplateExercise.template_id == template.id))
    session.delete(template)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{template_id}/exercises", response_model=list[TemplateExerciseRead])
def list_template_exercises(
    template_id: int,
    session: Session = Depends(get_session),
) -> list[TemplateExercise]:
    _get_template_or_404(session, template_id)
    statement = (
        select(TemplateExercise)
        .where(TemplateExercise.template_id == template_id)
        .order_by(TemplateExercise.order_in_template, TemplateExercise.id)
    )
    return list(session.exec(statement).all())


@router.post(
    "/{template_id}/exercises",
    response_model=TemplateExerciseRead,
    status_code=status.HTTP_201_CREATED,
)
def add_template_exercise(
    template_id: int,
    payload: TemplateExerciseCreate,
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> TemplateExercise:
    _get_template_or_404(session, template_id)
    ensure_accessible_exercise_or_400(
        session=session,
        exercise_id=payload.exercise_id,
        user_id=current_user.id if current_user is not None else None,
    )

    template_exercise = TemplateExercise.model_validate(payload)
    template_exercise.template_id = template_id
    template_exercise.updated_at = utcnow()
    session.add(template_exercise)
    session.commit()
    session.refresh(template_exercise)
    return template_exercise


@router.patch("/{template_id}/exercises/{template_exercise_id}", response_model=TemplateExerciseRead)
def update_template_exercise(
    template_id: int,
    template_exercise_id: int,
    payload: TemplateExerciseUpdate,
    current_user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_session),
) -> TemplateExercise:
    template_exercise = _get_template_exercise_or_404(session, template_id, template_exercise_id)
    updates = payload.model_dump(exclude_unset=True)

    if "exercise_id" in updates:
        ensure_accessible_exercise_or_400(
            session=session,
            exercise_id=updates["exercise_id"],
            user_id=current_user.id if current_user is not None else None,
        )

    template_exercise.sqlmodel_update(updates)

    template_exercise.updated_at = utcnow()
    session.add(template_exercise)
    session.commit()
    session.refresh(template_exercise)
    return template_exercise


@router.delete("/{template_id}/exercises/{template_exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template_exercise(
    template_id: int,
    template_exercise_id: int,
    session: Session = Depends(get_session),
) -> Response:
    template_exercise = _get_template_exercise_or_404(session, template_id, template_exercise_id)
    session.delete(template_exercise)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
