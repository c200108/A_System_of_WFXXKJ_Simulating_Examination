@echo off
chcp 936 >nul
rem 让 Python 按控制台代码页输出，中文提示才不会变乱码
set "PYTHONIOENCODING=mbcs:replace"
title 组卷台-后端  (关掉这个窗口就停止后端)
cd /d "%~dp0..\backend"
echo 后端启动中，地址 http://127.0.0.1:8000  接口文档 /docs
echo 这个窗口不要关，关了后端就停了。
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
echo.
echo 后端已退出。
pause
