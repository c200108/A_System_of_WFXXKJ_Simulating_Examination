from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# 公开接口用：带令牌就认出是谁，不带也照样放行
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    cred_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
    except Exception:
        raise cred_error
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise cred_error
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def get_optional_user(
    token: str | None = Depends(oauth2_optional), db: Session = Depends(get_db)
) -> User | None:
    """公开接口想知道"看的人是谁"时用。没登录、令牌过期都返回 None，不报错。

    典型场景：反馈列表谁都能看，但登录的老师要看到自己有没有点过赞。
    """
    if not token:
        return None
    try:
        user_id = int(decode_token(token).get("sub", 0))
    except Exception:
        return None
    user = db.get(User, user_id)
    return user if user and user.is_active else None
