from fastapi import HTTPException, status
from sqlmodel import Session

from app.models.session import (
    SessionSet,
    SessionSetCreate,
    SessionSetRead,
    SessionSetUpdate,
    WorkoutSession,
)
from app.models.template import TemplateExercise
from app.services.exercise_access import ensure_accessible_exercise_or_400
from app.services.persistence import save_and_refresh
from app.services.progression_service import check_and_create_pr


def _resolve_template_exercise(
    session: Session,
    template_exercise_id: int | None,
    workout_session: WorkoutSession,
) -> TemplateExercise | None:
    if template_exercise_id is None:
        return None
    template_exercise = session.get(TemplateExercise, template_exercise_id)
    if template_exercise is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected template exercise does not exist.",
        )
    if (
        workout_session.template_id is not None
        and template_exercise.template_id != workout_session.template_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected template exercise does not belong to this session template.",
        )
    return template_exercise


def _prepare_session_set(
    session: Session,
    payload: SessionSetCreate,
    workout_session: WorkoutSession,
    user_id: int,
    missing_detail: str,
) -> tuple[SessionSet, int]:
    template_exercise = _resolve_template_exercise(
        session, payload.template_exercise_id, workout_session
    )
    if payload.exercise_id is None and template_exercise is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=missing_detail)

    exercise_id = payload.exercise_id
    if exercise_id is None and template_exercise is not None:
        exercise_id = template_exercise.exercise_id
    ensure_accessible_exercise_or_400(session=session, exercise_id=exercise_id, user_id=user_id)
    assert exercise_id is not None

    session_set = SessionSet.model_validate(payload)
    session_set.session_id = workout_session.id
    if session_set.exercise_id is None:
        session_set.exercise_id = exercise_id
    return session_set, exercise_id


def add_session_sets(
    session: Session,
    workout_session: WorkoutSession,
    user_id: int | None,
    payloads: list[SessionSetCreate],
    *,
    missing_detail: str = "exercise_id or template_exercise_id is required.",
) -> None:
    """Validate and stage sets for a session-create or session-update transaction."""
    if user_id is None:
        raise ValueError("A current user is required to add session sets.")
    for payload in payloads:
        session_set, _ = _prepare_session_set(
            session, payload, workout_session, user_id, missing_detail
        )
        session.add(session_set)


def _set_response(
    session: Session,
    user_id: int,
    exercise_id: int,
    session_set: SessionSet,
    performed_at,
) -> dict:
    set_data = SessionSetRead.model_validate(session_set).model_dump()
    pr = check_and_create_pr(session, user_id, exercise_id, session_set, performed_at)
    if pr is not None:
        set_data["personal_record"] = {"pr_type": pr.pr_type, "value": float(pr.value)}
    return set_data


def create_session_set(
    session: Session,
    workout_session: WorkoutSession,
    user_id: int | None,
    payload: SessionSetCreate,
) -> dict:
    if user_id is None:
        raise ValueError("A current user is required to create a session set.")
    session_set, exercise_id = _prepare_session_set(
        session,
        payload,
        workout_session,
        user_id,
        "exercise_id or template_exercise_id is required.",
    )
    session_set = save_and_refresh(session, session_set)
    return _set_response(session, user_id, exercise_id, session_set, workout_session.performed_at)


def update_session_set(
    session: Session,
    workout_session: WorkoutSession,
    session_set: SessionSet,
    user_id: int | None,
    payload: SessionSetUpdate,
) -> dict:
    if user_id is None:
        raise ValueError("A current user is required to update a session set.")
    previous_exercise_id = session_set.exercise_id
    updates = payload.model_dump(exclude_unset=True)
    template_exercise_id = updates.get("template_exercise_id", session_set.template_exercise_id)
    template_exercise = _resolve_template_exercise(session, template_exercise_id, workout_session)

    exercise_id = updates.get("exercise_id", session_set.exercise_id)
    if exercise_id is None and template_exercise is not None:
        exercise_id = template_exercise.exercise_id
        updates["exercise_id"] = exercise_id
    if exercise_id is None and template_exercise is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exercise_id or template_exercise_id is required.",
        )
    ensure_accessible_exercise_or_400(session=session, exercise_id=exercise_id, user_id=user_id)
    assert exercise_id is not None

    session_set.sqlmodel_update(updates)
    session_set = save_and_refresh(session, session_set)
    resolved_exercise_id = exercise_id if exercise_id is not None else previous_exercise_id
    assert resolved_exercise_id is not None
    return _set_response(
        session, user_id, resolved_exercise_id, session_set, workout_session.performed_at
    )


def bulk_create_session_sets(
    session: Session,
    workout_session: WorkoutSession,
    user_id: int | None,
    payloads: list[SessionSetCreate],
) -> list[dict]:
    if user_id is None:
        raise ValueError("A current user is required to create session sets.")
    prepared: list[tuple[SessionSet, int]] = []
    for payload in payloads:
        session_set, exercise_id = _prepare_session_set(
            session,
            payload,
            workout_session,
            user_id,
            "exercise_id or template_exercise_id is required for each set.",
        )
        session.add(session_set)
        prepared.append((session_set, exercise_id))

    session.commit()
    results = []
    for session_set, exercise_id in prepared:
        session.refresh(session_set)
        results.append(
            _set_response(session, user_id, exercise_id, session_set, workout_session.performed_at)
        )
    return results
