"""
SQLAlchemy engine and session management for Neon PostgreSQL.

Neon is a standard Postgres wire-protocol database, so this is a plain
SQLAlchemy + psycopg setup — no Neon-specific driver is required. Using
`postgresql+psycopg://` (psycopg3) in DATABASE_URL is recommended.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,  # important for serverless Neon connections that may idle out
    echo=settings.DATABASE_ECHO,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
