"""
Database engine and session factory for the timetable system.

All SQLAlchemy models must import Base from here and register themselves via
the standard `__tablename__` / Column declarations before `create_all` is called.

Session lifecycle:
  - HTTP requests: use `get_db()` as a FastAPI Depends — the session is closed
    when the request ends (via the finally block in the generator).
  - Background tasks: instantiate SessionLocal() directly, close in a finally block.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Copy .env.example to .env and fill in your PostgreSQL connection string."
    )

engine = create_engine(
    DATABASE_URL,
    # Return connections to the pool after a configurable timeout so stale
    # connections from Neon's serverless PostgreSQL are cleaned up automatically.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
