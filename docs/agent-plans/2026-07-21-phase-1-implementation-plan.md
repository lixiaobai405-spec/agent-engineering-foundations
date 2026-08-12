# Phase 1 Read-only Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在六周内从零实现一个可测试、只读、安全且可观察的 Python Agent Runtime，并用 CLI 与本地 Trace Viewer 完成端到端验收。

**Architecture:** 第一阶段分为三个可独立验收的里程碑：先稳定领域协议与扩展接口，再实现只读工具和 Agent Loop，最后加入 JSONL、SSE 与浏览器调试界面。各层只通过 `ModelProvider`、`Tool`、`EventSink` 协议协作，真实模型、文件系统、CLI 和 Web 框架不进入核心循环。

**Tech Stack:** Python 3.12、Anaconda、Pydantic 2、OpenAI Python SDK、Typer、Rich、FastAPI、SSE、原生 HTML/CSS/TypeScript、pytest、pytest-asyncio、Ruff、mypy

---

## 1. 执行前提

- 工作目录：`D:\codex-pj\search_agent`
- Git 分支：`main`
- Python 环境：Anaconda 环境 `agent-foundations`
- 第三方参考仓库：只读，不复制其核心代码
- 第一阶段不实现写文件、Shell、Git、审批、Memory、MCP 或 Sub-Agent
- 自动测试不调用真实模型或付费 API
- `.env`、Trace、缓存、构建产物不得进入 Git

## 2. 里程碑与依赖关系

```text
Milestone 1：Foundations
Message / ModelProvider / Tool / Registry / Context / FakeModel
                         │
                         ▼
Milestone 2：Read-only Agent
PathPolicy / 3 Tools / Agent Loop / OpenAI Provider / CLI
                         │
                         ▼
Milestone 3：Observability
Trace / JSONL / Redaction / Replay / FastAPI / SSE / Viewer
```

| 顺序 | 计划 | 预计时间 | 可验收产物 |
|---|---|---:|---|
| 1 | [Milestone 1: Foundations](2026-07-21-phase-1a-foundations-plan.md) | 第 1–2 周，约 40–48 小时 | 领域模型、协议、FakeModel、ToolRegistry、ContextBuilder 全部通过单元与契约测试 |
| 2 | [Milestone 2: Read-only Agent](2026-07-21-phase-1b-readonly-agent-plan.md) | 第 3–4 周，约 40–48 小时 | CLI 可通过三个只读工具分析 fixture 项目，越权与敏感读取被拒绝 |
| 3 | [Milestone 3: Trace Viewer](2026-07-21-phase-1c-trace-viewer-plan.md) | 第 5–6 周，约 40–48 小时 | 完整事件写入 JSONL、实时 SSE 展示、历史回放和浏览器验收 |

### Phase 1D：进入 Phase 2 前的独立扩展

Phase 1A–1C 构成原六周只读 Runtime 计划；Phase 1D 是用户于 2026-08-02 确认、在 Phase 2 之前插入的本机 Interactive Chat UI（交互式聊天界面）扩展：

- 设计：[`2026-08-02-phase-1d-interactive-chat-ui-design.md`](2026-08-02-phase-1d-interactive-chat-ui-design.md)
- 实施：[`2026-08-02-phase-1d-interactive-chat-ui-plan.md`](2026-08-02-phase-1d-interactive-chat-ui-plan.md)
- Task 12 实现与 fresh 质量门禁已完成；用户于 2026-08-08 确认第一阶段通过人工验收（evidence: `docs/task-evidence/phase-1d-task-12.md`）。该确认不补造历史测试输出，也不改变 evidence 中已经记录的 TDD 证据结论。
- Phase 1D 仍只提供 Chat 控制面、SQLite 多轮状态、SSE 活动摘要和一次性项目外精确只读审批。
- MCP、Memory、Sub-Agent、Shell、Sandbox、写文件和 Token streaming 没有回填 Phase 1D；Phase 2 设计与详细实施计划已生成，尚未开始任何实现 Task。权威设计见 [`2026-08-08-phase-2-controllable-coding-agent-design.md`](2026-08-08-phase-2-controllable-coding-agent-design.md)，实施计划见 [`2026-08-08-phase-2-controllable-coding-agent-plan.md`](2026-08-08-phase-2-controllable-coding-agent-plan.md)。

## 3. 每周节奏

### 第 1 周：领域协议与 Provider

- [ ] 完成 Milestone 1 的 Task 1–3。
- [ ] 记录 `Message`、`ModelRequest`、`ModelResponse` 为什么要与 SDK 类型隔离。
- [ ] 周末只读对照 `huggingface/smolagents` 的模型与消息边界。

### 第 2 周：Tool 与 Context

- [ ] 完成 Milestone 1 的 Task 4–6。
- [ ] 记录 JSON Schema 校验发生在工具执行前的原因。
- [ ] 周末只读对照 `openai/openai-agents-python` 的 Tool 抽象。

