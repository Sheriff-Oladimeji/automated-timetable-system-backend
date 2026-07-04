"""
Pydantic request/response schemas for the CSET timetable API.

Naming convention:
  <Entity>Create  — request body for POST (creation)
  <Entity>Update  — request body for PUT (partial update, all fields optional)
  <Entity>Out     — response body (always includes id, safe to serialize)
"""

import re
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional
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


_MATRIC_RE = re.compile(r"^\d{4}/\d{5}$")


class StudentRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    matric_number: str
    department_id: int
    level: int

    @field_validator("matric_number")
    @classmethod
    def matric_format(cls, v: str) -> str:
        if not _MATRIC_RE.match(v):
            raise ValueError("Matric number must be in the format YYYY/NNNNN (e.g. 2020/15210)")
        return v

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v: int) -> int:
        if v not in (100, 200, 300, 400, 500, 600, 700):
            raise ValueError("level must be one of 100, 200, 300, 400, 500, 600, 700")
        return v


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

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v: int) -> int:
        if v not in (100, 200, 300, 400, 500, 600, 700):
            raise ValueError("level must be one of 100, 200, 300, 400, 500, 600, 700")
        return v

    @field_validator("hours_per_week")
    @classmethod
    def hours_positive(cls, v: int) -> int:
        if v < 1 or v > 20:
            raise ValueError("hours_per_week must be between 1 and 20")
        return v

    @field_validator("enrolled_count")
    @classmethod
    def enrolled_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("enrolled_count cannot be negative")
        return v


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    hours_per_week: Optional[int] = None
    enrolled_count: Optional[int] = None

    @field_validator("hours_per_week")
    @classmethod
    def hours_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 20):
            raise ValueError("hours_per_week must be between 1 and 20")
        return v

    @field_validator("enrolled_count")
    @classmethod
    def enrolled_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("enrolled_count cannot be negative")
        return v


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

    @field_validator("capacity")
    @classmethod
    def capacity_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("capacity must be at least 1")
        return v


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    is_available: Optional[bool] = None

    @field_validator("capacity")
    @classmethod
    def capacity_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("capacity must be at least 1")
        return v


class RoomOut(BaseModel):
    id: int
    name: str
    room_type: RoomType
    capacity: int
    is_available: bool

    class Config:
        from_attributes = True


# ─── TIME SLOT ───────────────────────────────────────────────────────────────

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _validate_time_str(value: str, field_name: str) -> str:
    """Ensure value is a valid HH:MM time string (00:00–23:59)."""
    if not _TIME_RE.match(value):
        raise ValueError(f"{field_name} must be in HH:MM format (e.g. '08:00')")
    h, m = int(value[:2]), int(value[3:])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"{field_name} is not a valid time (got '{value}')")
    return value


class TimeSlotCreate(BaseModel):
    day: Day
    start_time: str
    end_time: str
    duration_minutes: int

    @field_validator("start_time")
    @classmethod
    def validate_start(cls, v: str) -> str:
        return _validate_time_str(v, "start_time")

    @field_validator("end_time")
    @classmethod
    def validate_end(cls, v: str) -> str:
        return _validate_time_str(v, "end_time")

    @model_validator(mode="after")
    def end_after_start(self) -> "TimeSlotCreate":
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self

    @field_validator("duration_minutes")
    @classmethod
    def duration_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("duration_minutes must be at least 1")
        return v


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
    """
    Soft-constraint penalty weights used by the CP-SAT solver.

    Higher values make the solver try harder to avoid the corresponding violation.
    Weights are relative to each other — doubling all weights has no effect.

    Fields:
        unavailability_penalty  — penalty per session placed in a lecturer's unavailable slot
        back_to_back_penalty    — penalty per consecutive same-group session pair on same day
        spread_sessions_penalty — penalty when two sessions of the same course fall on the same day
        room_capacity_penalty   — penalty per session placed in an undersized room
        time_limit_seconds      — hard ceiling on solver wall-clock time
    """

    unavailability_penalty: int = 100
    back_to_back_penalty: int = 10
    spread_sessions_penalty: int = 5
    room_capacity_penalty: int = 20
    time_limit_seconds: int = 60

    class Config:
        from_attributes = True  # allows ORM → schema conversion


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
    """Full schedule entry with all related objects eagerly loaded."""

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
    """Admin moves a session to a different room and/or time slot."""

    room_id: int
    time_slot_id: int


# ─── STUDENT ─────────────────────────────────────────────────────────────────


class StudentCreate(BaseModel):
    department_id: int
    level: int
    matric_number: str

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v: int) -> int:
        if v not in (100, 200, 300, 400, 500, 600, 700):
            raise ValueError("level must be one of 100, 200, 300, 400, 500, 600, 700")
        return v


class StudentOut(BaseModel):
    id: int
    department_id: int
    level: int
    matric_number: str

    class Config:
        from_attributes = True
