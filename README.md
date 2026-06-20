# CSET Automated Timetable System — Backend

FastAPI + PostgreSQL backend for the constraint-based automated timetable scheduler used by the College of Science, Engineering and Technology (CSET), UNIOSUN.

The system replaces the manual process of allocating courses to rooms and time slots by running a [Google OR-Tools CP-SAT](https://developers.google.com/optimization/reference/python/sat/python/cp_model) solver that respects hard constraints (no double-booking, room-type matching) and optimises soft constraints (lecturer availability, class spreading, room capacity).

---

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A PostgreSQL database (local or [Neon](https://neon.tech))

---

## Quick Start

```bash
# 1. Enter the backend directory
cd backend

# 2. Install dependencies
uv sync

# 3. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL and SECRET_KEY

# 4. Run database migrations
uv run alembic upgrade head

# 5. Start the development server
uv run fastapi dev app/main.py
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

---

## First-Run Setup

After the server starts, create the first admin account:

```bash
curl -X POST http://localhost:8000/auth/register-admin \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@cset.edu.ng", "password": "strongpassword"}'
```

This endpoint is automatically disabled once any admin account exists.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py           # FastAPI app, CORS, router registration
│   ├── database.py       # SQLAlchemy engine + session factory
│   ├── models.py         # ORM models (all tables)
│   ├── schemas.py        # Pydantic request/response schemas + validation
│   ├── dependencies.py   # JWT auth + role guards (require_admin etc.)
│   ├── routers/
│   │   ├── auth.py       # Login, /me, first-admin bootstrap
│   │   ├── resources.py  # CRUD: faculties, departments, courses, lecturers, rooms, slots
│   │   ├── constraints.py# Lecturer unavailability + solver penalty weights
│   │   ├── scheduler.py  # Trigger runs, poll status, list run history
│   │   ├── timetable.py  # View/edit timetable, publish/unpublish
│   │   ├── lecturer.py   # Lecturer views own schedule + unavailability
│   │   └── student.py    # Student views published timetable
│   └── scheduler/
│       ├── model.py      # CP-SAT constraint model (hard + soft constraints)
│       ├── solver.py     # Solver orchestration: fetch → build → solve → persist
│       └── validator.py  # Hard-constraint check for manual adjustments
├── alembic/              # Database migration scripts
│   ├── env.py            # Reads DATABASE_URL from .env automatically
│   └── versions/         # Auto-generated migration files
├── alembic.ini           # Alembic configuration
├── pyproject.toml        # Python dependencies (managed by uv)
├── .env.example          # Template for required environment variables
└── .env                  # Your local secrets (git-ignored)
```

---

## Database Migrations

This project uses [Alembic](https://alembic.sqlalchemy.org/) for schema migrations.

```bash
# Apply all pending migrations (run after pulling new code)
uv run alembic upgrade head

# Generate a new migration after changing app/models.py
uv run alembic revision --autogenerate -m "add foo column to bar table"

# Roll back the last migration
uv run alembic downgrade -1

# Show migration history
uv run alembic history --verbose
```

---

## Roles and Access

| Role      | Can do                                                                 |
|-----------|------------------------------------------------------------------------|
| `admin`   | Everything — manage resources, run scheduler, publish timetable        |
| `lecturer`| View own schedule, submit/remove own unavailability                    |
| `student` | View the published timetable (filtered to own dept + level by default) |

---

## Scheduling Workflow

1. Admin creates Faculties → Departments → Courses → Lecturers → Rooms → TimeSlots
2. Admin assigns lecturers to courses (`POST /resources/lecturer-courses`)
3. Lecturers submit unavailability (`POST /lecturer/unavailability`)
4. Admin (optionally) tunes penalty weights (`PUT /constraints/config`)
5. Admin triggers a run (`POST /scheduler/run`) — returns immediately
6. Frontend polls `GET /scheduler/status/{run_id}` until status is no longer `pending` or `running`
7. Admin reviews the timetable (`GET /timetable/{run_id}`) and optionally adjusts entries manually
8. Admin publishes (`POST /timetable/{run_id}/publish`) — lecturers and students can now see it

---

## Hard Constraints (always enforced)

| # | Constraint |
|---|-----------|
| H1 | Each course session has exactly one assignment |
| H2 | No room is used by two sessions simultaneously |
| H3 | No lecturer teaches two sessions at the same time |
| H4 | No student cohort (dept + level) has two classes at the same time |
| H5 | Lab courses → laboratory rooms only; theory courses → non-laboratory rooms only |

## Soft Constraints (penalised, configurable)

| # | Constraint | Default weight |
|---|-----------|----------------|
| S1 | Lecturer assigned to an unavailable slot | 100 |
| S2 | Same student group has back-to-back sessions | 10 |
| S3 | Multiple sessions of a course fall on the same day | 5 |
| S4 | Session placed in a room smaller than enrollment | 20 |

Adjust weights via `PUT /constraints/config` before running the scheduler.

---

## Known Limitations

- **Multiple lecturers per course**: when a course has more than one assigned lecturer the solver uses only the first assignment. Subsequent ones are stored for reference.
- **No student-to-course enrollment**: students are assigned to a cohort (dept + level), not to individual courses. The solver ensures no two courses at the same level clash.
- **Polling-based status updates**: the frontend polls `/scheduler/status/{run_id}`. A WebSocket endpoint would be more efficient but is not yet implemented.
