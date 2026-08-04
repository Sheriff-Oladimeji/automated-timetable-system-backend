"""
Solver orchestration for the CSET timetable scheduling system.

Flow:
  1. Load all resources from the database
  2. Pre-validate that a feasible schedule is possible (fast checks before the solver)
  3. Build the CP-SAT model
  4. Run the solver
  5. Persist results (or failure reason) back to the database

run.status is updated throughout so the frontend polling /status/{run_id}
gets accurate progress information at each stage.
"""

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session
from app import models
from app.scheduler.model import build_model
import time
import math


def _sessions_needed(hours_per_week: int) -> int:
    """Number of class-period slots a course needs (1 session = 2 contact hours)."""
    return max(1, math.ceil(hours_per_week / 2))


# ─── PRE-VALIDATION ──────────────────────────────────────────────────────────

def _validate_feasibility(courses, rooms, time_slots, unavailability):
    """
    Run fast feasibility checks before handing off to the CP-SAT solver.
    Returns a list of human-readable error strings (empty = all good).
    """
    errors = []

    session_breakdown = {c["code"]: _sessions_needed(c["hours_per_week"]) for c in courses}
    total_sessions = sum(session_breakdown.values())
    if total_sessions > len(time_slots):
        breakdown_str = ", ".join(f"{code}: {n}" for code, n in session_breakdown.items())
        errors.append(
            f"Not enough time slots: need {total_sessions} class periods "
            f"({breakdown_str}) but only {len(time_slots)} time slot(s) defined. "
            f"Each time slot is one class period — add {total_sessions - len(time_slots)} more."
        )

    lab_rooms = [r for r in rooms if r["room_type"] == "laboratory"]
    theory_rooms = [r for r in rooms if r["room_type"] != "laboratory"]

    for c in courses:
        is_lab = c["course_type"] == "lab"
        compatible_rooms = lab_rooms if is_lab else theory_rooms

        # Check room type availability
        if not compatible_rooms:
            room_kind = "laboratory" if is_lab else "non-laboratory (lecture hall or seminar)"
            errors.append(
                f"Course '{c.get('code', c['id'])}' is a {'lab' if is_lab else 'theory'} course "
                f"but no {room_kind} rooms exist. Add the right room type."
            )
            continue

        # Check room capacity
        enrolled = c["enrolled_count"]
        if enrolled > 0:
            fitting_rooms = [r for r in compatible_rooms if r["capacity"] >= enrolled]
            if not fitting_rooms:
                best = max(compatible_rooms, key=lambda r: r["capacity"])
                errors.append(
                    f"Course '{c.get('code', c['id'])}' has {enrolled} students "
                    f"but the largest compatible room holds only {best['capacity']}. "
                    f"Add a larger room or reduce enrolled count."
                )

        # Check if lecturer has enough available slots for their sessions needed
        lid = c["lecturer_id"]
        blocked = sum(
            1 for slot in time_slots
            if any(
                u["lecturer_id"] == lid
                and u["day"] == slot["day"]
                and u["start_time"] <= slot["start_time"] < u["end_time"]
                for u in unavailability
            )
        )
        available_slots = len(time_slots) - blocked
        sessions_needed = _sessions_needed(c["hours_per_week"])
        if available_slots < sessions_needed:
            errors.append(
                f"Course '{c.get('code', c['id'])}': lecturer has only {available_slots} "
                f"available slot(s) but needs {sessions_needed} session(s). "
                f"Reduce unavailability records or add more time slots."
            )

    return errors


# ─── MAIN SOLVER ─────────────────────────────────────────────────────────────

