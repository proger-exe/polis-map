from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models import AppSetting, User


def current_user(x_user_id: int = Header(default=1), db: Session = Depends(get_db)) -> User:
    user = db.get(User, x_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown MVP user")
    return user


def require_roles(user: User, roles: set[str]) -> None:
    if user.role == "admin":
        return
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Role is not allowed for this action")


def require_admin_token(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Admin token is required")
    token = authorization.removeprefix(prefix).strip()
    row = db.get(AppSetting, f"admin_token:{token}")
    if not row:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    expires_at = datetime.fromisoformat(row.value)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Admin token expired")
    user = db.get(User, 1)
    if not user or user.role != "admin":
        raise HTTPException(status_code=401, detail="Admin user is missing")
    return user


def admin_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.admin_token_ttl_hours)
