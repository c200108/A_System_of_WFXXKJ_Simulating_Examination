import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .siteconfig import site
from .routers import (
    app_mobile,
    auth,
    classes,
    community,
    config,
    desk,
    dicts,
    exams,
    imports,
    papers,
    questions,
    recycle,
    sims,
    students,
    take,
    typing_train,
)

app = FastAPI(
    title=f"{site.site.title} API",
    description="题库、组卷、导入、教师账号的后端接口。文档地址 /docs",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 题目配图直接由后端托管；生产环境也可以交给 Nginx 直读同一个目录
os.makedirs(os.path.join(settings.upload_dir, "images"), exist_ok=True)
os.makedirs(os.path.join(settings.upload_dir, "seats"), exist_ok=True)   # 班级上机座次表
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(config.router)  # 公开，前端启动时读
app.include_router(auth.router)
app.include_router(classes.router)  # 班级：老师能看，增删改要管理员
app.include_router(dicts.router)
app.include_router(questions.router)
app.include_router(sims.router)  # 仿真操作题：题面环境与判分规则
app.include_router(imports.router)
app.include_router(papers.router)
app.include_router(exams.router)
app.include_router(desk.router)  # 桌面客户端：导出考试包（交卷走 take 那条路）
app.include_router(take.router)  # 凭链接答题，公开访问
app.include_router(students.student_api)  # 学生平台，认学生令牌
app.include_router(students.admin_api)  # 学生账号管理，认教师令牌
app.include_router(typing_train.router)  # 打字训练：学生端公开，教师端要登录
app.include_router(community.router)  # 反馈与更新日志
app.include_router(app_mobile.router)  # 教师端安卓 APP：认服务器、心跳保持登录
app.include_router(recycle.router)  # 数据回收站


@app.on_event("startup")
def _purge_recycle_hourly():
    """回收站里过了 7 天的，服务起来时清一次，之后每小时清一次。

    打开回收站、删东西时也会顺手清；这里兜底那种「谁也没去点」的时候。
    后台线程里出什么错都不能影响服务本身。
    """
    import threading
    import time as _time

    from .database import SessionLocal
    from .services import recycle as bin_

    def loop():
        while True:
            try:
                with SessionLocal() as db:
                    bin_.purge(db)
            except Exception:                    # noqa: BLE001
                pass
            _time.sleep(3600)

    threading.Thread(target=loop, name="recycle-purge", daemon=True).start()


@app.get("/api/health", tags=["运维"], summary="健康检查")
def health():
    return {"status": "ok"}
