@echo off
chcp 936 >nul
setlocal
title 试卷转题库

rem 把装着试卷 Word 文档的文件夹，直接拖到这个文件上面松手就行。
rem 也可以双击打开，再把文件夹路径粘进去。
rem 干活的是 backend/tools/docx_to_bank.py，用法见 docs/试卷转题库.md
rem
rem 【本文件必须存成 GBK/ANSI 编码】cmd 是按当前代码页逐行解析批处理文件的，
rem 存成 UTF-8 的话里面的中文会把命令行本身撑乱，整个脚本都跑不起来。

set "ROOT=%~dp0.."
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
rem 控制台是 GBK，题干里偶尔有 GBK 打不出来的字符（下划线、圆点）。
rem 加 replace 让它显示成问号，而不是让整个程序崩掉。
set "PYTHONIOENCODING=gbk:replace"

if "%~1"=="" goto ask
set "FOLDER=%~1"
goto run

:ask
echo.
echo   把装着试卷的文件夹拖到本文件上面松手，就会自动开始。
echo   也可以把文件夹路径粘在下面，按回车：
echo.
set /p "FOLDER=   文件夹: "
if "%FOLDER%"=="" goto nothing

:run
echo.
pushd "%ROOT%\backend"
"%PY%" -m tools.docx_to_bank "%FOLDER%"
set "CODE=%ERRORLEVEL%"
popd
if not "%CODE%"=="0" goto failed

echo.
echo   输出文件夹已经打开，把里面那个 xlsx 传到「题库 - 批量导入」就行。
if exist "%FOLDER%\题库导入" start "" "%FOLDER%\题库导入"
goto end

:nothing
echo.
echo   没给文件夹，什么都没做。
goto end

:failed
echo.
echo   没跑成。上面几行写了原因，多半是这两种：
echo     1. 文件夹里没有 .docx 文件
echo     2. 试卷不是菁优网那种带【答案】的版式，认不出来
goto end

:end
echo.
pause
