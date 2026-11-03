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
    client_update,
    community,
    config,
    data_apis,
    desk,
    hook,
    insight,
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


class HookCors:
    """/api/hook/ 下的接口（第三方网页送数据）单独放行跨域。

    全站的 CORS 白名单只有本站地址，老师自己做的网页挂在别的域名上，浏览器会被挡住。
    这里任何来源都放行、不带 Cookie（靠每个 API 自己的密钥，不靠登录状态）；
    「只允许哪些网站」由每个 API 的来源白名单在接口里判，见 routers/hook.py。
    **必须加在 CORSMiddleware 外面**（后 add 的在外层），否则预检请求先被它拒了。
    """

    HEADERS = [
        (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
        (b"access-control-allow-headers", b"Authorization, Content-Type, X-Api-Key, X-Device-Id"),
        (b"access-control-max-age", b"86400"),
    ]

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/hook/"):
            return await self.app(scope, receive, send)
        origin = dict(scope.get("headers") or []).get(b"origin", b"*") or b"*"
        if scope["method"] == "OPTIONS":
            await send({"type": "http.response.start", "status": 204, "headers": [
                (b"access-control-allow-origin", origin), (b"vary", b"Origin"), *self.HEADERS]})
            await send({"type": "http.response.body", "body": b""})
            return

        async def wrapped(msg):
            if msg["type"] == "http.response.start":
                hs = [(k, v) for k, v in msg.get("headers", [])
                      if k.lower() not in (b"access-control-allow-origin", b"access-control-allow-credentials")]
                hs += [(b"access-control-allow-origin", origin), (b"vary", b"Origin")]
                msg = {**msg, "headers": hs}
            await send(msg)

        # 普通请求照常经过 CORSMiddleware（白名单外的 Origin 它不拦，只是不加头），出来时统一换成这里的头
        return await self.app(scope, receive, wrapped)


app.add_middleware(HookCors)

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
app.include_router(client_update.router)  # 学生端 exe 检查更新：清单 + 下载，公开只读
app.include_router(data_apis.router)  # 教师端「API」板块：老师建接口、看数据表单和大图
app.include_router(hook.router)  # 第三方教学网页往 API 里送数据，认每个 API 自己的密钥
app.include_router(insight.router)  # 学生学情：考试、排名、打字、第三方网页数据


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
