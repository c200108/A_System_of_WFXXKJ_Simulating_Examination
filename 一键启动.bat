@echo off
chcp 936 >nul
rem 让 Python 按控制台代码页输出，中文提示才不会变乱码
set "PYTHONIOENCODING=mbcs:replace"
title 信息技术组卷台 - 一键启动
cd /d "%~dp0"
setlocal

echo.
echo ==================================================
echo            信息技术组卷台   一键启动
echo ==================================================
echo.
echo  第一次运行要装依赖，需要联网，大概三到五分钟。
echo  以后再启动只要十几秒。
echo.

rem ---------- 环境检查 ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Python。
    echo        请先安装 Python 3.10 以上版本：https://www.python.org/downloads/
    echo        安装时务必勾选 "Add Python to PATH"。
    echo.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Node.js。
    echo        请先安装 Node.js 18 以上版本：https://nodejs.org/
    echo.
    pause
    exit /b 1
)

rem ---------- Python 版本检查 ----------
for /f "delims=" %%V in ('python -c "import sys;print(1 if sys.version_info>=(3,10) else 0)"') do set "PYOK=%%V"
if not "%PYOK%"=="1" (
    echo [错误] Python 版本太低，本系统需要 3.10 或以上。
    python -c "import sys;print('       当前用的是 '+sys.version.split()[0]+'   '+sys.executable)"
    echo        这台机器装了多个 Python，请把 3.10 以上那个放到 PATH 靠前的位置。
    echo.
    pause
    exit /b 1
)
set "VENV=%~dp0backend\.venv\Scripts"

rem ---------- 1. 后端虚拟环境 ----------
echo [1/6] 准备后端运行环境...
if not exist "%VENV%\python.exe" (
    python -m venv "%~dp0backend\.venv"
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败。
        pause
        exit /b 1
    )
)

rem ---------- 2. 后端依赖 ----------
echo [2/6] 安装后端依赖...
"%VENV%\python.exe" -m pip install --disable-pip-version-check -q -r "%~dp0backend\requirements.txt"
if errorlevel 1 (
    echo [错误] 后端依赖安装失败，请检查网络后重试。
    echo        如果公司或学校网络受限，可以试试国内镜像：
    echo        backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

if not exist "%~dp0backend\.env" (
    copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
    echo       已生成 backend\.env（默认用 SQLite，正式部署再换 MySQL）
)

rem ---------- 3. 数据库 ----------
echo [3/6] 初始化数据库...
pushd "%~dp0backend"
if not exist "data" mkdir "data"
rem 用 python -m 调用，这样项目文件夹改名或换台电脑都不会失效
"%VENV%\python.exe" -m alembic upgrade head
if errorlevel 1 (
    echo [错误] 数据库迁移失败。
    popd
    pause
    exit /b 1
)
"%VENV%\python.exe" -m app.seed

rem ---------- 4. 首次导入原题库 ----------
echo [4/6] 导入原题库...
if exist "data\.migrated" (
    echo       已经导过了，跳过。
) else (
    if exist "%~dp0legacy\信息技术组卷台.html" (
        "%VENV%\python.exe" -m tools.migrate_from_html
        echo ok> "data\.migrated"
    ) else (
        echo       没找到 legacy 目录下的原始 HTML，跳过。
    )
)
popd

rem ---------- 5. 前端依赖 ----------
echo [5/6] 安装前端依赖...
if exist "%~dp0frontend\node_modules" (
    echo       已安装，跳过。
) else (
    pushd "%~dp0frontend"
    call npm install
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败，请检查网络后重试。
        echo        网络慢可以先切镜像：npm config set registry https://registry.npmmirror.com
        popd
        pause
        exit /b 1
    )
    popd
)

rem ---------- 6. 启动 ----------
echo [6/6] 启动服务...
start "组卷台-后端" "%~dp0scripts\run-backend.bat"
start "组卷台-前端" "%~dp0scripts\run-frontend.bat"

echo.
echo       正在等待服务就绪...
powershell -NoProfile -Command "for($i=0;$i -lt 90;$i++){try{$null=Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 2; exit 0}catch{Start-Sleep -Milliseconds 800}}; exit 1"

if errorlevel 1 (
    echo.
    echo [提示] 等待超时。请看新弹出的两个黑窗口里有没有报错信息。
    echo        服务可能还在启动，稍等片刻手动打开 http://localhost:5173
) else (
    start "" http://localhost:5173
)

echo.
echo ==================================================
echo   启动完成
echo.
echo   使用地址：http://localhost:5173
echo   接口文档：http://127.0.0.1:8000/docs
echo   默认账号：见 backend\.env 里的 ADMIN_USERNAME / ADMIN_PASSWORD
echo             （默认 admin / admin123，登录后请立刻改密码）
echo.
echo   要停止服务：关掉那两个黑窗口，或者双击 一键停止.bat
echo ==================================================
echo.
pause
