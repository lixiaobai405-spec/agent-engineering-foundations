# Agent Engineering Foundations

一个以学习 Agent Engineering 为目标的只读 Python Agent Runtime。第一阶段实现模型适配、工具调用、文件安全边界、Agent Loop、JSONL Trace、本地 Web Viewer，以及本机多轮 Chat 控制面（Phase 1D）。

## 当前能力

### 一次性 CLI 分析

- `agent-foundations analyze`：对本地项目执行单次只读分析，写入 JSONL Trace，可选连接 Viewer 实时推送。

### Trace Viewer

- `agent-foundations viewer`：只读 Trace Viewer，绑定 `127.0.0.1`，展示 JSONL 中的 step 时间线与脱敏详情。

### 本机 Chat + Trace

- `agent-foundations chat`：本机多轮 Chat 控制面，并挂载同一 Trace Viewer。
- SQLite 持久化 conversation、message、run、approval 和脱敏后的 tool activity UI 投影；SSE 推送活动摘要（非 durable log）。
- Chat 对 user/assistant message 渲染安全 GFM（GitHub Flavored Markdown），fenced code 使用 Shiki token 高亮并支持复制原始代码；不渲染 raw HTML、图片或不安全 URL。
- 每个 run 只显示一个可折叠工具组：active/waiting 默认展开，terminal 默认折叠；这里只保留安全摘要，完整细节仍在 Trace Viewer。
- 浏览器访问 `/chat` 进行多轮对话；`/trace?conversation_id=...&session_id=...` 精确查看该轮完整 Trace。
- 早于 tool activity 投影表的历史 run 仍显示对话和 Trace 链接，但可能不显示工具组；系统不会从 JSONL 反向伪造 UI 数据。

### Runtime 基础

- 三个只读工具：`list_directory`、`read_file`、`search_text`
- OpenAI-compatible Provider 适配与有界 Agent Loop
- 结构化 `TraceEvent` 与递归脱敏（Redactor）
- 本地 JSONL Trace 持久化（`JsonlEventSink`）
- 可选最佳努力实时事件推送（`LiveEventSink`）

## 安全边界

- 只提供 `list_directory`、`read_file`、`search_text`。
- **不写文件**，不运行 Shell 或 Git，**无 network 工具**。
- 所有路径必须位于项目根目录，**敏感文件默认硬拒绝**（审批无法绕过）。
- API Key 只从**服务端**环境变量读取，并在 Trace 写入前脱敏；不进入 SQLite Chat JSON 或前端。
- 所有服务只绑定 **`127.0.0.1`**；不支持远程绑定或多租户。
- **不支持 Token streaming**；SSE 仅作实时活动提示，历史以 HTTP/SQLite/JSONL 为准。
- Phase 1D **不支持**永久目录授权、会话级 allow-all 或写/命令/网络审批。

### 权限模式

创建 conversation 时选择：

| 模式 | 行为 |
|------|------|
| `PROJECT_READ_ONLY` | 仅允许项目根内只读；项目外路径**无审批卡**，直接拒绝。 |
| `ASK_FOR_ACCESS` | 项目内只读；项目外路径弹出**一次性**精确路径只读审批（`read` + `external_exact_path`）。 |

- 每次外部只读批准仅对**该次** `session_id + tool_call_id + canonical_path` 有效。
- 下一次访问同一路径需要**新的** approval。
- 敏感路径在两种模式下均不可审批绕过。

## 数据位置

| 路径 | 用途 |
|------|------|
| `.agent-foundations/chat.sqlite3` | Chat 控制面状态（conversation、message、run、approval） |
| `traces/` | Agent Runtime JSONL Trace（按 `session_id` 组织） |

默认路径可通过 CLI 参数覆盖（见下方命令帮助）。

## Anaconda 环境

```powershell
conda create -n agent-foundations python=3.12 -y
conda activate agent-foundations
python -m pip install -e ".[dev]"
npm install
npm run build:viewer
npm run build:chat
```

复制 `.env.example` 为 `.env` 并填入实际值；`analyze` 会在当前工作目录自动加载 `.env`（已设置的 shell 环境变量优先）。**不要**提交真实 `.env`。

| 变量 | 说明 |
|------|------|
| `AGENT_API_KEY` | Provider API Key（真实模型时必填；仅 `chat`/`analyze` 服务端使用） |
| `AGENT_MODEL` | 模型名称（真实模型时必填） |
| `AGENT_BASE_URL` | OpenAI-compatible API 地址（可选，默认 `https://api.openai.com/v1`） |

## 运行

### 一次性 CLI 分析

**终端一（可选）**启动 Viewer：

```powershell
conda activate agent-foundations
agent-foundations viewer --trace-dir traces --port 8765
```

**终端二**运行分析（可选 `--viewer-url` 启用实时事件）：

```powershell
conda activate agent-foundations
agent-foundations analyze "D:\path\to\project" "解释项目入口" --trace-dir traces --viewer-url "http://127.0.0.1:8765"
```

不指定 `--viewer-url` 时，Trace 仍写入 `--trace-dir`（默认 `traces/`）。

### 仅 Trace Viewer

```powershell
conda activate agent-foundations
agent-foundations viewer --trace-dir traces --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。

### Chat 控制面 + Trace Viewer

```powershell
conda activate agent-foundations
agent-foundations chat --state-db .agent-foundations/chat.sqlite3 --trace-dir traces --port 8765
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--state-db` | `.agent-foundations/chat.sqlite3` | SQLite Chat 状态库 |
| `--trace-dir` | `traces` | JSONL Trace 目录 |
| `--port` | `8765`（1024–65535） | 本机 HTTP 端口 |

浏览器打开 `http://127.0.0.1:8765/chat`。页面刷新后通过 HTTP 恢复 messages、runs、tool activities、latest run 与 pending approval，再连接 SSE 并立即做一次 activity catch-up；**SSE 不 replay 历史**。Chat 与 Trace 服务仍只绑定 `127.0.0.1`。

**真实模型**：需在服务端配置 `AGENT_API_KEY`、`AGENT_MODEL`（及可选 `AGENT_BASE_URL`），并单独授权与承担费用。自动测试使用 FakeModel，不调用真实 API。

## 验证

```powershell
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
npm run test:viewer
npm run typecheck:viewer
npm run test:chat
npm run typecheck:chat
npm run build:chat
git diff --check
```

自动测试使用 FakeModel、Fake SDK、fixture 或 Playwright 离线场景，**不调用真实模型或付费 API**。真实 API Smoke Test 只在用户主动确认费用后手动执行。

## 学习笔记

- [01 Foundations](docs/learning-notes/01-foundations.md)
- [02 Read-only Agent](docs/learning-notes/02-readonly-agent.md)
- [03 Observability](docs/learning-notes/03-observability.md)
- [04 Chat Control Plane](docs/learning-notes/04-chat-control-plane.md)
