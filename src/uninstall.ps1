# src/uninstall.ps1
# TimeIndex 守护进程卸载脚本

# 1. 自提权逻辑
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "正在请求管理员权限..." -ForegroundColor Yellow
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$ServiceName = "TimeIndexDaemon"
$NssmPath = Join-Path $PSScriptRoot "nssm.exe"

Write-Host "正在卸载 TimeIndex 守护进程服务..." -ForegroundColor Cyan

# 检查 nssm 是否存在
if (-not (Test-Path $NssmPath)) {
    Write-Error "找不到 nssm.exe: $NssmPath"
    exit 1
}

# 停止服务
Write-Host "正在停止服务..."
& $NssmPath stop $ServiceName

# 移除服务
Write-Host "正在移除服务..."
& $NssmPath remove $ServiceName confirm

# 验证是否移除成功
$services = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -eq $services) {
    Write-Host "服务卸载成功！" -ForegroundColor Green
} else {
    Write-Host "错误：服务卸载失败，服务仍然存在。" -ForegroundColor Red
    exit 1
}

pause
