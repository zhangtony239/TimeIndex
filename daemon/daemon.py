"""
后台守护进程核心 - Daemon

负责整合 WMI 监控、LLM 意图推测、向量存储和闲时任务调度。
"""

import logging
import threading
import time
import os
import ctypes
from typing import Optional, List, Dict, Any
from datetime import datetime
from queue import Queue, Empty

from .wmi_monitor import WmiCollector, SystemSnapshot, ProcessEvent
from .llm_processor import LLMProcessor
from utils.config import config

logger = logging.getLogger(__name__)


class Daemon:
    """
    后台守护进程核心
    
    功能:
    - 启动 WMI 监控采集系统事件
    - 调用 LLM 进行意图推测
    - 将结果写入向量数据库 (LanceDB)
    - 闲时任务：聚类重打标优化数据
    """
    
    def __init__(
        self,
        wmi_interval: int = 5,
        idle_threshold: int = 300,  # 5分钟无活动视为空闲
        retag_batch_size: int = 20,
        global_blacklist: Optional[List[str]] = None
    ):
        """
        初始化守护进程
        
        Args:
            wmi_interval: WMI 采集间隔（秒）
            idle_threshold: 空闲阈值（秒）
            retag_batch_size: 重打标批次大小
            global_blacklist: 全局屏蔽的进程名列表
        """
        self.wmi_collector = WmiCollector(
            interval=wmi_interval,
            global_blacklist=global_blacklist or []
        )
        self.llm_processor = LLMProcessor()
        
        # 事件队列，用于传递采集到的快照
        self._snapshot_queue: Queue = Queue(maxsize=100)
        
        # 处理线程
        self._process_thread: Optional[threading.Thread] = None
        self._idle_thread: Optional[threading.Thread] = None
        
        # 状态标志
        self._is_running = False
        self._idle_threshold = idle_threshold
        self._last_activity_time = time.time()
        self._retag_batch_size = retag_batch_size
        
        # 并发锁，保护数据库读写
        self._db_lock = threading.Lock()
        
        # 注册回调
        self.wmi_collector.add_callback(self._on_snapshot)
        
        logger.info("Daemon initialized")
    
    def start(self):
        """启动守护进程"""
        if self._is_running:
            logger.warning("Daemon is already running")
            return
        
        # 检查权限
        if not self._is_admin():
            logger.warning("Daemon is not running with admin privileges. Some WMI features may not work.")
        
        self._is_running = True
        
        # 启动 WMI 采集
        self.wmi_collector.start()
        
        # 启动快照处理线程
        self._process_thread = threading.Thread(
            target=self._process_loop,
            name="DaemonProcessThread",
            daemon=True
        )
        self._process_thread.start()
        
        # 启动闲时任务线程
        self._idle_thread = threading.Thread(
            target=self._idle_loop,
            name="DaemonIdleThread",
            daemon=True
        )
        self._idle_thread.start()
        
        logger.info("Daemon started")
    
    def stop(self):
        """停止守护进程"""
        self._is_running = False
        
        # 停止 WMI 采集
        self.wmi_collector.stop()
        
        # 等待处理线程结束
        if self._process_thread:
            self._process_thread.join(timeout=10)
        if self._idle_thread:
            self._idle_thread.join(timeout=10)
        
        logger.info("Daemon stopped")
    
    def _on_snapshot(self, snapshot: SystemSnapshot):
        """快照回调函数，将快照放入队列"""
        try:
            self._snapshot_queue.put_nowait(snapshot)
            self._last_activity_time = time.time()
        except Exception:
            # 队列满时丢弃最旧的
            try:
                self._snapshot_queue.get_nowait()
                self._snapshot_queue.put_nowait(snapshot)
            except Exception:
                pass
    
    def _process_loop(self):
        """快照处理循环"""
        while self._is_running:
            try:
                # 从队列获取快照（带超时）
                snapshot = self._snapshot_queue.get(timeout=1)
                self._process_snapshot(snapshot)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in process_loop: {e}", exc_info=True)
    
    def _process_snapshot(self, snapshot: SystemSnapshot):
        """处理单个快照"""
        try:
            # 1. 调用 LLM 进行意图推测
            intent = self.llm_processor.infer_intent(snapshot)
            
            # 2. 构建记录
            record = self._build_record(snapshot, intent)
            
            # 3. 写入数据库 (需要加锁)
            with self._db_lock:
                self._write_to_db(record)
            
            logger.debug(f"Processed snapshot: {intent.get('summary', 'N/A')}")
            
        except Exception as e:
            logger.error(f"Error processing snapshot: {e}", exc_info=True)
    
    def _build_record(self, snapshot: SystemSnapshot, intent: Dict[str, Any]) -> Dict[str, Any]:
        """构建数据库记录"""
        # 提取主要窗口信息
        active_windows = []
        for win in snapshot.windows[:5]:
            active_windows.append({
                "title": win.title,
                "process": win.process_name,
                "pid": win.pid
            })
        
        # 提取进程事件
        events = []
        for event in snapshot.process_events:
            events.append({
                "type": event.event_type,
                "process": event.process_name,
                "pid": event.pid
            })
        
        return {
            "id": f"{snapshot.timestamp.timestamp()}",
            "timestamp": snapshot.timestamp.isoformat(),
            "summary": intent.get("summary", ""),
            "tags": intent.get("tags", []),
            "confidence": intent.get("confidence", 0.0),
            "primary_app": intent.get("primary_app", "unknown"),
            "active_windows": active_windows,
            "process_events": events,
            "hardware": {
                "cpu_percent": snapshot.hardware.cpu_percent if snapshot.hardware else 0,
                "memory_percent": snapshot.hardware.memory_percent if snapshot.hardware else 0
            } if snapshot.hardware else {},
            "refined_tags": None,
            "refined_summary": None,
            "cluster_id": None
        }
    
    def _write_to_db(self, record: Dict[str, Any]):
        """写入数据库 (占位符，待 db 模块实现)"""
        # TODO: 集成 LanceDB
        logger.debug(f"Writing record to DB: {record['id']}")
        pass
    
    def _idle_loop(self):
        """闲时任务循环"""
        while self._is_running:
            try:
                # 检查是否空闲
                idle_time = time.time() - self._last_activity_time
                if idle_time >= self._idle_threshold:
                    self._run_retag_task()
                
                # 每60秒检查一次
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in idle_loop: {e}", exc_info=True)
    
    def _run_retag_task(self):
        """执行重打标任务"""
        logger.info("Starting idle retag task...")
        
        try:
            # 1. 从数据库读取待重打标的记录
            with self._db_lock:
                records = self._read_pending_retag_records(self._retag_batch_size)
            
            if not records:
                logger.debug("No records to retag")
                return
            
            # 2. 调用 LLM 进行重打标
            retagged = self.llm_processor.retag_cluster(records)
            
            # 3. 写回数据库
            with self._db_lock:
                self._update_retag_records(retagged)
            
            logger.info(f"Retag task completed for {len(retagged)} records")
            
        except Exception as e:
            logger.error(f"Error in retag task: {e}", exc_info=True)
    
    def _read_pending_retag_records(self, batch_size: int) -> List[Dict[str, Any]]:
        """读取待重打标的记录 (占位符)"""
        # TODO: 集成 LanceDB
        return []
    
    def _update_retag_records(self, records: List[Dict[str, Any]]):
        """更新重打标后的记录 (占位符)"""
        # TODO: 集成 LanceDB
        pass
    
    @staticmethod
    def _is_admin() -> bool:
        """检查是否以管理员权限运行"""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    
    @property
    def is_running(self) -> bool:
        """检查守护进程是否运行中"""
        return self._is_running
    
    @property
    def idle_time(self) -> float:
        """获取当前空闲时间（秒）"""
        return time.time() - self._last_activity_time
