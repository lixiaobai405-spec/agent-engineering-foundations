# Agent Engineering Foundations

一个以学习 Agent Engineering 为目标的 Python Agent Runtime。第一阶段完成只读分析、JSONL Trace、本地 Viewer 与本机 Chat 控制面；第二阶段在同一 Runtime 上增加 Offline Eval、Planning、Durable Execution、版本化 Permission Profile、项目内受控 `apply_patch`、Sandbox 内受限 `run_command`、只读 Git 与 loss-aware context compaction。

`PROJECT_FULL_ACCESS` 只表示项目范围内已实现能力可按版本化 Policy 自动执行，**仍受硬 Policy 与 Sandbox 限制**。它不表示任意 Shell、互联网、家目录、凭据或电脑级完全访问。

## 当前能力

### 一次性 CLI 分析

- `agent-foundations analyze`：对本地项目执行单次只读分析，写入 JSONL Trace，可选连接 Viewer 实时推送。

### Offline Eval

- `agent-foundations evaluate`：用 FakeModel 重放固定任务集，不读取真实凭据、不调用真实 Provider、不启动 Docker。
- Phase 1 基线：`docs/eval-baselines/phase-1-v1.json`
- Phase 2 基线：`docs/eval-baselines/phase-2-v1.json`（脚本 Token，不是账单）

### Trace Viewer

- `agent-foundations viewer`：只读 Trace Viewer，绑定 `127.0.0.1`，展示 JSONL 中的 step 时间线与脱敏详情。

### 本机 Chat + Trace

- `agent-foundations chat`：本机多轮 Chat 控制面，并挂载同一 Trace Viewer。
- SQLite 持久化 conversation、message、run、approval、patch proposal、command artifact metadata 和脱敏后的 tool activity UI 投影；SSE 推送活动摘要（非 durable log）。
- Chat 对 user/assistant message 渲染安全 GFM（GitHub Flavored Markdown），fenced code 使用 Shiki token 高亮并支持复制原始代码；不渲染 raw HTML、图片或不安全 URL。
- 每个 run 只显示一个可折叠工具组：active/waiting 默认展开，terminal 默认折叠；命令结果默认展示 CommandFeedback，不把 raw stdout 送进模型。
- 浏览器访问 `/chat` 进行多轮对话；`/trace?conversation_id=...&session_id=...` 精确查看该轮完整 Trace。
- 早于 tool activity 投影表的历史 run 仍显示对话和 Trace 链接，但可能不显示工具组；系统不会从 JSONL 反向伪造 UI 数据。

### Runtime 基础

- 只读工具：`list_directory`、`read_file`、`search_text`
- Planning：`set_plan`、`update_plan_step`、`replan`
- Patch：`validate_patch`（无写入）、受控 `apply_patch`（项目内，经 Policy/Approval/Sandbox）
- 命令：清单内 `run_command`，以及受限 `read_command_output` / `search_command_output`
- 只读 Git：`git_status`、`git_diff`、`git_log`（隔离配置，经 ExecutionBackend，无 Git 写工具）
- OpenAI-compatible Provider 适配、有界重试/限流与有界 Agent Loop
- 结构化 `TraceEvent` 与递归脱敏（Redactor）
- 本地 JSONL Trace 持久化（`JsonlEventSink`）
- 可选最佳努力实时事件推送（`LiveEventSink`）
- Durable run / side-effect ledger（schema v1–v10）

## 安全边界

- 敏感文件默认硬拒绝（审批无法绕过）。
- 项目外写入、任意 Shell、包安装、Git 写操作、network Tool 均不可用。
- `apply_patch` 与 `run_command` 必须走 Controlled Executor + Sandbox；Offline Eval 与 FakeBackend 测试不得退化为宿主机 subprocess。
- API Key 只从**服务端**环境变量读取，并在 Trace 写入前脱敏；不进入 SQLite Chat JSON、Artifact raw scan 或前端。
- 所有服务只绑定 **`127.0.0.1`**；不支持远程绑定或多租户。
- **不支持 Token streaming**；SSE 仅作实时活动提示，历史以 HTTP/SQLite/JSONL 为准。
- 不提供 MCP、Memory、Skills、Hooks、Sub-Agent、Browser、`HOST_FULL_ACCESS` 或 `TrustedHostExecutor`。

### 权限模式

创建 conversation 时选择版本化 Permission Profile：

| 模式 | 行为 |
|------|------|
| `PROJECT_READ_ONLY` | 项目根内只读 + planning/validate_patch/git read；拒绝 `apply_patch` 与 `run_command`。 |
| `ASK_ALWAYS` | 每次 Patch/命令都询问；一次性 Capability，再次访问需要新审批。 |
| `RISK_BASED` | 按 Policy 对写/命令询问。 |
| `PROJECT_FULL_ACCESS` | 项目范围内已实现能力可按 Policy 自动执行；**仍受硬 Policy 与 Sandbox 限制**。 |
| `CUSTOM` | 默认不扩大到写/命令。 |
| 遗留 `ASK_FOR_ACCESS` | 迁移为新 Profile 配置；项目外只读仍是一次性精确路径审批。 |

- 每次外部只读批准仅对**该次** `session_id + tool_call_id + canonical_path` 有效。
- deny 不产生副作用。
- 敏感路径在所有模式下均不可审批绕过。

## 数据位置

Chat 默认数据根是 `CommandArtifactStore.default_artifact_root()` 的父目录（`AgentFoundations`，例如 `%LOCALAPPDATA%/AgentFoundations` 或 XDG 等价路径）。不要写死盘符。覆盖优先级：`--data-root` > 环境变量 `AGENT_FOUNDATIONS_DATA_ROOT` > 该默认根。

| 路径 | 用途 |
|------|------|
| `<data-root>/chat.sqlite3` | Chat 控制面状态（conversation、message、run、approval、durable effects、artifact metadata） |
| `<data-root>/command-output/` | Command Artifact 原始字节（Agent 默认不读） |
| `<data-root>/controller/` | 受控命令工作区快照 |
| `<data-root>/traces/` | Agent Runtime JSONL Trace（按 `session_id` 组织） |

独立 `viewer` / `analyze` 仍使用各自的 `--trace-dir`。HTTP 路由名 `/command-artifacts/{id}/pages` 不变。

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
agent-foundations chat --port 8765
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--data-root` | `default_artifact_root().parent` | Chat sqlite / command-output / controller / traces 根目录 |
| `--port` | `8765`（1024–65535） | 本机 HTTP 端口 |

环境变量 `AGENT_FOUNDATIONS_DATA_ROOT` 在未传 `--data-root` 时覆盖默认根。独立 `viewer` 仍使用 `--trace-dir`。

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
- [05 Offline Eval and Planning](docs/learning-notes/05-offline-eval-and-planning.md)
- [06 Durable Execution](docs/learning-notes/06-durable-execution.md)
- [07 Security and Controlled Tools](docs/learning-notes/07-security-and-controlled-tools.md)
- [08 Command Feedback and Context Compaction](docs/learning-notes/08-command-feedback-and-context-compaction.md)
