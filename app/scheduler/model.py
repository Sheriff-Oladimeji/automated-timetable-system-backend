"""
CP-SAT constraint model for the CSET timetable scheduling problem.

The model receives pre-processed data (courses expanded into sessions, rooms,
time slots, unavailability) and penalty-weight config, then builds a Google
OR-Tools CP-SAT model that the solver in solver.py will optimise.

Decision variable:
    x[(session_idx, room_id, slot_id)] ∈ {0, 1}
    = 1  iff  session is assigned to that (room, time slot) pair

Hard constraints (infeasible if broken):
    H1 — Each session is assigned to exactly one (room, slot)
    H2 — No room is double-booked in the same slot
    H3 — No lecturer teaches two sessions at the same time
    H4 — No student-group (dept + level) has two sessions in the same slot
    H5 — Lab courses → laboratory rooms only; theory courses → non-laboratory rooms only

Soft constraints (penalised in the objective):
    S1 — Lecturer assigned during a slot they marked as unavailable
    S2 — Same student-group has back-to-back sessions on the same day
    S3 — Multiple sessions of the same course fall on the same day
    S4 — A session is placed in a room whose capacity is less than the enrolled count

Objective:
    Minimise  w_unavail × ΣS1  +  w_b2b × ΣS2  +  w_spread × ΣS3  +  w_capacity × ΣS4
"""

from ortools.sat.python import cp_model
from typing import List, Dict, Any


