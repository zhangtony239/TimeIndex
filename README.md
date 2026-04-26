# TimeIndex

English | [简体中文](./README_zh.md)

TimeIndex is a personal activity automated indexing and task execution system based on local Large Language Models (e.g., gemma-4-e4b). It silently monitors Windows system activities in the background, uses LLMs to understand user intent, and stores it in a vector database to form a searchable and analyzable personal timeline.

## 🌟 Key Features

-   **Silent Monitoring**: Real-time collection of system activity logs such as process starts and window titles based on WMI.
-   **Intelligent Understanding**: Automatically summarizes activity and identifies user intent using local LLMs (e.g., Ollama).
-   **Semantic Search**: Supports natural language search of historical activities based on the LanceDB vector database.
-   **Idle Optimization**: Automatically performs data clustering and re-tagging when the system is idle to improve timeline quality.
-   **Automated Execution**: Understands vague instructions based on the timeline, generates ToDos, and executes them through the skill system.

## 🏗️ Project Architecture

The project adopts a modular design, mainly including the following parts:

-   **Daemon**: Responsible for WMI monitoring, LLM intent inference, and data ingestion.
-   **Storage**: Uses LanceDB to store vectorized logs, supporting efficient RAG retrieval.
-   **CLI**: Provides the `/ti` series of commands for querying, searching, and system management.
-   **Skills**: Defines execution standards for automated tasks.

## 🚀 Quick Start

### Prerequisites

-   Python >= 3.12
-   [uv](https://github.com/astral-sh/uv) (Recommended package management tool)
-   [Ollama](https://ollama.com/)/[LMStudio](https://lmstudio.ai/) (Specified LLM models need to be pulled in advance)
-   Windows OS (Administrator privileges required for WMI monitoring)

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/your-repo/TimeIndex.git
    cd TimeIndex
    ```

2.  Install and register the tool:
    ```bash
    uv tool install .
    ```

3.  Install the daemon:
    ```bash
    ti daemon install
    ```

4.  Install the `timeindex` skill to OpenClaw/ZeroClaw:
    - For **OpenClaw**: Copy the `timeindex` directory to the OpenClaw `skills` folder.
    - For **ZeroClaw**:
      ```bash
      zeroclaw skills install ./timeindex
      ```

## 🛠️ Common Commands

TimeIndex interacts through the `/ti` series of commands:

-   `ti get [timerange]`: Get activity summaries for a specified range (default: latest 50).
-   `ti search [query]`: Search activity records using natural language semantic search.
-   `ti about [tags]`: Query related activities based on tags.
-   `ti config`: View configuration and perform environment self-check.
-   `ti daemon [install|uninstall]`: Install or uninstall the background daemon.

## ⚙️ Configuration

The configuration file is located at `~/.timeindex/config.yaml` (automatically created on first run).

-   `LLM_MODEL`: Specifies the Ollama model to use.
-   `USER_DEBUG`: When enabled, detailed debug logs will be generated on the desktop.
-   `rag_keepalive`: Retention duration for RAG data.

## 📄 License

[MIT License](LICENSE)
