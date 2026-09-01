from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import settings


def get_engine():
    """Lazily create and return SQLAlchemy engine if DATABASE_URL is configured."""
    if not settings.DATABASE_URL:
        return None
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def get_sessionmaker():
    """Lazily create and return sessionmaker."""
    engine = get_engine()
    if not engine:
        return None
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session | None, None, None]:
    """Dependency for providing database session to requests."""
    if not settings.DATABASE_URL:
        yield None
        return
    session_factory = get_sessionmaker()
    if not session_factory:
        yield None
        return
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
