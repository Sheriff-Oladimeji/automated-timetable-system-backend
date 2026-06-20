"""
Lecturer router — lecturers view their own schedule and manage unavailability.

Endpoints:
    GET    /lecturer/schedule               — lecturer: own published timetable (filter by day)
    GET    /lecturer/unavailability         — lecturer: own unavailability records
    POST   /lecturer/unavailability         — lecturer: mark a slot as unavailable
    DELETE /lecturer/unavailability/{id}    — lecturer: remove an unavailability record
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.database import get_db
from app import models, schemas
from app.dependencies import require_lecturer, get_current_user

router = APIRouter()


@router.get("/schedule", response_model=List[schemas.ScheduleEntryOut])
def get_my_schedule(
    day: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_lecturer),
):
    """
    Lecturer views their own published timetable.
    Optionally filter by day.
    """
    # Get the published run
    published_run = (
        db.query(models.SchedulingRun)
        .filter(models.SchedulingRun.is_published == True)
        .first()
    )
    if not published_run:
        raise HTTPException(status_code=404, detail="No published timetable yet")

    # Find this lecturer's profile
    lecturer = (
        db.query(models.Lecturer)
        .filter(models.Lecturer.user_id == current_user.id)
        .first()
    )
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer profile not found")

    query = (
        db.query(models.ScheduleEntry)
        .options(
            joinedload(models.ScheduleEntry.course),
            joinedload(models.ScheduleEntry.lecturer),
            joinedload(models.ScheduleEntry.room),
            joinedload(models.ScheduleEntry.time_slot),
        )
        .filter(
            models.ScheduleEntry.run_id == published_run.id,
            models.ScheduleEntry.lecturer_id == lecturer.id,
        )
    )

    if day:
        query = query.join(models.TimeSlot).filter(models.TimeSlot.day == day)

    return query.all()


@router.get("/unavailability", response_model=List[schemas.UnavailabilityOut])
def get_my_unavailability(
    db: Session = Depends(get_db), current_user: models.User = Depends(require_lecturer)
):
    """Lecturer views their own submitted unavailability records"""
    lecturer = (
        db.query(models.Lecturer)
        .filter(models.Lecturer.user_id == current_user.id)
        .first()
    )
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer profile not found")

    return (
        db.query(models.LecturerUnavailability)
        .filter(models.LecturerUnavailability.lecturer_id == lecturer.id)
        .all()
    )


@router.post("/unavailability", response_model=schemas.UnavailabilityOut)
def submit_unavailability(
    data: schemas.UnavailabilityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_lecturer),
):
    """Lecturer submits a time slot they are not available for"""
    lecturer = (
        db.query(models.Lecturer)
        .filter(models.Lecturer.user_id == current_user.id)
        .first()
    )
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer profile not found")

    # Force lecturer_id to be their own
    if data.lecturer_id != lecturer.id:
        raise HTTPException(
            status_code=403, detail="You can only submit your own unavailability"
        )

    existing = (
        db.query(models.LecturerUnavailability)
        .filter(
            models.LecturerUnavailability.lecturer_id == lecturer.id,
            models.LecturerUnavailability.time_slot_id == data.time_slot_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Already marked unavailable for this slot"
        )

    record = models.LecturerUnavailability(
        lecturer_id=lecturer.id, time_slot_id=data.time_slot_id, reason=data.reason
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/unavailability/{record_id}")
def remove_my_unavailability(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_lecturer),
):
    """Lecturer removes one of their unavailability records"""
    lecturer = (
        db.query(models.Lecturer)
        .filter(models.Lecturer.user_id == current_user.id)
        .first()
    )
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer profile not found")

    record = (
        db.query(models.LecturerUnavailability)
        .filter(
            models.LecturerUnavailability.id == record_id,
            models.LecturerUnavailability.lecturer_id == lecturer.id,
        )
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=404, detail="Record not found or does not belong to you"
        )

    db.delete(record)
    db.commit()
    return {"message": "Unavailability record removed"}
