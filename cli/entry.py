"""
cli/entry.py - CLI 入口

处理用户的显式命令：
- /ti get [timerange|start,end]: 获取指定时间范围的日志摘要
- /ti about [tags]: 根据标签查询相关活动记录
- /ti daemon install: 安装守护进程（配置自启动），写入 WMI 过滤设置
- /ti daemon uninstall: 卸载守护进程
- /ti config [key:value]: 修改 .env 配置项
- /ti config: 读取配置项并执行自检
"""

import sys
import argparse
import logging
import json
from datetime import datetime, timedelta
from typing import List, Optional

from db.vector_store import TimeIndexStore
from utils.config import config

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def format_record(record: dict) -> str:
    """格式化单条记录为可读字符串"""
    lines = []
    ts = record.get("timestamp", "N/A")
    summary = record.get("summary", "N/A")
    refined_summary = record.get("refined_summary")
    tags = record.get("tags", [])
    refined_tags = record.get("refined_tags")
    app = record.get("primary_app", "unknown")
    confidence = record.get("confidence", 0.0)
    
    lines.append(f"  时间: {ts}")
    lines.append(f"  应用: {app}")
    lines.append(f"  摘要: {refined_summary or summary}")
    lines.append(f"  标签: {refined_tags or tags}")
    lines.append(f"  置信度: {confidence:.2f}")
    
    if refined_summary and refined_summary != summary:
        lines.append(f"  原始摘要: {summary}")
    
    return "\n".join(lines)


