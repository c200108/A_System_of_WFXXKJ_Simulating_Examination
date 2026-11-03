"""教师端「API」板块的管理接口（教师令牌）（2.16.0）。

**严格按老师隔离**：老师只看得到、管得着自己建的 API；别人的一律 404（连「有这个 API」
都不告诉）。管理员看全部、能按老师筛选、能把 API 转给另一位老师。
和考试不一样 —— 管理员建的 API 普通老师也看不到。

第三方往里送数据走 routers/hook.py，不经过这里。
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import clock
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import DataApi, DataRecord, SchoolClass, User
from ..services import dataapi as svc
from ..services import dataapi_prompt as prompt_svc
from ..services import recycle
from .hook import record_out

router = APIRouter(prefix="/api/data-apis", tags=["API 数据板块"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------- 入参
class ApiCreate(BaseModel):
    name: str = Field(max_length=64)
    description: str = Field(default="", max_length=2000)
    template: str = "custom"


class ApiUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    template: str | None = None
    status: str | None = None
    accept_from: datetime | None = None
    accept_until: datetime | None = None
    clear_window: bool = False
    allowed_origins: str | None = Field(default=None, max_length=1000)
    dedupe: str | None = None
    allow_get: bool | None = None
    public_summary: bool | None = None
    class_ids: list[int] | None = None
    field_meta: dict | None = None


class RotateIn(BaseModel):
    which: str = "write"            # write / read
    enable: bool = True             # read 专用：False 关掉读取接口


class TransferIn(BaseModel):
    owner_id: int


class FlagIn(BaseModel):
    ids: list[int]
    flag: str = "invalid"           # normal / invalid


class DeleteRecordsIn(BaseModel):
    ids: list[int] = []
    all: bool = False


# ---------------------------------------------------------------- 取
def _visible(stmt, me: User):
    return stmt if me.role == "admin" else stmt.where(DataApi.owner_id == me.id)


def _get(db: Session, api_id: int, me: User) -> DataApi:
    api = db.get(DataApi, api_id)
    if not api or (me.role != "admin" and api.owner_id != me.id):
        raise HTTPException(status_code=404, detail="这个 API 不存在")
    return api


def _base_url(request: Request) -> str:
    """接收地址前面那段。.env 配了 PUBLIC_BASE_URL 就用它；没配就照老师现在打开网页用的地址。"""
    pub = (settings.public_url or "").strip().rstrip("/")
    if pub:
        return pub
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _owner_names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: (u.name or u.username) for u in db.scalars(select(User).where(User.id.in_(ids)))}


def _summary(db: Session, api: DataApi, owners: dict, today_counts: dict) -> dict:
    return {
        "id": api.id, "name": api.name, "description": api.description, "template": api.template,
        "template_name": svc.TEMPLATES.get(api.template, api.template),
        "status": api.status, "key": api.key, "owner_id": api.owner_id,
        "owner_name": owners.get(api.owner_id or 0, "（已无主）"),
        "record_count": api.record_count or 0, "today_count": today_counts.get(api.id, 0),
        "last_received_at": api.last_received_at, "created_at": api.created_at,
    }


def _detail(db: Session, api: DataApi, request: Request) -> dict:
    owners = _owner_names(db, [api.owner_id])
    base = _base_url(request)
    cids = svc.class_ids_of(api)
    classes = db.scalars(select(SchoolClass).where(SchoolClass.id.in_(cids))).all() if cids else []
    try:
        meta = json.loads(api.field_meta or "{}")
    except ValueError:
        meta = {}
    return {
        **_summary(db, api, owners, {}),
        "endpoint": f"{base}/api/hook/{api.key}",
        "sdk_url": f"{base}/api/hook/sdk.js",
        "write_token": api.write_token,
        "read_token": api.read_token,
        "accept_from": api.accept_from, "accept_until": api.accept_until,
        "allowed_origins": api.allowed_origins, "dedupe": api.dedupe,
        "allow_get": api.allow_get, "public_summary": api.public_summary,
        "class_ids": cids, "class_names": [c.display for c in classes],
        "field_meta": meta,
        "max_records": svc.MAX_RECORDS,
        "templates": svc.TEMPLATES, "type_names": svc.TYPE_NAMES,
    }


# ---------------------------------------------------------------- API 本身
@router.get("", summary="API 列表（管理员看全部，可按老师筛选）")
def list_apis(owner_id: int | None = None, me: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    stmt = _visible(select(DataApi), me)
    if owner_id and me.role == "admin":
        stmt = stmt.where(DataApi.owner_id == owner_id)
    rows = db.scalars(stmt.order_by(DataApi.id.desc())).all()
    start = clock.now().replace(hour=0, minute=0, second=0)
    today = dict(db.execute(
        select(DataRecord.api_id, func.count()).where(
            DataRecord.api_id.in_([r.id for r in rows]), DataRecord.received_at >= start)
        .group_by(DataRecord.api_id)).all()) if rows else {}
    owners = _owner_names(db, [r.owner_id for r in rows])
    out = {"items": [_summary(db, r, owners, today) for r in rows], "templates": svc.TEMPLATES}
    if me.role == "admin":
        out["teachers"] = [{"id": u.id, "name": u.name or u.username}
                           for u in db.scalars(select(User).order_by(User.id))]
    return out


@router.post("", summary="新建 API")
def create_api(body: ApiCreate, request: Request, me: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填 API 名称")
    if body.template not in svc.TEMPLATES:
        raise HTTPException(status_code=400, detail="用途模板不对")
    key = svc.new_key()
    while db.scalar(select(DataApi.id).where(DataApi.key == key)):
        key = svc.new_key()
    api = DataApi(owner_id=me.id, name=name, description=body.description.strip(),
                  template=body.template, key=key, write_token=svc.new_token(),
                  status="active", dedupe="all", field_meta="{}")
    db.add(api)
    db.commit()
    db.refresh(api)
    return _detail(db, api, request)


@router.get("/{api_id}", summary="API 详情（含密钥和接入地址）")
def get_api(api_id: int, request: Request, me: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    return _detail(db, _get(db, api_id, me), request)


@router.put("/{api_id}", summary="改 API 的名称、描述、接收设置")
def update_api(api_id: int, body: ApiUpdate, request: Request, me: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        if not (data["name"] or "").strip():
            raise HTTPException(status_code=400, detail="API 名称不能为空")
        api.name = data["name"].strip()
    if "description" in data:
        api.description = (data["description"] or "").strip()
    if "template" in data:
        if data["template"] not in svc.TEMPLATES:
            raise HTTPException(status_code=400, detail="用途模板不对")
        api.template = data["template"]
    if "status" in data:
        if data["status"] not in ("active", "paused"):
            raise HTTPException(status_code=400, detail="状态只能是 active 或 paused")
        api.status = data["status"]
    if body.clear_window:
        api.accept_from = api.accept_until = None
    else:
        if "accept_from" in data:
            api.accept_from = data["accept_from"].replace(tzinfo=None, microsecond=0) if data["accept_from"] else None
        if "accept_until" in data:
            api.accept_until = data["accept_until"].replace(tzinfo=None, microsecond=0) if data["accept_until"] else None
    if api.accept_from and api.accept_until and api.accept_from >= api.accept_until:
        raise HTTPException(status_code=400, detail="接收开始时间要早于截止时间")
    if "allowed_origins" in data:
        lines = []
        for x in (data["allowed_origins"] or "").replace(",", "\n").splitlines():
            x = x.strip().rstrip("/")
            if not x:
                continue
            if x != "*" and not x.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail=f"「{x}」不是网址，要以 http:// 或 https:// 开头")
            lines.append(x)
        api.allowed_origins = "\n".join(lines)[:1000]
    redo = False
    if "dedupe" in data:
        if data["dedupe"] not in ("all", "latest"):
            raise HTTPException(status_code=400, detail="重复提交只能选 all 或 latest")
        redo = data["dedupe"] != api.dedupe
        api.dedupe = data["dedupe"]
    if "allow_get" in data:
        api.allow_get = bool(data["allow_get"])
    if "public_summary" in data:
        api.public_summary = bool(data["public_summary"])
    if "class_ids" in data:
        ids = sorted({int(i) for i in data["class_ids"] or []})
        if ids:
            found = {c.id for c in db.scalars(select(SchoolClass).where(SchoolClass.id.in_(ids)))}
            ids = [i for i in ids if i in found]
        api.class_ids = ",".join(map(str, ids))[:255]
    if "field_meta" in data:
        meta = {}
        for k, v in (data["field_meta"] or {}).items():
            if not isinstance(v, dict):
                continue
            meta[str(k)[:120]] = {"label": str(v.get("label") or "")[:40],
                                  "kind": v.get("kind") if v.get("kind") in ("number", "text", "choice") else "",
                                  "hidden": bool(v.get("hidden"))}
        api.field_meta = json.dumps(dict(list(meta.items())[:200]), ensure_ascii=False)
    if redo:
        svc.resupersede(db, api)
    db.commit()
    db.refresh(api)
    return _detail(db, api, request)


@router.get("/{api_id}/ai-prompt", summary="AI 专用提示词：交给 AI 生成接好这个 API 的教学网页")
def ai_prompt(api_id: int, request: Request, base: str = "", me: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """base 是前端按学生能访问的地址算出来的前缀（网页 studentLink、APP 连的服务器地址）：
    后端在 nginx 后面看到的 Host 不带端口，自己拼会少了 :3315。不传或不像网址就用 _base_url。"""
    api = _get(db, api_id, me)
    root = _base_url(request)
    p = urlsplit(base.strip())
    if p.scheme in ("http", "https") and p.netloc:
        root = f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}"
    cids = svc.class_ids_of(api)
    classes = db.scalars(select(SchoolClass).where(SchoolClass.id.in_(cids))).all() if cids else []
    endpoint = f"{root}/api/hook/{api.key}"
    return {"prompt": prompt_svc.build(api, endpoint, [c.display for c in classes]), "endpoint": endpoint}


@router.post("/{api_id}/rotate-token", summary="重新生成写入密钥／开关读取密钥")
def rotate_token(api_id: int, body: RotateIn, request: Request, me: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    if body.which == "write":
        api.write_token = svc.new_token()
    elif body.which == "read":
        api.read_token = svc.new_token() if body.enable else ""
    else:
        raise HTTPException(status_code=400, detail="which 只能是 write 或 read")
    db.commit()
    return _detail(db, api, request)


@router.post("/{api_id}/transfer", summary="把 API 转给另一位老师（管理员）")
def transfer(api_id: int, body: TransferIn, request: Request, me: User = Depends(require_admin),
             db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    to = db.get(User, body.owner_id)
    if not to or not to.is_active:
        raise HTTPException(status_code=404, detail="这位老师不存在或已停用")
    api.owner_id = to.id
    db.commit()
    return _detail(db, api, request)


@router.delete("/{api_id}", summary="删除 API（连同数据进回收站，7 天内可还原）")
def delete_api(api_id: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    recycle.trash(db, me, "data_api", f"API「{api.name}」", DataApi, [api.id],
                  detail=f"含 {api.record_count or 0} 条数据")
    db.delete(api)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 数据表单
def _filtered(stmt, api: DataApi, *, type_: str, activity: str, page: str, class_name: str,
              keyword: str, matched: str, flag: str, since, until):
    stmt = stmt.where(DataRecord.api_id == api.id)
    if type_:
        stmt = stmt.where(DataRecord.type == type_)
    if activity:
        stmt = stmt.where(or_(DataRecord.activity_id == activity, DataRecord.activity_name == activity))
    if page:
        stmt = stmt.where(DataRecord.page == ("" if page == "-" else page))
    if class_name:
        stmt = stmt.where(DataRecord.class_name == class_name)
    if matched == "yes":
        stmt = stmt.where(DataRecord.student_id.is_not(None))
    elif matched == "no":
        stmt = stmt.where(DataRecord.student_id.is_(None))
    if flag in ("normal", "invalid"):
        stmt = stmt.where(DataRecord.flag == flag)
    if since:
        stmt = stmt.where(DataRecord.received_at >= since)
    if until:
        stmt = stmt.where(DataRecord.received_at <= until)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(DataRecord.student_name.like(like), DataRecord.student_no.like(like),
                              DataRecord.comment.like(like), DataRecord.payload.like(like)))
    return stmt


def _filters(type: str = "", activity: str = "", page_url: str = "", class_name: str = "",
             keyword: str = "", matched: str = "", flag: str = "", since: datetime | None = None,
             until: datetime | None = None) -> dict:
    return {"type_": type, "activity": activity, "page": page_url, "class_name": class_name,
            "keyword": keyword, "matched": matched, "flag": flag,
            "since": since.replace(tzinfo=None) if since else None,
            "until": until.replace(tzinfo=None) if until else None}


@router.get("/{api_id}/records", summary="数据表单：分页 + 筛选")
def list_records(api_id: int, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500),
                 f: dict = Depends(_filters), me: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    base = _filtered(select(DataRecord), api, **f)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(DataRecord.received_at.desc(), DataRecord.id.desc())
                      .offset((page - 1) * size).limit(size)).all()
    items, cols = [], {}
    for r in rows:
        o = record_out(r)
        o["student_matched"] = r.student_id is not None
        o["student_id"] = r.student_id
        o["source_ip"], o["origin"] = r.source_ip, r.origin
        o["fields"] = svc.flat(o["payload"]) if isinstance(o["payload"], dict) else {}
        for k in o["fields"]:
            cols[k] = cols.get(k, 0) + 1
        items.append(o)
    try:
        meta = json.loads(api.field_meta or "{}")
    except ValueError:
        meta = {}
    known = set(svc.ALIASES) | {"data", "client_id", "q"}
    for names in svc.ALIASES.values():
        known |= set(names)
    columns = [{"key": k, "label": (meta.get(k) or {}).get("label") or k, "kind": (meta.get(k) or {}).get("kind", ""),
                "hidden": (meta.get(k) or {}).get("hidden", False)}
               for k, _ in sorted(cols.items(), key=lambda kv: -kv[1])
               if k.split(".")[-1] not in known or k in meta][:40]
    # 筛选下拉的候选
    opts = lambda col: [x for x in db.scalars(  # noqa: E731
        select(col).where(DataRecord.api_id == api.id).distinct().limit(200)) if x]
    return {"total": total, "items": items, "columns": columns,
            "options": {"types": opts(DataRecord.type), "activities": opts(DataRecord.activity_name),
                        "pages": opts(DataRecord.page), "classes": opts(DataRecord.class_name)},
            "type_names": svc.TYPE_NAMES}


@router.patch("/{api_id}/records", summary="批量标记有效／无效")
def flag_records(api_id: int, body: FlagIn, me: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    if body.flag not in ("normal", "invalid"):
        raise HTTPException(status_code=400, detail="flag 只能是 normal 或 invalid")
    n = 0
    for i in range(0, len(body.ids), 500):
        part = body.ids[i:i + 500]
        for r in db.scalars(select(DataRecord).where(DataRecord.api_id == api.id, DataRecord.id.in_(part))):
            r.flag = body.flag
            n += 1
    db.commit()
    return {"ok": True, "count": n}


@router.post("/{api_id}/records/delete", summary="批量删除数据（进回收站）")
def delete_records(api_id: int, body: DeleteRecordsIn, me: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    q = select(DataRecord.id).where(DataRecord.api_id == api.id)
    if not body.all:
        if not body.ids:
            return {"ok": True, "count": 0}
        q = q.where(DataRecord.id.in_(body.ids[:10000]))
    ids = list(db.scalars(q))
    if ids:
        recycle.trash(db, me, "data_record", f"API「{api.name}」的 {len(ids)} 条数据", DataRecord, ids)
        recycle.delete_ids(db, DataRecord, ids)
        svc.recount(db, api)
        if api.dedupe == "latest":
            svc.resupersede(db, api)
    db.commit()
    return {"ok": True, "count": len(ids)}


@router.get("/{api_id}/sources", summary="来源网页：每个使用这个 API 的网页各收了多少")
def sources(api_id: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    rows = db.execute(
        select(DataRecord.page, func.count(), func.count(func.distinct(DataRecord.student_no)),
               func.count(func.distinct(DataRecord.student_id)), func.max(DataRecord.received_at),
               func.min(DataRecord.received_at), func.avg(DataRecord.score))
        .where(DataRecord.api_id == api.id).group_by(DataRecord.page)
        .order_by(func.max(DataRecord.received_at).desc())).all()
    return {"items": [{"page": p or "", "records": n, "people": ppl, "matched": m,
                       "last_at": last, "first_at": first,
                       "avg_score": round(a, 2) if a is not None else None}
                      for p, n, ppl, m, last, first, a in rows]}


@router.get("/{api_id}/stats", summary="数据大图要的统计")
def api_stats(api_id: int, type: str = "", activity: str = "", page_url: str = "", class_name: str = "",
              minutes: int = 0, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    since = clock.now() - timedelta(minutes=minutes) if minutes > 0 else None
    s = svc.stats(db, api, type_=type, activity=activity, page=page_url, class_name=class_name, since=since)
    s["api"] = {"id": api.id, "name": api.name, "template": api.template, "status": api.status}
    return s


@router.post("/{api_id}/test", summary="发一条测试数据")
def send_test(api_id: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    sample = {
        "type": svc.DEFAULT_TYPE.get(api.template, "data"),
        "activity": {"id": "test", "name": "测试数据"},
        "student": {"no": "", "name": "测试学生", "class": ""},
        "score": 8, "max_score": 10,
        "answers": [{"q": "1", "answer": "B", "correct": True, "score": 5, "max": 5},
                    {"q": "2", "answer": "C", "correct": False, "score": 3, "max": 5}],
        "ratings": [{"item": "参与度", "score": 4, "max": 5}, {"item": "合作", "score": 5, "max": 5}],
        "comment": "这是一条测试数据，可以在数据表单里删除",
        "page": "教师端「发一条测试数据」",
    }
    try:
        svc.accepting(api)
    except svc.Rejected as e:
        raise HTTPException(status_code=400, detail=e.message)
    res = svc.store(db, api, [sample], {"ip": "", "device": "", "origin": "", "ua": "教师端测试"})
    db.commit()
    if not res[0].get("ok"):
        raise HTTPException(status_code=400, detail=res[0].get("message"))
    return res[0]


@router.get("/{api_id}/export", summary="导出数据（xlsx / csv）")
def export(api_id: int, format: str = "xlsx", f: dict = Depends(_filters),
           me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api = _get(db, api_id, me)
    rows = db.scalars(_filtered(select(DataRecord), api, **f).order_by(DataRecord.received_at)
                      .limit(svc.MAX_RECORDS)).all()
    outs = [record_out(r) for r in rows]
    dyn: list[str] = []
    for o in outs:
        for k in (svc.flat(o["payload"]) if isinstance(o["payload"], dict) else {}):
            if k not in dyn:
                dyn.append(k)
    try:
        meta = json.loads(api.field_meta or "{}")
    except ValueError:
        meta = {}
    head = ["编号", "收到时间", "类型", "活动", "学号", "姓名", "班级", "对上名单", "被评人", "得分", "满分",
            "评语", "来源网页", "状态"] + [(meta.get(k) or {}).get("label") or k for k in dyn[:60]]
    table = [head]
    for o, r in zip(outs, rows):
        fl = svc.flat(o["payload"]) if isinstance(o["payload"], dict) else {}
        table.append([
            r.id, r.received_at.strftime("%Y-%m-%d %H:%M:%S") if r.received_at else "",
            svc.TYPE_NAMES.get(r.type, r.type), r.activity_name or r.activity_id, r.student_no, r.student_name,
            r.class_name, "是" if r.student_id else "", r.target_name or r.target_no,
            r.score if r.score is not None else "", r.max_score if r.max_score is not None else "",
            r.comment, r.page, "无效" if r.flag == "invalid" else ("被替代" if r.superseded else ""),
        ] + [_cell(fl.get(k)) for k in dyn[:60]])
    name = f"{api.name}-数据-{clock.now():%Y%m%d%H%M}"
    if format == "csv":
        buf = io.StringIO()
        csv.writer(buf).writerows(table)
        data = ("﻿" + buf.getvalue()).encode("utf-8")
        mime, ext = "text/csv; charset=utf-8", "csv"
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "数据"
        for row in table:
            ws.append(row)
        bio = io.BytesIO()
        wb.save(bio)
        data, mime, ext = bio.getvalue(), XLSX_MIME, "xlsx"
    return Response(data, media_type=mime, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}.{ext}"})


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)[:32000]
    if isinstance(v, bool):
        return "是" if v else "否"
    return v if isinstance(v, (int, float)) else str(v)[:32000]
