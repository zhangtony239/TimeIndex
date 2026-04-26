# src/TimeIndex/uninstall.ps1
# TimeIndex 守护进程卸载脚本

# 1. 自提权逻辑
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "正在请求管理员权限..." -ForegroundColor Yellow
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$TaskName = "TimeIndexDaemon"
$UserConfigDir = Join-Path $HOME ".timeindex"

# 2. 清理持久化目录
Write-Host "正在检查持久化目录清理..." -ForegroundColor Cyan
if (Test-Path $UserConfigDir) {
    $choice = Read-Host "是否删除持久化配置目录 $UserConfigDir ? (Y/N)"
    if ($choice -eq 'Y' -or $choice -eq 'y') {
        Remove-Item -Path $UserConfigDir -Recurse -Force
        Write-Host "已删除持久化目录。" -ForegroundColor Green
    } else {
        Write-Host "已保留持久化目录。" -ForegroundColor Gray
    }
}

# 3. 停止并删除计划任务
Write-Host "正在删除 TimeIndex 计划任务..." -ForegroundColor Cyan

# 停止并删除计划任务
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Write-Host "正在停止任务..."
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    
    Write-Host "正在注销任务..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    
    Write-Host "计划任务已成功删除！" -ForegroundColor Green
} else {
    Write-Host "未找到名为 $TaskName 的计划任务。" -ForegroundColor Yellow
}

pause
