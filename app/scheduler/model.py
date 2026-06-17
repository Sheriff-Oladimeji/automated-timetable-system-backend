from ortools.sat.python import cp_model
from typing import List, Dict, Any


def build_model(data: Dict[str, Any], config: Dict[str, Any]):
    """
    Builds the CP-SAT model for the timetable scheduling problem.

    Args:
        data: dict with keys:
            - courses: list of course dicts (id, course_type, hours_per_week,
                       enrolled_count, department_id, level, lecturer_id)
            - rooms: list of room dicts (id, room_type, capacity)
            - time_slots: list of time slot dicts (id, day, start_time)
            - unavailability: set of (lecturer_id, time_slot_id) tuples
        config: dict with penalty weights from ConstraintConfig

    Returns:
        (model, variables, course_sessions) tuple
    """
    model = cp_model.CpModel()

    courses = data["courses"]
    rooms = data["rooms"]
    time_slots = data["time_slots"]
    unavailability = data["unavailability"]  # set of (lecturer_id, slot_id)

    # ── EXPAND COURSES INTO SESSIONS ─────────────────────────────────────────
    # A course with hours_per_week=2 needs 2 separate session assignments
    course_sessions = []
    for course in courses:
        for session_num in range(course["hours_per_week"]):
            course_sessions.append(
                {
                    "course_id": course["id"],
                    "session_num": session_num,
                    "course_type": course["course_type"],
                    "enrolled_count": course["enrolled_count"],
                    "department_id": course["department_id"],
                    "level": course["level"],
                    "lecturer_id": course["lecturer_id"],
                }
            )

    # ── DECISION VARIABLES ────────────────────────────────────────────────────
    # x[(session_idx, room_id, slot_id)] = 1 means session is assigned here
    x = {}
    for s_idx, session in enumerate(course_sessions):
        for room in rooms:
            for slot in time_slots:
                x[(s_idx, room["id"], slot["id"])] = model.new_bool_var(
                    f"x_s{s_idx}_r{room['id']}_t{slot['id']}"
                )

    # ── HARD CONSTRAINT 1: Each session gets exactly one room + time slot ─────
    for s_idx in range(len(course_sessions)):
        model.add_exactly_one(
            x[(s_idx, room["id"], slot["id"])] for room in rooms for slot in time_slots
        )

    # ── HARD CONSTRAINT 2: No room double-booked ─────────────────────────────
    for room in rooms:
        for slot in time_slots:
            model.add_at_most_one(
                x[(s_idx, room["id"], slot["id"])]
                for s_idx in range(len(course_sessions))
            )

    # ── HARD CONSTRAINT 3: No lecturer in two places at once ──────────────────
    for slot in time_slots:
        # Group sessions by lecturer
        lecturer_ids = set(s["lecturer_id"] for s in course_sessions)
        for lecturer_id in lecturer_ids:
            model.add_at_most_one(
                x[(s_idx, room["id"], slot["id"])]
                for s_idx, session in enumerate(course_sessions)
                if session["lecturer_id"] == lecturer_id
                for room in rooms
            )

    # ── HARD CONSTRAINT 4: No student group clash ─────────────────────────────
    # Sessions from same department + level cannot share a time slot
    for slot in time_slots:
        dept_level_groups = set(
            (s["department_id"], s["level"]) for s in course_sessions
        )
        for dept_id, level in dept_level_groups:
            model.add_at_most_one(
                x[(s_idx, room["id"], slot["id"])]
                for s_idx, session in enumerate(course_sessions)
                if session["department_id"] == dept_id and session["level"] == level
                for room in rooms
            )

    # ── HARD CONSTRAINT 5: Room type must match course type ───────────────────
    # Lab courses → only lab rooms; theory courses → lecture halls or seminar rooms
    for s_idx, session in enumerate(course_sessions):
        for room in rooms:
            for slot in time_slots:
                if (
                    session["course_type"] == "lab"
                    and room["room_type"] != "laboratory"
                ):
                    model.add(x[(s_idx, room["id"], slot["id"])] == 0)
                elif (
                    session["course_type"] == "theory"
                    and room["room_type"] == "laboratory"
                ):
                    model.add(x[(s_idx, room["id"], slot["id"])] == 0)

    # ── SOFT CONSTRAINT 1: Lecturer unavailability ────────────────────────────
    unavailability_violations = []
    for s_idx, session in enumerate(course_sessions):
        for room in rooms:
            for slot in time_slots:
                if (session["lecturer_id"], slot["id"]) in unavailability:
                    violation = model.new_bool_var(f"unavail_s{s_idx}_t{slot['id']}")
                    model.add(x[(s_idx, room["id"], slot["id"])] <= violation)
                    unavailability_violations.append(violation)

    # ── SOFT CONSTRAINT 2: Avoid back-to-back sessions for same student group ─
    back_to_back_violations = []
    slot_list = sorted(time_slots, key=lambda s: (s["day"], s["start_time"]))
    slot_index = {slot["id"]: i for i, slot in enumerate(slot_list)}

    for i in range(len(slot_list) - 1):
        slot_a = slot_list[i]
        slot_b = slot_list[i + 1]

        # Only penalise if consecutive slots on the same day
        if slot_a["day"] != slot_b["day"]:
            continue

        dept_level_groups = set(
            (s["department_id"], s["level"]) for s in course_sessions
        )
        for dept_id, level in dept_level_groups:
            sessions_in_group = [
                s_idx
                for s_idx, s in enumerate(course_sessions)
                if s["department_id"] == dept_id and s["level"] == level
            ]

            assigned_a = model.new_bool_var(f"b2b_a_{dept_id}_{level}_{i}")
            assigned_b = model.new_bool_var(f"b2b_b_{dept_id}_{level}_{i}")
            violation = model.new_bool_var(f"b2b_v_{dept_id}_{level}_{i}")

            model.add_max_equality(
                assigned_a,
                [
                    x[(s_idx, room["id"], slot_a["id"])]
                    for s_idx in sessions_in_group
                    for room in rooms
                ],
            )
            model.add_max_equality(
                assigned_b,
                [
                    x[(s_idx, room["id"], slot_b["id"])]
                    for s_idx in sessions_in_group
                    for room in rooms
                ],
            )

            # violation = 1 if both slots occupied by same group
            model.add(violation >= assigned_a + assigned_b - 1)
            back_to_back_violations.append(violation)

    # ── SOFT CONSTRAINT 3: Spread course sessions across different days ────────
    spread_violations = []
    days = list(set(slot["day"] for slot in time_slots))

    for course in courses:
        if course["hours_per_week"] <= 1:
            continue
        course_session_indices = [
            s_idx
            for s_idx, s in enumerate(course_sessions)
            if s["course_id"] == course["id"]
        ]
        if len(course_session_indices) < 2:
            continue

        # Check if two sessions from same course land on the same day
        for day in days:
            slots_on_day = [slot for slot in time_slots if slot["day"] == day]
            if not slots_on_day:
                continue

            sessions_on_day = []
            for s_idx in course_session_indices:
                for room in rooms:
                    for slot in slots_on_day:
                        sessions_on_day.append(x[(s_idx, room["id"], slot["id"])])

            total_on_day = model.new_int_var(
                0, len(course_session_indices), f"spread_{course['id']}_{day}"
            )
            model.add(total_on_day == sum(sessions_on_day))

            violation = model.new_bool_var(f"spread_v_{course['id']}_{day}")
            model.add(total_on_day >= 2).only_enforce_if(violation)
            model.add(total_on_day <= 1).only_enforce_if(violation.Not())
            spread_violations.append(violation)

    # ── OBJECTIVE FUNCTION ────────────────────────────────────────────────────
    # Minimise total weighted penalty from soft constraint violations
    w_unavail = config.get("unavailability_penalty", 100)
    w_b2b = config.get("back_to_back_penalty", 10)
    w_spread = config.get("spread_sessions_penalty", 5)

    model.minimize(
        w_unavail * sum(unavailability_violations)
        + w_b2b * sum(back_to_back_violations)
        + w_spread * sum(spread_violations)
    )

    return model, x, course_sessions
