@echo off
chcp 936 >nul
title 信息技术组卷台 - 一键部署
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy.ps1"
if errorlevel 1 (
    echo.
    echo 部署未完成，请看上面的提示。
    pause
)