def build_model(data: Dict[str, Any], config: Dict[str, Any]):
    """
    Build the CP-SAT model.

    Args:
        data: {
            "courses":      list of course dicts (id, course_type, hours_per_week,
                            enrolled_count, department_id, level, lecturer_id)
            "rooms":        list of room dicts (id, room_type, capacity)
            "time_slots":   list of time-slot dicts (id, day, start_time)
            "unavailability": set of (lecturer_id, time_slot_id) pairs
        }
        config: penalty weights — keys match ConstraintConfig field names

    Returns:
        (model, x, course_sessions)
            model          — the fully built CpModel
            x              — decision-variable dict keyed by (s_idx, room_id, slot_id)
            course_sessions — list of session dicts (same order as x's s_idx axis)
    """
    model = cp_model.CpModel()

    courses = data["courses"]
    rooms = data["rooms"]
    time_slots = data["time_slots"]
    unavailability = data["unavailability"]  # set of (lecturer_id, slot_id)

    # ── EXPAND COURSES INTO SESSIONS ─────────────────────────────────────────
    # A course with hours_per_week=2 becomes 2 independent sessions in the model.
    # The spread constraint (S3) later penalises placing both on the same day.
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
    x = {}
    for s_idx, session in enumerate(course_sessions):
        for room in rooms:
            for slot in time_slots:
                x[(s_idx, room["id"], slot["id"])] = model.new_bool_var(
                    f"x_s{s_idx}_r{room['id']}_t{slot['id']}"
                )

    # ── H1: Each session assigned to exactly one (room, slot) ────────────────
    for s_idx in range(len(course_sessions)):
        model.add_exactly_one(
            x[(s_idx, room["id"], slot["id"])] for room in rooms for slot in time_slots
        )

    # ── H2: No room double-booked in the same slot ───────────────────────────
    for room in rooms:
        for slot in time_slots:
            model.add_at_most_one(
                x[(s_idx, room["id"], slot["id"])]
                for s_idx in range(len(course_sessions))
            )

    # ── H3: No lecturer teaches two sessions at the same time ────────────────
    lecturer_ids = set(s["lecturer_id"] for s in course_sessions)
    for slot in time_slots:
        for lecturer_id in lecturer_ids:
            model.add_at_most_one(
                x[(s_idx, room["id"], slot["id"])]
                for s_idx, session in enumerate(course_sessions)
                if session["lecturer_id"] == lecturer_id
                for room in rooms
            )

    # ── H4: No student-group clash (dept + level share a slot) ───────────────
    dept_level_groups = set(
        (s["department_id"], s["level"]) for s in course_sessions
    )
    for slot in time_slots:
        for dept_id, level in dept_level_groups:
            model.add_at_most_one(
                x[(s_idx, room["id"], slot["id"])]
                for s_idx, session in enumerate(course_sessions)
                if session["department_id"] == dept_id and session["level"] == level
                for room in rooms
            )

    # ── H5: Room type must match course type ─────────────────────────────────
    # lab course  → must go in a laboratory room
    # theory course → must NOT go in a laboratory room
    for s_idx, session in enumerate(course_sessions):
        for room in rooms:
            for slot in time_slots:
                if session["course_type"] == "lab" and room["room_type"] != "laboratory":
                    model.add(x[(s_idx, room["id"], slot["id"])] == 0)
                elif (
                    session["course_type"] == "theory"
                    and room["room_type"] == "laboratory"
                ):
                    model.add(x[(s_idx, room["id"], slot["id"])] == 0)

    # ── S1: Lecturer unavailability penalty ───────────────────────────────────
    unavailability_violations = []
    for s_idx, session in enumerate(course_sessions):
        for room in rooms:
            for slot in time_slots:
                if (session["lecturer_id"], slot["id"]) in unavailability:
                    # One violation indicator per (session, room, slot) triple so
                    # the model can't collapse multiple assignments into one penalty.
                    v = model.new_bool_var(f"unavail_s{s_idx}_r{room['id']}_t{slot['id']}")
                    model.add(x[(s_idx, room["id"], slot["id"])] <= v)
                    unavailability_violations.append(v)

    # ── S2: Back-to-back sessions for same student group ─────────────────────
    back_to_back_violations = []
    slot_list = sorted(time_slots, key=lambda s: (s["day"], s["start_time"]))

    for i in range(len(slot_list) - 1):
        slot_a = slot_list[i]
        slot_b = slot_list[i + 1]

        # Only penalise consecutive slots on the same day
        if slot_a["day"] != slot_b["day"]:
            continue

        for dept_id, level in dept_level_groups:
            sessions_in_group = [
                s_idx
                for s_idx, s in enumerate(course_sessions)
                if s["department_id"] == dept_id and s["level"] == level
            ]
            if not sessions_in_group:
                continue

            # assigned_a / assigned_b = 1 if any session of this group is in that slot
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

            # violation = 1 iff both adjacent slots have a session from this group
            model.add(violation >= assigned_a + assigned_b - 1)
            back_to_back_violations.append(violation)

    # ── S3: Spread course sessions across different days ──────────────────────
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

        for day in days:
            slots_on_day = [slot for slot in time_slots if slot["day"] == day]
            if not slots_on_day:
                continue

            # Count how many of this course's sessions land on this day
            sessions_on_day = [
                x[(s_idx, room["id"], slot["id"])]
                for s_idx in course_session_indices
                for room in rooms
                for slot in slots_on_day
            ]

            total_on_day = model.new_int_var(
                0, len(course_session_indices), f"spread_{course['id']}_{day}"
            )
            model.add(total_on_day == sum(sessions_on_day))

            violation = model.new_bool_var(f"spread_v_{course['id']}_{day}")
            model.add(total_on_day >= 2).only_enforce_if(violation)
            model.add(total_on_day <= 1).only_enforce_if(violation.Not())
            spread_violations.append(violation)

    # ── S4: Room capacity soft constraint ────────────────────────────────────
    # Penalise when a course's enrolled_count exceeds the assigned room's capacity.
    # This is a soft constraint: the solver will prefer larger rooms but won't
    # declare infeasible just because no perfectly-sized room exists.
    capacity_violations = []
    for s_idx, session in enumerate(course_sessions):
        for room in rooms:
            if room["capacity"] < session["enrolled_count"]:
                for slot in time_slots:
                    # The variable itself acts as the violation indicator
                    capacity_violations.append(x[(s_idx, room["id"], slot["id"])])

    # ── OBJECTIVE ────────────────────────────────────────────────────────────
    w_unavail = config.get("unavailability_penalty", 100)
    w_b2b = config.get("back_to_back_penalty", 10)
    w_spread = config.get("spread_sessions_penalty", 5)
    w_capacity = config.get("room_capacity_penalty", 20)

    objective_terms = (
        w_unavail * sum(unavailability_violations)
        + w_b2b * sum(back_to_back_violations)
        + w_spread * sum(spread_violations)
        + w_capacity * sum(capacity_violations)
    )
    model.minimize(objective_terms)

    return model, x, course_sessions
