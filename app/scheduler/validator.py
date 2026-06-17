from sqlalchemy.orm import Session
from app import models
from typing import Tuple, List


def validate_manual_adjustment(
    entry_id: int, new_room_id: int, new_slot_id: int, db: Session
) -> Tuple[bool, List[str]]:
    """
    Checks whether moving a schedule entry to a new room + time slot
    would violate any hard constraints.

    Returns:
        (is_valid: bool, violations: list of violation messages)
    """
    violations = []

    entry = (
        db.query(models.ScheduleEntry)
        .filter(models.ScheduleEntry.id == entry_id)
        .first()
    )
    if not entry:
        return False, ["Entry not found"]

    run_id = entry.run_id

    # All OTHER entries in the same run (excluding the one being moved)
    other_entries = (
        db.query(models.ScheduleEntry)
        .filter(
            models.ScheduleEntry.run_id == run_id, models.ScheduleEntry.id != entry_id
        )
        .all()
    )

    # ── CHECK 1: Room not already booked at new slot ──────────────────────────
    room_conflict = any(
        e.room_id == new_room_id and e.time_slot_id == new_slot_id
        for e in other_entries
    )
    if room_conflict:
        room = db.query(models.Room).filter(models.Room.id == new_room_id).first()
        slot = (
            db.query(models.TimeSlot).filter(models.TimeSlot.id == new_slot_id).first()
        )
        violations.append(
            f"Room '{room.name}' is already booked at "
            f"{slot.day} {slot.start_time}–{slot.end_time}"
        )

    # ── CHECK 2: Lecturer not already scheduled at new slot ───────────────────
    lecturer_conflict = any(
        e.lecturer_id == entry.lecturer_id and e.time_slot_id == new_slot_id
        for e in other_entries
    )
    if lecturer_conflict:
        lecturer = (
            db.query(models.Lecturer)
            .filter(models.Lecturer.id == entry.lecturer_id)
            .first()
        )
        slot = (
            db.query(models.TimeSlot).filter(models.TimeSlot.id == new_slot_id).first()
        )
        violations.append(
            f"Lecturer '{lecturer.title} {lecturer.last_name}' already has "
            f"a class at {slot.day} {slot.start_time}–{slot.end_time}"
        )

    # ── CHECK 3: No student group clash ───────────────────────────────────────
    course = db.query(models.Course).filter(models.Course.id == entry.course_id).first()

    student_conflict = any(
        e.time_slot_id == new_slot_id
        and db.query(models.Course)
        .filter(
            models.Course.id == e.course_id,
            models.Course.department_id == course.department_id,
            models.Course.level == course.level,
        )
        .first()
        is not None
        for e in other_entries
    )
    if student_conflict:
        slot = (
            db.query(models.TimeSlot).filter(models.TimeSlot.id == new_slot_id).first()
        )
        violations.append(
            f"Another {course.level}-level {course.department_id} course "
            f"is already scheduled at {slot.day} {slot.start_time}–{slot.end_time}"
        )

    # ── CHECK 4: Room type matches course type ────────────────────────────────
    new_room = db.query(models.Room).filter(models.Room.id == new_room_id).first()
    if (
        course.course_type == models.CourseType.lab
        and new_room.room_type != models.RoomType.laboratory
    ):
        violations.append(
            f"Course '{course.name}' is a lab course but "
            f"'{new_room.name}' is not a laboratory"
        )
    elif (
        course.course_type == models.CourseType.theory
        and new_room.room_type == models.RoomType.laboratory
    ):
        violations.append(
            f"Course '{course.name}' is a theory course and cannot "
            f"be placed in laboratory '{new_room.name}'"
        )

    return len(violations) == 0, violations
