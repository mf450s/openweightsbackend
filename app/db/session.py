from collections.abc import Generator

from sqlmodel import Session, create_engine

from app.core.config import get_settings

settings = get_settings()

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=not is_sqlite,
)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
