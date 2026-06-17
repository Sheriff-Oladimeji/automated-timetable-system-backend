from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.database import get_db
from app import models, schemas
from app.dependencies import require_admin
from app.scheduler.validator import validate_manual_adjustment

router = APIRouter()


@router.get("/{run_id}", response_model=List[schemas.ScheduleEntryOut])
def get_timetable(
    run_id: int, db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    """Admin views the full generated timetable for a specific run"""
    run = (
        db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Scheduling run not found")

    if run.status not in [models.SolverStatus.optimal, models.SolverStatus.feasible]:
        raise HTTPException(
            status_code=400,
            detail=f"Timetable not available — run status is {run.status}",
        )

    entries = (
        db.query(models.ScheduleEntry)
        .options(
            joinedload(models.ScheduleEntry.course),
            joinedload(models.ScheduleEntry.lecturer),
            joinedload(models.ScheduleEntry.room),
            joinedload(models.ScheduleEntry.time_slot),
        )
        .filter(models.ScheduleEntry.run_id == run_id)
        .all()
    )

    return entries


@router.put("/entry/{entry_id}", response_model=schemas.ScheduleEntryOut)
def adjust_entry(
    entry_id: int,
    data: schemas.ManualAdjustRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """
    Admin manually moves a session to a different room/time slot.
    Validates against all hard constraints before committing.
    """
    entry = (
        db.query(models.ScheduleEntry)
        .filter(models.ScheduleEntry.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Check the run is not published yet
    run = (
        db.query(models.SchedulingRun)
        .filter(models.SchedulingRun.id == entry.run_id)
        .first()
    )
    if run.is_published:
        raise HTTPException(status_code=400, detail="Cannot edit a published timetable")

    # Validate against hard constraints
    is_valid, violations = validate_manual_adjustment(
        entry_id, data.room_id, data.time_slot_id, db
    )
    if not is_valid:
        raise HTTPException(
            status_code=422,
            detail={"message": "Hard constraint violation", "violations": violations},
        )

    # Apply the adjustment
    entry.room_id = data.room_id
    entry.time_slot_id = data.time_slot_id
    entry.is_manually_adjusted = True
    db.commit()
    db.refresh(entry)

    # Reload with relationships
    entry = (
        db.query(models.ScheduleEntry)
        .options(
            joinedload(models.ScheduleEntry.course),
            joinedload(models.ScheduleEntry.lecturer),
            joinedload(models.ScheduleEntry.room),
            joinedload(models.ScheduleEntry.time_slot),
        )
        .filter(models.ScheduleEntry.id == entry_id)
        .first()
    )

    return entry


@router.post("/{run_id}/publish")
def publish_timetable(
    run_id: int, db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    """
    Admin publishes the timetable — makes it visible to lecturers and students.
    Unpublishes any previously published run first.
    """
    run = (
        db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status not in [models.SolverStatus.optimal, models.SolverStatus.feasible]:
        raise HTTPException(
            status_code=400, detail="Only completed runs can be published"
        )

    # Unpublish any currently published run
    db.query(models.SchedulingRun).filter(
        models.SchedulingRun.is_published == True, models.SchedulingRun.id != run_id
    ).update({"is_published": False})

    run.is_published = True
    db.commit()

    return {"message": f"Timetable run #{run_id} published successfully"}


@router.post("/{run_id}/unpublish")
def unpublish_timetable(
    run_id: int, db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    run = (
        db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run.is_published = False
    db.commit()
    return {"message": f"Timetable run #{run_id} unpublished"}
