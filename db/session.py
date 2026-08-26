"""
SQLAlchemy engine/session setup. Reads config.DATABASE_URL (env override
via DATABASE_URL, defaults to the local docker-compose Postgres).
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.config import DATABASE_URL

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def get_session():
    """Usage: with get_session() as session: ..."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
