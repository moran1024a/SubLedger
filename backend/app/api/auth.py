from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.errors import AppError
from app.models import User
from app.schemas import LoginRequest, UserResponse
from app.services.auth import authenticate_user, create_session, revoke_session
from app.services.logging import write_system_log, write_user_log

from app.services.users import lock_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client_key = request.client.host if request.client is not None else None
    try:
        user = authenticate_user(
            db,
            payload.username,
            payload.password,
            request.app.state.login_limiter,
            client_key,
        )
        token = create_session(db, user, request.app.state.settings.app.session_expire_days)
    except AppError as exc:
        known_user = db.scalar(select(User).where(User.username == payload.username))
        if known_user is not None:
            write_user_log(
                request.app.state.settings,
                user_id=known_user.id,
                level="WARNING",
                module="auth",
                event="login_failed",
                result="failure",
                request_id=request.state.request_id,
                message="登录失败",
                data={"reason": exc.code},
            )
        else:
            write_system_log(
                request.app.state.settings,
                level="WARNING",
                module="auth",
                event="login_failed",
                result="failure",
                request_id=request.state.request_id,
                message="登录失败",
                data={"reason": exc.code},
            )
        raise
    db.commit()
    response.set_cookie(
        key=request.app.state.settings.security.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.security.cookie_secure,
        path="/",
        max_age=request.app.state.settings.app.session_expire_days * 86400,
    )
    write_user_log(
        request.app.state.settings,
        user_id=user.id,
        level="INFO",
        module="auth",
        event="login_success",
        request_id=request.state.request_id,
        message="登录成功",
    )
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    token = request.cookies.get(request.app.state.settings.security.cookie_name)
    lock_user(db, user.id)
    revoke_session(db, token)
    db.commit()
    response.delete_cookie(request.app.state.settings.security.cookie_name, path="/")
    write_user_log(
        request.app.state.settings,
        user_id=user.id,
        level="INFO",
        module="auth",
        event="logout",
        request_id=request.state.request_id,
        message="退出登录",
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user
