from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import Student, User
from .security import TOKEN_STUDENT, TOKEN_TEACHER, decode_token

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

    # 学生令牌绝不能进教师接口。教师和学生是两张表，光看 sub 是个数字
    # 分不出是谁，必须认这个类型标记。老版本令牌没有 typ，一律当作失效，
    # 让人重新登录一次 —— 宁可多登一次，也不能放错人进来。
    if payload.get("typ") != TOKEN_TEACHER:
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
        payload = decode_token(token)
        if payload.get("typ") != TOKEN_TEACHER:
            return None  # 学生令牌在这里也不算"登录的老师"
        user_id = int(payload.get("sub", 0))
    except Exception:
        return None
    user = db.get(User, user_id)
    return user if user and user.is_active else None


def get_current_student(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Student:
    """学生平台专用。教师令牌进不来，反过来也一样。"""
    cred_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("typ") != TOKEN_STUDENT:
            raise cred_error
        student_id = int(payload.get("sub", 0))
    except HTTPException:
        raise
    except Exception:
        raise cred_error

    student = db.get(Student, student_id)
    if not student or not student.is_active:
        raise cred_error
    return student


def get_optional_student(
    token: str | None = Depends(oauth2_optional), db: Session = Depends(get_db)
) -> Student | None:
    """公开接口想知道"是不是登录的学生"时用。没登录返回 None，不报错。

    打字训练两条路共用一个提交接口：学生平台上带着令牌来，成绩记到账号；
    公开的 /dazi 页面不带令牌，手填班级姓名。
    """
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("typ") != TOKEN_STUDENT:
            return None
        student_id = int(payload.get("sub", 0))
    except Exception:
        return None
    row = db.get(Student, student_id)
    return row if row and row.is_active else None
