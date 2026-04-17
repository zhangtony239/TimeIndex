# Daemon 模块开发指南 (daemon_howtodev.md)

## 1. 模块概述

Daemon 模块是 TimeIndex 系统的核心后台守护进程，负责长期运行的系统监控、数据采集、意图推测和任务调度。本指南基于 sysmaid 项目中已验证的 WMI 封装实现，为 daemon 模块的开发提供技术规范。

## 2. Daemon 模块开发建议

基于 sysmaid 的 WMI 封装经验，daemon 模块应遵循以下规范：

### 2.1 目录结构

```
daemon/
├── __init__.py
├── daemon.py           # 核心循环：WMI监控与任务调度
├── wmi_monitor.py      # 封装 Windows WMI 日志采集
└── llm_processor.py    # 与 Ollama 交互，负责意图推测和聚类重打标
```

### 2.2 wmi_monitor.py 设计建议

参考 sysmaid 的 Watchdog 架构，建议实现以下组件：

```python
# wmi_monitor.py 建议结构
class WmiCollector:
    """WMI 数据采集器，负责定期收集系统状态"""
    
    def __init__(self, interval=5):
        self.interval = interval
        self._thread = None
        self._is_running = False
        self._callbacks = []
    
    def start(self):
        """启动采集线程"""
        pythoncom.CoInitialize()
        self.c = wmi.WMI()
        # ... 启动轮询线程
    
    def collect_process_events(self):
        """收集进程创建/退出事件"""
        # 使用 BaseWmiEvent 模式订阅 __InstanceCreationEvent / __InstanceDeletionEvent
    
    def collect_window_titles(self):
        """收集当前可见窗口标题"""
        # 使用 win32gui.EnumWindows 枚举窗口
    
    def collect_hardware_stats(self):
        """收集 CPU、内存、GPU 等硬件统计"""
        # 使用 psutil 获取系统资源使用情况
```

### 2.3 daemon.py 设计建议

```python
# daemon.py 建议结构
class Daemon:
    """后台守护进程核心"""
    
    def __init__(self):
        self.wmi_monitor = WmiCollector()
        self.llm_processor = LLMProcessor()
        self.vector_store = VectorStore()
        self._is_running = False
        self._idle_timer = None
    
    def start(self):
        """启动守护进程"""
        self._is_running = True
        self.wmi_monitor.start()
        self._start_idle_task()
    
    def _start_idle_task(self):
        """启动闲时任务：聚类重打标"""
        # 监控系统空闲状态
        # 在闲时调用 LLM 进行数据优化
    
    def _process_event(self, event):
        """处理 WMI 采集到的事件"""
        # 1. 调用 LLM 进行意图推测
        # 2. 将结果写入 LanceDB
```

### 2.4 关键技术要点

1. **COM 线程模型**: 
   - 每个使用 WMI 的线程必须先调用 `pythoncom.CoInitialize()`
   - 线程结束前必须调用 `pythoncom.CoUninitialize()`
   - 建议在 Watchdog 的 `_loop()` 中统一管理

2. **异步非阻塞**:
   - Daemon 的监控和 LLM 请求必须是异步非阻塞的
   - 使用 `threading.Thread` 或 `asyncio` 避免阻塞主循环
   - WMI 事件订阅使用 `NextEvent(timeout)` 避免无限阻塞

3. **并发安全**:
   - LanceDB 的读写需注意并发锁问题
   - Daemon 的实时写入与闲时重打标进程之间可能存在冲突
   - 建议使用线程锁或队列机制

4. **容错机制**:
   - 每个 Watchdog 线程崩溃时应记录日志并继续运行其他 Watchdog
   - 主线程应有容错机制防止所有监控线程意外崩溃后僵死

5. **权限要求**:
   - WMI 监控可能需要管理员权限
   - 某些操作（如 kill_process、lock_volume）明确需要管理员权限
   - 建议在启动时进行权限检查

---

## 3. 开发 Checklist

- [ ] 实现 WMI 监控基类（参考 `BaseWatchdog`、`BaseWmiEvent`）
- [ ] 实现进程监控器（参考 `ProcessWatchdog`）
- [ ] 实现硬件监控器（参考 `HardwareWatchdog`）
- [ ] 实现进程启动/退出条件检测
- [ ] 实现窗口状态检测
- [ ] 实现 CPU 高负载检测
- [ ] 实现 WMI 事件订阅循环（处理超时异常）
- [ ] 实现统一启动管理（`start()` 函数）
- [ ] 实现暂停/恢复机制
- [ ] 实现 COM 初始化和清理
- [ ] 实现错误日志记录
- [ ] 实现 Action 模块（进程管理、服务控制等）
- [ ] 实现与 LLM 处理器的集成
- [ ] 实现与 LanceDB 的集成
- [ ] 实现闲时任务调度
- [ ] 实现并发锁机制
- [ ] 实现权限检查

---

## 4. 参考WMI实现项目：SysMaid的参考文件索引

| 文件 | 关键内容 |
|------|----------|
| [`sysmaid/maid.py`](sysmaid/maid.py) | 核心 Watchdog 架构、Watcher 封装、统一启动 |
| [`sysmaid/condiction/is_running.py`](sysmaid/condiction/is_running.py) | 进程启动检测（WMI 事件订阅） |
| [`sysmaid/condiction/is_exited.py`](sysmaid/condiction/is_exited.py) | 进程退出检测（WMI 事件订阅） |
| [`sysmaid/condiction/has_no_window.py`](sysmaid/condiction/has_no_window.py) | 僵尸进程检测（轮询模式） |
| [`sysmaid/condiction/is_too_busy.py`](sysmaid/condiction/is_too_busy.py) | CPU 高负载持续检测 |
| [`sysmaid/condiction/has_windows_look_like.py`](sysmaid/condiction/has_windows_look_like.py) | 屏幕图像模板匹配 |
| [`sysmaid/action/get_top_processes.py`](sysmaid/action/get_top_processes.py) | 获取高 CPU 进程 |
| [`sysmaid/action/kill_process.py`](sysmaid/action/kill_process.py) | 强制终止进程 |
| [`sysmaid/action/stop_service.py`](sysmaid/action/stop_service.py) | 停止 Windows 服务 |
| [`sysmaid/action/lock_volume.py`](sysmaid/action/lock_volume.py) | 锁定 BitLocker 卷 |
| [`sysmaid/action/alarm.py`](sysmaid/action/alarm.py) | 系统消息框 |
| [`sysmaid/action/write_file.py`](sysmaid/action/write_file.py) | 文件写入 |
