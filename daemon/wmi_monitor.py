"""
WMI 数据采集器 - 负责定期收集系统状态

基于 sysmaid 项目的 WMI 封装经验，实现进程事件监控、窗口标题采集和硬件统计。
"""

import logging
import threading
import time
import pythoncom
import wmi
import psutil
import win32gui
import win32process
import pywintypes
from typing import Callable, List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ProcessEvent:
    """进程事件数据类"""
    timestamp: datetime
    event_type: str  # 'created' or 'exited'
    process_name: str
    pid: int
    command_line: Optional[str] = None


@dataclass
class WindowInfo:
    """窗口信息数据类"""
    hwnd: int
    title: str
    pid: int
    process_name: str


@dataclass
class HardwareStats:
    """硬件统计数据类"""
    timestamp: datetime
    cpu_percent: float
    cpu_percent_percore: List[float]
    memory_percent: float
    memory_available_gb: float
    memory_total_gb: float
    gpu_percent: float = 0.0  # 预留 GPU 监控


@dataclass
class SystemSnapshot:
    """系统状态快照"""
    timestamp: datetime
    process_events: List[ProcessEvent] = field(default_factory=list)
    windows: List[WindowInfo] = field(default_factory=list)
    hardware: Optional[HardwareStats] = None


class WmiCollector:
    """
    WMI 数据采集器，负责定期收集系统状态
    
    功能:
    - 进程创建/退出事件监控 (WMI 事件订阅)
    - 窗口标题采集 (win32gui.EnumWindows)
    - 硬件统计 (psutil)
    """
    
    def __init__(self, interval: int = 5, global_blacklist: Optional[List[str]] = None):
        """
        初始化 WMI 采集器
        
        Args:
            interval: 采集间隔（秒）
            global_blacklist: 全局屏蔽的进程名列表
        """
        self.interval = interval
        self.global_blacklist = global_blacklist or []
        self._thread: Optional[threading.Thread] = None
        self._event_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._callbacks: List[Callable[[SystemSnapshot], None]] = []
        self._event_callbacks: List[Callable[[ProcessEvent], None]] = []
        self._lock = threading.Lock()
        self._recent_events: List[ProcessEvent] = []
        self._max_event_buffer = 100  # 最大事件缓冲区大小
    
    def add_callback(self, callback: Callable[[SystemSnapshot], None]):
        """添加快照回调函数"""
        self._callbacks.append(callback)
    
    def add_event_callback(self, callback: Callable[[ProcessEvent], None]):
        """添加事件回调函数"""
        self._event_callbacks.append(callback)
    
    def start(self):
        """启动采集线程"""
        if self._is_running:
            logger.warning("WmiCollector is already running")
            return
        
        self._is_running = True
        
        # 启动定期采集线程
        self._thread = threading.Thread(target=self._poll_loop, name="WmiPollThread", daemon=True)
        self._thread.start()
        
        # 启动 WMI 事件订阅线程
        self._event_thread = threading.Thread(target=self._event_loop, name="WmiEventThread", daemon=True)
        self._event_thread.start()
        
        logger.info("WmiCollector started")
    
    def stop(self):
        """停止采集"""
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._event_thread:
            self._event_thread.join(timeout=5)
        logger.info("WmiCollector stopped")
    
    def _poll_loop(self):
        """定期采集循环"""
        pythoncom.CoInitialize()
        try:
            while self._is_running:
                try:
                    snapshot = self._collect_snapshot()
                    with self._lock:
                        for callback in self._callbacks:
                            callback(snapshot)
                except Exception as e:
                    logger.error(f"Error in poll_loop: {e}", exc_info=True)
                time.sleep(self.interval)
        finally:
            pythoncom.CoUninitialize()
    
    def _event_loop(self):
        """WMI 事件订阅循环"""
        pythoncom.CoInitialize()
        try:
            c = wmi.WMI()
            
            # 订阅进程创建事件
            create_query = (
                "SELECT * FROM __InstanceCreationEvent "
                "WITHIN 2 WHERE TargetInstance ISA 'Win32_Process'"
            )
            create_watcher = c.ExecNotificationQuery(create_query)
            
            # 订阅进程退出事件
            delete_query = (
                "SELECT * FROM __InstanceDeletionEvent "
                "WITHIN 2 WHERE TargetInstance ISA 'Win32_Process'"
            )
            delete_watcher = c.ExecNotificationQuery(delete_query)
            
            logger.info("WMI event subscription started")
            
            while self._is_running:
                try:
                    # 检查进程创建事件
                    try:
                        event = create_watcher.NextEvent(1)
                        self._handle_process_event(event, 'created')
                    except pywintypes.com_error as e:
                        if not self._is_timeout_error(e):
                            raise
                    
                    # 检查进程退出事件
                    try:
                        event = delete_watcher.NextEvent(1)
                        self._handle_process_event(event, 'exited')
                    except pywintypes.com_error as e:
                        if not self._is_timeout_error(e):
                            raise
                            
                except Exception as e:
                    logger.error(f"Error in event_loop: {e}", exc_info=True)
                    time.sleep(1)  # 错误后短暂休眠
                    
        except Exception as e:
            logger.critical(f"WMI event loop crashed: {e}", exc_info=True)
        finally:
            pythoncom.CoUninitialize()
    
    def _is_timeout_error(self, e: pywintypes.com_error) -> bool:
        """检查是否是超时错误 (WBEM_S_TIMEDOUT = -2147209215)"""
        try:
            if len(e.args) > 2 and e.args[2] and e.args[2][5] == -2147209215:
                return True
        except (IndexError, TypeError):
            pass
        return False
    
    def _handle_process_event(self, event, event_type: str):
        """处理 WMI 进程事件"""
        try:
            process = event.TargetInstance
            process_name = process.Name
            pid = process.ProcessId
            command_line = getattr(process, 'CommandLine', None)
            
            # 过滤黑名单
            if process_name.lower() in [b.lower() for b in self.global_blacklist]:
                return
            
            proc_event = ProcessEvent(
                timestamp=datetime.now(),
                event_type=event_type,
                process_name=process_name,
                pid=pid,
                command_line=command_line
            )
            
            # 添加到事件缓冲区
            with self._lock:
                self._recent_events.append(proc_event)
                if len(self._recent_events) > self._max_event_buffer:
                    self._recent_events = self._recent_events[-self._max_event_buffer:]
                
                # 触发事件回调
                for callback in self._event_callbacks:
                    callback(proc_event)
                    
        except Exception as e:
            logger.error(f"Error handling process event: {e}", exc_info=True)
    
    def _collect_snapshot(self) -> SystemSnapshot:
        """采集系统状态快照"""
        now = datetime.now()
        
        # 采集窗口信息
        windows = self._collect_window_titles()
        
        # 采集硬件统计
        hardware = self._collect_hardware_stats()
        
        # 获取最近的事件
        with self._lock:
            recent_events = list(self._recent_events)
            self._recent_events = []  # 清空已处理的事件
        
        return SystemSnapshot(
            timestamp=now,
            process_events=recent_events,
            windows=windows,
            hardware=hardware
        )
    
    def _collect_window_titles(self) -> List[WindowInfo]:
        """收集当前可见窗口标题"""
        windows = []
        pids_with_windows = set()
        
        def enum_windows_callback(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    title = win32gui.GetWindowText(hwnd)
                    pids_with_windows.add(pid)
                    
                    # 获取进程名
                    process_name = self._get_process_name(pid)
                    
                    windows.append(WindowInfo(
                        hwnd=hwnd,
                        title=title,
                        pid=pid,
                        process_name=process_name
                    ))
            except Exception:
                pass  # 忽略无法获取信息的窗口
        
        try:
            win32gui.EnumWindows(enum_windows_callback, None)
        except Exception as e:
            logger.error(f"Error enumerating windows: {e}", exc_info=True)
        
        return windows
    
    def _collect_hardware_stats(self) -> HardwareStats:
        """收集 CPU、内存等硬件统计"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0)
            cpu_percent_percore = psutil.cpu_percent(interval=0, percpu=True)
            memory = psutil.virtual_memory()
            
            return HardwareStats(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                cpu_percent_percore=cpu_percent_percore,
                memory_percent=memory.percent,
                memory_available_gb=memory.available / (1024 ** 3),
                memory_total_gb=memory.total / (1024 ** 3)
            )
        except Exception as e:
            logger.error(f"Error collecting hardware stats: {e}", exc_info=True)
            return HardwareStats(
                timestamp=datetime.now(),
                cpu_percent=0,
                cpu_percent_percore=[],
                memory_percent=0,
                memory_available_gb=0,
                memory_total_gb=0
            )
    
    def _get_process_name(self, pid: int) -> str:
        """根据 PID 获取进程名"""
        try:
            process = psutil.Process(pid)
            return process.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return "unknown"
    
    @property
    def is_running(self) -> bool:
        """检查采集器是否运行中"""
        return self._is_running
