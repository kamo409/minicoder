# MiniCoder

一个约 600 行、**零第三方依赖**的迷你 Coding Agent（纯 Python 标准库实现）。

受 [FirstCoder](https://github.com/komorgiaogiao/firstcoder) 启发的学习型项目：从零实现一个最小但完整的 AI 编程智能体，用于吃透 Agent 的内部机制。

## 核心机制

- **Agent Loop**：一个 for 循环 —— 发送 messages → 模型回复 → 若模型请求调用工具则执行 → 把结果追加回 messages → 再次发送，直到模型给出最终答复。"记忆"就是靠每次重发完整 messages 实现的。
- **Function Calling**：TOOLS 清单（JSON Schema 写的工具说明书）随每次请求发给模型；HANDLERS 字典负责查表执行。
- **安全机制**：
  - `_safe_path()` 把所有文件操作锁在工作目录内，防路径穿越
  - 文件编辑、命令执行前需要 y/n 人工确认；拒绝信息会作为文字返回给模型而不是让程序崩溃
  - `run_python` 带 15 秒超时，防死循环
- **edit_file 三道保险**：目标文本找不到、或出现多次时拒绝修改；修改前可预览 diff。
- **会话持久化**：对话记录存 `session.json`，支持跨会话续聊。

## 工具集

| 工具 | 功能 |
|---|---|
| `read_file` | 读取文件内容 |
| `list_dir` | 列出目录 |
| `file_size` | 查看文件大小 |
| `edit_file` | 精确替换文件中的片段（带三道保险 + diff 预览） |
| `run_python` | 执行 Python 脚本（15 秒超时） |

## 运行

需要 Python 3.8+，无需 `pip install` 任何东西。

配置 DeepSeek API Key：设置环境变量 `DEEPSEEK_API_KEY`，或在项目根目录放一个 `key.txt`（已被 .gitignore 排除，不会提交）。

```bash
python agent.py                    # 对话模式（日常用法，exit 退出自动存盘）
python agent.py --fix              # 演示：生成一个有 bug 的文件让 Agent 修复
python agent.py --continue 任务...  # 接着上次会话继续执行新任务
```

## 文件结构

| 文件 | 职责 |
|---|---|
| `agent.py` | 主循环 `run()`、对话模式 `chat()`、命令行分发 `main()` |
| `llm.py` | API 请求发送、消息格式转换、key 加载 |
| `tools.py` | 5 个工具实现、TOOLS 清单、HANDLERS 表、权限确认、diff 生成 |
