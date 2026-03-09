"""
FastAPI dependency injection — get_current_user / get_optional_current_user
"""
import os

from fastapi import Cookie, HTTPException, Request
from jose import JWTError, jwt

from api import db

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


async def get_current_user(access_token: str | None = Cookie(default=None)) -> dict:
    """쿠키에서 JWT 추출 → 유저 반환. 인증 필요한 라우터에 Depends로 사용."""
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
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def get_optional_current_user(request: Request) -> dict | None:
    """인증 선택적 dependency — 로그인 시 유저 반환, 미로그인 시 None."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            return None
        user = db.get_user_by_id(user_id)
        if user and user.get("is_active"):
            return user
        return None
    except JWTError:
        return None
