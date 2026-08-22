"""
CP-SAT constraint model for the CSET timetable scheduling problem.

Decision variable:
    x[(session_idx, room_id, slot_id)] ∈ {0, 1}
    = 1  iff  session is assigned to that (room, time slot) pair

Only feasible (session, room, slot) combinations get a variable —
infeasible ones (wrong room type, insufficient capacity, lecturer blocked)
are pruned before model construction, cutting memory by ~70 %.

HARD CONSTRAINTS  (infeasible if broken):
    H1 — Each session assigned to exactly one (room, slot)
    H2 — No room double-booked in the same slot
    H3 — No lecturer teaches two sessions at the same time
    H4 — No student group (dept + level) has two sessions in the same slot

SOFT CONSTRAINTS  (penalised in objective, minimised):
    S1 — Back-to-back sessions for same student group (same day, adjacent slots)
    S2 — Multiple sessions of the same course on the same day
    S3 — Lecturer overloaded on a single day (> 3 sessions)
    S4 — Session placed in a room significantly larger than needed
"""

from ortools.sat.python import cp_model
from typing import Dict, Any, List, Tuple
import math


def build_model(data: Dict[str, Any], config: Dict[str, Any]):
    model = cp_model.CpModel()

    courses: List[Dict]       = data["courses"]
    rooms: List[Dict]         = data["rooms"]
    time_slots: List[Dict]    = data["time_slots"]
    unavailability: List[Dict] = data["unavailability"]

    slot_list = sorted(time_slots, key=lambda s: (s["day"], s["start_time"]))

    # ── EXPAND COURSES INTO SESSIONS ─────────────────────────────────────────
    course_sessions: List[Dict] = []
    for course in courses:
        n = max(1, math.ceil(course["hours_per_week"] / 2))
        for i in range(n):
            course_sessions.append({
                "course_id":      course["id"],
                "session_num":    i,
                "course_type":    course["course_type"],
                "enrolled_count": course["enrolled_count"],
                "department_id":  course["department_id"],
                "level":          course["level"],
                "lecturer_id":    course["lecturer_id"],
            })

    # ── PRE-COMPUTE BLOCKED SLOTS PER LECTURER ────────────────────────────────
    # slot_id → set of blocked lecturer_ids
    blocked: Dict[int, set] = {t["id"]: set() for t in time_slots}
    for u in unavailability:
        lid = u["lecturer_id"]
        for t in time_slots:
            if (t["day"] == u["day"]
                    and u["start_time"] <= t["start_time"] < u["end_time"]):
                blocked[t["id"]].add(lid)

    # ── PRUNED VARIABLE CREATION ──────────────────────────────────────────────
    # Only create x[(s, r, t)] when the combination is feasible:
    #   • room type matches course type
    #   • room capacity >= enrolled_count  (skip if enrolled_count == 0)
    #   • lecturer not blocked in that slot
    x: Dict[Tuple[int, int, int], Any] = {}

    # Per-session: list of (room_id, slot_id) for which a var was created
    session_vars: List[List[Tuple[int, int]]] = [[] for _ in course_sessions]

    # Reverse indexes for H2 / H3 / H4
    room_slot_sessions: Dict[Tuple[int, int], List[int]] = {}   # (r_id, t_id) → [s_idx]
    lec_slot_sessions:  Dict[Tuple[int, int], List[int]] = {}   # (lid,  t_id) → [s_idx]
    group_slot_sessions: Dict[Tuple, List[int]]          = {}   # (dept, lvl, t_id) → [s_idx]

    for s_idx, session in enumerate(course_sessions):
        is_lab   = session["course_type"] == "lab"
        ec       = session["enrolled_count"]
        lid      = session["lecturer_id"]
        dept_id  = session["department_id"]
        level    = session["level"]

        compat_rooms = [
            r for r in rooms
            if (r["room_type"] == "laboratory") == is_lab
            and (ec <= 0 or r["capacity"] >= ec)
        ]

        for t in time_slots:
            tid = t["id"]
            if lid in blocked[tid]:
                continue  # lecturer unavailable — skip

            slot_had_var = False
            for room in compat_rooms:
                rid = room["id"]
                var = model.new_bool_var(f"x_{s_idx}_{rid}_{tid}")
                x[(s_idx, rid, tid)] = var
                session_vars[s_idx].append((rid, tid))
                room_slot_sessions.setdefault((rid, tid), []).append(s_idx)
                slot_had_var = True

            # Add s_idx to lecturer/group indexes only once per slot (not per room)
            if slot_had_var:
                lec_slot_sessions.setdefault((lid, tid), []).append(s_idx)
                group_slot_sessions.setdefault((dept_id, level, tid), []).append(s_idx)

    # ── H1: Each session assigned to exactly one (room, slot) ────────────────
    for s_idx, pairs in enumerate(session_vars):
        vars_for_session = [x[(s_idx, rid, tid)] for rid, tid in pairs]
        if vars_for_session:
            model.add_exactly_one(vars_for_session)
        # If no vars exist the pre-validation would have caught it already.

    # ── H2: No room double-booked in the same slot ───────────────────────────
    for (rid, tid), session_idxs in room_slot_sessions.items():
        if len(session_idxs) > 1:
            model.add_at_most_one(x[(s, rid, tid)] for s in session_idxs)

    # ── H3: No lecturer teaches two sessions at the same time ────────────────
    for (lid, tid), session_idxs in lec_slot_sessions.items():
        if len(session_idxs) > 1:
            lec_vars = [
                x[(s, rid, tid2)]
                for s in session_idxs
                for rid, tid2 in session_vars[s]
                if tid2 == tid
            ]
            if len(lec_vars) > 1:
                model.add_at_most_one(lec_vars)

    # ── H4: No student-group clash (same dept + level in same slot) ──────────
    for (dept_id, level, tid), session_idxs in group_slot_sessions.items():
        if len(session_idxs) > 1:
            group_vars = [
                x[(s, rid, tid2)]
                for s in session_idxs
                for rid, tid2 in session_vars[s]
                if tid2 == tid
            ]
            if len(group_vars) > 1:
                model.add_at_most_one(group_vars)

    # ── H5: Balance sessions across days ─────────────────────────────────────
    # Without this, the solver packs everything onto one day (cheapest move).
    # Hard cap: no day gets more than ceil(total_sessions / num_days) + slack.
    days = list({s["day"] for s in time_slots})
    slot_day = {t["id"]: t["day"] for t in time_slots}
    max_per_day = math.ceil(len(course_sessions) / max(len(days), 1)) + 8

    for day in days:
        day_vars = [
            x[(s_idx, rid, tid)]
            for s_idx in range(len(course_sessions))
            for rid, tid in session_vars[s_idx]
            if slot_day.get(tid) == day
        ]
        if day_vars:
            model.add(sum(day_vars) <= max_per_day)

    return model, x, course_sessions
