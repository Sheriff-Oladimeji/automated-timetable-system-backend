from ortools.sat.python import cp_model
from sqlalchemy.orm import Session
from app import models
from app.scheduler.model import build_model
import time


def run_solver(run_id: int, db: Session, config: dict):
    """
    Main solver function. Called as a background task.
    Fetches all data from DB, runs CP-SAT, saves results.
    """
    run = (
        db.query(models.SchedulingRun).filter(models.SchedulingRun.id == run_id).first()
    )

    if not run:
        return

    # Mark as running
    run.status = models.SolverStatus.running
    db.commit()

    try:
        # ── FETCH ALL DATA FROM DB ────────────────────────────────────────────
        courses_db = db.query(models.Course).all()
        rooms_db = db.query(models.Room).filter(models.Room.is_available == True).all()
        time_slots_db = db.query(models.TimeSlot).all()
        unavailability_db = db.query(models.LecturerUnavailability).all()
        lecturer_courses_db = db.query(models.LecturerCourse).all()

        # Map course_id → lecturer_id (take first assigned lecturer)
        course_lecturer_map = {}
        for lc in lecturer_courses_db:
            if lc.course_id not in course_lecturer_map:
                course_lecturer_map[lc.course_id] = lc.lecturer_id

        # Build course list with lecturer info
        courses = []
        for c in courses_db:
            lecturer_id = course_lecturer_map.get(c.id)
            if lecturer_id is None:
                continue  # Skip courses with no lecturer assigned
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
            {
                "id": r.id,
                "room_type": r.room_type.value,
                "capacity": r.capacity,
            }
            for r in rooms_db
        ]

        time_slots = [
            {
                "id": s.id,
                "day": s.day.value,
                "start_time": s.start_time,
            }
            for s in time_slots_db
        ]

        unavailability = set((u.lecturer_id, u.time_slot_id) for u in unavailability_db)

        data = {
            "courses": courses,
            "rooms": rooms,
            "time_slots": time_slots,
            "unavailability": unavailability,
        }

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

        # ── HANDLE INFEASIBLE ─────────────────────────────────────────────────
        if status in [cp_model.INFEASIBLE, cp_model.UNKNOWN]:
            run.status = models.SolverStatus.infeasible
            run.solver_status = solver_status_str
            run.computation_seconds = elapsed
            db.commit()
            return

        # ── SAVE RESULTS TO DB ────────────────────────────────────────────────
        entries_to_add = []
        for s_idx, session in enumerate(course_sessions):
            for room in rooms:
                for slot in time_slots:
                    if solver.value(x[(s_idx, room["id"], slot["id"])]) == 1:
                        entry = models.ScheduleEntry(
                            run_id=run_id,
                            course_id=session["course_id"],
                            lecturer_id=session["lecturer_id"],
                            room_id=room["id"],
                            time_slot_id=slot["id"],
                        )
                        entries_to_add.append(entry)

        db.bulk_save_objects(entries_to_add)

        # Update run record
        run.status = (
            models.SolverStatus.optimal
            if status == cp_model.OPTIMAL
            else models.SolverStatus.feasible
        )
        run.solver_status = solver_status_str
        run.objective_value = solver.objective_value
        run.computation_seconds = elapsed
        db.commit()

    except Exception as e:
        run.status = models.SolverStatus.failed
        run.notes = str(e)
        db.commit()
        raise
