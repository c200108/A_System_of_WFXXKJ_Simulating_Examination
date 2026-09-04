# 一键部署的实际逻辑，由根目录的「一键部署.bat」调用。
# 从检查 Docker 到验证业务链路，全程自动；任何一步失败都给出可操作的提示。
#
# 本文件必须存为 UTF-8 **带 BOM**，否则 Windows PowerShell 5.1 会按 ANSI 读，中文全乱。

# 注意：不要设成 "Stop"。PowerShell 5.1 会把原生命令（docker 等）写到 stderr 的
# 每一行包成 ErrorRecord，即使退出码是 0 也会被当成异常中断脚本。
# 这里一律靠 $LASTEXITCODE 判断成败，cmdlet 则在需要处单独加 -ErrorAction Stop。
$ErrorActionPreference = "Continue"
$root = Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent
Set-Location $root

function Say([string]$t) { Write-Host $t }
function Step([string]$t) { Write-Host "" ; Write-Host $t -ForegroundColor Cyan }
function Ok([string]$t) { Write-Host "      $t" -ForegroundColor Green }
function Warn([string]$t) { Write-Host "      $t" -ForegroundColor Yellow }
function Die([string]$t) {
    Write-Host ""
    Write-Host "[失败] $t" -ForegroundColor Red
    Write-Host ""
    Write-Host "按任意键退出..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Say "=================================================="
Say "      信息技术组卷台   一键部署"
Say "=================================================="

# ---------------------------------------------------------------- 1 Docker
Step "[1/6] 检查 Docker..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Die @"
这台电脑没装 Docker。

  下载地址：https://www.docker.com/products/docker-desktop/
  装好后重启电脑，再双击本脚本。

  注意两个前提（新手最容易卡在这里）：
    1. 需要开启 WSL2 —— 安装程序会引导你装
    2. 需要在 BIOS 里开启虚拟化（CPU Virtualization）
"@
}

docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Die @"
Docker 已安装但没有运行。

  在开始菜单里启动「Docker Desktop」，等托盘图标变成稳定状态
  （不再转圈）之后，再双击本脚本。
"@
}
Ok "Docker 就绪  $((docker --version) -replace 'Docker version ','')"

# ---------------------------------------------------------------- 2 配置
Step "[2/6] 准备配置文件..."

function New-Secret([int]$len) {
    $chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789".ToCharArray()
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] $len
    $rng.GetBytes($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

# PowerShell 5.1 的 Get-Content 默认按系统 ANSI(GBK) 读文件。.env 里有中文注释，
# 用 GBK 解码 UTF-8 字节会串码，甚至把下一行吞进注释行——曾导致 JWT_SECRET
# 和 MYSQL_ROOT_PASSWORD 两行整个漏出安全检查。所以一律显式按 UTF-8 读。
function Read-Utf8Lines([string]$path) {
    return [System.IO.File]::ReadAllLines($path, (New-Object System.Text.UTF8Encoding $false))
}
# .env.example 里的这些值是公开在 GitHub 上的，出现即等于没有密码
$KnownDefaults = @(
    "change_this_to_a_long_random_string", "change_this_root_pwd", "change_this_user_pwd",
    "change_this_admin_pwd", "please-change-me", "please-change-this-to-a-long-random-string",
    "change-me-in-production", "admin123", "exam_pwd", "root_pwd", "你的密码"
)

function Test-EnvIsSafe([string]$path) {
    $bad = @()
    Read-Utf8Lines $path | Where-Object { $_ -match "^\s*[A-Z_]+\s*=" } | ForEach-Object {
        $kv = $_ -split "=", 2
        $k = $kv[0].Trim(); $v = $kv[1].Trim()
        if (@("JWT_SECRET", "ADMIN_PASSWORD", "MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD") -contains $k) {
            if ($KnownDefaults -contains $v) { $bad += $k }
        }
    }
    return $bad
}

$adminPw = $null
$needGenerate = $true

if (Test-Path ".env") {
    $bad = Test-EnvIsSafe ".env"
    if ($bad.Count -eq 0) {
        Ok ".env 已存在且口令已自定义，沿用现有配置"
        $needGenerate = $false
    } else {
        Warn "现有 .env 里这几项还是示例默认值：$($bad -join '、')"
        Warn "这些值公开在 GitHub 上，用它们部署等于没有密码。"
        Say ""
        $ans = (Read-Host "  重新生成一份随机口令？旧文件会备份为 .env.bak  [Y/n]").Trim()
        if ($ans -eq "n" -or $ans -eq "N") {
            Die "已取消。请手工改好 .env 里的这几项后再运行。"
        }
        Move-Item ".env" ".env.bak" -Force
        Ok "旧配置已备份为 .env.bak"
    }
}

if ($needGenerate) {
    Say ""
    Say "  这台机器对外的访问地址是什么？"
    Say "  · 有公网 IP 就填 IP，例如 203.0.113.10"
    Say "  · 有域名就填域名，例如 exam.school.edu.cn"
    Say "  · 只在本机试用直接回车"
    $hostAddr = (Read-Host "  地址 [localhost]").Trim()
    if (-not $hostAddr) { $hostAddr = "localhost" }

    $port = (Read-Host "  对外端口 [8080]").Trim()
    if (-not $port) { $port = "8080" }

    $adminPw = New-Secret 16
    $envText = @"
# 由 一键部署.bat 生成于 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# 本文件含明文口令，不要提交进 Git，也不要发给别人。

MYSQL_ROOT_PASSWORD=$(New-Secret 20)
MYSQL_DATABASE=exam
MYSQL_USER=exam
MYSQL_PASSWORD=$(New-Secret 20)

# 换掉它会让所有已登录的人重新登录，属于正常现象
JWT_SECRET=$(New-Secret 48)

ADMIN_USERNAME=admin
ADMIN_PASSWORD=$adminPw

WEB_PORT=$port
CORS_ORIGINS=http://${hostAddr}:${port}
"@
    [System.IO.File]::WriteAllText("$root\.env", $envText, (New-Object System.Text.UTF8Encoding $false))
    Ok "已生成 .env，所有口令都是随机的"
}

# 读回配置，后面几步要用
$cfg = @{}
Read-Utf8Lines ".env" | Where-Object { $_ -match "^\s*[A-Z_]+\s*=" } | ForEach-Object {
    $kv = $_ -split "=", 2
    $cfg[$kv[0].Trim()] = $kv[1].Trim()
}
$webPort = if ($cfg.WEB_PORT) { $cfg.WEB_PORT } else { "8080" }

# ---------------------------------------------------------------- 3 端口
Step "[3/6] 检查端口 $webPort..."
$busy = Get-NetTCPConnection -LocalPort $webPort -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $pr = Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue
    $who = if ($pr) { "$($pr.ProcessName)（PID $($pr.Id)）" } else { "某个进程" }
    Warn "端口 $webPort 已被 $who 占用"
    Warn "如果那不是本系统的容器，请改 .env 里的 WEB_PORT 换一个端口再重来"
} else {
    Ok "端口空闲"
}

