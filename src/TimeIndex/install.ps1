# src/TimeIndex/install.ps1
# TimeIndex 守护进程安装脚本

# 1. 自提权逻辑
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "正在请求管理员权限..." -ForegroundColor Yellow
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$TaskName = "TimeIndexDaemon"
$QuietPath = Join-Path $PSScriptRoot "Quiet.exe"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$UserConfigDir = Join-Path $HOME ".timeindex"
$UserConfigPath = Join-Path $UserConfigDir "config.yaml"
$DefaultConfigPath = Join-Path $PSScriptRoot "config.yaml"

# 2. 配置文件持久化
Write-Host "正在检查配置文件持久化..." -ForegroundColor Cyan
if (-not (Test-Path $UserConfigDir)) {
    New-Item -ItemType Directory -Path $UserConfigDir -Force | Out-Null
    Write-Host "已创建配置目录: $UserConfigDir" -ForegroundColor Gray
}

if (-not (Test-Path $UserConfigPath)) {
    if (Test-Path $DefaultConfigPath) {
        Copy-Item -Path $DefaultConfigPath -Destination $UserConfigPath
        Write-Host "已持久化默认配置到: $UserConfigPath" -ForegroundColor Green
    } else {
        Write-Warning "找不到默认配置文件: $DefaultConfigPath"
    }
} else {
    Write-Host "配置文件已存在，跳过持久化。" -ForegroundColor Gray
}

# 3. 注册计划任务
Write-Host "正在注册 TimeIndex 计划任务 (使用 Quiet.exe)..." -ForegroundColor Cyan

# 检查 Quiet.exe 是否存在
if (-not (Test-Path $QuietPath)) {
    Write-Error "找不到 Quiet.exe: $QuietPath"
    exit 1
}

# 检查 ti 是否安装 (假设已通过 uv tool install 全局注册)
if (-not (Get-Command ti -ErrorAction SilentlyContinue)) {
    Write-Error "找不到 ti 命令，请先通过 'uv tool install .' 安装。"
    exit 1
}

# 创建计划任务
# 使用当前用户运行，登录时启动
$Action = New-ScheduledTaskAction -Execute $QuietPath -Argument "ti daemon start" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0

# 如果任务已存在，先删除
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "TimeIndex 后台监控守护进程"

# 立即启动任务
Start-ScheduledTask -TaskName $TaskName

Write-Host "计划任务注册并启动成功！" -ForegroundColor Green

pause
