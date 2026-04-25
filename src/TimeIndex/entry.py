"""
cli/entry.py - CLI 入口 (Typer 实现)

处理用户的显式命令：
- /ti get [timerange|start,end]: 获取指定时间范围的日志摘要
- /ti about [tags]: 根据标签查询相关活动记录
- /ti daemon install: 安装守护进程（配置自启动），写入 WMI 过滤设置
- /ti daemon uninstall: 卸载守护进程
- /ti config [key:value]: 修改 config.yaml 配置项
- /ti config: 读取配置项并执行自检
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table

from .db.vector_store import TimeIndexStore
from .utils.config import config

# 初始化 Typer 和 Console
app = typer.Typer(help="TimeIndex - 个人活动自动化索引系统", add_completion=False)
daemon_app = typer.Typer(help="守护进程管理")
app.add_typer(daemon_app, name="daemon")

console = Console()
logger = logging.getLogger(__name__)

class TimeRange(str, Enum):
    today = "today"
    yesterday = "yesterday"
    week = "week"
    month = "month"

def setup_logging(verbose: bool = False):
    """配置日志 (已由 config.py 统一管理，此处仅处理 CLI 显式 verbose)"""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

def format_record(record: dict) -> str:
    """格式化单条记录为可读字符串"""
    ts = record.get("timestamp", "N/A")
    summary = record.get("summary", "N/A")
    refined_summary = record.get("refined_summary")
    tags = record.get("tags", [])
    refined_tags = record.get("refined_tags")
    app_name = record.get("primary_app", "unknown")
    confidence = record.get("confidence", 0.0)
    
    res = f"[bold cyan]时间:[/bold cyan] {ts}\n"
    res += f"[bold cyan]应用:[/bold cyan] {app_name}\n"
    res += f"[bold cyan]摘要:[/bold cyan] {refined_summary or summary}\n"
    res += f"[bold cyan]标签:[/bold cyan] {refined_tags or tags}\n"
    res += f"[bold cyan]置信度:[/bold cyan] {confidence:.2f}"
    
    if refined_summary and refined_summary != summary:
        res += f"\n[dim]原始摘要: {summary}[/dim]"
    
    return res

@app.command()
def get(
    timerange: Optional[TimeRange] = typer.Argument(None, help="预设时间范围"),
    start: Optional[str] = typer.Option(None, "--start", help="开始时间 (ISO 格式)"),
    end: Optional[str] = typer.Option(None, "--end", help="结束时间 (ISO 格式)"),
    limit: int = typer.Option(50, "--limit", help="返回最新记录数限制（按时间倒序）"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="启用详细输出")
):
    """获取指定时间范围内最新的日志摘要"""
    setup_logging(verbose)
    store = TimeIndexStore()
    
    now = datetime.now()
    if timerange:
        if timerange == TimeRange.today:
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now
        elif timerange == TimeRange.yesterday:
            start_dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = start_dt + timedelta(days=1)
        elif timerange == TimeRange.week:
            start_dt = now - timedelta(weeks=1)
            end_dt = now
        elif timerange == TimeRange.month:
            start_dt = now - timedelta(days=30)
            end_dt = now
    elif start and end:
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            console.print("[red]时间格式错误，请使用 ISO 格式 (如 2024-01-01T10:00:00)[/red]")
            raise typer.Exit(1)
    else:
        # 默认获取今天
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now

    console.print(f"\n[bold green]查询时间范围:[/bold green] {start_dt} ~ {end_dt}")
    console.print("-" * 50)
    
    records = store.get_activities_in_range(start_dt, end_dt, limit)
    
    if not records:
        console.print("[yellow]未找到记录[/yellow]")
        return
    
    console.print(f"找到 {len(records)} 条记录:\n")
    for i, record in enumerate(records):
        console.print(f"[[bold]{i+1}[/bold]]")
        console.print(format_record(record))
        console.print()

@app.command()
def about(
    tags: List[str] = typer.Argument(..., help="要查询的标签"),
    limit: int = typer.Option(50, "--limit", help="返回记录数限制"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="启用详细输出")
):
    """根据标签查询相关活动记录"""
    setup_logging(verbose)
    store = TimeIndexStore()
    
    console.print(f"\n[bold green]查询标签:[/bold green] {', '.join(tags)}")
    console.print("-" * 50)
    
    records = store.get_activities_by_tags(tags, limit)
    
    if not records:
        console.print(f"[yellow]未找到包含标签 {', '.join(tags)} 的记录[/yellow]")
        return
    
    console.print(f"找到 {len(records)} 条记录:\n")
    for i, record in enumerate(records):
        console.print(f"[[bold]{i+1}[/bold]]")
        console.print(format_record(record))
        console.print()

@daemon_app.command("install")
def daemon_install():
    """安装守护进程（注册计划任务），写入 WMI 过滤设置"""
    import subprocess
    from pathlib import Path
    
    # 修正路径：entry.py 在 src/TimeIndex/entry.py，脚本在 src/install.ps1
    script_path = Path(__file__).parent.parent / "install.ps1"
    if not script_path.exists():
        console.print(f"[red]错误: 找不到安装脚本 {script_path}[/red]")
        raise typer.Exit(1)
    
    console.print("[cyan]正在启动安装脚本 (需要管理员权限)...[/cyan]")
    try:
        # 使用 powershell 执行脚本
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)], check=True)
        console.print("[green]安装脚本执行完毕。[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]安装脚本执行失败: {e}[/red]")
        raise typer.Exit(1)

@daemon_app.command("uninstall")
def daemon_uninstall():
    """卸载守护进程（删除计划任务）"""
    import subprocess
    from pathlib import Path
    
    # 修正路径：entry.py 在 src/TimeIndex/entry.py，脚本在 src/uninstall.ps1
    script_path = Path(__file__).parent.parent / "uninstall.ps1"
    if not script_path.exists():
        console.print(f"[red]错误: 找不到卸载脚本 {script_path}[/red]")
        raise typer.Exit(1)
    
    console.print("[cyan]正在启动卸载脚本 (需要管理员权限)...[/cyan]")
    try:
        # 使用 powershell 执行脚本
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)], check=True)
        console.print("[green]卸载脚本执行完毕。[/green]")
    except subprocess.CalledProcessError as e:
        console.print("[red]约束：若 daemon 卸载失败，必须终止卸载流程并告警[/red]")
        console.print(f"[red]卸载脚本执行失败: {e}[/red]")
        raise typer.Exit(1)

@daemon_app.command("start")
def daemon_start(verbose: bool = typer.Option(False, "--verbose", "-v", help="启用详细输出")):
    """启动守护进程"""
    setup_logging(verbose)
    console.print("[bold green]启动守护进程...[/bold green]")
    from .daemon.daemon import Daemon
    
    # 使用统一的运行逻辑
    try:
        Daemon.run_quiet()
    except Exception as e:
        console.print(f"[red]守护进程运行出错: {e}[/red]")
        raise typer.Exit(1)

@app.command(name="config")
def config_cmd(
    key_value: Optional[str] = typer.Argument(None, help="配置项 (key:value 格式)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="启用详细输出")
):
    """修改 config.yaml 配置项或运行自检"""
    setup_logging(verbose)
    if key_value:
        if ':' not in key_value:
            console.print("[red]格式错误，请使用 key:value 格式[/red]")
            raise typer.Exit(1)
        
        key, _, value = key_value.partition(':')
        key = key.strip()
        value = value.strip()
        
        _update_config_yaml(key, value)
        console.print(f"[green]配置已更新:[/green] {key} = {value}")
        console.print("[yellow]注意：需要重启守护进程才能生效[/yellow]")
    else:
        # 显示当前配置
        table = Table(title="当前配置")
        table.add_column("配置项", style="cyan")
        table.add_column("当前值", style="magenta")
        
        table.add_row("global_blacklist", str(config.global_blacklist))
        table.add_row("retag_rules", str(config.retag_rules))
        table.add_row("rag_keepalive", str(config.rag_keepalive))
        table.add_row("rag_timeout", f"{config.rag_timeout} 天")
        table.add_row("retag_mode", str(config.retag_mode))
        table.add_row("cpu_performance_weight", str(config.cpu_performance_weight))
        table.add_row("LLM_BASE_URL", config.llm_base_url)
        table.add_row("LLM_API_KEY", '*' * len(config.llm_api_key) if config.llm_api_key else "(未设置)")
        table.add_row("USER_DEBUG", str(config.user_debug))
        
        console.print(table)
        
        # 运行自检
        _run_doctor()

def _update_config_yaml(key: str, value: str):
    """更新 config.yaml 文件中的配置项"""
    import yaml
    from pathlib import Path
    
    config_path = Path("config.yaml")
    
    current_config = {}
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            current_config = yaml.safe_load(f) or {}
    
    # 尝试转换类型
    try:
        import ast
        typed_value = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        typed_value = value
        
    current_config[key] = typed_value
    
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(current_config, f, allow_unicode=True, sort_keys=False)
    
    # 重新加载配置
    config.reload()

def _run_doctor():
    """运行环境自检"""
    console.print("\n[bold]环境自检:[/bold]")
    console.print("-" * 50)
    
    # 检查 Ollama 连通性
    console.print("  [1] 检查 Ollama 服务连通性...")
    try:
        from .daemon.llm_processor import LLMProcessor
        processor = LLMProcessor()
        if processor.is_available():
            console.print("      [green]✓ Ollama 服务正常[/green]")
        else:
            console.print("      [red]✗ Ollama 服务不可用[/red]")
            console.print(f"        请检查 LLM_BASE_URL: {config.llm_base_url}")
    except Exception as e:
        console.print(f"      [red]✗ Ollama 检查失败: {e}[/red]")
    
    # 检查 LanceDB
    console.print("  [2] 检查 LanceDB 数据库...")
    try:
        store = TimeIndexStore()
        count = store.get_count()
        console.print(f"      [green]✓ LanceDB 正常，当前记录数: {count}[/green]")
    except Exception as e:
        console.print(f"      [red]✗ LanceDB 检查失败: {e}[/red]")
    
    # 检查 WMI 权限
    console.print("  [3] 检查 WMI 权限...")
    try:
        import ctypes
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        if is_admin:
            console.print("      [green]✓ 当前以管理员权限运行[/green]")
        else:
            console.print("      [yellow]⚠ 当前非管理员权限，部分 WMI 功能可能不可用[/yellow]")
    except Exception as e:
        console.print(f"      [red]✗ WMI 权限检查失败: {e}[/red]")
    
    console.print()

if __name__ == "__main__":
    app()
