from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        return False


# 令牌里的身份类型。教师和学生是两张表，同一个 id 在两边指的是不同的人，
# 所以令牌必须说清楚"这个 id 该去哪张表查"，否则学生令牌会被当成教师令牌。
TOKEN_TEACHER = "t"
TOKEN_STUDENT = "s"


def create_access_token(user_id: int, role: str, typ: str = TOKEN_TEACHER) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": typ,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