def run_solver(run_id: int, db: Session, config: dict) -> None:
    """
    Execute the CP-SAT solver for a scheduling run and persist the results.

    Args:
        run_id: Primary key of the SchedulingRun row to update.
        db:     Database session (caller is responsible for closing it).
        config: Flat dict of penalty weights and time_limit_seconds.
    """
    run = db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
    if not run:
        return

    run.status = models.SolverStatus.running
    db.commit()

    try:
        # ── 1. FETCH DATA ─────────────────────────────────────────────────────
        courses_db      = db.query(models.Course).all()
        rooms_db        = db.query(models.Room).filter(models.Room.is_available == True).all()
        time_slots_db   = db.query(models.TimeSlot).all()
        unavail_db      = db.query(models.LecturerUnavailability).all()
        lc_db           = db.query(models.LecturerCourse).all()

        # Build course → lecturer map (first assignment wins)
        course_lecturer: dict[int, int] = {}
        for lc in lc_db:
            if lc.course_id not in course_lecturer:
                course_lecturer[lc.course_id] = lc.lecturer_id

        courses, skipped = [], []
        for c in courses_db:
            lid = course_lecturer.get(c.id)
            if lid is None:
                skipped.append(f"{c.code} ({c.name})")
                continue
            courses.append({
                "id":            c.id,
                "code":          c.code,
                "course_type":   c.course_type.value,
                "hours_per_week": c.hours_per_week,
                "enrolled_count": c.enrolled_count,
                "department_id": c.department_id,
                "level":         c.level,
                "lecturer_id":   lid,
            })

        rooms = [
            {"id": r.id, "room_type": r.room_type.value, "capacity": r.capacity}
            for r in rooms_db
        ]
        time_slots = [
            {"id": s.id, "day": s.day.value, "start_time": s.start_time}
            for s in time_slots_db
        ]
        unavailability = [
            {"lecturer_id": u.lecturer_id, "day": u.day, "start_time": u.start_time, "end_time": u.end_time}
            for u in unavail_db
        ]

        skip_note = (
            f"Skipped {len(skipped)} course(s) with no lecturer assigned: "
            + ", ".join(skipped) + ". "
        ) if skipped else ""

        # ── 2. BASIC PRESENCE CHECKS ──────────────────────────────────────────
        if not courses:
            _fail(run, db, skip_note +
                  "No courses with assigned lecturers. Assign at least one lecturer per course.")
            return
        if not rooms:
            _fail(run, db, "No available rooms. Mark at least one room as available.")
            return
        if not time_slots:
            _fail(run, db, "No time slots defined. Add time slots before scheduling.")
            return

        # ── 3. FEASIBILITY PRE-CHECKS ─────────────────────────────────────────
        pre_errors = _validate_feasibility(courses, rooms, time_slots, unavailability)
        if pre_errors:
            _fail(run, db, skip_note + "Cannot produce a valid timetable:\n• " +
                  "\n• ".join(pre_errors))
            return

        data = {
            "courses":        courses,
            "rooms":          rooms,
            "time_slots":     time_slots,
            "unavailability": unavailability,
        }

        # ── 4. BUILD MODEL ────────────────────────────────────────────────────
        model, x, course_sessions = build_model(data, config)

        # ── 5. RUN SOLVER ─────────────────────────────────────────────────────
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = config.get("time_limit_seconds", 60)
        solver.parameters.log_search_progress = False
        solver.parameters.num_workers = 4  # use multiple cores when available

        t0 = time.time()
        status = solver.solve(model)
        elapsed = time.time() - t0

        STATUS_MAP = {
            cp_model.OPTIMAL:    "OPTIMAL",
            cp_model.FEASIBLE:   "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.UNKNOWN:    "UNKNOWN",
        }
        status_str = STATUS_MAP.get(status, "UNKNOWN")

        # ── 6. HANDLE INFEASIBLE / TIMEOUT ────────────────────────────────────
        if status in (cp_model.INFEASIBLE, cp_model.UNKNOWN):
            hint = (
                "The solver could not find a valid timetable within the time limit. "
                "Try: (1) adding more time slots, (2) reducing unavailability records, "
                "(3) adding more/larger rooms, or (4) increasing the solver time limit."
            ) if status == cp_model.UNKNOWN else (
                "The constraint set is provably infeasible. "
                "Check: (1) every course has a compatible room (type + capacity), "
                "(2) lecturers are not marked unavailable for all slots, "
                "(3) there are enough time slots for all sessions."
            )
            run.status = models.SolverStatus.infeasible
            run.solver_status = status_str
            run.computation_seconds = elapsed
            run.notes = skip_note + hint
            db.commit()
            return

        # ── 7. PERSIST SCHEDULE ENTRIES ───────────────────────────────────────
        entries = []
        for s_idx, session in enumerate(course_sessions):
            for room in rooms:
                for slot in time_slots:
                    if solver.value(x[(s_idx, room["id"], slot["id"])]) == 1:
                        entries.append(models.ScheduleEntry(
                            run_id=run_id,
                            course_id=session["course_id"],
                            lecturer_id=session["lecturer_id"],
                            room_id=room["id"],
                            time_slot_id=slot["id"],
                        ))

        db.bulk_save_objects(entries)

        run.status = (
            models.SolverStatus.optimal
            if status == cp_model.OPTIMAL
            else models.SolverStatus.feasible
        )
        run.solver_status = status_str
        run.objective_value = solver.objective_value
        run.computation_seconds = elapsed
        run.notes = skip_note or None
        db.commit()

    except Exception as exc:
        db.rollback()
        run = db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
        if run:
            run.status = models.SolverStatus.failed
            run.notes = f"Unexpected error: {exc}"
            db.commit()
        raise


def _fail(run: models.SchedulingRun, db: Session, message: str) -> None:
    """Mark a run as failed with a clear reason and commit."""
    run.status = models.SolverStatus.failed
    run.notes = message
    db.commit()
