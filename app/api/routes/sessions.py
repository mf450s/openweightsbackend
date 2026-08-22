from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.common import PaginatedResponse, utcnow
from app.models.progression import PersonalRecord
from app.models.session import (
    SessionSet,
    SessionSetBulkCreate,
    SessionSetCreate,
    SessionSetIdsDelete,
    SessionSetRead,
    SessionSetUpdate,
    WorkoutSession,
    WorkoutSessionCreate,
    WorkoutSessionRead,
    WorkoutSessionUpdate,
)
from app.models.template import WorkoutTemplate
from app.models.user import User
from app.services.persistence import no_content_response, save_and_refresh
from app.services.session_service import delete_workout_session_with_sets
from app.services.workout_set_orchestration import (
    add_session_sets,
)
from app.services.workout_set_orchestration import (
    bulk_create_session_sets as orchestrate_bulk_create_session_sets,
)
from app.services.workout_set_orchestration import (
    create_session_set as orchestrate_create_session_set,
)
from app.services.workout_set_orchestration import (
    update_session_set as orchestrate_update_session_set,
)

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


@router.get("/", response_model=PaginatedResponse)
def list_sessions(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> PaginatedResponse[WorkoutSessionRead]:
    base = select(WorkoutSession).where(WorkoutSession.user_id == current_user.id)
    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    items = list(
        session.exec(
            base.order_by(WorkoutSession.performed_at.desc(), WorkoutSession.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return PaginatedResponse[WorkoutSessionRead](
        items=items, total=total, limit=limit, offset=offset
    )


# ── Calendar ────────────────────────────────────────────────────────────────


class CalendarDay(BaseModel):
    day: int  # 1-31
    sessions: list[WorkoutSessionRead]


class CalendarResponse(BaseModel):
    year: int
    month: int
    days: list[CalendarDay]


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CalendarResponse:
    """Return all workout sessions for the given month grouped by day."""
    statement = (
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(func.extract("year", WorkoutSession.performed_at) == year)
        .where(func.extract("month", WorkoutSession.performed_at) == month)
        .order_by(WorkoutSession.performed_at.asc(), WorkoutSession.id.asc())
    )
    sessions_list = list(session.exec(statement).all())

    # Group by day
    day_map: dict[int, list[WorkoutSession]] = {}
    for ws in sessions_list:
        day = ws.performed_at.day
        day_map.setdefault(day, []).append(ws)

    days = [
        CalendarDay(day=day, sessions=[WorkoutSessionRead.model_validate(s) for s in day_map[day]])
        for day in sorted(day_map)
    ]

    return CalendarResponse(year=year, month=month, days=days)


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
    sets_payload = payload.sets
    session_create_data = payload.model_dump(exclude={"sets"})
    workout_session = WorkoutSession.model_validate(session_create_data)
    workout_session.user_id = current_user.id
    workout_session = save_and_refresh(session, workout_session)

    if sets_payload:
        add_session_sets(session, workout_session, current_user.id, sets_payload)
        session.commit()
        session.refresh(workout_session)

    return workout_session


@router.patch("/{session_id}", response_model=WorkoutSessionRead)
def update_session(
    session_id: int,
    payload: WorkoutSessionUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutSession:
    workout_session = _get_session_or_404(session, session_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    sets_payload = updates.pop("sets", None)

    if "template_id" in updates:
        _validate_template_for_session(session, updates["template_id"])
    workout_session.sqlmodel_update(updates)

    if sets_payload is not None:
        # delete existing sets
        existing_sets = session.exec(
            select(SessionSet).where(SessionSet.session_id == session_id)
        ).all()
        for s in existing_sets:
            session.delete(s)

        # recreate from payload
        add_session_sets(session, workout_session, current_user.id, sets_payload)
        session.flush()

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


@router.get("/{session_id}/sets", response_model=PaginatedResponse)
def list_session_sets(
    session_id: int,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> PaginatedResponse[SessionSetRead]:
    _get_session_or_404(session, session_id, current_user)
    base = select(SessionSet).where(SessionSet.session_id == session_id)
    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    items = list(
        session.exec(
            base.order_by(SessionSet.set_number, SessionSet.id).offset(offset).limit(limit)
        ).all()
    )
    return PaginatedResponse[SessionSetRead](items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/{session_id}/sets", response_model=SessionSetRead, status_code=status.HTTP_201_CREATED
)
def create_session_set(
    session_id: int,
    payload: SessionSetCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    workout_session = _get_session_or_404(session, session_id, current_user)
    return orchestrate_create_session_set(session, workout_session, current_user.id, payload)


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
    return orchestrate_update_session_set(
        session, workout_session, session_set, current_user.id, payload
    )


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


# ── Workout Execution ──────────────────────────────────────────────────


@router.post("/{session_id}/start", response_model=WorkoutSessionRead)
def start_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> WorkoutSession:
    """Start a workout session: set started_at=now and active_session=true."""
    workout_session = _get_session_or_404(session, session_id, current_user)
    workout_session.started_at = utcnow()
    workout_session.active_session = True
    return save_and_refresh(session, workout_session)


@router.post("/{session_id}/end")
def end_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """End a workout session: set ended_at=now, active_session=false, return volume & PRs."""
    workout_session = _get_session_or_404(session, session_id, current_user)
    workout_session.ended_at = utcnow()
    workout_session.active_session = False
    save_and_refresh(session, workout_session)

    session_data = WorkoutSessionRead.model_validate(workout_session).model_dump()

    # Compute total session volume (sum of weight_kg * reps for completed sets)
    sets_statement = select(SessionSet).where(SessionSet.session_id == session_id)
    all_sets = list(session.exec(sets_statement).all())
    total_volume = None
    volumes = []
    for s in all_sets:
        if s.completed and s.weight_kg is not None and s.reps is not None:
            volumes.append(float(s.weight_kg) * s.reps)
    if volumes:
        total_volume = round(sum(volumes), 2)
    session_data["total_volume"] = total_volume

    # Collect any PRs found during this session
    set_ids = [s.id for s in all_sets]
    prs = []
    if set_ids:
        pr_statement = select(PersonalRecord).where(PersonalRecord.session_set_id.in_(set_ids))
        prs = list(session.exec(pr_statement).all())
    session_data["personal_records"] = [
        {"pr_type": pr.pr_type, "value": float(pr.value)} for pr in prs
    ]

    return session_data


@router.post("/{session_id}/sets/bulk")
def bulk_create_session_sets(
    session_id: int,
    payload: SessionSetBulkCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Create multiple session sets in a single transaction with PR detection."""
    workout_session = _get_session_or_404(session, session_id, current_user)
    return orchestrate_bulk_create_session_sets(
        session, workout_session, current_user.id, payload.sets
    )


@router.post("/{session_id}/sets/bulk/delete", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete_session_sets(
    session_id: int,
    payload: SessionSetIdsDelete,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """Delete multiple session sets in a single transaction."""
    _get_session_or_404(session, session_id, current_user)
    if not payload.set_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="set_ids must not be empty.",
        )
    statement = select(SessionSet).where(
        SessionSet.session_id == session_id,
        SessionSet.id.in_(payload.set_ids),
    )
    sets_to_delete = list(session.exec(statement).all())
    for s in sets_to_delete:
        session.delete(s)
    session.commit()
    return no_content_response()
