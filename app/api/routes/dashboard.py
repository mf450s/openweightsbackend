from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.session import SessionSet, WorkoutSession
from app.models.user import User

router = APIRouter()


class DashboardStats(BaseModel):
    total_sessions: int
    total_sets: int
    total_volume: float  # sum of weight_kg * reps for all completed sets
    current_streak_days: int  # consecutive days with at least one session
    this_week_sessions: int
    this_week_volume: float


def _compute_current_streak(session: Session, user_id: int) -> int:
    """Count consecutive days (starting from today backwards) with at least one session."""
    today = date.today()

    # Get all distinct session dates for this user, ordered desc
    statement = (
        select(func.date(WorkoutSession.performed_at))
        .where(WorkoutSession.user_id == user_id)
        .distinct()
        .order_by(func.date(WorkoutSession.performed_at).desc())
    )
    session_dates = list(session.exec(statement).all())

    streak = 0
    # Start from today and count consecutive days
    for i, d in enumerate(session_dates):
        expected = today - timedelta(days=i)
        # SQLite returns strings from func.date(); convert for comparison
        session_date = date.fromisoformat(d) if isinstance(d, str) else d
        if session_date == expected:
            streak += 1
        else:
            break
    return streak


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> DashboardStats:
    """Return summary dashboard stats for the current user."""

    # Total sessions
    total_sessions_stmt = (
        select(func.count())
        .select_from(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
    )
    total_sessions = session.exec(total_sessions_stmt).one()

    # Total sets (across all user sessions)
    total_sets_stmt = (
        select(func.count())
        .select_from(SessionSet)
        .join(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
    )
    total_sets = session.exec(total_sets_stmt).one()

    # Total volume: sum(weight_kg * reps) for completed sets
    total_volume_stmt = (
        select(func.coalesce(func.sum(SessionSet.weight_kg * SessionSet.reps), 0))
        .select_from(SessionSet)
        .join(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(SessionSet.completed == True)  # noqa: E712
    )
    total_volume = float(session.exec(total_volume_stmt).one())

    # This week (Monday to Sunday)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    this_week_sessions_stmt = (
        select(func.count())
        .select_from(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(func.date(WorkoutSession.performed_at) >= monday)
        .where(func.date(WorkoutSession.performed_at) <= sunday)
    )
    this_week_sessions = session.exec(this_week_sessions_stmt).one()

    this_week_volume_stmt = (
        select(func.coalesce(func.sum(SessionSet.weight_kg * SessionSet.reps), 0))
        .select_from(SessionSet)
        .join(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .where(SessionSet.completed == True)  # noqa: E712
        .where(func.date(WorkoutSession.performed_at) >= monday)
        .where(func.date(WorkoutSession.performed_at) <= sunday)
    )
    this_week_volume = float(session.exec(this_week_volume_stmt).one())

    current_streak_days = _compute_current_streak(session, current_user.id)

    return DashboardStats(
        total_sessions=total_sessions,
        total_sets=total_sets,
        total_volume=total_volume,
        current_streak_days=current_streak_days,
        this_week_sessions=this_week_sessions,
        this_week_volume=this_week_volume,
    )
