"""
FastAPI dependencies -- Milestone 5.

A plain per-request session, not db.session.get_session() (which commits
on exit) -- every route in this API is read-only (journal querying), so
there's nothing to commit; closing is all that's needed.
"""

from typing import Iterator

from sqlalchemy.orm import Session

from db.session import SessionLocal


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
