"""
Resources router — CRUD for all scheduling resources.

Endpoints:
    Faculties    GET /faculties            (public)
                 POST /faculties           (admin)
                 DELETE /faculties/{id}    (admin)

    Departments  GET /departments          (public)
                 POST /departments         (admin)
                 DELETE /departments/{id}  (admin)

    Courses      GET /courses              (public, filters: department_id, level)
                 POST /courses             (admin)
                 PUT /courses/{id}         (admin)
                 DELETE /courses/{id}      (admin)

    Lecturers    GET /lecturers            (public, filter: department_id)
                 POST /lecturers           (admin) — also creates a User account
                 PUT /lecturers/{id}       (admin)
                 DELETE /lecturers/{id}    (admin)

    Lecturer-    POST /lecturer-courses    (admin)
    Courses      DELETE /lecturer-courses/{id} (admin)

    Rooms        GET /rooms                (public, filter: room_type)
                 POST /rooms               (admin)
                 PUT /rooms/{id}           (admin)
                 DELETE /rooms/{id}        (admin)

    TimeSlots    GET /timeslots            (public, sorted day+time)
                 POST /timeslots           (admin)
                 DELETE /timeslots/{id}    (admin)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import models, schemas
from app.dependencies import require_admin
from app.routers.auth import hash_password

router = APIRouter()


# ─── FACULTIES ───────────────────────────────────────────────────────────────


@router.get("/faculties", response_model=List[schemas.FacultyOut])
def get_faculties(db: Session = Depends(get_db)):
    """List all faculties."""
    return db.query(models.Faculty).all()


@router.post("/faculties", response_model=schemas.FacultyOut, status_code=201)
def create_faculty(
    data: schemas.FacultyCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Create a new faculty. Code must be unique."""
    if db.query(models.Faculty).filter(models.Faculty.code == data.code).first():
        raise HTTPException(status_code=400, detail="Faculty code already exists")
    faculty = models.Faculty(**data.model_dump())
    db.add(faculty)
    db.commit()
    db.refresh(faculty)
    return faculty


