@echo off
chcp 936 >nul
title 信息技术组卷台 - 停止服务

echo.
echo 正在停止组卷台的前后端服务...
echo （只停 python / node 进程；其他程序占用同一端口时会跳过，不会误杀）
echo.

powershell -NoProfile -Command "$found=$false; foreach($p in 8000,5173){ Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $pr = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if($pr -and ($pr.ProcessName -match 'python|node')){ Write-Host ('  已停止 ' + $pr.ProcessName + ' (PID ' + $pr.Id + ')，端口 ' + $p); Stop-Process -Id $pr.Id -Force; $found=$true } elseif($pr){ Write-Host ('  跳过端口 ' + $p + '：占用者是 ' + $pr.ProcessName + '，不是组卷台的进程') } } }; if(-not $found){ Write-Host '  没有发现正在运行的组卷台服务。' }"

echo.
echo 完成。如果还有黑窗口没关，直接关掉即可。
echo.
pause
