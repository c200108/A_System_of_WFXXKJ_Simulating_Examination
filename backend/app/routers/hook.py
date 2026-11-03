"""教师端「API」的公开一侧：第三方网页往这里送数据、取汇总（2.16.0）。

    POST /api/hook/{key}             收数据（JSON／批量数组／sendBeacon／HTML 表单）
    GET  /api/hook/{key}?...         收数据（老师在设置里打开「允许 GET」才行）
    GET  /api/hook/{key}/records     取记录（读取密钥）
    GET  /api/hook/{key}/summary     取汇总，不含个人信息（读取密钥；老师允许的话写入密钥也行）
    GET  /api/hook/sdk.js            接入小工具

不认教师令牌，只认每个 API 自己的密钥。跨域在 main.py 的 HookCors 里单独放行 ——
全站的 CORS 白名单只有本站地址，第三方网页会被挡在外面。

传入传出规范见 docs/API数据接入规范.md。
"""

from __future__ import annotations

import hmac
import json
import pathlib
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DataApi, DataRecord
from ..services import dataapi as svc
from ..services import throttle

router = APIRouter(prefix="/api/hook", tags=["API 数据接收（公开）"])

SDK_FILE = pathlib.Path(__file__).resolve().parent.parent / "static" / "wfxx-collect.js"

# 限频：同一设备每分钟、同一 API 每小时。机房整体一个出口 IP，认不出设备时按 IP 放宽
PER_DEVICE_MIN = 30
PER_IP_MIN = 600
PER_API_HOUR = 5000


def _fail(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"ok": False, "code": code, "message": message}, status_code=status,
                        headers=headers or {})


def _token(request: Request, body: dict | None) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or request.query_params.get("token")
            or (str(body.get("_token") or "") if isinstance(body, dict) else "")).strip()


