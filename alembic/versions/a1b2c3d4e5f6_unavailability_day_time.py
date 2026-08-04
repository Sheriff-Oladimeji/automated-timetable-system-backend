"""unavailability_day_time

Revision ID: a1b2c3d4e5f6
Revises: c64030bad7fb
Create Date: 2026-08-04

Replace time_slot_id FK in lecturer_unavailability with
day + start_time + end_time so lecturers define their own windows.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c64030bad7fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clear existing records — they reference old time_slot_id FK
    op.execute("DELETE FROM lecturer_unavailability")

    # Drop old unique constraint and FK
    op.drop_constraint("uq_lecturer_unavailability", "lecturer_unavailability", type_="unique")
    op.drop_constraint(
        "lecturer_unavailability_time_slot_id_fkey",
        "lecturer_unavailability",
        type_="foreignkey",
    )
    op.drop_column("lecturer_unavailability", "time_slot_id")

    # Add new columns
    op.add_column("lecturer_unavailability", sa.Column("day", sa.String(), nullable=False, server_default="monday"))
    op.add_column("lecturer_unavailability", sa.Column("start_time", sa.String(), nullable=False, server_default="08:00"))
    op.add_column("lecturer_unavailability", sa.Column("end_time", sa.String(), nullable=False, server_default="09:00"))

    # Remove server defaults (only needed during column add)
    op.alter_column("lecturer_unavailability", "day", server_default=None)
    op.alter_column("lecturer_unavailability", "start_time", server_default=None)
    op.alter_column("lecturer_unavailability", "end_time", server_default=None)

    # New unique constraint: one window per lecturer per day+start
    op.create_unique_constraint(
        "uq_lecturer_unavailability",
        "lecturer_unavailability",
        ["lecturer_id", "day", "start_time"],
    )


def downgrade() -> None:
    op.execute("DELETE FROM lecturer_unavailability")

    op.drop_constraint("uq_lecturer_unavailability", "lecturer_unavailability", type_="unique")
    op.drop_column("lecturer_unavailability", "end_time")
    op.drop_column("lecturer_unavailability", "start_time")
    op.drop_column("lecturer_unavailability", "day")

    op.add_column("lecturer_unavailability", sa.Column("time_slot_id", sa.Integer(), nullable=False))
    op.create_foreign_key(
        "lecturer_unavailability_time_slot_id_fkey",
        "lecturer_unavailability",
        "time_slots",
        ["time_slot_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_lecturer_unavailability",
        "lecturer_unavailability",
        ["lecturer_id", "time_slot_id"],
    )
