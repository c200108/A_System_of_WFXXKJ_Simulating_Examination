# Windows Server 上把外网端口转发到 WSL2 里的服务。
#
# 为什么需要：WSL2 用的是 NAT 网络，容器监听在 WSL 内部的 IP 上。
# 从 Windows 本机访问 localhost:8080 能通（WSL 会自动转发 localhost），
# 但**外网访问服务器公网 IP 是不通的** —— 不做这一步，你自己能打开、学生打不开。
#
# 另一个坑：WSL 的 IP 每次重启都会变，所以还要注册一个开机任务自动重设。
#
# 用法（管理员 PowerShell）：
#   powershell -ExecutionPolicy Bypass -File scripts\win-server-port-forward.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\win-server-port-forward.ps1 -Port 8080
#
# 内部使用（开机任务调用，不要手动加）：
#   ... -AtBoot

param(
    [int]$Port = 8080,
    [string]$Distro = "Ubuntu-22.04",
    [switch]$AtBoot
)

$ErrorActionPreference = "Continue"

function Say($t) { Write-Host $t }
function Ok($t) { Write-Host "      $t" -ForegroundColor Green }
function Warn($t) { Write-Host "      $t" -ForegroundColor Yellow }
function Die($t) { Write-Host "`n[失败] $t" -ForegroundColor Red; exit 1 }

# 必须管理员：netsh portproxy 和防火墙规则都要提权
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Die "需要管理员权限。右键 PowerShell → 以管理员身份运行。" }

if (-not $AtBoot) {
    Say "=================================================="
    Say "   WSL2 端口转发设置（Windows Server）"
    Say "=================================================="
}

# ---------------------------------------------------------------- 取 WSL 的 IP
# 开机任务触发时 WSL 可能还没起来，重试几次
$wslIp = $null
for ($i = 1; $i -le 10; $i++) {
    $raw = wsl -d $Distro -e hostname -I 2>$null
    if ($LASTEXITCODE -eq 0 -and $raw) {
        $wslIp = ($raw -split '\s+' | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' })[0]
        if ($wslIp) { break }
    }
    if (-not $AtBoot) { Warn "WSL 还没就绪，等待中... ($i/10)" }
    Start-Sleep -Seconds 5
}
if (-not $wslIp) {
    Die "拿不到 $Distro 的 IP。先确认发行版已安装并能启动：
      wsl -l -v
      wsl -d $Distro -e echo ok"
}
if (-not $AtBoot) { Ok "WSL 内网 IP：$wslIp" }

# ---------------------------------------------------------------- 端口转发
# 先删旧规则，避免 WSL 换 IP 后残留一条指向旧地址的
netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 2>$null | Out-Null
netsh interface portproxy add v4tov4 `
    listenport=$Port listenaddress=0.0.0.0 `
    connectport=$Port connectaddress=$wslIp | Out-Null

if ($LASTEXITCODE -ne 0) { Die "端口转发设置失败" }
if (-not $AtBoot) { Ok "已转发 0.0.0.0:$Port → ${wslIp}:$Port" }

# ---------------------------------------------------------------- 防火墙
$ruleName = "组卷台 WSL $Port"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound `
        -LocalPort $Port -Protocol TCP -Action Allow -Profile Any | Out-Null
    if (-not $AtBoot) { Ok "已放行防火墙入站 $Port" }
} elseif (-not $AtBoot) {
    Ok "防火墙规则已存在"
}

if ($AtBoot) { exit 0 }   # 开机任务到此为止

# ---------------------------------------------------------------- 开机自动重设
Say ""
Say "注册开机任务（WSL 每次重启 IP 都会变，必须自动重设）..."

$taskName = "组卷台-WSL端口转发"
$scriptPath = $MyInvocation.MyCommand.Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Port $Port -Distro $Distro -AtBoot"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
# 开机后 WSL 和 Docker 都要时间启动，延迟两分钟再执行
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Description "开机后把外网端口转发到 WSL2 里的组卷台" | Out-Null
Ok "已注册开机任务「$taskName」"

# ---------------------------------------------------------------- 验证
Say ""
Say "当前转发规则："
netsh interface portproxy show v4tov4 | Select-Object -Skip 2 | ForEach-Object { "      $_" }

Say ""
try {
    $r = Invoke-WebRequest "http://localhost:$Port/api/health" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    Ok "本机访问正常：$($r.Content)"
} catch {
    Warn "本机访问 http://localhost:$Port 不通"
    Warn "确认 WSL 里的服务已启动：wsl -d $Distro -e docker compose ps"
}

Say ""
Say "=================================================="
Say "  设置完成"
Say ""
Say "  最后一步：在云服务器控制台的**安全组**里放行 $Port 端口入站，"
Say "  然后用 http://公网IP:$Port 访问。"
Say ""
Say "  WSL 重启后如果外网又打不开，手动重跑本脚本即可。"
Say "=================================================="
