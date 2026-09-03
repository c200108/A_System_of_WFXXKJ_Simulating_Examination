import json
import os
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import DICT_SCOPE, DICT_TYPE
from ..database import get_db
from ..deps import get_current_user
from ..models import ImportLog, Option, Question, User
from ..schemas import ImportLogOut, ImportResult, ImportRowError
from ..services.importer import build_template, parse_upload, stem_hash
from .dicts import active_names

router = APIRouter(prefix="/api/imports", tags=["题库导入"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/template", summary="下载空白导入模板")
def download_template(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = build_template(active_names(db, DICT_SCOPE), active_names(db, DICT_TYPE))
    filename = quote("题库导入模板.xlsx")
    return Response(
        content=data,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/questions", response_model=ImportResult, summary="上传模板文件导入题库")
async def import_questions(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xlsm", ".csv")):
        raise HTTPException(status_code=400, detail="只支持 .xlsx 或 .csv 文件")
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件不能超过 {settings.max_upload_mb} MB")

    scopes = set(active_names(db, DICT_SCOPE))
    is_csv = name.endswith(".csv")
    try:
        good, errors, rows_seen = parse_upload(content, name, scopes)
    except Exception as exc:  # 文件损坏、编码认不出、不是表格等
        raise HTTPException(status_code=400, detail=f"这个文件读不了：{exc}")

    # 原件留底，出问题能回溯到教师上传的那一份
    raw_dir = os.path.join(settings.upload_dir, "imports")
    os.makedirs(raw_dir, exist_ok=True)
    saved_name = f"{uuid.uuid4().hex}{'.csv' if is_csv else '.xlsx'}"
    with open(os.path.join(raw_dir, saved_name), "wb") as f:
        f.write(content)

    existing = {h for (h,) in db.execute(select(Question.stem_hash)).all()}
    seen_in_file: set[str] = set()
    by_type: dict[str, int] = {}
    skipped = 0
    created: list[Question] = []

    for item in good:
        h = stem_hash(item["stem"])
        if h in existing or h in seen_in_file:
            skipped += 1
            errors.append(
                {"sheet": item["sheet"], "row": item["row"], "reason": "题干与已有题目重复，已跳过"}
            )
            continue
        seen_in_file.add(h)

        q = Question(
            type=item["type"],
            stem=item["stem"],
            stem_hash=h,
            answer=item["answer"],
            scope=item["scope"],
            source=item["source"],
            image_url=item["image_url"],
            created_by=user.id,
        )
        for i, (label, text) in enumerate(item["options"]):
            q.options.append(Option(label=label, content=text, sort_order=i))
        db.add(q)
        created.append(q)
        by_type[item["type"]] = by_type.get(item["type"], 0) + 1

    db.flush()
    for q in created:
        q.code = f"C{q.id:04d}"

    result = ImportResult(
        filename=file.filename or "",
        total=rows_seen,
        success=len(created),
        failed=len([e for e in errors if "重复" not in e["reason"]]),
        skipped=skipped,
        by_type=by_type,
        errors=[ImportRowError(**e) for e in errors[:200]],
    )

    db.add(
        ImportLog(
            filename=file.filename or "",
            total=result.total,
            success=result.success,
            failed=result.failed,
            skipped=result.skipped,
            detail_json=json.dumps(
                {"saved_as": saved_name, "errors": errors[:200]}, ensure_ascii=False
            ),
            user_id=user.id,
        )
    )
    db.commit()
    return result


@router.get("/logs", response_model=list[ImportLogOut], summary="导入记录")
def import_logs(
    limit: int = 50, _: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rows = db.scalars(select(ImportLog).order_by(ImportLog.id.desc()).limit(limit)).all()
    out = []
    for r in rows:
        item = ImportLogOut.model_validate(r)
        operator = db.get(User, r.user_id) if r.user_id else None
        item.operator = operator.name if operator else ""
        out.append(item)
    return out
