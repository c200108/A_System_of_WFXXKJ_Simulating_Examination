@echo off
chcp 936 >nul
rem 让 Python 按控制台代码页输出，中文提示才不会变乱码
set "PYTHONIOENCODING=mbcs:replace"
title 组卷台-后端  (关掉这个窗口就停止后端)
cd /d "%~dp0..\backend"
rem .venv 只能在建它的那台电脑上用（它记着那台电脑上 Python 的完整路径），
rem 整个项目拷到别的电脑就会报 No Python at 'C:\Users\别人\...'。先试一下能不能跑。
if not exist ".venv\Scripts\python.exe" goto novenv
".venv\Scripts\python.exe" -c "import sys" >nul 2>&1 || goto novenv
echo 后端启动中，地址 http://127.0.0.1:8000  接口文档 /docs
echo 这个窗口不要关，关了后端就停了。
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
echo.
echo 后端已退出。
pause
goto :eof

:novenv
echo 后端的 Python 环境 backend\.venv 没有，或者是从别的电脑拷来的，这台电脑上用不了。
echo 删掉它重建一次（要联网，在项目根目录下执行）：
echo.
echo     rmdir /s /q backend\.venv
echo     python -m venv backend\.venv
echo     backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
echo.
pause
