"""
Main solver orchestration for the CSET timetable scheduling system.

Called as a BackgroundTask from the scheduler router.
Flow:
  1. Fetch all resources from the database
  2. Build the CP-SAT model (app/scheduler/model.py)
  3. Run the solver with a configurable time limit
  4. Persist results (or failure reason) back to SchedulingRun + ScheduleEntry rows

The function updates run.status throughout so the frontend polling /status/{run_id}
gets accurate progress information.
"""

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session
from app import models
from app.scheduler.model import build_model
import time


def run_solver(run_id: int, db: Session, config: dict) -> None:
    """
    Execute the CP-SAT solver for a scheduling run and persist the results.

    Args:
        run_id: Primary key of the SchedulingRun row to update.
        db:     Database session (caller is responsible for closing it).
        config: Flat dict matching ConstraintConfig field names — penalty weights
                and time_limit_seconds.
    """
    run = db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
    if not run:
        return

    run.status = models.SolverStatus.running
    db.commit()

    try:
        # ── FETCH ALL DATA FROM DB ────────────────────────────────────────────
        courses_db = db.query(models.Course).all()
        rooms_db = db.query(models.Room).filter(models.Room.is_available == True).all()
        time_slots_db = db.query(models.TimeSlot).all()
        unavailability_db = db.query(models.LecturerUnavailability).all()
        lecturer_courses_db = db.query(models.LecturerCourse).all()

        # Map course_id → lecturer_id (first assignment wins when multiple lecturers
        # are assigned to the same course — this is a known limitation; see README)
        course_lecturer_map: dict[int, int] = {}
        for lc in lecturer_courses_db:
            if lc.course_id not in course_lecturer_map:
                course_lecturer_map[lc.course_id] = lc.lecturer_id

        # Build the course list, skipping any course with no lecturer assigned
        courses = []
        skipped_courses = []
        for c in courses_db:
            lecturer_id = course_lecturer_map.get(c.id)
            if lecturer_id is None:
                skipped_courses.append(f"{c.code} ({c.name})")
                continue
            courses.append(
                {
                    "id": c.id,
                    "course_type": c.course_type.value,
                    "hours_per_week": c.hours_per_week,
                    "enrolled_count": c.enrolled_count,
                    "department_id": c.department_id,
                    "level": c.level,
                    "lecturer_id": lecturer_id,
                }
            )

        rooms = [
            {"id": r.id, "room_type": r.room_type.value, "capacity": r.capacity}
            for r in rooms_db
        ]

        time_slots = [
            {"id": s.id, "day": s.day.value, "start_time": s.start_time}
            for s in time_slots_db
        ]

        unavailability = {
            (u.lecturer_id, u.time_slot_id) for u in unavailability_db
        }

        if not courses:
            run.status = models.SolverStatus.failed
            run.notes = (
                "No courses with assigned lecturers found. "
                "Assign at least one lecturer to each course before running the scheduler."
            )
            db.commit()
            return

        if not rooms:
            run.status = models.SolverStatus.failed
            run.notes = "No available rooms found. Mark at least one room as available."
            db.commit()
            return

        if not time_slots:
            run.status = models.SolverStatus.failed
            run.notes = "No time slots defined. Create time slots before running the scheduler."
            db.commit()
            return

        data = {
            "courses": courses,
            "rooms": rooms,
            "time_slots": time_slots,
            "unavailability": unavailability,
        }

        # Record any skipped courses in the run notes for transparency
        skip_note = ""
        if skipped_courses:
            skip_note = (
                f"Skipped {len(skipped_courses)} course(s) with no lecturer assigned: "
                + ", ".join(skipped_courses)
                + ". "
            )

        # ── BUILD MODEL ───────────────────────────────────────────────────────
        model, x, course_sessions = build_model(data, config)

        # ── RUN SOLVER ────────────────────────────────────────────────────────
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = config.get("time_limit_seconds", 60)
        solver.parameters.log_search_progress = False

        start_time = time.time()
        status = solver.solve(model)
        elapsed = time.time() - start_time

        status_map = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.UNKNOWN: "UNKNOWN",
        }
        solver_status_str = status_map.get(status, "UNKNOWN")

        # ── HANDLE INFEASIBLE / UNKNOWN ───────────────────────────────────────
        if status in [cp_model.INFEASIBLE, cp_model.UNKNOWN]:
            run.status = models.SolverStatus.infeasible
            run.solver_status = solver_status_str
            run.computation_seconds = elapsed
            run.notes = (
                skip_note
                + "The solver could not find a valid timetable. "
                + "Check that there are enough rooms, time slots, and that hard "
                + "constraints are satisfiable (e.g. not too many unavailability records)."
            )
            db.commit()
            return

        # ── SAVE RESULTS ──────────────────────────────────────────────────────
        entries_to_add = []
        for s_idx, session in enumerate(course_sessions):
            for room in rooms:
                for slot in time_slots:
                    if solver.value(x[(s_idx, room["id"], slot["id"])]) == 1:
                        entries_to_add.append(
                            models.ScheduleEntry(
                                run_id=run_id,
                                course_id=session["course_id"],
                                lecturer_id=session["lecturer_id"],
                                room_id=room["id"],
                                time_slot_id=slot["id"],
                            )
                        )

        db.bulk_save_objects(entries_to_add)

        run.status = (
            models.SolverStatus.optimal
            if status == cp_model.OPTIMAL
            else models.SolverStatus.feasible
        )
        run.solver_status = solver_status_str
        run.objective_value = solver.objective_value
        run.computation_seconds = elapsed
        run.notes = skip_note if skip_note else None
        db.commit()

    except Exception as exc:
        # Roll back any partial ScheduleEntry inserts before marking as failed
        db.rollback()
        run = db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
        if run:
            run.status = models.SolverStatus.failed
            run.notes = f"Unexpected error: {exc}"
            db.commit()
        raise
