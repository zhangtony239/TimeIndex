"""
测试脚本 - 验证 daemon 模块基本功能
"""

import logging
import time
import sys
import os

# 将 src 目录添加到 sys.path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 测试配置加载
def test_config():
    print("=" * 50)
    print("测试配置加载...")
    from TimeIndex.utils.config import config
    
    print(f"global_blacklist: {config.global_blacklist}")
    print(f"retag_rules: {config.retag_rules}")
    print(f"rag_keepalive: {config.rag_keepalive}")
    print(f"retag_mode: {config.retag_mode}")
    print(f"LLM_BASE_URL: {config.llm_base_url}")
    print("配置加载测试完成!")
    print("=" * 50)

# 测试 WMI 采集器
def test_wmi_collector():
    print("=" * 50)
    print("测试 WMI 采集器...")
    from TimeIndex.daemon.wmi_monitor import WmiCollector
    
    collector = WmiCollector(interval=2)
    
    def on_snapshot(snapshot):
        print(f"收到快照: {snapshot.timestamp}")
        print(f"  进程事件: {len(snapshot.process_events)}")
        print(f"  窗口数: {len(snapshot.windows)}")
        if snapshot.hardware:
            print(f"  CPU: {snapshot.hardware.cpu_percent}%")
            print(f"  内存: {snapshot.hardware.memory_percent}%")
    
    collector.add_callback(on_snapshot)
    collector.start()
    
    # 运行 10 秒
    print("采集器运行中 (10秒)...")
    time.sleep(10)
    
    collector.stop()
    print("WMI 采集器测试完成!")
    print("=" * 50)

# 测试 LLM 处理器
def test_llm_processor():
    print("=" * 50)
    print("测试 LLM 处理器...")
    from TimeIndex.daemon.llm_processor import LLMProcessor
    
    processor = LLMProcessor()
    
    # 检查服务可用性
    available = processor.is_available()
    print(f"LLM 服务可用: {available}")
    
    if available:
        from TimeIndex.daemon.wmi_monitor import SystemSnapshot, HardwareStats
        from datetime import datetime
        
        # 创建测试快照
        snapshot = SystemSnapshot(
            timestamp=datetime.now(),
            windows=[],
            hardware=HardwareStats(
                timestamp=datetime.now(),
                cpu_percent=50.0,
                cpu_percent_percore=[50.0],
                memory_percent=60.0,
                memory_available_gb=8.0,
                memory_total_gb=16.0
            )
        )
        
        intent = processor.infer_intent(snapshot)
        print(f"意图推断结果: {intent}")
    
    print("LLM 处理器测试完成!")
    print("=" * 50)

# 测试守护进程
def test_daemon():
    print("=" * 50)
    print("测试守护进程...")
    from TimeIndex.daemon.daemon import Daemon
    
    daemon = Daemon(
        wmi_interval=2,
        idle_threshold=60  # 1分钟空闲阈值用于测试
    )
    
    print("启动守护进程...")
    daemon.start()
    
    # 运行 15 秒
    print("守护进程运行中 (15秒)...")
    time.sleep(15)
    
    print("停止守护进程...")
    daemon.stop()
    
    print("守护进程测试完成!")
    print("=" * 50)

if __name__ == "__main__":
    print("TimeIndex Daemon 模块测试")
    print()
    
    # 运行测试
    test_config()
    
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        test_wmi_collector()
        test_llm_processor()
        test_daemon()
    else:
        print("运行 'python test_daemon.py full' 执行完整测试")
        print("当前仅测试配置加载")
    
    print()
    print("所有测试完成!")
