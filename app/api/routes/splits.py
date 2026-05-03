from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.template import TrainingSplit, TrainingSplitCreate, TrainingSplitRead, TrainingSplitUpdate, WorkoutTemplate
from app.models.user import User
from app.services.persistence import no_content_response, save_and_refresh

router = APIRouter()


def _get_split_or_404(session: Session, split_id: int, current_user: User) -> TrainingSplit:
    split = session.get(TrainingSplit, split_id)
    if split is None or split.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split not found.")
    return split


@router.get("/", response_model=list[TrainingSplitRead])
def list_splits(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[TrainingSplit]:
    statement = (
        select(TrainingSplit)
        .where(TrainingSplit.user_id == current_user.id)
        .order_by(TrainingSplit.id)
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


@router.get("/{split_id}", response_model=TrainingSplitRead)
def read_split(
    split_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TrainingSplit:
    return _get_split_or_404(session, split_id, current_user)


@router.post("/", response_model=TrainingSplitRead, status_code=status.HTTP_201_CREATED)
def create_split(
    payload: TrainingSplitCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TrainingSplit:
    split = TrainingSplit.model_validate(payload)
    split.user_id = current_user.id
    return save_and_refresh(session, split)


@router.patch("/{split_id}", response_model=TrainingSplitRead)
def update_split(
    split_id: int,
    payload: TrainingSplitUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TrainingSplit:
    split = _get_split_or_404(session, split_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    split.sqlmodel_update(updates)
    return save_and_refresh(session, split)


@router.delete("/{split_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_split(
    split_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    split = _get_split_or_404(session, split_id, current_user)

    templates = session.exec(
        select(WorkoutTemplate).where(WorkoutTemplate.split_id == split.id)
    ).all()
    for template in templates:
        template.split_id = None
        template.order_in_split = None

    session.delete(split)
    session.commit()
    return no_content_response()
