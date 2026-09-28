"""
PMAS — Security & Authentication
JWT-based auth with role-based access control (RBAC).
Supports: patient, pharmacist, admin roles.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db, User, UserRole
from schemas import TokenResponse

# ─── Config ─────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "pmas-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    import bcrypt
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False


def create_access_token(user_id: UUID, role: str) -> str:
    """Create a JWT access token."""
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# ─── Dependencies ───────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get the current authenticated user from JWT token."""
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    return user


async def require_pharmacist_or_admin(
    user: User = Depends(get_current_user)
) -> User:
    """Allow both pharmacist and admin roles."""
    if user.role not in (UserRole.pharmacist, UserRole.admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacist or admin access required"
        )
    return user


async def require_admin(
    user: User = Depends(get_current_user)
) -> User:
    """Allow only the admin role (account governance endpoints)."""
    if user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required"
        )
    return user
