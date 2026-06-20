"""
FastAPI dependency functions for authentication and role-based access control.

Usage in route handlers:
    current_user = Depends(get_current_user)   # any authenticated user
    _            = Depends(require_admin)       # admin only
    _            = Depends(require_lecturer)    # lecturer or admin
    _            = Depends(require_student)     # student or admin
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from app.database import get_db
from app import models
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    """Decode JWT and return the authenticated User, or raise 401."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # sub is stored as a string; cast to int before querying
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Raise 403 if the caller is not an admin."""
    if current_user.role != models.UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_lecturer(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """Raise 403 if the caller is neither a lecturer nor an admin."""
    if current_user.role not in [models.UserRole.lecturer, models.UserRole.admin]:
        raise HTTPException(status_code=403, detail="Lecturer access required")
    return current_user


def require_student(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """Raise 403 if the caller is neither a student nor an admin."""
    if current_user.role not in [models.UserRole.student, models.UserRole.admin]:
        raise HTTPException(status_code=403, detail="Student access required")
    return current_user
