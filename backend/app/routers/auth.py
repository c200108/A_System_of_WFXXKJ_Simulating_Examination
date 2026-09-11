import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import (
    Exam,
    FeedbackReply,
    ImportLog,
    Paper,
    Question,
    TypingText,
    User,
)
from ..schemas import (
    PasswordChange,
    UserBulkIn,
    ProfileUpdate,
    TokenOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["认证"])

# 用户名只允许字母、数字、下划线、点、减号，且必须字母或数字开头。
# 限制这一圈是为了避免空格、中文、引号进到登录框里，出问题时不好排查。
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
USERNAME_MIN, PASSWORD_MIN = 3, 6


def check_username(username: str) -> str:
    """校验用户名，不合规就抛一句说得清的中文。返回去掉首尾空格的结果。"""
    name = (username or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if len(name) < USERNAME_MIN:
        raise HTTPException(
            status_code=400, detail=f"用户名太短，至少 {USERNAME_MIN} 个字符（现在是 {len(name)} 个）"
        )
    if len(name) > 64:
        raise HTTPException(status_code=400, detail="用户名太长，最多 64 个字符")
    if not USERNAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="用户名只能用字母、数字、下划线、点、减号，且要以字母或数字开头（不能有空格和中文）",
        )
    return name


def check_password(password: str) -> str:
    """校验密码强度。规则简单但每条都说清楚，别让人对着"请求失败"猜。"""
    pwd = password or ""
    if not pwd:
        raise HTTPException(status_code=400, detail="密码不能为空")
    if len(pwd) < PASSWORD_MIN:
        raise HTTPException(
            status_code=400, detail=f"密码太短，至少 {PASSWORD_MIN} 位（现在是 {len(pwd)} 位）"
        )
    if len(pwd) > 64:
        raise HTTPException(status_code=400, detail="密码太长，最多 64 位")
    if pwd.strip() != pwd:
        raise HTTPException(status_code=400, detail="密码开头或结尾有空格，请去掉")
    if pwd.isdigit():
        raise HTTPException(status_code=400, detail="密码不能是纯数字，请混入字母")
    return pwd


def _detach_user(db: Session, user_id: int) -> None:
    """真删账号前，把指向他的外键统统置空。

    这些外键都是可空的，置空后历史数据（题目、试卷、考试、成绩、导入记录、
    反馈回复）全部保留，只是"是谁建的"这条线索断了。不置空的话 MySQL 会
    直接报外键约束错误，删不掉。
    点赞记录是 CASCADE，会跟着账号一起删，不用在这里处理。
    """
    for model, field in (
        (Question, "created_by"),
        (Paper, "created_by"),
        (Exam, "created_by"),
        (ImportLog, "user_id"),
        (TypingText, "created_by"),
        (FeedbackReply, "user_id"),
    ):
        col = getattr(model, field)
        db.query(model).filter(col == user_id).update({col: None}, synchronize_session=False)


@router.post("/login", response_model=TokenOut, summary="教师登录")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码不正确")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用，请联系管理员")
    return TokenOut(
        access_token=create_access_token(user.id, user.role),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut, summary="当前登录人")
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut, summary="改自己的资料（姓名、任教年级班级、联系方式）")
def update_me(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """只能改这三项。用户名、角色、启停都得管理员来，避免有人给自己提权。"""
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(user, k, (v or "").strip())
    db.commit()
    db.refresh(user)
    return user


@router.post("/password", summary="修改自己的密码")
def change_password(
    body: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    pwd = check_password(body.new_password)
    if verify_password(pwd, user.password_hash):
        raise HTTPException(status_code=400, detail="新密码和原密码一样，换一个吧")
    user.password_hash = hash_password(pwd)
    db.commit()
    return {"ok": True}


@router.get("/users", response_model=list[UserOut], summary="教师列表（管理员）")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("/users", response_model=UserOut, summary="新增教师（管理员）")
def create_user(
    body: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    username = check_username(body.username)
    password = check_password(body.password)
    if body.role not in ("admin", "teacher"):
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 teacher")

    # 比对不分大小写：Wang 和 wang 看着像两个人，登录时却容易记混
    clash = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if clash:
        extra = "（该账号已停用，可在列表里直接启用）" if not clash.is_active else ""
        raise HTTPException(status_code=400, detail=f"用户名「{clash.username}」已存在{extra}")

    user = User(
        username=username,
        password_hash=hash_password(password),
        name=(body.name or username).strip()[:64],
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut, summary="改教师资料或重置密码（管理员）")
def update_user(
    user_id: int,
    body: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """老师忘了密码只能由管理员重置——系统里没有邮箱，找回不了。"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    data = body.model_dump(exclude_unset=True)

    if "role" in data:
        if data["role"] not in ("admin", "teacher"):
            raise HTTPException(status_code=400, detail="角色只能是 admin 或 teacher")
        # 把自己降级会立刻失去管理权限，且可能让系统一个管理员都不剩
        if user_id == admin.id and data["role"] != "admin":
            raise HTTPException(status_code=400, detail="不能取消自己的管理员身份")

    if "is_active" in data and user_id == admin.id and not data["is_active"]:
        raise HTTPException(status_code=400, detail="不能停用自己")

    if data.pop("password", None):
        user.password_hash = hash_password(check_password(body.password))

    for k, v in data.items():
        setattr(user, k, v)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", summary="停用教师（管理员）")
def deactivate_user(
    user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能停用自己")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = False
    db.commit()
    return {"ok": True}


def _guard(users: list[User], admin: User, db: Session, verb: str) -> None:
    """删除/停用前的两道闸：不能动自己，也不能把管理员清空。

    管理员一个不剩的话，谁都进不了账号管理页，只能去服务器上改数据库。
    """
    if any(u.id == admin.id for u in users):
        raise HTTPException(status_code=400, detail=f"不能{verb}自己的账号")

    losing = {u.id for u in users if u.role == "admin"}
    if losing:
        left = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active.is_(True), User.id.notin_(losing))
        )
        if not left:
            raise HTTPException(
                status_code=400, detail=f"这样{verb}之后就没有管理员了，先留一个再操作"
            )


@router.post("/users/bulk", summary="批量停用／启用／删除账号（管理员）")
def bulk_users(
    body: UserBulkIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """界面上勾一批再一次性处理。

    **delete 是真删，不可恢复** —— 界面上要手工输入「删除」两个字才放行。
    被删账号建过的题目、试卷、考试、成绩都保留，只是不再记录"是谁建的"。
    只是想让人登不上，用 disable，随时能再启用。
    """
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何账号")

    users = list(db.scalars(select(User).where(User.id.in_(ids))))
    if not users:
        raise HTTPException(status_code=404, detail="选中的账号都不存在了，刷新看看")

    if body.action == "enable":
        for u in users:
            u.is_active = True
        db.commit()
        return {"action": "enable", "affected": len(users)}

    _guard(users, admin, db, "停用" if body.action == "disable" else "删除")

    if body.action == "disable":
        for u in users:
            u.is_active = False
        db.commit()
        return {"action": "disable", "affected": len(users)}

    names = [u.name or u.username for u in users]
    for u in users:
        _detach_user(db, u.id)
        db.delete(u)
    db.commit()
    return {"action": "delete", "affected": len(users), "names": names}