def cmd_get(args: argparse.Namespace):
    """处理 /ti get 命令"""
    store = TimeIndexStore()
    
    # 解析时间范围
    if args.timerange:
        # 预设时间范围
        now = datetime.now()
        if args.timerange == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif args.timerange == "yesterday":
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif args.timerange == "week":
            start = now - timedelta(weeks=1)
            end = now
        elif args.timerange == "month":
            start = now - timedelta(days=30)
            end = now
        else:
            print(f"未知的时间范围: {args.timerange}")
            print("支持的范围: today, yesterday, week, month")
            return
    elif args.start and args.end:
        # 自定义时间范围
        try:
            start = datetime.fromisoformat(args.start)
            end = datetime.fromisoformat(args.end)
        except ValueError:
            print("时间格式错误，请使用 ISO 格式 (如 2024-01-01T10:00:00)")
            return
    else:
        # 默认获取今天
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime.now()
    
    limit = args.limit or 50
    
    print(f"\n查询时间范围: {start.strftime('%Y-%m-%d %H:%M:%S')} ~ {end.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    records = store.get_activities_in_range(start, end, limit)
    
    if not records:
        print("未找到记录")
        return
    
    print(f"找到 {len(records)} 条记录:\n")
    for i, record in enumerate(records):
        print(f"[{i+1}]")
        print(format_record(record))
        print()


def cmd_about(args: argparse.Namespace):
    """处理 /ti about 命令"""
    if not args.tags:
        print("请指定标签，例如: /ti about coding browsing")
        return
    
    store = TimeIndexStore()
    tags = args.tags
    limit = args.limit or 50
    
    print(f"\n查询标签: {', '.join(tags)}")
    print("-" * 50)
    
    records = store.get_activities_by_tags(tags, limit)
    
    if not records:
        print(f"未找到包含标签 {', '.join(tags)} 的记录")
        return
    
    print(f"找到 {len(records)} 条记录:\n")
    for i, record in enumerate(records):
        print(f"[{i+1}]")
        print(format_record(record))
        print()


def cmd_daemon(args: argparse.Namespace):
    """处理 /ti daemon 命令"""
    action = args.action
    
    if action == "install":
        # TODO: 实现守护进程安装（Windows 服务注入）
        print("守护进程安装功能尚未实现，涉及 Windows 服务注入，待开发。")
        print("TODO: 配置自启动，写入 WMI 过滤设置")
        
    elif action == "uninstall":
        # TODO: 实现守护进程卸载
        print("守护进程卸载功能尚未实现，涉及 Windows 服务移除，待开发。")
        print("约束：若 daemon 卸载失败，必须终止卸载流程并告警")
        
    elif action == "start":
        # 启动守护进程（前台运行）
        print("启动守护进程...")
        from daemon.daemon import Daemon
        d = Daemon()
        try:
            d.start()
            print("守护进程已启动。按 Ctrl+C 停止。")
            import time
            while d.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n正在停止守护进程...")
            d.stop()
            print("守护进程已停止")
            
    elif action == "status":
        # 检查守护进程状态
        print("守护进程状态检查功能待实现")
        
    else:
        print(f"未知的 daemon 操作: {action}")
        print("支持的操作: install, uninstall, start, status")


def cmd_config(args: argparse.Namespace):
    """处理 /ti config 命令"""
    if args.key_value:
        # 修改配置
        key_value = args.key_value
        if ':' not in key_value:
            print("格式错误，请使用 key:value 格式")
            return
        
        key, _, value = key_value.partition(':')
        key = key.strip()
        value = value.strip()
        
        # 更新 .env 文件
        _update_env(key, value)
        print(f"配置已更新: {key} = {value}")
        print("注意：需要重启守护进程才能生效")
    else:
        # 显示当前配置
        print("\n当前配置:")
        print("-" * 50)
        print(f"  global_blacklist: {config.global_blacklist}")
        print(f"  retag_rules: {config.retag_rules}")
        print(f"  rag_keepalive: {config.rag_keepalive}")
        print(f"  rag_timeout: {config.rag_timeout} 天")
        print(f"  retag_mode: {config.retag_mode}")
        print(f"  cpu_performance_weight: {config.cpu_performance_weight}")
        print(f"  LLM_BASE_URL: {config.llm_base_url}")
        print(f"  LLM_API_KEY: {'*' * len(config.llm_api_key) if config.llm_api_key else '(未设置)'}")
        print()
        
        # 运行自检
        _run_doctor()


def _update_env(key: str, value: str):
    """更新 .env 文件中的配置项"""
    import os
    from pathlib import Path
    
    env_path = Path(__file__).parent.parent / ".env"
    
    if not env_path.exists():
        env_path.touch()
    
    lines = []
    found = False
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith('#') or '=' not in line:
                lines.append(line)
                continue
            
            env_key, _, env_value = line.partition('=')
            if env_key.strip() == key:
                lines.append(f"{key} = {value}\n")
                found = True
            else:
                lines.append(line)
    
    if not found:
        lines.append(f"\n{key} = {value}\n")
    
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    # 重新加载配置
    config.reload()


def _run_doctor():
    """运行环境自检"""
    print("\n环境自检:")
    print("-" * 50)
    
    # 检查 Ollama 连通性
    print("  [1] 检查 Ollama 服务连通性...")
    try:
        from daemon.llm_processor import LLMProcessor
        processor = LLMProcessor()
        if processor.is_available():
            print("      ✓ Ollama 服务正常")
        else:
            print("      ✗ Ollama 服务不可用")
            print(f"        请检查 LLM_BASE_URL: {config.llm_base_url}")
    except Exception as e:
        print(f"      ✗ Ollama 检查失败: {e}")
    
    # 检查 LanceDB
    print("  [2] 检查 LanceDB 数据库...")
    try:
        from db.vector_store import TimeIndexStore
        store = TimeIndexStore()
        count = store.get_count()
        print(f"      ✓ LanceDB 正常，当前记录数: {count}")
    except Exception as e:
        print(f"      ✗ LanceDB 检查失败: {e}")
    
    # 检查 WMI 权限
    print("  [3] 检查 WMI 权限...")
    try:
        import ctypes
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        if is_admin:
            print("      ✓ 当前以管理员权限运行")
        else:
            print("      ⚠ 当前非管理员权限，部分 WMI 功能可能不可用")
    except Exception as e:
        print(f"      ✗ WMI 权限检查失败: {e}")
    
    print()


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="ti",
        description="TimeIndex - 个人活动自动化索引系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  ti get today              获取今天的活动记录
  ti get week               获取本周的活动记录
  ti get --start 2024-01-01T00:00:00 --end 2024-01-02T00:00:00
                            获取指定时间范围的记录
  ti about coding meeting   查询包含 coding 或 meeting 标签的记录
  ti config                 查看当前配置并运行自检
  ti config rag_timeout:7   修改配置
  ti daemon start           启动守护进程
  ti daemon install         安装守护进程（自启动）
  ti daemon uninstall       卸载守护进程
        """
    )
    
    parser.add_argument("-v", "--verbose", action="store_true", help="启用详细输出")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # /ti get 命令
    get_parser = subparsers.add_parser("get", help="获取指定时间范围的日志摘要")
    get_parser.add_argument("timerange", nargs="?", help="时间范围 (today, yesterday, week, month)")
    get_parser.add_argument("--start", help="开始时间 (ISO 格式)")
    get_parser.add_argument("--end", help="结束时间 (ISO 格式)")
    get_parser.add_argument("--limit", type=int, default=50, help="返回记录数限制")
    get_parser.set_defaults(func=cmd_get)
    
    # /ti about 命令
    about_parser = subparsers.add_parser("about", help="根据标签查询相关活动记录")
    about_parser.add_argument("tags", nargs="+", help="要查询的标签")
    about_parser.add_argument("--limit", type=int, default=50, help="返回记录数限制")
    about_parser.set_defaults(func=cmd_about)
    
    # /ti daemon 命令
    daemon_parser = subparsers.add_parser("daemon", help="守护进程管理")
    daemon_subparsers = daemon_parser.add_subparsers(dest="action", help="操作")
    
    daemon_install = daemon_subparsers.add_parser("install", help="安装守护进程")
    daemon_install.set_defaults(func=cmd_daemon)
    
    daemon_uninstall = daemon_subparsers.add_parser("uninstall", help="卸载守护进程")
    daemon_uninstall.set_defaults(func=cmd_daemon)
    
    daemon_start = daemon_subparsers.add_parser("start", help="启动守护进程（前台）")
    daemon_start.set_defaults(func=cmd_daemon)
    
    daemon_status = daemon_subparsers.add_parser("status", help="查看守护进程状态")
    daemon_status.set_defaults(func=cmd_daemon)
    
    # /ti config 命令
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_parser.add_argument("key_value", nargs="?", help="配置项 (key:value 格式)")
    config_parser.set_defaults(func=cmd_config)
    
    return parser


def main(argv: Optional[List[str]] = None):
    """CLI 入口点"""
    parser = create_parser()
    args = parser.parse_args(argv)
    
    if not args.command:
        parser.print_help()
        return
    
    setup_logging(args.verbose)
    
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n操作已取消")
    except Exception as e:
        logger.error(f"命令执行失败: {e}", exc_info=True)
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
