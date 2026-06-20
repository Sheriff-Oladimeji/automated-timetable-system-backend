"""initial_schema

Revision ID: c64030bad7fb
Revises:
Create Date: 2026-06-20

Creates all tables for the CSET Automated Timetable System.

To apply:  alembic upgrade head
To revert: alembic downgrade base
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c64030bad7fb"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "lecturer", "student", name="userrole"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # ── faculties ─────────────────────────────────────────────────────────────
    op.create_table(
        "faculties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False, unique=True),
    )

    # ── departments ───────────────────────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("faculty_id", sa.Integer(), sa.ForeignKey("faculties.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False, unique=True),
    )

    # ── courses ───────────────────────────────────────────────────────────────
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column(
            "course_type",
            sa.Enum("theory", "lab", name="coursetype"),
            nullable=False,
        ),
        sa.Column("hours_per_week", sa.Integer(), default=2),
        sa.Column("enrolled_count", sa.Integer(), default=0),
    )

    # ── rooms ─────────────────────────────────────────────────────────────────
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "room_type",
            sa.Enum("lecture_hall", "seminar_room", "laboratory", name="roomtype"),
            nullable=False,
        ),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("is_available", sa.Boolean(), default=True),
    )

    # ── time_slots ────────────────────────────────────────────────────────────
    op.create_table(
        "time_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "day",
            sa.Enum("monday", "tuesday", "wednesday", "thursday", "friday", name="day"),
            nullable=False,
        ),
        sa.Column("start_time", sa.String(), nullable=False),
        sa.Column("end_time", sa.String(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.UniqueConstraint("day", "start_time", "end_time", name="uq_timeslot"),
    )

    # ── lecturers ────────────────────────────────────────────────────────────
    op.create_table(
        "lecturers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False, unique=True),
    )

    # ── lecturer_courses ──────────────────────────────────────────────────────
    op.create_table(
        "lecturer_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lecturer_id", sa.Integer(), sa.ForeignKey("lecturers.id"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.UniqueConstraint("lecturer_id", "course_id", name="uq_lecturer_course"),
    )

    # ── students ──────────────────────────────────────────────────────────────
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("matric_number", sa.String(), nullable=False, unique=True),
    )

    # ── lecturer_unavailability ───────────────────────────────────────────────
    op.create_table(
        "lecturer_unavailability",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lecturer_id", sa.Integer(), sa.ForeignKey("lecturers.id"), nullable=False),
        sa.Column("time_slot_id", sa.Integer(), sa.ForeignKey("time_slots.id"), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "lecturer_id", "time_slot_id", name="uq_lecturer_unavailability"
        ),
    )

    # ── system_config ─────────────────────────────────────────────────────────
    op.create_table(
        "system_config",
        sa.Column("id", sa.Integer(), primary_key=True, default=1),
        sa.Column("unavailability_penalty", sa.Integer(), default=100, nullable=False),
        sa.Column("back_to_back_penalty", sa.Integer(), default=10, nullable=False),
        sa.Column("spread_sessions_penalty", sa.Integer(), default=5, nullable=False),
        sa.Column("room_capacity_penalty", sa.Integer(), default=20, nullable=False),
        sa.Column("time_limit_seconds", sa.Integer(), default=60, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── scheduling_runs ───────────────────────────────────────────────────────
    op.create_table(
        "scheduling_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "optimal", "feasible", "infeasible", "failed",
                name="solverstatus",
            ),
            default="pending",
        ),
        sa.Column("solver_status", sa.String(), nullable=True),
        sa.Column("objective_value", sa.Float(), nullable=True),
        sa.Column("computation_seconds", sa.Float(), nullable=True),
        sa.Column("is_published", sa.Boolean(), default=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # ── schedule_entries ──────────────────────────────────────────────────────
    op.create_table(
        "schedule_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("scheduling_runs.id"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("lecturer_id", sa.Integer(), sa.ForeignKey("lecturers.id"), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("time_slot_id", sa.Integer(), sa.ForeignKey("time_slots.id"), nullable=False),
        sa.Column("is_manually_adjusted", sa.Boolean(), default=False),
    )


def downgrade() -> None:
    op.drop_table("schedule_entries")
    op.drop_table("scheduling_runs")
    op.drop_table("system_config")
    op.drop_table("lecturer_unavailability")
    op.drop_table("students")
    op.drop_table("lecturer_courses")
    op.drop_table("lecturers")
    op.drop_table("time_slots")
    op.drop_table("rooms")
    op.drop_table("courses")
    op.drop_table("departments")
    op.drop_table("faculties")
    op.drop_table("users")

    # Drop all custom enum types
    for enum_name in ("userrole", "coursetype", "roomtype", "day", "solverstatus"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
