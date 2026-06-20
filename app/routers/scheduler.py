"""
Scheduler router — trigger CP-SAT runs and poll their status.

Endpoints:
    POST /scheduler/run              — admin: start a new scheduling run
    GET  /scheduler/status/{run_id}  — admin: poll run progress
    GET  /scheduler/runs             — admin: list all past runs (newest first)

The solver runs as a FastAPI BackgroundTask so POST /run returns immediately.
Frontend should poll /status/{run_id} every few seconds until status is no
longer 'pending' or 'running'.
"""

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, SessionLocal
from app import models, schemas
from app.dependencies import require_admin
from app.scheduler.solver import run_solver
from app.routers.constraints import get_or_create_config

router = APIRouter()


def run_solver_background(run_id: int, config: dict) -> None:
    """
    Wrapper executed by FastAPI's BackgroundTasks.

    Creates its own DB session because background tasks run outside the
    request lifecycle and cannot reuse the request-scoped session.
    """
    db = SessionLocal()
    try:
        run_solver(run_id, db, config)
    finally:
        db.close()


@router.post("/run", response_model=schemas.SchedulerRunOut)
def trigger_scheduler(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """
    Start a new scheduling run.

    Returns immediately with the run record (status='pending').
    The solver runs in the background — poll /status/{run_id} to track progress.
    Returns 409 if a run is already in progress.
    """
    active_run = (
        db.query(models.SchedulingRun)
        .filter(models.SchedulingRun.status == models.SolverStatus.running)
        .first()
    )
    if active_run:
        raise HTTPException(
            status_code=409,
            detail=f"A scheduling run is already in progress (ID: {active_run.id}). "
                   f"Wait for it to finish before starting a new one.",
        )

    run = models.SchedulingRun(status=models.SolverStatus.pending)
    db.add(run)
    db.commit()
    db.refresh(run)

    # Read config from DB so the background task gets a stable snapshot
    config = schemas.ConstraintConfig.model_validate(
        get_or_create_config(db)
    ).model_dump()

    background_tasks.add_task(run_solver_background, run.id, config)

    return run


@router.get("/status/{run_id}", response_model=schemas.SchedulerRunOut)
def get_run_status(
    run_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Return the current status of a scheduling run (for polling)."""
    run = (
        db.query(models.SchedulingRun)
        .filter(models.SchedulingRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs", response_model=List[schemas.SchedulerRunOut])
def get_all_runs(
    db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    """List all scheduling runs, newest first."""
    return (
        db.query(models.SchedulingRun)
        .order_by(models.SchedulingRun.created_at.desc())
        .all()
    )
