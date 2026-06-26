"""
FastAPI application entry point for the CSET Automated Timetable System.

The app uses a lifespan context manager to create database tables on startup
(development convenience — in production use Alembic migrations instead).

CORS is configured for the default Vite dev server (localhost:5173).
Update `allow_origins` for staging/production deployments.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base

# Import all models so SQLAlchemy registers them with Base before create_all
from app import models  # noqa: F401

from app.routers import (
    auth,
    resources,
    constraints,
    scheduler,
    timetable,
    lecturer,
    student,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create all tables on startup if they don't exist yet."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="CSET Automated Timetable System",
    description=(
        "Constraint-based automated timetable scheduler for the College of Science, "
        "Engineering and Technology (CSET), UNIOSUN. "
        "Uses Google OR-Tools CP-SAT to assign courses to rooms and time slots "
        "while respecting lecturer availability, room capacity, and course type constraints."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(resources.router, prefix="/resources", tags=["Resources"])
app.include_router(constraints.router, prefix="/constraints", tags=["Constraints"])
app.include_router(scheduler.router, prefix="/scheduler", tags=["Scheduler"])
app.include_router(timetable.router, prefix="/timetable", tags=["Timetable"])
app.include_router(lecturer.router, prefix="/lecturer", tags=["Lecturer"])
app.include_router(student.router, prefix="/student", tags=["Student"])


@app.get("/", tags=["Health"])
def health_check():
    """Health check — confirms the API is running."""
    return {"status": "ok", "message": "CSET Timetable API is running"}
