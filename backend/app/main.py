import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import auth, dicts, exams, imports, papers, questions, take

app = FastAPI(
    title="信息技术组卷台 API",
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

app.include_router(auth.router)
app.include_router(dicts.router)
app.include_router(questions.router)
app.include_router(imports.router)
app.include_router(papers.router)
app.include_router(exams.router)
app.include_router(take.router)  # 学生端，公开访问


@app.get("/api/health", tags=["运维"], summary="健康检查")
def health():
    return {"status": "ok"}