@router.delete("/faculties/{faculty_id}")
def delete_faculty(
    faculty_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Delete a faculty. Fails if departments are still linked to it."""
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    db.delete(faculty)
    db.commit()
    return {"message": "Faculty deleted"}


# ─── DEPARTMENTS ─────────────────────────────────────────────────────────────


@router.get("/departments", response_model=List[schemas.DepartmentOut])
def get_departments(db: Session = Depends(get_db)):
    """List all departments."""
    return db.query(models.Department).all()


@router.post("/departments", response_model=schemas.DepartmentOut, status_code=201)
def create_department(
    data: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Create a new department. Code must be unique."""
    if db.query(models.Department).filter(models.Department.code == data.code).first():
        raise HTTPException(status_code=400, detail="Department code already exists")
    if not db.query(models.Faculty).filter(models.Faculty.id == data.faculty_id).first():
        raise HTTPException(status_code=404, detail="Faculty not found")
    dept = models.Department(**data.model_dump())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.delete("/departments/{dept_id}")
def delete_department(
    dept_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Delete a department."""
    dept = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.delete(dept)
    db.commit()
    return {"message": "Department deleted"}


# ─── COURSES ─────────────────────────────────────────────────────────────────


@router.get("/courses", response_model=List[schemas.CourseOut])
def get_courses(
    department_id: int = None, level: int = None, db: Session = Depends(get_db)
):
    """List courses. Optional filters: department_id, level."""
    query = db.query(models.Course)
    if department_id:
        query = query.filter(models.Course.department_id == department_id)
    if level:
        query = query.filter(models.Course.level == level)
    return query.all()


@router.post("/courses", response_model=schemas.CourseOut, status_code=201)
def create_course(
    data: schemas.CourseCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Create a course. Course code must be unique."""
    if db.query(models.Course).filter(models.Course.code == data.code).first():
        raise HTTPException(status_code=400, detail="Course code already exists")
    if not db.query(models.Department).filter(models.Department.id == data.department_id).first():
        raise HTTPException(status_code=404, detail="Department not found")
    course = models.Course(**data.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.put("/courses/{course_id}", response_model=schemas.CourseOut)
def update_course(
    course_id: int,
    data: schemas.CourseUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Update a course's name, hours_per_week, or enrolled_count."""
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course


@router.delete("/courses/{course_id}")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Delete a course and all its lecturer assignments."""
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    db.delete(course)
    db.commit()
    return {"message": "Course deleted"}


# ─── LECTURERS ───────────────────────────────────────────────────────────────


@router.get("/lecturers", response_model=List[schemas.LecturerOut])
def get_lecturers(department_id: int = None, db: Session = Depends(get_db)):
    """List lecturers. Optional filter: department_id."""
    query = db.query(models.Lecturer)
    if department_id:
        query = query.filter(models.Lecturer.department_id == department_id)
    return query.all()


@router.post("/lecturers", response_model=schemas.LecturerOut, status_code=201)
def create_lecturer(
    data: schemas.LecturerCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """
    Create a lecturer and automatically provision their login account.

    The account is created with a default password of 'changeme123'.
    The lecturer should change it on first login.
    If a User with the same email already exists it is reused (no duplicate account).
    """
    if not db.query(models.Department).filter(models.Department.id == data.department_id).first():
        raise HTTPException(status_code=404, detail="Department not found")

    if db.query(models.Lecturer).filter(models.Lecturer.email == data.email).first():
        raise HTTPException(status_code=400, detail="A lecturer with this email already exists")

    existing_user = db.query(models.User).filter(models.User.email == data.email).first()
    if not existing_user:
        user = models.User(
            email=data.email,
            hashed_password=hash_password("changeme123"),
            role=models.UserRole.lecturer,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    else:
        user_id = existing_user.id

    lecturer = models.Lecturer(
        user_id=user_id,
        department_id=data.department_id,
        title=data.title,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
    )
    db.add(lecturer)
    db.commit()
    db.refresh(lecturer)
    return lecturer


@router.put("/lecturers/{lecturer_id}", response_model=schemas.LecturerOut)
def update_lecturer(
    lecturer_id: int,
    data: schemas.LecturerUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Update a lecturer's title or name fields."""
    lecturer = (
        db.query(models.Lecturer).filter(models.Lecturer.id == lecturer_id).first()
    )
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(lecturer, field, value)
    db.commit()
    db.refresh(lecturer)
    return lecturer


@router.delete("/lecturers/{lecturer_id}")
def delete_lecturer(
    lecturer_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Delete a lecturer record (their User account is preserved)."""
    lecturer = (
        db.query(models.Lecturer).filter(models.Lecturer.id == lecturer_id).first()
    )
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")
    db.delete(lecturer)
    db.commit()
    return {"message": "Lecturer deleted"}


# ─── LECTURER-COURSE ASSIGNMENTS ─────────────────────────────────────────────


@router.get("/lecturer-courses", response_model=List[schemas.LecturerCourseOut])
def list_lecturer_courses(
    lecturer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """List all lecturer-course assignments, optionally filtered by lecturer."""
    q = db.query(models.LecturerCourse)
    if lecturer_id:
        q = q.filter(models.LecturerCourse.lecturer_id == lecturer_id)
    return q.all()


@router.post("/lecturer-courses", response_model=schemas.LecturerCourseOut, status_code=201)
def assign_lecturer_to_course(
    data: schemas.LecturerCourseCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Assign a lecturer to a course. A lecturer can only be assigned once per course."""
    if not db.query(models.Lecturer).filter(models.Lecturer.id == data.lecturer_id).first():
        raise HTTPException(status_code=404, detail="Lecturer not found")
    if not db.query(models.Course).filter(models.Course.id == data.course_id).first():
        raise HTTPException(status_code=404, detail="Course not found")

    existing = (
        db.query(models.LecturerCourse)
        .filter(
            models.LecturerCourse.lecturer_id == data.lecturer_id,
            models.LecturerCourse.course_id == data.course_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Assignment already exists")

    assignment = models.LecturerCourse(**data.model_dump())
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/lecturer-courses/{assignment_id}")
def remove_lecturer_course(
    assignment_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Remove a lecturer-course assignment."""
    assignment = (
        db.query(models.LecturerCourse)
        .filter(models.LecturerCourse.id == assignment_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assignment)
    db.commit()
    return {"message": "Assignment removed"}


# ─── ROOMS ───────────────────────────────────────────────────────────────────


@router.get("/rooms", response_model=List[schemas.RoomOut])
def get_rooms(room_type: str = None, db: Session = Depends(get_db)):
    """List rooms. Optional filter: room_type (lecture_hall | seminar_room | laboratory)."""
    query = db.query(models.Room)
    if room_type:
        try:
            rt = models.RoomType(room_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid room_type '{room_type}'. "
                       f"Must be one of: lecture_hall, seminar_room, laboratory",
            )
        query = query.filter(models.Room.room_type == rt)
    return query.all()


@router.post("/rooms", response_model=schemas.RoomOut, status_code=201)
def create_room(
    data: schemas.RoomCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Create a room. Name does not need to be unique but should be descriptive."""
    room = models.Room(**data.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.put("/rooms/{room_id}", response_model=schemas.RoomOut)
def update_room(
    room_id: int,
    data: schemas.RoomUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Update a room's name, capacity, or availability flag."""
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(room, field, value)
    db.commit()
    db.refresh(room)
    return room


@router.delete("/rooms/{room_id}")
def delete_room(
    room_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Delete a room."""
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    db.delete(room)
    db.commit()
    return {"message": "Room deleted"}


# ─── TIME SLOTS ──────────────────────────────────────────────────────────────


@router.get("/timeslots", response_model=List[schemas.TimeSlotOut])
def get_timeslots(db: Session = Depends(get_db)):
    """List all time slots sorted by day and start time."""
    return (
        db.query(models.TimeSlot)
        .order_by(models.TimeSlot.day, models.TimeSlot.start_time)
        .all()
    )


@router.post("/timeslots", response_model=schemas.TimeSlotOut, status_code=201)
def create_timeslot(
    data: schemas.TimeSlotCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """
    Create a time slot. The (day, start_time, end_time) combination must be unique.
    Times must be in HH:MM format.
    """
    existing = (
        db.query(models.TimeSlot)
        .filter(
            models.TimeSlot.day == data.day,
            models.TimeSlot.start_time == data.start_time,
            models.TimeSlot.end_time == data.end_time,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"A time slot already exists for {data.day} {data.start_time}–{data.end_time}",
        )
    slot = models.TimeSlot(**data.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


@router.delete("/timeslots/{slot_id}")
def delete_timeslot(
    slot_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Delete a time slot. Fails if any schedule entries reference it."""
    slot = db.query(models.TimeSlot).filter(models.TimeSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    db.delete(slot)
    db.commit()
    return {"message": "Time slot deleted"}
