from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, delete, select

from app.api.deps import get_current_user, get_optional_current_user
from app.db.session import get_session
from app.models.common import PaginatedResponse, utcnow
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
from app.services.persistence import no_content_response, save_and_refresh

router = APIRouter()


def _get_user_template_or_404(
    session: Session, template_id: int, current_user: User
) -> WorkoutTemplate:
    template = session.get(WorkoutTemplate, template_id)
    if template is None or template.user_id != current_user.id:
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


@router.get("/", response_model=PaginatedResponse)
def list_templates(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> PaginatedResponse[WorkoutTemplateRead]:
    base = select(WorkoutTemplate).where(WorkoutTemplate.user_id == current_user.id)
    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    items = list(session.exec(base.order_by(WorkoutTemplate.id).offset(offset).limit(limit)).all())
    return PaginatedResponse[WorkoutTemplateRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/{template_id}", response_model=WorkoutTemplateRead)
def read_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutTemplate:
    return _get_user_template_or_404(session, template_id, current_user)


@router.post("/", response_model=WorkoutTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: WorkoutTemplateCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutTemplate:
    exercises_payload = payload.exercises
    template_data = payload.model_dump(exclude={"exercises"})
    template = WorkoutTemplate.model_validate(template_data)
    template.user_id = current_user.id
    template = save_and_refresh(session, template)

    if exercises_payload:
        for exercise_payload in exercises_payload:
            ensure_accessible_exercise_or_400(
                session=session,
                exercise_id=exercise_payload.exercise_id,
                user_id=current_user.id,
            )
            te = TemplateExercise.model_validate(exercise_payload)
            te.template_id = template.id
            te.updated_at = utcnow()
            session.add(te)
        session.commit()
        session.refresh(template)

    return template


@router.patch("/{template_id}", response_model=WorkoutTemplateRead)
def update_template(
    template_id: int,
    payload: WorkoutTemplateUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutTemplate:
    template = _get_user_template_or_404(session, template_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    exercises_payload = updates.pop("exercises", None)

    template.sqlmodel_update(updates)

    if exercises_payload is not None:
        # delete existing exercises
        session.exec(delete(TemplateExercise).where(TemplateExercise.template_id == template_id))
        # recreate
        for exercise_payload in exercises_payload:
            ensure_accessible_exercise_or_400(
                session=session,
                exercise_id=exercise_payload.exercise_id,
                user_id=current_user.id,
            )
            te = TemplateExercise.model_validate(exercise_payload)
            te.template_id = template.id
            te.updated_at = utcnow()
            session.add(te)
        session.flush()

    return save_and_refresh(session, template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    template = _get_user_template_or_404(session, template_id, current_user)

    session.exec(delete(TemplateExercise).where(TemplateExercise.template_id == template.id))
    session.delete(template)
    session.commit()
    return no_content_response()


@router.get("/{template_id}/exercises", response_model=PaginatedResponse)
def list_template_exercises(
    template_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> PaginatedResponse[TemplateExerciseRead]:
    _get_user_template_or_404(session, template_id, current_user)
    base = select(TemplateExercise).where(TemplateExercise.template_id == template_id)
    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    items = list(
        session.exec(
            base.order_by(TemplateExercise.order_in_template, TemplateExercise.id)
            .offset(offset).limit(limit)
        ).all()
    )
    return PaginatedResponse[TemplateExerciseRead](
        items=items, total=total, limit=limit, offset=offset
    )


@router.post(
    "/{template_id}/exercises",
    response_model=TemplateExerciseRead,
    status_code=status.HTTP_201_CREATED,
)
def add_template_exercise(
    template_id: int,
    payload: TemplateExerciseCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TemplateExercise:
    _get_user_template_or_404(session, template_id, current_user)
    ensure_accessible_exercise_or_400(
        session=session,
        exercise_id=payload.exercise_id,
        user_id=current_user.id,
    )

    template_exercise = TemplateExercise.model_validate(payload)
    template_exercise.template_id = template_id
    template_exercise.updated_at = utcnow()
    return save_and_refresh(session, template_exercise)


@router.patch(
    "/{template_id}/exercises/{template_exercise_id}", response_model=TemplateExerciseRead
)
def update_template_exercise(
    template_id: int,
    template_exercise_id: int,
    payload: TemplateExerciseUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TemplateExercise:
    template_exercise = _get_template_exercise_or_404(session, template_id, template_exercise_id)

    # Verify template ownership
    _get_user_template_or_404(session, template_id, current_user)

    updates = payload.model_dump(exclude_unset=True)

    if "exercise_id" in updates:
        ensure_accessible_exercise_or_400(
            session=session,
            exercise_id=updates["exercise_id"],
            user_id=current_user.id,
        )

    template_exercise.sqlmodel_update(updates)

    template_exercise.updated_at = utcnow()
    return save_and_refresh(session, template_exercise)


@router.delete(
    "/{template_id}/exercises/{template_exercise_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_template_exercise(
    template_id: int,
    template_exercise_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    template_exercise = _get_template_exercise_or_404(session, template_id, template_exercise_id)

    # Verify template ownership
    _get_user_template_or_404(session, template_id, current_user)

    session.delete(template_exercise)
    session.commit()
    return no_content_response()


# ── Bulk operations ─────────────────────────────────────────────────────────


class ReorderExercisesRequest(BaseModel):
    exercise_ids: list[int]


@router.put("/{template_id}/exercises/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_template_exercises(
    template_id: int,
    payload: ReorderExercisesRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """Reorder template exercises by providing exercise IDs in the desired order."""
    _get_user_template_or_404(session, template_id, current_user)

    # Fetch all existing template exercises for this template
    statement = (
        select(TemplateExercise)
        .where(TemplateExercise.template_id == template_id)
        .order_by(TemplateExercise.id)
    )
    existing = {te.id: te for te in session.exec(statement).all()}

    # Validate all IDs exist and belong to this template
    for te_id in payload.exercise_ids:
        if te_id not in existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template exercise {te_id} not found in this template.",
            )

    # Update order_in_template based on position (1-indexed)
    for i, te_id in enumerate(payload.exercise_ids, start=1):
        existing[te_id].order_in_template = i

    session.commit()
    return no_content_response()


@router.post("/{template_id}/duplicate", response_model=WorkoutTemplateRead, status_code=status.HTTP_201_CREATED)
def duplicate_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutTemplate:
    """Deep-copy a workout template with all its exercises."""
    original = _get_user_template_or_404(session, template_id, current_user)

    # Create a new template with "(Copy)" suffix
    new_template = WorkoutTemplate(
        name=f"{original.name} (Copy)",
        split_id=original.split_id,
        order_in_split=original.order_in_split,
        user_id=current_user.id,
        description=original.description,
    )
    session.add(new_template)
    session.commit()
    session.refresh(new_template)

    # Copy all template exercises
    statement = (
        select(TemplateExercise)
        .where(TemplateExercise.template_id == template_id)
        .order_by(TemplateExercise.id)
    )
    original_exercises = list(session.exec(statement).all())

    for te in original_exercises:
        new_te = TemplateExercise(
            template_id=new_template.id,
            exercise_id=te.exercise_id,
            sets=te.sets,
            reps=te.reps,
            rir=te.rir,
            order_in_template=te.order_in_template,
            pause_seconds=te.pause_seconds,
            weight_kg=te.weight_kg,
            updated_at=te.updated_at,
        )
        session.add(new_te)

    session.commit()
    session.refresh(new_template)
    return new_template
