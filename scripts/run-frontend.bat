@echo off
chcp 936 >nul
title 组卷台-前端  (关掉这个窗口就停止前端)
cd /d "%~dp0..\frontend"
echo 前端启动中，地址 http://localhost:5173
echo 这个窗口不要关，关了页面就打不开了。
echo.
call npm run dev
echo.
echo 前端已退出。
pause
