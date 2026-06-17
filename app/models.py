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
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


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


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    lecturer = relationship("Lecturer", back_populates="user", uselist=False)
    student = relationship("Student", back_populates="user", uselist=False)


class Faculty(Base):
    __tablename__ = "faculties"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False)
    departments = relationship("Department", back_populates="faculty")


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    faculty_id = Column(Integer, ForeignKey("faculties.id"), nullable=False)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False)
    faculty = relationship("Faculty", back_populates="departments")
    courses = relationship("Course", back_populates="department")
    students = relationship("Student", back_populates="department")


class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    course_type = Column(Enum(CourseType), nullable=False)
    hours_per_week = Column(Integer, default=2)
    enrolled_count = Column(Integer, default=0)
    department = relationship("Department", back_populates="courses")
    lecturer_assignments = relationship("LecturerCourse", back_populates="course")
    schedule_entries = relationship("ScheduleEntry", back_populates="course")


class Lecturer(Base):
    __tablename__ = "lecturers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    title = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    user = relationship("User", back_populates="lecturer")
    course_assignments = relationship("LecturerCourse", back_populates="lecturer")
    unavailability = relationship("LecturerUnavailability", back_populates="lecturer")
    schedule_entries = relationship("ScheduleEntry", back_populates="lecturer")


class LecturerCourse(Base):
    __tablename__ = "lecturer_courses"
    id = Column(Integer, primary_key=True, index=True)
    lecturer_id = Column(Integer, ForeignKey("lecturers.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    lecturer = relationship("Lecturer", back_populates="course_assignments")
    course = relationship("Course", back_populates="lecturer_assignments")


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    room_type = Column(Enum(RoomType), nullable=False)
    capacity = Column(Integer, nullable=False)
    is_available = Column(Boolean, default=True)
    schedule_entries = relationship("ScheduleEntry", back_populates="room")


class TimeSlot(Base):
    __tablename__ = "time_slots"
    id = Column(Integer, primary_key=True, index=True)
    day = Column(Enum(Day), nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    unavailability = relationship("LecturerUnavailability", back_populates="time_slot")
    schedule_entries = relationship("ScheduleEntry", back_populates="time_slot")


class LecturerUnavailability(Base):
    __tablename__ = "lecturer_unavailability"
    id = Column(Integer, primary_key=True, index=True)
    lecturer_id = Column(Integer, ForeignKey("lecturers.id"), nullable=False)
    time_slot_id = Column(Integer, ForeignKey("time_slots.id"), nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    lecturer = relationship("Lecturer", back_populates="unavailability")
    time_slot = relationship("TimeSlot", back_populates="unavailability")


class SchedulingRun(Base):
    __tablename__ = "scheduling_runs"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(Enum(SolverStatus), default=SolverStatus.pending)
    solver_status = Column(String, nullable=True)
    objective_value = Column(Float, nullable=True)
    computation_seconds = Column(Float, nullable=True)
    is_published = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    entries = relationship("ScheduleEntry", back_populates="run")


class ScheduleEntry(Base):
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


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    level = Column(Integer, nullable=False)
    matric_number = Column(String, unique=True, nullable=False)
    user = relationship("User", back_populates="student")
    department = relationship("Department", back_populates="students")
