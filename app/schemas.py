from pydantic import BaseModel, EmailStr
from typing import Optional, List
from enum import Enum
from datetime import datetime


# ─── ENUMS ───────────────────────────────────────────────────────────────────


class UserRole(str, Enum):
    admin = "admin"
    lecturer = "lecturer"
    student = "student"


class CourseType(str, Enum):
    theory = "theory"
    lab = "lab"


class RoomType(str, Enum):
    lecture_hall = "lecture_hall"
    seminar_room = "seminar_room"
    laboratory = "laboratory"


class SolverStatus(str, Enum):
    pending = "pending"
    running = "running"
    optimal = "optimal"
    feasible = "feasible"
    infeasible = "infeasible"
    failed = "failed"


class Day(str, Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"


# ─── AUTH ────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    role: UserRole


class UserOut(BaseModel):
    id: int
    email: str
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True


# ─── FACULTY ─────────────────────────────────────────────────────────────────


class FacultyCreate(BaseModel):
    name: str
    code: str


class FacultyOut(BaseModel):
    id: int
    name: str
    code: str

    class Config:
        from_attributes = True


# ─── DEPARTMENT ──────────────────────────────────────────────────────────────


class DepartmentCreate(BaseModel):
    faculty_id: int
    name: str
    code: str


class DepartmentOut(BaseModel):
    id: int
    faculty_id: int
    name: str
    code: str

    class Config:
        from_attributes = True


# ─── COURSE ──────────────────────────────────────────────────────────────────


class CourseCreate(BaseModel):
    department_id: int
    code: str
    name: str
    level: int
    course_type: CourseType
    hours_per_week: int = 2
    enrolled_count: int = 0


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    hours_per_week: Optional[int] = None
    enrolled_count: Optional[int] = None


class CourseOut(BaseModel):
    id: int
    department_id: int
    code: str
    name: str
    level: int
    course_type: CourseType
    hours_per_week: int
    enrolled_count: int

    class Config:
        from_attributes = True


# ─── LECTURER ────────────────────────────────────────────────────────────────


class LecturerCreate(BaseModel):
    department_id: int
    title: str
    first_name: str
    last_name: str
    email: EmailStr


class LecturerUpdate(BaseModel):
    title: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class LecturerOut(BaseModel):
    id: int
    department_id: int
    title: str
    first_name: str
    last_name: str
    email: str

    class Config:
        from_attributes = True


class LecturerCourseCreate(BaseModel):
    lecturer_id: int
    course_id: int


class LecturerCourseOut(BaseModel):
    id: int
    lecturer_id: int
    course_id: int

    class Config:
        from_attributes = True


# ─── ROOM ────────────────────────────────────────────────────────────────────


class RoomCreate(BaseModel):
    name: str
    room_type: RoomType
    capacity: int


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    is_available: Optional[bool] = None


class RoomOut(BaseModel):
    id: int
    name: str
    room_type: RoomType
    capacity: int
    is_available: bool

    class Config:
        from_attributes = True


# ─── TIME SLOT ───────────────────────────────────────────────────────────────


class TimeSlotCreate(BaseModel):
    day: Day
    start_time: str
    end_time: str
    duration_minutes: int


class TimeSlotOut(BaseModel):
    id: int
    day: Day
    start_time: str
    end_time: str
    duration_minutes: int

    class Config:
        from_attributes = True


# ─── CONSTRAINTS ─────────────────────────────────────────────────────────────


class UnavailabilityCreate(BaseModel):
    lecturer_id: int
    time_slot_id: int
    reason: Optional[str] = None


class UnavailabilityOut(BaseModel):
    id: int
    lecturer_id: int
    time_slot_id: int
    reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ConstraintConfig(BaseModel):
    """Soft constraint penalty weights — admin configures before each run"""

    unavailability_penalty: int = 100
    back_to_back_penalty: int = 10
    spread_sessions_penalty: int = 5
    room_capacity_penalty: int = 20
    time_limit_seconds: int = 60  # max time solver is allowed to run


# ─── SCHEDULER ───────────────────────────────────────────────────────────────


class SchedulerRunOut(BaseModel):
    id: int
    created_at: datetime
    status: SolverStatus
    solver_status: Optional[str]
    objective_value: Optional[float]
    computation_seconds: Optional[float]
    is_published: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


# ─── SCHEDULE ENTRY ──────────────────────────────────────────────────────────


class ScheduleEntryOut(BaseModel):
    id: int
    run_id: int
    course_id: int
    lecturer_id: int
    room_id: int
    time_slot_id: int
    is_manually_adjusted: bool

    course: CourseOut
    lecturer: LecturerOut
    room: RoomOut
    time_slot: TimeSlotOut

    class Config:
        from_attributes = True


class ManualAdjustRequest(BaseModel):
    """Admin moves a session to a different room and/or time slot"""

    room_id: int
    time_slot_id: int


# ─── STUDENT ─────────────────────────────────────────────────────────────────


class StudentCreate(BaseModel):
    department_id: int
    level: int
    matric_number: str


class StudentOut(BaseModel):
    id: int
    department_id: int
    level: int
    matric_number: str

    class Config:
        from_attributes = True
