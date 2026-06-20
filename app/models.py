"""
SQLAlchemy ORM models for the CSET timetable scheduling system.

Table relationships at a glance:
  Faculty → Department → Course ← LecturerCourse → Lecturer
  Lecturer ← LecturerUnavailability → TimeSlot
  SchedulingRun → ScheduleEntry ← Course / Lecturer / Room / TimeSlot
  User 1:1 Lecturer | User 1:1 Student
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    Enum,
    DateTime,
    Float,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


# ─── ENUMS ───────────────────────────────────────────────────────────────────


class UserRole(str, enum.Enum):
    admin = "admin"
    lecturer = "lecturer"
    student = "student"


class CourseType(str, enum.Enum):
    theory = "theory"
    lab = "lab"


class RoomType(str, enum.Enum):
    lecture_hall = "lecture_hall"
    seminar_room = "seminar_room"
    laboratory = "laboratory"


class SolverStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    optimal = "optimal"
    feasible = "feasible"
    infeasible = "infeasible"
    failed = "failed"


class Day(str, enum.Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"


# ─── USERS ───────────────────────────────────────────────────────────────────


class User(Base):
    """Login identity. One per real person; role determines access level."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lecturer = relationship("Lecturer", back_populates="user", uselist=False)
    student = relationship("Student", back_populates="user", uselist=False)


# ─── ACADEMIC STRUCTURE ──────────────────────────────────────────────────────


class Faculty(Base):
    """Top-level academic grouping (e.g. Faculty of Computing)."""

    __tablename__ = "faculties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False)

    departments = relationship("Department", back_populates="faculty")


class Department(Base):
    """Sub-unit of a Faculty (e.g. Dept. of Computer Science)."""

    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    faculty_id = Column(Integer, ForeignKey("faculties.id"), nullable=False)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False)

    faculty = relationship("Faculty", back_populates="departments")
    courses = relationship("Course", back_populates="department")
    students = relationship("Student", back_populates="department")


class Course(Base):
    """
    A module offered by a department.
    hours_per_week drives how many sessions the solver must schedule each week.
    enrolled_count is used to enforce the room-capacity soft constraint.
    """

    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    level = Column(Integer, nullable=False)  # e.g. 100, 200, 300, 400
    course_type = Column(Enum(CourseType), nullable=False)
    hours_per_week = Column(Integer, default=2)
    enrolled_count = Column(Integer, default=0)

    department = relationship("Department", back_populates="courses")
    lecturer_assignments = relationship("LecturerCourse", back_populates="course")
    schedule_entries = relationship("ScheduleEntry", back_populates="course")


# ─── LECTURERS ───────────────────────────────────────────────────────────────


class Lecturer(Base):
    """
    A teaching staff member. May or may not have a User account (user_id nullable
    allows importing lecturers before their accounts are created).
    """

    __tablename__ = "lecturers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    title = Column(String, nullable=False)  # Dr., Prof., Mr., etc.
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)

    user = relationship("User", back_populates="lecturer")
    course_assignments = relationship("LecturerCourse", back_populates="lecturer")
    unavailability = relationship("LecturerUnavailability", back_populates="lecturer")
    schedule_entries = relationship("ScheduleEntry", back_populates="lecturer")


