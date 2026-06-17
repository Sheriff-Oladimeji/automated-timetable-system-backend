from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, SessionLocal
from app import models, schemas
from app.dependencies import require_admin
from app.scheduler.solver import run_solver
from app.routers.constraints import _constraint_config

router = APIRouter()


def run_solver_background(run_id: int, config: dict):
    """
    Wrapper that creates its own DB session for the background task.
    Background tasks run outside the request lifecycle so they need
    their own session — they can't reuse the request's session.
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
    Admin triggers a new scheduling run.
    Creates a run record immediately and starts the solver in the background.
    Frontend polls /scheduler/status/{run_id} to track progress.
    """
    # Check no run is currently in progress
    active_run = (
        db.query(models.SchedulingRun)
        .filter(models.SchedulingRun.status == models.SolverStatus.running)
        .first()
    )
    if active_run:
        raise HTTPException(
            status_code=409,
            detail=f"A scheduling run is already in progress (ID: {active_run.id})",
        )

    # Create the run record
    run = models.SchedulingRun(status=models.SolverStatus.pending)
    db.add(run)
    db.commit()
    db.refresh(run)

    # Convert constraint config to dict for the background task
    config = _constraint_config.model_dump()

    # Start solver in background — returns immediately to the client
    background_tasks.add_task(run_solver_background, run.id, config)

    return run


@router.get("/status/{run_id}", response_model=schemas.SchedulerRunOut)
def get_run_status(
    run_id: int, db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    """Frontend polls this every 3 seconds after triggering a run"""
    run = (
        db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs", response_model=List[schemas.SchedulerRunOut])
def get_all_runs(
    db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    """Admin views history of all scheduling runs"""
    return (
        db.query(models.SchedulingRun)
        .order_by(models.SchedulingRun.created_at.desc())
        .all()
    )