def _same(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def _origin_ok(api: DataApi, request: Request) -> bool:
    allowed = [x.strip().rstrip("/") for x in (api.allowed_origins or "").splitlines() if x.strip()]
    if not allowed:
        return True
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin:
        # 不是浏览器跨域发来的（服务器端程序、curl）：白名单只管浏览器，靠密钥
        ref = request.headers.get("referer") or ""
        if not ref:
            return True
        p = urlsplit(ref)
        origin = f"{p.scheme}://{p.netloc}"
    return origin in allowed or "*" in allowed


def _api(db: Session, key: str) -> DataApi | None:
    return db.scalar(select(DataApi).where(DataApi.key == key)) if key and len(key) <= 24 else None


async def _parse(request: Request) -> tuple[object, str]:
    """读请求体 → (数据, 出错码)。认 JSON、纯文本里的 JSON、表单、multipart。"""
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype == "multipart/form-data":
        form = await request.form()
        out: dict = {}
        for k, v in form.multi_items():
            v = getattr(v, "filename", None) and {"文件": v.filename} or v
            out[k] = [*out[k], v] if isinstance(out.get(k), list) else ([out[k], v] if k in out else v)
        return out, ""
    raw = await request.body()
    if len(raw) > svc.MAX_BODY_BYTES:
        return None, "PAYLOAD_TOO_LARGE"
    if not raw.strip():
        return None, "EMPTY"
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gb18030")
        except UnicodeDecodeError:
            return None, "UNSUPPORTED_TYPE"
    if ctype == "application/x-www-form-urlencoded":
        out = {}
        for k, v in parse_qsl(text, keep_blank_values=True):
            out[k] = [*out[k], v] if isinstance(out.get(k), list) else ([out[k], v] if k in out else v)
        return out, ""
    try:
        return json.loads(text), ""
    except ValueError:
        if ctype in ("application/json",):
            return None, "BAD_JSON"
        if "=" in text and "\n" not in text.strip() and ctype in ("", "text/plain"):
            return dict(parse_qsl(text, keep_blank_values=True)), ""
        return {"text": text[:svc.MAX_ITEM_BYTES]}, ""


def _items(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        keys = set(data) - {"_token", "_redirect"}
        if keys == {"records"} and isinstance(data["records"], list):
            return data["records"]
        return [{k: v for k, v in data.items() if k not in ("_token", "_redirect")}]
    return [data]


def _meta(request: Request) -> dict:
    ip = (request.headers.get("x-real-ip") or (request.client.host if request.client else "") or "")
    return {"ip": ip, "device": (request.headers.get("x-device-id") or "")[:80],
            "origin": request.headers.get("origin") or "", "ua": request.headers.get("user-agent") or "",
            "referer": request.headers.get("referer") or ""}


def _limit(db: Session, api: DataApi, request: Request, n: int) -> None:
    who = throttle.device_of(request)
    per = PER_DEVICE_MIN if who.startswith("d:") else PER_IP_MIN
    throttle.check(db, "hook", f"{api.id}:{who}", per, 60, "提交太频繁了")
    throttle.check(db, "hook_api", str(api.id), PER_API_HOUR, 3600, "这个 API 这一小时收得太多了")
    for _ in range(min(n, 50)):
        throttle.hit(db, "hook", f"{api.id}:{who}")
    throttle.hit(db, "hook_api", str(api.id))


def _form_reply(request: Request, data, ok: bool, msg: str):
    """纯 HTML 表单提交上来的：给 _redirect 就跳回去，否则回一个能看懂的小页面，不让学生看见一串 JSON。"""
    target = data.get("_redirect") if isinstance(data, dict) else None
    if isinstance(target, str) and target.startswith(("http://", "https://")):
        sep = "&" if "?" in target else "?"
        return RedirectResponse(f"{target}{sep}wfxx={'ok' if ok else 'fail'}", status_code=303)
    color = "#16a34a" if ok else "#dc2626"
    return HTMLResponse(
        f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<title>{'提交成功' if ok else '提交失败'}</title>"
        f"<div style='font:18px sans-serif;text-align:center;margin-top:20vh;color:{color}'>"
        f"{'✓ 提交成功' if ok else '✗ ' + msg}<br><small style='color:#888'>可以关闭这个页面了</small></div>",
        status_code=200 if ok else 400)


async def _receive(key: str, request: Request, db: Session, data, err: str):
    from fastapi import HTTPException

    api = _api(db, key)
    if not api:
        return _fail(404, "API_NOT_FOUND", "接收地址不对，这个 API 不存在或已删除")
    if err == "PAYLOAD_TOO_LARGE":
        return _fail(413, err, f"一次提交不能超过 {svc.MAX_BODY_BYTES // 1024 // 1024} MB")
    if err == "EMPTY":
        return _fail(422, err, "提交的内容是空的")
    if err == "BAD_JSON":
        return _fail(400, err, "JSON 格式不对")
    if err:
        return _fail(415, err, "认不出提交的格式，请用 JSON 或表单")
    tok = _token(request, data if isinstance(data, dict) else None)
    if not tok:
        return _fail(401, "TOKEN_MISSING", "没有带写入密钥")
    if not _same(tok, api.write_token):
        return _fail(401, "TOKEN_INVALID", "写入密钥不对")
    if not _origin_ok(api, request):
        return _fail(403, "ORIGIN_DENIED", "这个网站不在老师设置的允许来源里")
    try:
        svc.accepting(api)
    except svc.Rejected as e:
        return _fail(e.status, e.code, e.message)
    items = _items(data)
    if len(items) > svc.MAX_BATCH:
        return _fail(413, "TOO_MANY", f"一次最多提交 {svc.MAX_BATCH} 条")
    if not items:
        return _fail(422, "EMPTY", "提交的内容是空的")
    try:
        _limit(db, api, request, len(items))
    except HTTPException as e:
        return _fail(429, "RATE_LIMITED", e.detail, getattr(e, "headers", None))

    results = svc.store(db, api, items, _meta(request))
    db.commit()

    is_form = (request.headers.get("content-type") or "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data"))
    has_redirect = isinstance(data, dict) and isinstance(data.get("_redirect"), str)
    wants_html = is_form and (has_redirect or "text/html" in (request.headers.get("accept") or ""))
    first = results[0]
    if wants_html:
        return _form_reply(request, data, first.get("ok"), first.get("message", ""))

    now = datetime.now().astimezone().replace(microsecond=0).isoformat()
    if isinstance(data, list) or len(items) > 1 or (isinstance(data, dict) and "records" in data):
        ok_n = sum(1 for r in results if r.get("ok") and not r.get("duplicate"))
        dup = sum(1 for r in results if r.get("duplicate"))
        bad = sum(1 for r in results if not r.get("ok"))
        return JSONResponse({"ok": bad == 0, "accepted": ok_n, "duplicates": dup, "rejected": bad,
                             "received_at": now, "results": results}, status_code=200)
    if not first.get("ok"):
        status = {"QUOTA_FULL": 507, "PAYLOAD_TOO_LARGE": 413, "EMPTY": 422}.get(first["code"], 400)
        return _fail(status, first["code"], first["message"])
    return JSONResponse({"ok": True, "id": first["id"], "received_at": now,
                         "duplicate": first["duplicate"],
                         "student_matched": first.get("student_matched", False)},
                        status_code=200 if first["duplicate"] else 201)


@router.get("/sdk.js", summary="接入小工具 wfxx-collect.js", include_in_schema=False)
def sdk():
    return Response(SDK_FILE.read_text(encoding="utf-8"), media_type="application/javascript; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.post("/{key}", summary="收数据")
async def receive(key: str, request: Request, db: Session = Depends(get_db)):
    data, err = await _parse(request)
    return await _receive(key, request, db, data, err)


@router.get("/{key}", summary="收数据（GET，需老师打开「允许 GET」）")
async def receive_get(key: str, request: Request, db: Session = Depends(get_db)):
    api = _api(db, key)
    if not api:
        return _fail(404, "API_NOT_FOUND", "接收地址不对，这个 API 不存在或已删除")
    if not api.allow_get:
        return _fail(405, "GET_DISABLED", "这个 API 只收 POST；老师可以在设置里打开「允许 GET 提交」")
    data = {k: v for k, v in request.query_params.items() if k != "token"}
    return await _receive(key, request, db, data, "" if data else "EMPTY")


def _reader(db: Session, key: str, request: Request, *, summary: bool):
    api = _api(db, key)
    if not api:
        return None, _fail(404, "API_NOT_FOUND", "这个 API 不存在或已删除")
    tok = _token(request, None)
    if not tok:
        return None, _fail(401, "TOKEN_MISSING", "没有带读取密钥")
    if _same(tok, api.read_token):
        return api, None
    if summary and api.public_summary and _same(tok, api.write_token):
        return api, None
    if not api.read_token and not (summary and api.public_summary):
        return None, _fail(403, "READ_DISABLED", "这个 API 没有开放读取")
    return None, _fail(401, "TOKEN_INVALID", "读取密钥不对")


@router.get("/{key}/records", summary="取记录（读取密钥）")
def read_records(key: str, request: Request, since: str = "", type: str = "", activity: str = "",
                 after_id: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    api, bad = _reader(db, key, request, summary=False)
    if bad:
        return bad
    limit = max(1, min(limit, 500))
    q = select(DataRecord).where(DataRecord.api_id == api.id, DataRecord.id > after_id)
    t = svc._time(since)
    if t:
        q = q.where(DataRecord.received_at >= t)
    if type:
        q = q.where(DataRecord.type == type)
    if activity:
        q = q.where((DataRecord.activity_id == activity) | (DataRecord.activity_name == activity))
    rows = db.scalars(q.order_by(DataRecord.id).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"ok": True, "records": [record_out(r) for r in rows],
            "next_after_id": rows[-1].id if more and rows else None}


@router.get("/{key}/summary", summary="取汇总，不含个人信息")
def read_summary(key: str, request: Request, activity: str = "", db: Session = Depends(get_db)):
    api, bad = _reader(db, key, request, summary=True)
    if bad:
        return bad
    return {"ok": True, **svc.summary(db, api, activity)}


def record_out(r: DataRecord) -> dict:
    try:
        payload = json.loads(r.payload or "{}")
    except ValueError:
        payload = {}
    if isinstance(payload, dict):
        payload.pop("_token", None)
    return {
        "id": r.id, "client_id": r.client_id, "type": r.type,
        "activity": {"id": r.activity_id, "name": r.activity_name},
        "student": {"no": r.student_no, "name": r.student_name, "class": r.class_name},
        "target": {"no": r.target_no, "name": r.target_name} if (r.target_no or r.target_name) else None,
        "score": r.score, "max_score": r.max_score, "comment": r.comment, "page": r.page,
        "flag": r.flag, "superseded": r.superseded,
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        "received_at": r.received_at.isoformat() if r.received_at else None,
        "payload": payload,
    }
