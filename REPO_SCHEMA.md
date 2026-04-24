# TimeIndex - Project Schema & Architecture

## 1. 项目概述 (Project Overview)

TimeIndex 是一个基于本地大模型（如 Gemma-4 运行于 Ollama）的个人活动自动化索引与任务执行系统。
核心目标是通过后台静默监控系统活动（WMI），利用 LLM 理解用户意图并存储到向量数据库（LanceDB）中形成时间线。基于时间线，系统能够理解用户的模糊指令，生成 ToDo 列表，并通过技能（Skills）系统自动化执行。

## 2. 建议的目录结构 (Directory Structure)

TimeIndex/
├── .env                    # 全局配置文件 (见配置定义)
├── pyproject.toml          # 项目配置与依赖管理 (使用 uv 管理依赖)
├── uv.lock                 # uv 锁定的依赖版本
├── entry.py               # CLI 入口，解析 /ti 系列命令
├── src/                   # 源代码目录
│   ├── install.ps1         # 服务安装脚本 (含自提权)
│   ├── uninstall.ps1       # 服务卸载脚本 (含自提权)
│   └── TimeIndex/
│       ├── daemon/         # 后台守护进程模块
│       │   ├── __init__.py
│       │   ├── daemon.py   # 核心循环：WMI监控与任务调度
│       │   ├── wmi_monitor.py # 封装 Windows WMI 日志采集
│       │   └── llm_processor.py # 与 Ollama 交互
│       ├── db/             # 数据库模块
│       │   ├── __init__.py
│       │   └── vector_store.py # 封装 LanceDB SDK
│       └── utils/          # 工具类
│           ├── config.py   # .env 解析与全局配置加载 (含 USER_DEBUG 动态日志逻辑)
│           └── doctor.py   # 环境自检与依赖检查
├── SKILL.md                # 技能定义与调用规范
└── README.md


## 3. 核心模块与组件设计 (Core Modules)

### 3.1 Daemon 层 (src/TimeIndex/daemon/daemon.py)

功能定位: 长期运行的后台守护进程。

数据流:

实时采集: 通过 `wmi_monitor.py` 读取程序原始日志（进程启动、窗口标题等）。

意图推测: 调用 `llm_processor.py` (基于 gemma4) 对原始日志进行一句话/标签化总结。

初始入库: 将总结后的数据通过 `vector_store.py` 写入 LanceDB。

闲时任务 (Idle Processing): 监控系统空闲状态。在闲时，提取 LanceDB 中的初级数据，结合页标题、详细参数等，调用 LLM 进行聚类重打标，优化数据库结构。

### 3.2 存储与 RAG 层 (src/TimeIndex/db/vector_store.py)

技术栈: LanceDB SDK

功能定位: 存储带时间戳的向量化日志。

生命周期管理: 根据 .env 中的 rag_keepalive 和 rag_timeout 自动清理或归档过期日志。

### 3.3 交互与入口层 (entry.py)

技术栈: [Typer](https://typer.tiangolo.com/)

CLI 入口，处理用户的显式命令：

/ti get [timerange|start,end]: 获取指定时间范围的日志摘要。

/ti about [tags]: 根据标签查询相关活动记录。

/ti daemon install: 安装守护进程（配置自启动），写入 WMI 过滤设置。

/ti daemon uninstall: 卸载守护进程。约束：若 daemon 卸载失败，必须终止卸载流程并告警。

/ti config [key:value]: 修改 .env 配置项。

/ti config: 读取配置项并执行自检（调用 `src/TimeIndex/utils/doctor.py`，实现类似 openclaw doctor 的效果）。

### 3.4 技能引擎与执行逻辑 (SKILL.md 实现)

当用户通过自然语言提出模糊任务时，执行以下工作流：

上下文检索: 从 LanceDB 中 RAG 查询初步日志，获取时间线指导。

意图确认: 依据时间线，利用 LLM 推测任务 ToDo 的可能性，并向用户确认意图。

技能调用: 确认 ToDo 后，动态加载并调用 skills/ 目录下相关的 Skill 脚本完成任务。

## 4. 开发规范提示 (Development Guidelines)

日志规范: 系统日志由 `src/TimeIndex/utils/config.py` 统一管理。受 `.env` 中的 `USER_DEBUG` 开关控制：
- `USER_DEBUG=false` (默认): 日志级别为 `ERROR`，仅输出到控制台。
- `USER_DEBUG=true`: 日志级别为 `DEBUG`，且会在用户桌面生成 `timeindex_debug.log` 文件。

平台限制: WMI 是 Windows 专属接口，请使用 wmi 或 psutil python 库实现，并注意处理权限问题（可能需要管理员权限运行 daemon）。

LLM 接口: 统一使用 OpenAI SDK 的 Python 客户端连接 LLM_BASE_URL，以便最大程度兼容 Ollama 提供的 API。

异步优先: Daemon 的监控和 LLM 请求必须是异步非阻塞的（推荐使用 asyncio），避免 WMI 监控漏掉事件。

容错机制: LanceDB 的读写需注意并发锁问题，特别是 Daemon 的实时写入与闲时重打标进程之间可能存在的冲突。

Doctor 自检: `src/TimeIndex/utils/doctor.py` 必须能够检查：WMI 权限、Ollama 服务连通性、模型(gemma4)是否已拉取、LanceDB 目录读写权限。