### 第 3 周：文件安全边界

- [ ] 完成 Milestone 2 的 Task 1–4。
- [ ] 对路径穿越、符号链接、敏感文件、二进制文件、大文件建立测试矩阵。
- [ ] 对 `tests/fixtures/sample_project` 执行三个工具的人工 Smoke Test。

### 第 4 周：Agent Loop 与 CLI

- [ ] 完成 Milestone 2 的 Task 5–8。
- [ ] 使用 FakeModel 重放“列目录 → 搜索 → 读文件 → 最终回答”。
- [ ] 周末只读对照 `pydantic/pydantic-ai` 的 Agent Loop 与依赖注入。

### 第 5 周：Trace 与回放

- [ ] 完成 Milestone 3 的 Task 1–4。
- [ ] 验证 API Key、Bearer Token、绝对项目路径不进入 JSONL。
- [ ] 用失败工具调用验证错误事件仍可回放。

### 第 6 周：Web Trace Viewer 与总验收

- [ ] 完成 Milestone 3 的 Task 5–8。
- [ ] 运行全部单元、集成、端到端、类型和风格检查。
- [ ] 完成第一阶段学习总结和架构决策记录。

## 4. 全阶段统一命令

第一次执行前，在 PowerShell 中创建环境：

```powershell
conda create -n agent-foundations python=3.12 -y
conda activate agent-foundations
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

每个 Task 完成后运行最小相关测试；每个 Milestone 结束后运行：

```powershell
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
```

预期：三条命令退出码均为 `0`，pytest 无失败，Ruff 输出 `All checks passed!`，mypy 输出 `Success: no issues found`。

## 5. 第一阶段最终验收

- [ ] `agent-foundations analyze D:\path\to\project "解释认证流程"` 能完成分析并输出最终答案。
- [ ] Agent 只能调用 `list_directory`、`read_file`、`search_text`。
- [ ] `..`、绝对路径逃逸、根目录外符号链接和敏感文件均被拒绝。
- [ ] FakeModel 可确定性复现多轮工具循环，不依赖网络。
- [ ] 超过十步后产生 `agent.loop.stopped`，Session 以失败状态结束。
- [ ] 每一步产生结构化 `TraceEvent`，写入 `traces/<session-id>.jsonl`。
- [ ] Viewer 只绑定 `127.0.0.1`，可接收实时事件并加载历史 JSONL。
- [ ] Viewer 支持事件筛选、暂停自动滚动、详情标签页和复制 Raw JSON。
- [ ] Trace 不包含 API Key、Authorization 值或项目绝对路径。
- [ ] `pytest`、Ruff、mypy 和 Viewer TypeScript 构建全部通过。
- [ ] `README.md` 与三篇学习笔记能够解释模块职责、边界和取舍。

## 6. 原 Phase 1A–1C 明确不实现

- 文件创建、编辑、删除与 Unified Diff
- Shell、Git、测试执行与命令审批
- Docker Sandbox（沙箱）
- Planning、Checkpoint、Memory、Skills、Hooks、MCP
- Sub-Agent 与多 Agent 编排
- 面向最终用户的聊天 Web UI（已由独立 Phase 1D 计划承接，不回填到 1A–1C）
- Token 成本图、多 Agent 关系图与远程 Viewer

上述验收、独立 Phase 1D 的既定 Task 9–12 与总验收现已完成并由用户于 2026-08-08 确认。Phase 2 权威设计与详细实施计划随后已生成；用户将另行让 planner 为单个 Task 生成执行 prompt，当前状态不构成 executor 自动开始新 Task 的授权。

## 7. 实施时使用的官方基线

- [OpenAI Developer Quickstart](https://platform.openai.com/docs/quickstart/make-your-first-api-request)：环境变量保存 API Key，真实请求只用于人工 Smoke Test。
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)：工具由 Schema 描述，模型返回工具名与结构化参数。OpenAI 官方当前优先展示 Responses API；本阶段为兼容更多 OpenAI-compatible 服务，首个 Adapter 有意识地使用 Chat Completions，未来通过新的 `ModelProvider` 增加 Responses Adapter，不修改 Agent Loop。
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse) 与 [FastAPI SSE](https://fastapi.tiangolo.com/tutorial/server-sent-events/)：本阶段手写最小 SSE wire format 以学习协议，并只用于本机调试；升级到原生 `EventSourceResponse` 时不改变 `EventBroker`。
- [Playwright Python](https://playwright.dev/python/docs/intro)：使用官方 pytest plugin 和隔离的 `page` fixture 完成真实浏览器验收。
- [Pydantic 2](https://docs.pydantic.dev/2.12/)：统一使用 `model_validate`、`model_dump` 和 `model_dump_json`，不使用 Pydantic 1 的旧序列化 API。
