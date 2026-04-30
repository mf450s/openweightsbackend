from fastapi import Response, status
from sqlmodel import Session, SQLModel


def save_and_refresh(session: Session, instance: SQLModel) -> SQLModel:
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return instance


def no_content_response() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