class LecturerCourse(Base):
    """
    Many-to-many bridge between Lecturer and Course.
    When multiple lecturers are assigned to one course the solver uses the first one;
    subsequent assignments are stored for administrative reference.
    """

    __tablename__ = "lecturer_courses"
    __table_args__ = (
        # Prevent the same lecturer being assigned to the same course twice
        UniqueConstraint("lecturer_id", "course_id", name="uq_lecturer_course"),
    )

    id = Column(Integer, primary_key=True, index=True)
    lecturer_id = Column(Integer, ForeignKey("lecturers.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    lecturer = relationship("Lecturer", back_populates="course_assignments")
    course = relationship("Course", back_populates="lecturer_assignments")


# ─── ROOMS & TIME SLOTS ──────────────────────────────────────────────────────


class Room(Base):
    """
    A physical space that can be scheduled.
    room_type enforces the lab↔laboratory / theory↔non-lab matching constraint.
    """

    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    room_type = Column(Enum(RoomType), nullable=False)
    capacity = Column(Integer, nullable=False)
    is_available = Column(Boolean, default=True)

    schedule_entries = relationship("ScheduleEntry", back_populates="room")


class TimeSlot(Base):
    """
    A schedulable period in the week.
    start_time / end_time are stored as "HH:MM" strings (validated at API layer).
    The unique constraint prevents duplicate slots for the same day + time window.
    """

    __tablename__ = "time_slots"
    __table_args__ = (
        UniqueConstraint("day", "start_time", "end_time", name="uq_timeslot"),
    )

    id = Column(Integer, primary_key=True, index=True)
    day = Column(Enum(Day), nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)

    unavailability = relationship("LecturerUnavailability", back_populates="time_slot")
    schedule_entries = relationship("ScheduleEntry", back_populates="time_slot")


# ─── CONSTRAINTS ─────────────────────────────────────────────────────────────


class LecturerUnavailability(Base):
    """Records a time slot when a lecturer cannot be scheduled."""

    __tablename__ = "lecturer_unavailability"
    __table_args__ = (
        UniqueConstraint(
            "lecturer_id", "time_slot_id", name="uq_lecturer_unavailability"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    lecturer_id = Column(Integer, ForeignKey("lecturers.id"), nullable=False)
    time_slot_id = Column(Integer, ForeignKey("time_slots.id"), nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lecturer = relationship("Lecturer", back_populates="unavailability")
    time_slot = relationship("TimeSlot", back_populates="unavailability")


class SystemConfig(Base):
    """
    Singleton table (always id=1) that persists the solver's soft-constraint
    penalty weights across server restarts.
    Use get_or_create_config(db) to read and upsert_config(db, data) to write.
    """

    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, default=1)
    unavailability_penalty = Column(Integer, default=100, nullable=False)
    back_to_back_penalty = Column(Integer, default=10, nullable=False)
    spread_sessions_penalty = Column(Integer, default=5, nullable=False)
    room_capacity_penalty = Column(Integer, default=20, nullable=False)
    time_limit_seconds = Column(Integer, default=60, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ─── SCHEDULING ──────────────────────────────────────────────────────────────


class SchedulingRun(Base):
    """
    One complete attempt by the CP-SAT solver to produce a timetable.
    Frontend polls status until it reaches optimal / feasible / infeasible / failed.
    Only one run may be published at a time (enforced in the publish endpoint).
    """

    __tablename__ = "scheduling_runs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(Enum(SolverStatus), default=SolverStatus.pending)
    solver_status = Column(String, nullable=True)   # raw OR-Tools status string
    objective_value = Column(Float, nullable=True)  # weighted penalty total
    computation_seconds = Column(Float, nullable=True)
    is_published = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)  # error message on failure

    entries = relationship("ScheduleEntry", back_populates="run")


class ScheduleEntry(Base):
    """
    One session assignment produced by (or manually adjusted after) a scheduling run.
    course + lecturer → who and what; room + time_slot → where and when.
    """

    __tablename__ = "schedule_entries"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("scheduling_runs.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    lecturer_id = Column(Integer, ForeignKey("lecturers.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    time_slot_id = Column(Integer, ForeignKey("time_slots.id"), nullable=False)
    is_manually_adjusted = Column(Boolean, default=False)

    run = relationship("SchedulingRun", back_populates="entries")
    course = relationship("Course", back_populates="schedule_entries")
    lecturer = relationship("Lecturer", back_populates="schedule_entries")
    room = relationship("Room", back_populates="schedule_entries")
    time_slot = relationship("TimeSlot", back_populates="schedule_entries")


# ─── STUDENTS ────────────────────────────────────────────────────────────────


class Student(Base):
    """
    A registered student. The (department_id, level) pair defines their cohort —
    all students in the same cohort see the same timetable entries.
    """

    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    level = Column(Integer, nullable=False)
    matric_number = Column(String, unique=True, nullable=False)

    user = relationship("User", back_populates="student")
    department = relationship("Department", back_populates="students")
