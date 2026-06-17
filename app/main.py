from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import (
    auth,
    resources,
    constraints,
    scheduler,
    timetable,
    lecturer,
    student,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Timetable Scheduling System",
    description="Constraint-based automated timetable scheduler for CSET, UNIOSUN",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(resources.router, prefix="/resources", tags=["Resources"])
app.include_router(constraints.router, prefix="/constraints", tags=["Constraints"])
app.include_router(scheduler.router, prefix="/scheduler", tags=["Scheduler"])
app.include_router(timetable.router, prefix="/timetable", tags=["Timetable"])
app.include_router(lecturer.router, prefix="/lecturer", tags=["Lecturer"])
app.include_router(student.router, prefix="/student", tags=["Student"])


@app.get("/")
def root():
    return {"message": "Timetable Scheduling API is running"}
