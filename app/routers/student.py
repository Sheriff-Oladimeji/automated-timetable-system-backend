from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/timetable", response_model=List[schemas.ScheduleEntryOut])
def get_student_timetable(
    department_id: int = None,
    level: int = None,
    day: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Students view the published timetable.
    Filterable by department, level, and day.
    If no filters provided, returns timetable for the student's own dept + level.
    """
    # Get the published run
    published_run = (
        db.query(models.SchedulingRun)
        .filter(models.SchedulingRun.is_published == True)
        .first()
    )
    if not published_run:
        raise HTTPException(status_code=404, detail="No published timetable available")

    # If student is logged in and no filters given, default to their own dept+level
    if current_user.role == models.UserRole.student:
        student = (
            db.query(models.Student)
            .filter(models.Student.user_id == current_user.id)
            .first()
        )
        if student:
            if department_id is None:
                department_id = student.department_id
            if level is None:
                level = student.level

    # Base query with eager loading for full entry details
    query = (
        db.query(models.ScheduleEntry)
        .options(
            joinedload(models.ScheduleEntry.course),
            joinedload(models.ScheduleEntry.lecturer),
            joinedload(models.ScheduleEntry.room),
            joinedload(models.ScheduleEntry.time_slot),
        )
        .join(models.Course)
        .filter(models.ScheduleEntry.run_id == published_run.id)
    )

    if department_id:
        query = query.filter(models.Course.department_id == department_id)

    if level:
        query = query.filter(models.Course.level == level)

    if day:
        query = query.join(models.TimeSlot).filter(models.TimeSlot.day == day)

    return query.all()


@router.get("/departments", response_model=List[schemas.DepartmentOut])
def get_departments_for_filter(db: Session = Depends(get_db)):
    """Public endpoint — students use this to populate the department filter dropdown"""
    return db.query(models.Department).all()
