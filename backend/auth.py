"""
CropGuard AI — authentication and authorization.
JWT tokens (python-jose) + bcrypt password hashing (passlib with native bcrypt fallback).
"""

import sys
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

import os

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Query, Session

from database import get_db
from models import Farm, ManagerFarmAssignment, User
from schemas import UserOut

# JWT — 7-day expiry; set JWT_SECRET in production
JWT_SECRET = os.getenv("JWT_SECRET", "cropguard-dev-jwt-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login/form")
bearer_scheme = HTTPBearer(auto_error=False)

# passlib bcrypt (falls back to native bcrypt on Python 3.14+ if passlib backend fails)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    try:
        return _pwd_context.hash(password)
    except Exception:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_user_from_token(token, db)


async def get_current_user_bearer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _resolve_user_from_token(credentials.credentials, db)


def _resolve_user_from_token(token: str, db: Session) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = get_user_by_email(db, email)
    if user is None:
        raise credentials_exc
    return user


def require_roles(*roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


def user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
    )


def _manager_assigned_farm_ids(db: Session, manager_id: int) -> list[int]:
    rows = (
        db.query(ManagerFarmAssignment.farm_id)
        .filter(ManagerFarmAssignment.manager_id == manager_id)
        .all()
    )
    return [r[0] for r in rows]


# ── Role-based farm access ──────────────────────────────────────────────────────
def farms_query_for_user(db: Session, user: User) -> Query:
    """
    farmer  → own farms only (user_id)
    manager → farms assigned via manager_farm_assignments (fallback: manager_id)
    admin   → all farms
    """
    q = db.query(Farm)
    if user.role == "admin":
        return q
    if user.role == "manager":
        assigned_ids = _manager_assigned_farm_ids(db, user.id)
        if assigned_ids:
            return q.filter(Farm.id.in_(assigned_ids))
        return q.filter(Farm.manager_id == user.id)
    return q.filter(Farm.user_id == user.id)


def get_accessible_farm_ids(db: Session, user: User) -> list[int]:
    return [f.id for f in farms_query_for_user(db, user).all()]


def can_access_farm(db: Session, user: User, farm: Farm) -> bool:
    if user.role == "admin":
        return True
    if user.role == "manager":
        assigned_ids = _manager_assigned_farm_ids(db, user.id)
        if assigned_ids:
            return farm.id in assigned_ids
        return farm.manager_id == user.id
    return farm.user_id == user.id


def get_farm_for_user(db: Session, farm_id: int, user: User) -> Farm:
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")
    if not can_access_farm(db, user, farm):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return farm
