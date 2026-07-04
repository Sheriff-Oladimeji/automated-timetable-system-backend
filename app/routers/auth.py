"""
Authentication router — login, token refresh, self-profile, and first-run admin setup.

Endpoints:
    POST /auth/login           — email + password → JWT
    GET  /auth/me              — returns current user's profile
    POST /auth/register-admin  — creates the first admin account (blocked once one exists)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from jose import jwt
from datetime import datetime, timedelta, timezone
import bcrypt as _bcrypt
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_user
from dotenv import load_dotenv
import os

load_dotenv()

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def create_access_token(user_id: int, role: str) -> str:
    """Create a signed JWT that expires after ACCESS_TOKEN_EXPIRE_MINUTES."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire, "role": role}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login", response_model=schemas.Token)
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email + password and receive a Bearer JWT."""
    user = db.query(models.User).filter(models.User.email == request.email).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive"
        )
    token = create_access_token(user.id, user.role.value)
    return {"access_token": token, "token_type": "bearer", "role": user.role}


@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_student(request: schemas.StudentRegisterRequest, db: Session = Depends(get_db)):
    """
    Student self-registration. Creates a User + Student profile in one step.
    Open endpoint — no auth required.
    """
    if db.query(models.User).filter(models.User.email == request.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    if db.query(models.Student).filter(models.Student.matric_number == request.matric_number).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matric number already registered")

    dept = db.query(models.Department).filter(models.Department.id == request.department_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    user = models.User(
        email=request.email,
        hashed_password=hash_password(request.password),
        role=models.UserRole.student,
    )
    db.add(user)
    db.flush()

    student = models.Student(
        user_id=user.id,
        department_id=request.department_id,
        level=request.level,
        matric_number=request.matric_number,
    )
    db.add(student)
    db.commit()
    return {"message": "Account created. Please log in."}


@router.post("/register-admin", status_code=status.HTTP_201_CREATED)
def register_admin(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    Bootstrap endpoint: creates the very first admin account.

    This endpoint is intentionally open (no auth required) so a fresh deployment
    can be initialised without a chicken-and-egg problem. It is automatically
    disabled as soon as any admin account exists in the database.
    """
    # Refuse if any admin already exists — prevents privilege escalation
    existing_admin = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.admin)
        .first()
    )
    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An admin account already exists. Use the admin panel to manage accounts.",
        )

    if db.query(models.User).filter(models.User.email == request.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    user = models.User(
        email=request.email,
        hashed_password=hash_password(request.password),
        role=models.UserRole.admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Admin account created successfully", "id": user.id}
