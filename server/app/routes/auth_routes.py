# server/app/routes/auth_routes.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db import get_db
from ..models import AppUser
from ..auth import verify_password, create_access_token, hash_password  # <-- add hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(AppUser).filter(AppUser.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        return {"ok": False, "message": "Invalid credentials"}
    token = create_access_token({"uid": user.id, "role": user.role})
    return {"ok": True, "token": token, "role": user.role, "username": user.username}


# =========================
# Change Password (NEW)
# =========================
class ChangePasswordIn(BaseModel):
    username: str
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(data: ChangePasswordIn, db: Session = Depends(get_db)):
    user = db.query(AppUser).filter(AppUser.username == data.username).first()
    if not user:
        return {"ok": False, "message": "User not found"}

    if not verify_password(data.old_password, user.password_hash):
        return {"ok": False, "message": "Current password is incorrect"}

    if len(data.new_password) < 6:
        return {"ok": False, "message": "New password must be at least 6 characters"}

    user.password_hash = hash_password(data.new_password)
    db.commit()

    return {"ok": True, "message": "Password changed successfully"}
