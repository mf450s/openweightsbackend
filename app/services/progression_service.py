from datetime import datetime

from sqlmodel import Session, select

from app.models.progression import PersonalRecord
from app.models.session import SessionSet


def estimate_1rm(weight_kg: float, reps: int, rir: int = 0) -> float | None:
    if weight_kg is None or weight_kg <= 0 or reps is None or reps <= 0:
        return None
    w = float(weight_kg)
    effective_reps = reps + rir
    if effective_reps < 1:
        return None

    estimates = []

    epley = w * (1 + effective_reps / 30)
    estimates.append(epley)

    if effective_reps < 37:
        brzycki = w * (36 / (37 - effective_reps))
        estimates.append(brzycki)
        lander = (100 * w) / (101.3 - 2.67123 * effective_reps)
        estimates.append(lander)

    if not estimates:
        return None

    return round(sum(estimates) / len(estimates), 2)


def get_best_1rm_for_session(sets: list[SessionSet]) -> float | None:
    best = None
    for s in sets:
        if s.weight_kg is None or s.reps is None or not s.completed:
            continue
        est = estimate_1rm(s.weight_kg, s.reps, s.rir or 0)
        if est is not None and (best is None or est > best):
            best = est
    return best


def _get_current_pr(
    session: Session, user_id: int, exercise_id: int, pr_type: str
) -> PersonalRecord | None:
    statement = (
        select(PersonalRecord)
        .where(
            PersonalRecord.user_id == user_id,
            PersonalRecord.exercise_id == exercise_id,
            PersonalRecord.pr_type == pr_type,
        )
        .order_by(PersonalRecord.value.desc())
        .limit(1)
    )
    return session.exec(statement).first()


def check_and_create_pr(
    session: Session,
    user_id: int,
    exercise_id: int,
    session_set: SessionSet,
    achieved_at: datetime,
) -> PersonalRecord | None:
    if not session_set.completed:
        return None
    if session_set.weight_kg is None or session_set.reps is None:
        return None

    weight = float(session_set.weight_kg)
    reps = session_set.reps
    volume = weight * reps
    est_1rm = estimate_1rm(weight, reps, session_set.rir or 0)

    checks: list[tuple[str, float | None]] = [
        ("max_weight", weight),
        ("max_volume", volume),
        ("max_1rm", est_1rm),
    ]

    created: PersonalRecord | None = None

    for pr_type, value in checks:
        if value is None:
            continue
        current = _get_current_pr(session, user_id, exercise_id, pr_type)
        if current is not None and float(current.value) >= value:
            continue
        pr = PersonalRecord(
            user_id=user_id,
            exercise_id=exercise_id,
            pr_type=pr_type,
            value=round(value, 2),
            achieved_at=achieved_at,
            session_set_id=session_set.id,
        )
        session.add(pr)
        session.commit()
        session.refresh(pr)
        if created is None:
            created = pr

    return created
