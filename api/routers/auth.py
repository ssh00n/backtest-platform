"""
Auth router — register / login / logout / refresh / me
JWT + HttpOnly 쿠키 방식
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field

from api import db

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Config ───────────────────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Schemas ──────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    username: str
    is_active: bool
    created_at: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, response: Response):
    # 이메일 중복 체크
    existing = db.get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = hash_password(req.password)
    user = db.create_user(req.email, req.username, password_hash)
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")

    # 가입 즉시 로그인 처리
    access_token = create_access_token(user["id"])
    refresh_token = create_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db.save_refresh_token(user["id"], refresh_token, expires_at)
    set_auth_cookies(response, access_token, refresh_token)

    return user


@router.post("/login", response_model=UserOut)
async def login(req: LoginRequest, response: Response):
    user = db.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled")

    access_token = create_access_token(user["id"])
    refresh_token = create_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db.save_refresh_token(user["id"], refresh_token, expires_at)
    set_auth_cookies(response, access_token, refresh_token)

    # password_hash 제거 후 반환
    user.pop("password_hash", None)
    return user


@router.post("/logout")
async def logout(response: Response, refresh_token: str | None = Cookie(default=None)):
    if refresh_token:
        db.delete_refresh_token(refresh_token)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/api/auth/refresh")
    return {"message": "Logged out"}


@router.post("/refresh", response_model=UserOut)
async def refresh(response: Response, refresh_token: str | None = Cookie(default=None)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    token_record = db.get_refresh_token(refresh_token)
    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    expires_at = token_record["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        db.delete_refresh_token(refresh_token)
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.get_user_by_id(token_record["user_id"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    new_access_token = create_access_token(user["id"])
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return user


@router.get("/me", response_model=UserOut)
async def me(access_token: str | None = Cookie(default=None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(access_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User not found")
    return user