# ---------------------------------------------------------------- 4 构建
Step "[4/6] 构建并启动（首次要下载约 1GB，需要几分钟）..."
Say "      国内网络拉镜像容易中断，失败会自动重试。"

$built = $false
for ($i = 1; $i -le 3; $i++) {
    Say ""
    Say "      第 $i 次尝试..."
    docker compose up -d --build
    if ($LASTEXITCODE -eq 0) { $built = $true; break }
    if ($i -lt 3) {
        Warn "这次没成功（多半是拉镜像中断），10 秒后重试"
        Start-Sleep -Seconds 10
    }
}
if (-not $built) {
    Die @"
镜像构建失败，试了 3 次。

  最常见原因是拉取 Docker Hub 超时。配一个国内镜像加速再试：
    Docker Desktop → Settings → Docker Engine，加入这一段后 Apply & Restart

    { "registry-mirrors": ["https://docker.m.daocloud.io"] }

  然后重新双击本脚本。
"@
}
Ok "容器已启动"

# ---------------------------------------------------------------- 5 等待就绪
Step "[5/6] 等待服务就绪（首次启动要建库、导题库，约 1 分钟）..."

$ready = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 3
    $state = (docker compose ps --format "{{.Service}}={{.Health}}" 2>$null) -join " "
    if ($state -match "backend=healthy") { $ready = $true; break }
    if ($i % 5 -eq 0) { Say "      仍在启动... ($($i*3) 秒)  $state" }
}

if (-not $ready) {
    Say ""
    Say "      后端一直没有就绪，最后 25 行日志："
    docker compose logs backend --tail=25
    Die "服务启动失败，请把上面的日志发给维护者。"
}
Ok "后端健康检查通过"

# ---------------------------------------------------------------- 6 验证
Step "[6/6] 验证业务链路..."

$base = "http://localhost:$webPort"
try {
    $h = Invoke-RestMethod "$base/api/health" -TimeoutSec 15 -ErrorAction Stop
    Ok "接口健康：$($h.status)"
} catch { Die "接口不通：$($_.Exception.Message)" }

try {
    $form = @{ username = $cfg.ADMIN_USERNAME; password = $cfg.ADMIN_PASSWORD }
    $login = Invoke-RestMethod "$base/api/auth/login" -Method Post -Body $form `
             -ContentType "application/x-www-form-urlencoded" -TimeoutSec 20 -ErrorAction Stop
    $auth = @{ Authorization = "Bearer $($login.access_token)" }
    Ok "管理员登录成功"

    $stats = Invoke-RestMethod "$base/api/questions/stats" -Headers $auth -TimeoutSec 20 -ErrorAction Stop
    Ok "题库 $($stats.total) 题，带图 $($stats.with_image) 张"
    if ($stats.total -eq 0) {
        Warn "题库是空的。若要搬旧机器的数据，见 docs/部署指南.md 第四节"
    }
} catch {
    Warn "业务验证没通过：$($_.Exception.Message)"
    Warn "服务已经起来了，可以先手动打开页面看看。"
}

# ---------------------------------------------------------------- 完成
$cors = $cfg.CORS_ORIGINS
$publicUrl = if ($cors) { ($cors -split ",")[0] } else { $base }

Say ""
Say "=================================================="
Say "  部署完成"
Say ""
Say "  本机访问   ：$base"
if ($publicUrl -ne $base) {
    Say "  对外访问   ：$publicUrl"
}
Say "  接口文档   ：$base/docs"
Say ""
Say "  管理员账号 ：$($cfg.ADMIN_USERNAME)"
if ($adminPw) {
    Write-Host "  管理员密码 ：$adminPw" -ForegroundColor Yellow
    Say ""
    Say "  ↑ 请立刻记下来。密码也存在 .env 里，登录后请在系统里再改一次。"
} else {
    Say "  管理员密码 ：见 .env 里的 ADMIN_PASSWORD"
}
Say "=================================================="
Say ""
Say "  还要做的两件事："
Say "    1. 要让外网访问，在云服务器安全组 / 防火墙放行 $webPort 端口"
Say "    2. 把 backup/backup.sh 加进定时任务，部署当天就设好备份"
Say ""
Say "  常用命令（在项目目录下）："
Say "    docker compose ps                看状态"
Say "    docker compose logs -f backend   看日志"
Say "    docker compose down              停止（数据不丢）"
Say ""
Say "  完整说明见 docs\部署指南.md"
Say ""
Write-Host "按任意键退出..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
