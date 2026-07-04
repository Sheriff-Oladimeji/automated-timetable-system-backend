"""
Constraints router — lecturer unavailability records and solver penalty-weight config.

Endpoints:
    GET    /constraints/unavailability           — admin: list all records (filter by lecturer)
    POST   /constraints/unavailability           — lecturer/admin: add a record
    DELETE /constraints/unavailability/{id}      — lecturer/admin: remove a record
    GET    /constraints/config                   — admin: current penalty weights
    PUT    /constraints/config                   — admin: update penalty weights
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas
from app.dependencies import require_admin, get_current_user

router = APIRouter()


# ─── HELPERS ─────────────────────────────────────────────────────────────────


def get_or_create_config(db: Session) -> models.SystemConfig:
    """Return the singleton SystemConfig row, creating it with defaults if absent."""
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.id == 1).first()
    if not cfg:
        cfg = models.SystemConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# ─── LECTURER UNAVAILABILITY ─────────────────────────────────────────────────


@router.get("/unavailability", response_model=List[schemas.UnavailabilityOut])
def get_all_unavailability(
    lecturer_id: int = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Admin views all lecturer unavailability records, optionally filtered by lecturer."""
    query = db.query(models.LecturerUnavailability)
    if lecturer_id:
        query = query.filter(models.LecturerUnavailability.lecturer_id == lecturer_id)
    return query.all()


@router.post("/unavailability", response_model=schemas.UnavailabilityOut)
def add_unavailability(
    data: schemas.UnavailabilityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Mark a time slot as unavailable for a lecturer.

    - Lecturers may only submit records for themselves.
    - Admins may submit on behalf of any lecturer.
    """
    if current_user.role == models.UserRole.lecturer:
        lecturer = (
            db.query(models.Lecturer)
            .filter(models.Lecturer.user_id == current_user.id)
            .first()
        )
        if not lecturer or lecturer.id != data.lecturer_id:
            raise HTTPException(
                status_code=403,
                detail="You can only submit unavailability for yourself",
            )
    elif current_user.role != models.UserRole.admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify the referenced lecturer exists
    if not db.query(models.Lecturer).filter(models.Lecturer.id == data.lecturer_id).first():
        raise HTTPException(status_code=404, detail="Lecturer not found")

    # Verify the referenced time slot exists
    if not db.query(models.TimeSlot).filter(models.TimeSlot.id == data.time_slot_id).first():
        raise HTTPException(status_code=404, detail="Time slot not found")

    existing = (
        db.query(models.LecturerUnavailability)
        .filter(
            models.LecturerUnavailability.lecturer_id == data.lecturer_id,
            models.LecturerUnavailability.time_slot_id == data.time_slot_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Unavailability record already exists for this slot"
        )

    record = models.LecturerUnavailability(**data.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/unavailability/{record_id}")
def remove_unavailability(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Remove an unavailability record. Lecturers may only remove their own records."""
    record = (
        db.query(models.LecturerUnavailability)
        .filter(models.LecturerUnavailability.id == record_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    if current_user.role == models.UserRole.lecturer:
        lecturer = (
            db.query(models.Lecturer)
            .filter(models.Lecturer.user_id == current_user.id)
            .first()
        )
        if not lecturer or lecturer.id != record.lecturer_id:
            raise HTTPException(
                status_code=403, detail="You can only remove your own unavailability"
            )
    elif current_user.role != models.UserRole.admin:
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(record)
    db.commit()
    return {"message": "Unavailability record removed"}


# ─── CONSTRAINT CONFIG ───────────────────────────────────────────────────────


@router.get("/config", response_model=schemas.ConstraintConfig)
def get_constraint_config(
    db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    """Return the current soft-constraint penalty weights."""
    return get_or_create_config(db)


@router.put("/config", response_model=schemas.ConstraintConfig)
def update_constraint_config(
    data: schemas.ConstraintConfig,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """
    Update soft-constraint penalty weights.
    Changes are persisted in the database and survive server restarts.
    """
    cfg = get_or_create_config(db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    return cfg
