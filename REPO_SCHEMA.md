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

意图推测: 调用 `llm_processor.py`。利用 LLM 的推理能力（支持 `reasoning_content` 提取），将窗口标题与进程名结合，生成具体的活动摘要（Summary）和主要应用（Primary App）。

初始入库: 将总结后的数据通过 `vector_store.py` 写入 LanceDB。

闲时任务 (Idle Processing): 监控系统空闲状态。在闲时，提取 LanceDB 中的初级数据，结合页标题、详细参数等，调用 LLM 进行聚类重打标，优化数据库结构。

### 3.2 存储与 RAG 层 (src/TimeIndex/db/vector_store.py)

技术栈: LanceDB SDK

功能定位: 存储带时间戳的向量化日志。

生命周期管理: 根据 .env 中的 rag_keepalive 和 rag_timeout 自动清理或归档过期日志。

### 3.3 交互与入口层 (entry.py)

技术栈: [Typer](https://typer.tiangolo.com/)

CLI 入口，处理用户的显式命令：

/ti get [timerange|start,end]: 获取指定时间范围的日志摘要，按时间**倒序**排列，默认返回最新 **50** 条。

/ti about [tags]: 根据标签查询相关活动记录。

/ti daemon install: 安装守护进程（配置自启动），写入 WMI 过滤设置。

/ti daemon uninstall: 卸载守护进程。约束：若 daemon 卸载失败，必须终止卸载流程并告警。

/ti config [key:value]: 修改 .env 配置项。

/ti config: 读取配置项并执行自检（调用 `src/TimeIndex/utils/doctor.py`）。

### 3.4 环境自检模块 (src/TimeIndex/utils/doctor.py)

功能定位: 环境依赖与权限的“体检中心”。

检查项目:
- Python 版本 (>= 3.12) 与核心依赖包 (lancedb, openai, psutil 等) 安装情况。
- WMI 权限: 检查是否具有管理员权限。
- LLM 服务: 验证 Ollama 连通性及 `LLM_MODEL` 是否已拉取。
- 存储权限: 验证 LanceDB 目录的读写权限。

## 4. 开发规范提示 (Development Guidelines)

日志规范: 系统日志由 `src/TimeIndex/utils/config.py` 统一管理。
- `USER_DEBUG=false`: 级别为 `ERROR`，仅输出到控制台。
- `USER_DEBUG=true`: 级别为 `DEBUG`，同时输出到控制台及**用户桌面**的 `timeindex_debug.log`。

LLM 接口: 统一使用 OpenAI SDK 兼容模式。针对深度思考模型，处理器会自动尝试从 `reasoning_content` 字段提取有效载荷。

数据容错: 意图推断失败时，系统会生成基于进程名的 `fallback` 记录，确保时间线连续性。