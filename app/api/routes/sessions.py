from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, delete, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.session import (
    SessionSet,
    SessionSetCreate,
    SessionSetRead,
    SessionSetUpdate,
    WorkoutSession,
    WorkoutSessionCreate,
    WorkoutSessionRead,
    WorkoutSessionUpdate,
)
from app.models.template import TemplateExercise, WorkoutTemplate
from app.models.user import User
from app.services.exercise_access import ensure_accessible_exercise_or_400
from app.services.persistence import no_content_response, save_and_refresh
from app.services.progression_service import check_and_create_pr
from app.services.session_service import delete_workout_session_with_sets

router = APIRouter()


def _get_session_or_404(session: Session, session_id: int, current_user: User) -> WorkoutSession:
    workout_session = session.get(WorkoutSession, session_id)
    if workout_session is None or workout_session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return workout_session


def _get_session_set_or_404(session: Session, session_id: int, set_id: int) -> SessionSet:
    session_set = session.get(SessionSet, set_id)
    if session_set is None or session_set.session_id != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session set not found.")
    return session_set


def _validate_template_for_session(session: Session, template_id: int | None) -> None:
    if template_id is None:
        return
    if session.get(WorkoutTemplate, template_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected template does not exist.",
        )


def _validate_exercise_for_session_set(
    session: Session,
    exercise_id: int | None,
    user_id: int,
) -> None:
    if exercise_id is None:
        return
    ensure_accessible_exercise_or_400(session=session, exercise_id=exercise_id, user_id=user_id)


def _resolve_template_exercise_for_session_set(
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
    if workout_session.template_id is not None and template_exercise.template_id != workout_session.template_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected template exercise does not belong to this session template.",
        )
    return template_exercise


@router.get("/", response_model=list[WorkoutSessionRead])
def list_sessions(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[WorkoutSession]:
    statement = (
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .order_by(WorkoutSession.performed_at.desc(), WorkoutSession.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


@router.get("/{session_id}", response_model=WorkoutSessionRead)
def read_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutSession:
    return _get_session_or_404(session, session_id, current_user)


@router.post("/", response_model=WorkoutSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: WorkoutSessionCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutSession:
    _validate_template_for_session(session, payload.template_id)
    workout_session = WorkoutSession.model_validate(payload)
    workout_session.user_id = current_user.id
    return save_and_refresh(session, workout_session)


@router.patch("/{session_id}", response_model=WorkoutSessionRead)
def update_session(
    session_id: int,
    payload: WorkoutSessionUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutSession:
    workout_session = _get_session_or_404(session, session_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    if "template_id" in updates:
        _validate_template_for_session(session, updates["template_id"])
    workout_session.sqlmodel_update(updates)
    return save_and_refresh(session, workout_session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    workout_session = _get_session_or_404(session, session_id, current_user)
    delete_workout_session_with_sets(session, workout_session)
    session.commit()
    return no_content_response()


@router.get("/{session_id}/sets", response_model=list[SessionSetRead])
def list_session_sets(
    session_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[SessionSet]:
    _get_session_or_404(session, session_id, current_user)
    statement = (
        select(SessionSet)
        .where(SessionSet.session_id == session_id)
        .order_by(SessionSet.set_number, SessionSet.id)
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


@router.post("/{session_id}/sets", response_model=SessionSetRead, status_code=status.HTTP_201_CREATED)
def create_session_set(
    session_id: int,
    payload: SessionSetCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    workout_session = _get_session_or_404(session, session_id, current_user)
    template_exercise = _resolve_template_exercise_for_session_set(
        session,
        payload.template_exercise_id,
        workout_session,
    )
    if payload.exercise_id is None and template_exercise is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exercise_id or template_exercise_id is required.",
        )
    exercise_id = payload.exercise_id
    if exercise_id is None and template_exercise is not None:
        exercise_id = template_exercise.exercise_id
    _validate_exercise_for_session_set(session, exercise_id, current_user.id)

    session_set = SessionSet.model_validate(payload)
    session_set.session_id = session_id
    if session_set.exercise_id is None and exercise_id is not None:
        session_set.exercise_id = exercise_id
    session_set = save_and_refresh(session, session_set)

    set_data = SessionSetRead.model_validate(session_set).model_dump()
    if exercise_id is not None:
        pr = check_and_create_pr(
            session, current_user.id, exercise_id, session_set, workout_session.performed_at
        )
        if pr is not None:
            set_data["personal_record"] = {"pr_type": pr.pr_type, "value": float(pr.value)}

    return set_data


@router.patch("/{session_id}/sets/{set_id}", response_model=SessionSetRead)
def update_session_set(
    session_id: int,
    set_id: int,
    payload: SessionSetUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    workout_session = _get_session_or_404(session, session_id, current_user)
    session_set = _get_session_set_or_404(session, session_id, set_id)
    previous_exercise_id = session_set.exercise_id
    updates = payload.model_dump(exclude_unset=True)
    template_exercise_id = updates.get("template_exercise_id", session_set.template_exercise_id)
    template_exercise = _resolve_template_exercise_for_session_set(
        session,
        template_exercise_id,
        workout_session,
    )
    exercise_id = updates.get("exercise_id", session_set.exercise_id)
    if exercise_id is None and template_exercise is not None:
        exercise_id = template_exercise.exercise_id
        updates["exercise_id"] = exercise_id
    if exercise_id is None and template_exercise is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exercise_id or template_exercise_id is required.",
        )
    _validate_exercise_for_session_set(session, exercise_id, current_user.id)

    session_set.sqlmodel_update(updates)
    session_set = save_and_refresh(session, session_set)

    set_data = SessionSetRead.model_validate(session_set).model_dump()
    resolved_exercise_id = exercise_id or previous_exercise_id
    if resolved_exercise_id is not None:
        pr = check_and_create_pr(
            session,
            current_user.id,
            resolved_exercise_id,
            session_set,
            workout_session.performed_at,
        )
        if pr is not None:
            set_data["personal_record"] = {"pr_type": pr.pr_type, "value": float(pr.value)}

    return set_data


@router.delete("/{session_id}/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session_set(
    session_id: int,
    set_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    _get_session_or_404(session, session_id, current_user)
    session_set = _get_session_set_or_404(session, session_id, set_id)
    session.delete(session_set)
    session.commit()
    return no_content_response()
