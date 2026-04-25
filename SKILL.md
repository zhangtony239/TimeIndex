---
name: timeindex-skill-engine
description: >
  TimeIndex 时间线日记：当用户通过自然语言提出模糊任务时，使用此技能来获取用户之前的相关操作记录。
  用于理解用户意图、从时间线中检索上下文、生成 ToDo 列表，并调用相关技能脚本完成任务。
---

# TimeIndex 技能引擎

## 工作流

当用户通过自然语言提出模糊任务时，按以下流程执行：

### 1. 上下文检索

从 LanceDB 中 RAG 查询初步日志，获取时间线指导。

```bash
# 使用 CLI 查询时间线
ti get today --limit 20
```

```bash
# 按标签查询相关活动
ti about <tags>
```

### 2. 意图确认

依据时间线，利用 LLM 推测任务 ToDo 的可能性，并向用户确认意图。

向用户展示：
- 从时间线中观察到的活动模式
- 推测的用户意图
- 建议的 ToDo 列表

等待用户确认后继续。

### 3. 技能调用

确认 ToDo 后，动态加载并调用 `.agents/skills/` 目录下相关的 Skill 脚本完成任务。


## CLI 完整命令参考

### `ti get` - 获取时间范围日志

获取指定时间范围内**最新**的活动记录摘要（按时间倒序排列）。

```bash
# 获取今天的活动记录
ti get today

# 获取昨天的活动记录
ti get yesterday

# 获取本周的活动记录
ti get week

# 获取最近30天的活动记录
ti get month

# 获取指定时间范围的记录
ti get --start 2024-01-01T00:00:00 --end 2024-01-02T00:00:00

# 限制返回记录数
ti get today --limit 10
```

**参数说明：**
- `timerange`: 预设时间范围 (today, yesterday, week, month)
- `--start`: 开始时间 (ISO 格式，如 2024-01-01T10:00:00)
- `--end`: 结束时间 (ISO 格式)
- `--limit`: 返回记录数限制 (默认 50)

### `ti about` - 按标签查询

根据标签查询相关活动记录。

```bash
# 查询包含 coding 标签的记录
ti about coding

# 查询包含多个标签的记录（OR 关系）
ti about coding meeting

# 限制返回记录数
ti about browsing --limit 20
```

**参数说明：**
- `tags`: 要查询的标签列表（必填）
- `--limit`: 返回记录数限制 (默认 50)

### `ti daemon` - 守护进程管理

管理后台守护进程，负责 WMI 监控、LLM 意图推测和向量存储。

```bash
# 启动守护进程（前台运行）
ti daemon start

# 安装守护进程（配置自启动）
ti daemon install

# 卸载守护进程
ti daemon uninstall

# 查看守护进程状态
ti daemon status
```

**操作说明：**
- `start`: 前台启动守护进程，按 Ctrl+C 停止
- `install`: 安装守护进程为 Windows 服务，实现开机自启（需管理员权限）
- `uninstall`: 卸载守护进程服务
- `status`: 检查守护进程运行状态

### `ti config` - 配置管理

查看和修改系统配置。

```bash
# 查看当前配置并运行自检
ti config

# 修改配置项
ti config rag_timeout:7

# 修改 LLM 服务地址
ti config LLM_BASE_URL:http://localhost:11434/v1

# 修改重打标模式
ti config retag_mode:30
```

**配置项说明：**
- `global_blacklist`: 全局进程黑名单（列表格式）
- `retag_rules`: 重打标规则（字典格式）
- `rag_keepalive`: RAG 日志生命周期模式 (默认: auto)
- `rag_timeout`: RAG 日志超时阈值（天）
- `retag_mode`: 重打标 CPU 空闲阈值
- `cpu_performance_weight`: CPU 异构权重
- `LLM_BASE_URL`: LLM API 地址 (默认: http://localhost:11434/v1)
- `LLM_API_KEY`: LLM API 密钥 (默认: ollama)

**自检项目：**
- Ollama 服务连通性检查
- LanceDB 数据库状态检查
- WMI 权限检查

## 注意事项

- 技能激活由 LLM 根据用户意图自动判断
- 执行任何操作前，先向用户确认
- 优先使用已有的 CLI 命令 (`ti get`, `ti about`) 获取上下文
- 技能执行结果应反馈给用户
- 守护进程相关操作可能需要管理员权限
- 配置修改后需要重启守护进程才能生效
