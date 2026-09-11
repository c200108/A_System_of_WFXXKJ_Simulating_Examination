import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .siteconfig import site
from .routers import (
    auth,
    community,
    config,
    dicts,
    exams,
    imports,
    papers,
    questions,
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
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(config.router)  # 公开，前端启动时读
app.include_router(auth.router)
app.include_router(dicts.router)
app.include_router(questions.router)
app.include_router(imports.router)
app.include_router(papers.router)
app.include_router(exams.router)
app.include_router(take.router)  # 凭链接答题，公开访问
app.include_router(students.student_api)  # 学生平台，认学生令牌
app.include_router(students.admin_api)  # 学生账号管理，认教师令牌
app.include_router(typing_train.router)  # 打字训练：学生端公开，教师端要登录
app.include_router(community.router)  # 反馈与更新日志


@app.get("/api/health", tags=["运维"], summary="健康检查")
def health():
    return {"status": "ok"}
