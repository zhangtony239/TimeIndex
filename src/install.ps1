# src/install.ps1
# TimeIndex 守护进程安装脚本

# 1. 自提权逻辑
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "正在请求管理员权限..." -ForegroundColor Yellow
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$ServiceName = "TimeIndexDaemon"
$NssmPath = Join-Path $PSScriptRoot "nssm.exe"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$EntryPath = Join-Path $ProjectRoot "entry.py"

Write-Host "正在安装 TimeIndex 守护进程服务..." -ForegroundColor Cyan

# 检查 nssm 是否存在
if (-not (Test-Path $NssmPath)) {
    Write-Error "找不到 nssm.exe: $NssmPath"
    exit 1
}

# 检查 Python 虚拟环境
if (-not (Test-Path $PythonPath)) {
    Write-Error "找不到虚拟环境 Python: $PythonPath. 请先运行 uv sync。"
    exit 1
}

# 使用 nssm 安装服务
& $NssmPath install $ServiceName $PythonPath $EntryPath daemon start
& $NssmPath set $ServiceName AppDirectory $ProjectRoot
& $NssmPath set $ServiceName Description "TimeIndex 后台监控与 LLM 处理服务"
& $NssmPath set $ServiceName Start SERVICE_AUTO_START

# 启动服务
& $NssmPath start $ServiceName

$status = & $NssmPath status $ServiceName
if ($status -eq "SERVICE_RUNNING") {
    Write-Host "服务安装并启动成功！" -ForegroundColor Green
} else {
    Write-Host "服务安装成功，但启动状态为: $status" -ForegroundColor Yellow
}

pause
