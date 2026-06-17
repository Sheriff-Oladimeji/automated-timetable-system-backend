from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas
from app.dependencies import require_admin, require_lecturer, get_current_user

router = APIRouter()


# ─── LECTURER UNAVAILABILITY ─────────────────────────────────────────────────


@router.get("/unavailability", response_model=List[schemas.UnavailabilityOut])
def get_all_unavailability(
    lecturer_id: int = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Admin views all unavailability records"""
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
    Lecturers submit their own unavailability.
    Admins can submit on behalf of any lecturer.
    """
    if current_user.role == models.UserRole.lecturer:
        # Lecturers can only submit for themselves
        lecturer = (
            db.query(models.Lecturer)
            .filter(models.Lecturer.user_id == current_user.id)
            .first()
        )
        if not lecturer or lecturer.id != data.lecturer_id:
            raise HTTPException(
                status_code=403, detail="You can only submit your own unavailability"
            )

    # Check it doesn't already exist
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

    db.delete(record)
    db.commit()
    return {"message": "Unavailability record removed"}


# ─── CONSTRAINT CONFIG ───────────────────────────────────────────────────────

# Store constraint config in memory for now (could be a DB table later)
_constraint_config = schemas.ConstraintConfig()


@router.get("/config", response_model=schemas.ConstraintConfig)
def get_constraint_config(_: models.User = Depends(require_admin)):
    """Get current soft constraint penalty weights"""
    return _constraint_config


@router.put("/config", response_model=schemas.ConstraintConfig)
def update_constraint_config(
    data: schemas.ConstraintConfig, _: models.User = Depends(require_admin)
):
    """Admin updates soft constraint penalty weights before a scheduling run"""
    global _constraint_config
    _constraint_config = data
    return _constraint_config
