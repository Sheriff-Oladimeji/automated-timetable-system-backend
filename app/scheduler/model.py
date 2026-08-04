"""
CP-SAT constraint model for the CSET timetable scheduling problem.

Decision variable:
    x[(session_idx, room_id, slot_id)] ∈ {0, 1}
    = 1  iff  session is assigned to that (room, time slot) pair

HARD CONSTRAINTS  (infeasible if broken):
    H1 — Each session assigned to exactly one (room, slot)
    H2 — No room double-booked in the same slot
    H3 — No lecturer teaches two sessions at the same time
    H4 — No student group (dept + level) has two sessions in the same slot
    H5 — Lab courses → laboratory rooms only; theory → non-laboratory only
    H6 — Lecturer availability STRICTLY enforced (marked slots are forbidden)
    H7 — Room capacity must be ≥ enrolled student count

SOFT CONSTRAINTS  (penalised in objective, minimised):
    S1 — Back-to-back sessions for same student group (same day, adjacent slots)
    S2 — Multiple sessions of the same course on the same day
    S3 — Lecturer overloaded on a single day (> 3 sessions)
    S4 — Session placed in a room significantly larger than needed (capacity waste)
"""

from ortools.sat.python import cp_model
from typing import Dict, Any, List
import math


def build_model(data: Dict[str, Any], config: Dict[str, Any]):
    """
    Build and return the CP-SAT model.

    Args:
        data: {
            courses:       list of dicts with keys:
                           id, course_type, hours_per_week, enrolled_count,
                           department_id, level, lecturer_id
            rooms:         list of dicts: id, room_type, capacity
            time_slots:    list of dicts: id, day, start_time
            unavailability: set of (lecturer_id, time_slot_id) pairs
        }
        config: penalty weights and solver settings

    Returns:
        (model, x, course_sessions)
    """
    model = cp_model.CpModel()

    courses: List[Dict] = data["courses"]
    rooms: List[Dict] = data["rooms"]
    time_slots: List[Dict] = data["time_slots"]
    unavailability: List[Dict] = data["unavailability"]

    slot_list = sorted(time_slots, key=lambda s: (s["day"], s["start_time"]))
    days = list({s["day"] for s in time_slots})

    # ── EXPAND COURSES INTO SESSIONS ─────────────────────────────────────────
    # Each course needs ceil(hours_per_week / 2) sessions: every 2 contact hours
    # maps to one 2-hour class period.  A 2-hr course → 1 session; 4-hr → 2; 6-hr → 3.
    # S2 discourages placing all sessions for a course on the same day.
    course_sessions: List[Dict] = []
    for course in courses:
        n_sessions = max(1, math.ceil(course["hours_per_week"] / 2))
        for session_num in range(n_sessions):
            course_sessions.append({
                "course_id":    course["id"],
                "session_num":  session_num,
                "course_type":  course["course_type"],
                "enrolled_count": course["enrolled_count"],
                "department_id": course["department_id"],
                "level":        course["level"],
                "lecturer_id":  course["lecturer_id"],
            })

    # ── DECISION VARIABLES ────────────────────────────────────────────────────
    x: Dict[Tuple[int, int, int], Any] = {}
    for s_idx in range(len(course_sessions)):
        for room in rooms:
            for slot in time_slots:
                x[(s_idx, room["id"], slot["id"])] = model.new_bool_var(
                    f"x_{s_idx}_{room['id']}_{slot['id']}"
                )

    # Pre-compute groupings used by multiple constraints
    lecturer_ids = {s["lecturer_id"] for s in course_sessions}
    dept_level_groups = {(s["department_id"], s["level"]) for s in course_sessions}

    # ── H1: Each session assigned to exactly one (room, slot) ────────────────
    for s_idx in range(len(course_sessions)):
        model.add_exactly_one(
            x[(s_idx, r["id"], t["id"])]
            for r in rooms
            for t in time_slots
        )

    # ── H2: No room double-booked in the same slot ───────────────────────────
    for room in rooms:
        for slot in time_slots:
            model.add_at_most_one(
                x[(s_idx, room["id"], slot["id"])]
                for s_idx in range(len(course_sessions))
            )

    # ── H3: No lecturer teaches two sessions at the same time ────────────────
    for slot in time_slots:
        for lid in lecturer_ids:
            lec_vars = [
                x[(s_idx, r["id"], slot["id"])]
                for s_idx, s in enumerate(course_sessions)
                if s["lecturer_id"] == lid
                for r in rooms
            ]
            if lec_vars:
                model.add_at_most_one(lec_vars)

    # ── H4: No student-group clash (same dept + level in same slot) ──────────
    for slot in time_slots:
        for dept_id, level in dept_level_groups:
            group_vars = [
                x[(s_idx, r["id"], slot["id"])]
                for s_idx, s in enumerate(course_sessions)
                if s["department_id"] == dept_id and s["level"] == level
                for r in rooms
            ]
            if group_vars:
                model.add_at_most_one(group_vars)

    # ── H5: Room type must match course type ─────────────────────────────────
    for s_idx, session in enumerate(course_sessions):
        is_lab_course = session["course_type"] == "lab"
        for room in rooms:
            is_lab_room = room["room_type"] == "laboratory"
            if is_lab_course != is_lab_room:
                for slot in time_slots:
                    model.add(x[(s_idx, room["id"], slot["id"])] == 0)

    # ── H6: Lecturer unavailability — HARD (forbidden, not penalised) ─────────
    # A slot is blocked for a lecturer if it falls within any unavailability window
    # (same day, slot.start_time within [unavail.start_time, unavail.end_time)).
    for s_idx, session in enumerate(course_sessions):
        lid = session["lecturer_id"]
        for slot in time_slots:
            is_blocked = any(
                u["lecturer_id"] == lid
                and u["day"] == slot["day"]
                and u["start_time"] <= slot["start_time"] < u["end_time"]
                for u in unavailability
            )
            if is_blocked:
                for room in rooms:
                    model.add(x[(s_idx, room["id"], slot["id"])] == 0)

    # ── H7: Room capacity must fit enrolled students ──────────────────────────
    # If enrolled_count is 0 the constraint is skipped (no data to enforce).
    for s_idx, session in enumerate(course_sessions):
        ec = session["enrolled_count"]
        if ec <= 0:
            continue
        for room in rooms:
            if room["capacity"] < ec:
                for slot in time_slots:
                    model.add(x[(s_idx, room["id"], slot["id"])] == 0)

    # ── SOFT CONSTRAINTS ──────────────────────────────────────────────────────
    w_b2b    = int(config.get("back_to_back_penalty", 10))
    w_spread = int(config.get("spread_sessions_penalty", 5))

    # ── S1: Back-to-back sessions for same student group ─────────────────────
    back_to_back_violations: List[Any] = []
    for i in range(len(slot_list) - 1):
        slot_a = slot_list[i]
        slot_b = slot_list[i + 1]
        if slot_a["day"] != slot_b["day"]:
            continue  # Only penalise same-day adjacency

        for dept_id, level in dept_level_groups:
            grp = [
                s_idx for s_idx, s in enumerate(course_sessions)
                if s["department_id"] == dept_id and s["level"] == level
            ]
            if not grp:
                continue

            vars_a = [x[(s, r["id"], slot_a["id"])] for s in grp for r in rooms]
            vars_b = [x[(s, r["id"], slot_b["id"])] for s in grp for r in rooms]

            assigned_a = model.new_bool_var(f"b2b_a_{dept_id}_{level}_{i}")
            assigned_b = model.new_bool_var(f"b2b_b_{dept_id}_{level}_{i}")
            violation  = model.new_bool_var(f"b2b_v_{dept_id}_{level}_{i}")

            model.add_max_equality(assigned_a, vars_a)
            model.add_max_equality(assigned_b, vars_b)
            # violation = 1 iff both adjacent slots are occupied by this group
            model.add(violation >= assigned_a + assigned_b - 1)
            back_to_back_violations.append(violation)

    # ── S2: Spread course sessions across different days ──────────────────────
    spread_violations: List[Any] = []
    for course in courses:
        if course["hours_per_week"] <= 1:
            continue
        c_sessions = [
            s_idx for s_idx, s in enumerate(course_sessions)
            if s["course_id"] == course["id"]
        ]
        if len(c_sessions) < 2:
            continue
        for day in days:
            slots_on_day = [t for t in time_slots if t["day"] == day]
            if not slots_on_day:
                continue
            on_day_vars = [
                x[(s_idx, r["id"], t["id"])]
                for s_idx in c_sessions
                for r in rooms
                for t in slots_on_day
            ]
            total_on_day = model.new_int_var(
                0, len(c_sessions), f"spread_{course['id']}_{day}"
            )
            model.add(total_on_day == sum(on_day_vars))
            viol = model.new_bool_var(f"spread_v_{course['id']}_{day}")
            model.add(total_on_day >= 2).only_enforce_if(viol)
            model.add(total_on_day <= 1).only_enforce_if(viol.Not())
            spread_violations.append(viol)

    # ── S3: Lecturer daily overload — penalise > 3 sessions in one day ────────
    overload_violations: List[Any] = []
    MAX_SESSIONS_PER_DAY = 3
    for lid in lecturer_ids:
        lec_sessions = [
            s_idx for s_idx, s in enumerate(course_sessions)
            if s["lecturer_id"] == lid
        ]
        if len(lec_sessions) <= MAX_SESSIONS_PER_DAY:
            continue  # Can't exceed limit anyway
        for day in days:
            slots_on_day = [t for t in time_slots if t["day"] == day]
            daily_vars = [
                x[(s_idx, r["id"], t["id"])]
                for s_idx in lec_sessions
                for r in rooms
                for t in slots_on_day
            ]
            daily_count = model.new_int_var(
                0, len(lec_sessions), f"overload_{lid}_{day}"
            )
            model.add(daily_count == sum(daily_vars))
            excess = model.new_int_var(0, len(lec_sessions), f"excess_{lid}_{day}")
            model.add(excess >= daily_count - MAX_SESSIONS_PER_DAY)
            model.add(excess >= 0)
            overload_violations.append(excess)

    # ── S4: Capacity waste — prefer rooms close in size to enrolled count ──────
    capacity_waste: List[Any] = []
    for s_idx, session in enumerate(course_sessions):
        ec = session["enrolled_count"]
        if ec <= 0:
            continue
        for room in rooms:
            if room["capacity"] < ec:
                continue  # Already blocked by H7
            # Penalise if room is more than double the enrolled count
            if room["capacity"] > 2 * ec:
                for slot in time_slots:
                    capacity_waste.append(x[(s_idx, room["id"], slot["id"])])

    # ── OBJECTIVE ─────────────────────────────────────────────────────────────
    terms = []
    if back_to_back_violations:
        terms.append(w_b2b * sum(back_to_back_violations))
    if spread_violations:
        terms.append(w_spread * sum(spread_violations))
    if overload_violations:
        terms.append(w_b2b * sum(overload_violations))  # same weight as b2b
    if capacity_waste:
        terms.append(1 * sum(capacity_waste))  # low weight — just a tiebreaker

    if terms:
        model.minimize(sum(terms))

    return model, x, course_sessions
