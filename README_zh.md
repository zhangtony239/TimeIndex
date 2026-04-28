# TimeIndex

[English](./README.md) | 中文版

TimeIndex 是一个基于本地大模型（如 gemma-4-e4b）的个人活动自动化索引与任务执行系统。它通过后台静默监控 Windows 系统活动，利用 LLM 理解用户意图并存储到向量数据库中，形成可检索、可分析的个人时间线。

## 🌟 核心特性

-   **静默监控**: 基于 WMI 实时采集进程启动、窗口标题等系统活动日志。
-   **智能理解**: 利用本地 LLM（如 Ollama）自动总结活动摘要，识别用户意图。
-   **语义搜索**: 基于 LanceDB 向量数据库，支持通过自然语言搜索历史活动。
-   **闲时优化**: 系统空闲时自动进行数据聚类与重打标，提升时间线质量。
-   **自动化执行**: 基于时间线理解模糊指令，生成 ToDo 并通过技能系统执行。

## 🏗️ 项目架构

项目采用模块化设计，主要包含以下部分：

-   **Daemon (守护进程)**: 负责 WMI 监控、LLM 意图推断及数据入库。
-   **Storage (存储层)**: 使用 LanceDB 存储向量化日志，支持高效的 RAG 检索。
-   **CLI (交互层)**: 提供 `/ti` 系列命令，用于查询、搜索及系统管理。
-   **Skills (技能系统)**: 定义自动化任务的执行规范。

## 🚀 快速开始

### 环境要求

-   Python >= 3.12
-   [uv](https://github.com/astral-sh/uv) (推荐的包管理工具)
-   [Ollama](https://ollama.com/)/[LMStudio](https://lmstudio.ai/) (需预先拉取指定的 LLM 模型)
-   Windows 操作系统 (需管理员权限以运行 WMI 监控)

### 安装

1.  克隆仓库：
    ```bash
    git clone https://github.com/your-repo/TimeIndex.git
    cd TimeIndex
    ```

2.  安装并注册工具：
    ```bash
    uv tool install .
    ```
    > 💡 **提示**: 如果安装卡顿，可以尝试切换阿里源：
    > ```powershell
    > $env:UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"
    > uv tool install .
    > ```

3.  配置 LLM：
    > ⚠️ **重要**: 在安装守护进程之前，请确保已正确配置 `LLM_BASE_URL`。
    ```bash
    ti config LLM_BASE_URL:http://localhost:11434/v1
    ```

4.  安装守护进程：
    ```bash
    ti daemon install
    ```

5.  安装 `timeindex` 技能到 OpenClaw/ZeroClaw：
    - 对于 **OpenClaw**：将 `timeindex` 目录复制到 OpenClaw 的 `skills` 文件夹下。
    - 对于 **ZeroClaw**：
      ```bash
      zeroclaw skills install ./timeindex
      ```

## 🛠️ 常用命令

TimeIndex 通过 `/ti` 系列命令进行交互：

-   `ti get [timerange]`: 获取指定范围的日志摘要（默认最新 50 条）。
-   `ti search [query]`: 通过自然语言语义搜索活动记录。
-   `ti about [tags]`: 根据标签查询相关活动。
-   `ti config`: 查看配置并执行环境自检。
-   `ti daemon [install|uninstall]`: 安装或卸载后台守护进程。

## ⚙️ 配置说明

配置文件位于 `~/.timeindex/config.yaml`（首次运行会自动创建）。

-   `LLM_MODEL`: 指定使用的 Ollama 模型。
-   `USER_DEBUG`: 开启后将在桌面生成详细调试日志。
-   `rag_keepalive`: RAG 数据保留时长。

## 📄 开源协议

[MIT License](LICENSE)
