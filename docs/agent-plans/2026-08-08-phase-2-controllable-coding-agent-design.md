# Phase 2 可控 Coding Agent 设计

> 状态：已确认设计基线；详细实施计划已生成，尚未授权实现 Task
>
> 日期：2026-08-08
>
> 前置状态：Phase 1A–1D 已完成，用户于 2026-08-08 确认通过人工验收
>
> 文档性质：本文件定义目标、边界、架构和验收门，不是实施计划，不授权开始任何 Task

## 1. 目标

Phase 2 在不替换自研 Agent Runtime 核心的前提下，把 Phase 1 的只读代码分析 Agent 扩展为可控 Coding Agent：

```text
读取与分析代码
  → 制定和维护计划
  → 生成可审查的修改方案
  → 经确定性策略和必要审批修改项目文件
  → 在隔离边界内运行项目检查
  → 读取 Git 反馈并继续修正
```

本阶段优先学习四类底层机制：

1. Offline Agent Eval（离线智能体评测）如何比较能力变化。
2. Durable Execution（持久化执行）如何在崩溃后安全恢复。
3. Approval、Policy、Capability、Sandbox 如何分层。
4. Tool 能力如何从只读逐级扩大到项目内受控副作用。

外部框架只用于源码对照；内部领域协议、Agent Loop、状态恢复、权限决策和执行核心继续自研。未来 MCP、ACP、A2A 等协议只通过 Adapter 接入。

## 2. Phase 1 基线与不可回填边界

Phase 1 已具备：

- `Tool` / `ToolRegistry` 与结构化 Tool Calling。
- `list_directory`、`read_file`、`search_text` 三个只读文件 Tool。
- `AgentLoop`、Session、Context、JSONL Trace 与本机 Viewer。
- Chat 控制面、SQLite 多轮状态、SSE 活动摘要。
- `PROJECT_READ_ONLY` 与 `ASK_FOR_ACCESS` 两种只读权限模式。
- 对项目外精确路径的一次性只读审批。

Phase 1D 的范围和 Task 9–12 保持不变，不追溯加入：

- MCP、Memory、Sub-Agent。
- Shell、Sandbox、写文件、Git 写操作。
- Token streaming、网络访问或电脑级完全访问。

Phase 2 的新能力必须以新设计、新 Task 和新 evidence 实现，不能改写 Phase 1 的历史范围。

## 3. 阶段结构与顺序门禁

Phase 2 保持第 7–10 周的总体长度，拆成四个顺序子里程碑：

| 子里程碑 | 重点 | 最大权限 |
|---|---|---|
| Phase 2A | Offline Eval、Planning、Todo、受限重规划 | 继续只读，无外部副作用 |
| Phase 2B | Durable Execution、Unified Diff / Patch 预览 | 能表达修改，不得落盘 |
| Phase 2C | 安全分层、Permission Profile、受控 `apply_patch` | 经审批修改项目内文件 |
| Phase 2D | 受限命令、只读 Git、测试反馈与 Context Engineering | Sandbox 内运行项目命令 |

每个子里程碑必须先完成自动验证、evidence 和用户验收，才能扩大下一层权限。复选框、周计划或本设计均不构成 executor 自动开始 Task 的授权。

## 4. Phase 2A：Offline Eval 与 Planning

### 4.1 Offline Eval 基线

先冻结 Phase 1 能力基线，再修改 Agent 行为。固定任务集至少覆盖：

- 代码定位与调用链解释。
- 错误原因分析。
- 修改方案和 Unified Diff 生成。
- 测试失败修复推理。
- 路径越权、敏感文件和危险动作拒绝。

默认使用 FakeModel 或可回放响应，不调用真实付费模型。每次 Eval 记录：

- 任务集、Prompt、响应 fixture 和 Tool 集合版本。
- Runtime 版本与环境信息。
- 成功率、步骤数、无效 Tool Call、安全拒绝和审批次数。
- 恢复次数、Token、成本和延迟；离线 profile 不强求真实 Token 或成本。

### 4.2 Planning 边界

Planning、Todo 和重规划首先是 Runtime 控制能力，不等同于电脑 Tool：

- Plan 使用版本化结构保存目标、步骤、依赖与状态。
- Todo 只能反映已证实的运行状态，不能把“模型声称完成”当作完成。
- 重规划必须记录原因并受次数限制。
- 当前计划和变更写入 Trace，可被 Eval 比较。
- Phase 2A 不新增有外部副作用的 Tool。

## 5. Phase 2B：Durable Execution 与修改提案

### 5.1 Durable Execution

Checkpoint 只是 Durable Execution 的组成部分。完整边界至少包括：

```text
schema + version
+ resume / retry / cancel
+ idempotency key
+ side-effect ledger
+ crash-point replay tests
+ run owner + lease
```

恢复必须区分：

- 模型已经决定了什么。
- Tool 请求已经创建了什么。
- 用户已经批准了什么。
- 现实世界实际执行了什么。
- 执行结果是否已经原子提交。

同一 run 同时只能有一个有效 owner。lease 过期、接管、取消、重试与终止必须可审计。

### 5.2 Unified Diff / Patch 边界

本阶段允许生成、解析、校验和预览修改提案，但不写文件：

- Patch 必须绑定明确的项目根目录和基线文件状态。
- 校验路径、文件存在性、编码、大小和预期旧内容。
- Trace 记录提案摘要和校验结果，避免默认复制敏感源码全文。
- 基线变化时使旧提案失效，不静默套用到新文件。
- 为后续 `apply_patch` 定义稳定输入契约，但不提前执行副作用。

## 6. Phase 2C：安全分层与受控文件修改

### 6.1 分层职责

```text
Tool request
  → Policy：确定性规则返回 allow / ask / deny
  → Approval：用户对这一次具体动作作出决定
  → Capability：签发主体、run、tool call、资源、操作和有效期明确的最小授权
  → ExecutionBackend：选择允许使用的执行环境
  → Sandbox：限制进程、文件、网络和资源边界
  → Side-effect ledger + Trace：记录实际执行与结果
```

- Approval 表达人的决定，不负责强制隔离。
- Policy 可硬拒绝不可审批绕过的操作。
- Capability 是可消费、可衰减、可审计的具体授权。
- Sandbox 是执行边界，不自动授予权限。
- Permission Profile 是 Policy 配置入口，不是新 Tool，也不能创造 Runtime 尚未实现的能力。

### 6.2 Permission Profile

Phase 2 保留一个安全基线并实现四种新的版本化权限配置，共五个有效 Profile：

| Profile | 行为 |
|---|---|
| `PROJECT_READ_ONLY` | 保留 Phase 1 项目内只读基线，拒绝写入和命令 |
| `ASK_ALWAYS` | 所有文件写入和命令副作用都询问 |
| `RISK_BASED` | 明确安全的项目内操作可自动执行，风险操作询问 |
| `PROJECT_FULL_ACCESS` | 项目范围内已实现的能力可自动执行，仍受硬 Policy 与 Sandbox 限制 |
| `CUSTOM` | 按 Tool、路径、操作和命令类别配置 allow / ask / deny |

Profile 必须保存版本和明确的能力清单：

- Phase 1 的 legacy `ASK_FOR_ACCESS` 只用于读取旧状态，迁移后规范化为 `ASK_ALWAYS`，不得生成新的 legacy 值。
- 新增 Tool 后，旧授权不得自动覆盖新 Tool。
- Policy 或 Tool 集合版本变化时，恢复 run 必须重新计算并在需要时重新确认。
- Agent 不能自行切换 Profile 或扩大权限。
- `PROJECT_FULL_ACCESS` 不代表互联网、项目外文件或任意系统终端访问。

### 6.3 首个写 Tool

Phase 2C 优先只增加项目内 `apply_patch`，不同时开放任意写、删除和移动：

- Patch 必须通过 Phase 2B 的结构与基线校验。
- Tool Call 绑定 exact files、操作类型和一次性 Capability。
- 执行前记录 intent，执行后原子记录结果和文件指纹。
- 崩溃恢复不得重复已经提交的修改。
- 拒绝、冲突、部分失败和回滚结果均进入 side-effect ledger 与 Trace。

## 7. Phase 2D：受限命令、Git 与反馈闭环

### 7.1 `run_command`

Agent 获得的是结构化、受控的命令执行 Tool，不是无限制交互式终端。首批只支持项目已经定义的：

- 测试命令。
- lint、typecheck 和 build。
- 必要的只读诊断命令。

执行要求：

- 在 Sandbox 和明确工作目录中运行。
- 命令分类先于 Approval；硬拒绝规则不可通过审批绕过。
- 设置超时、输出上限、取消和进程树终止。
- 不读取或记录真实凭据。
- 使用幂等键和 side-effect ledger 处理崩溃边界。

Phase 2 默认拒绝：

- 包安装和任意网络访问。
- 项目外写入和系统配置修改。
- 任意 PowerShell / Bash。
- `git add`、`commit`、`push`、`reset` 等 Git 写操作。

### 7.2 Git Tool

优先提供结构化只读 Tool：

- `git_status`
- `git_diff`
- `git_log`

它们向 Agent 返回受限、可校验的结果，避免仅靠通用 Shell 拼接 Git 命令。Git 写操作不属于 Phase 2。

### 7.3 Context Engineering

在反馈闭环稳定后整合：

- Repo Map 与相关性评分。
- Context Budget 与来源可见性。
- 压缩、缓存、重试和限流。
- 测试失败结果的去噪与优先级。

所有行为变化必须回到同一离线 Eval 基线比较。

## 8. Tool 准入门

每个新 Tool 在进入 Runtime 前必须满足：

1. 有明确的 Agent Eval 用例。
2. 声明输入 Schema、资源范围、风险等级和副作用类型。
3. 定义 Policy、Approval 与最小 Capability。
4. 有副作用时定义 Sandbox 和 Durable Execution 恢复语义。
5. 记录请求、决策、实际执行和副作用结果。
6. 覆盖成功、拒绝、越权、重复执行和崩溃恢复测试。

Tool 数量可以增加，但权限面一次只扩大一级。

## 9. 协议边界

Phase 2 不实现 MCP、ACP 或 A2A。内部 `Tool`、Run、Approval、Capability、Trace 和 UI Event 领域协议必须先稳定：

- MCP 后续只负责 Agent 与 Tool / Resource / Prompt Provider 的互操作。
- ACP 后续只负责客户端/IDE 与 Agent Backend 的会话和运行交互。
- A2A 后续只负责独立 Agent 之间的任务委派与结构化结果。
- SSE / UI Event 只提供实时提示，不作为恢复事实源。
- JSONL Trace 负责观察与诊断，不作为控制或授权事实源。
- SQLite、Checkpoint 和 side-effect ledger 保存可恢复事实。
- OpenTelemetry 后续通过 Trace Adapter 导出，不反向控制 Runtime。

## 10. 电脑级完全访问的后续落点

电脑级完全访问不属于 Phase 2。路线采用三步安排：

1. Phase 2C：把 `PermissionProfile` 与 `ExecutionBackend` 分离，为可信主机执行保留清晰接口，但不实现或暴露该模式。
2. Phase 4：只读对照 Codex、OpenHands、goose、Browser Use 等项目，形成可信主机执行的威胁模型和设计选择。
3. Phase 5 第 19 周：在 Sandbox、网络策略、凭据保护、Durable Execution 和运行所有权成熟后，通过独立安全设计与用户确认门，再实现可选 `TrustedHostExecutor`。

电脑级完全访问表示：

```text
PermissionProfile = HOST_FULL_ACCESS
ExecutionBackend  = TrustedHostExecutor
CapabilityScope   = HOST
```

它必须满足：

- 默认关闭，只能由本机用户在启动时明确开启。
- Agent、配置迁移和 Checkpoint 恢复不能自动开启。
- Tool、Policy 或能力版本变化后重新确认。
- UI 持续显示醒目的主机完全访问状态。
- 保留取消、超时、进程树终止、审计和 Trace 脱敏。
- Sub-Agent 不自动继承，不能获得比父 Agent 更大的能力。
- 远程部署和多租户环境禁止使用。

Phase 4 的调研不构成实现授权；Phase 5 仍须先生成并确认独立设计和实施计划。

## 11. 非目标

Phase 2 明确不实现：

- MCP、ACP、A2A、Skills、Hooks、Memory、Sub-Agent。
- Browser、桌面 GUI 或通用 Computer Use。
- 网络 Tool、包安装和凭据代理。
- 任意项目外写入或电脑级完全访问。
- Git 写操作、commit、push、PR 或部署。
- Token streaming；现有 SSE 继续传递活动与状态事件。
- 远程绑定、登录、多租户或生产部署。

## 12. 验证与验收原则

详细命令、测试文件和 Red/Green 步骤由后续实施计划定义。阶段级验收至少要求：

- Phase 1 离线基线可重复运行，Phase 2 各增量有比较报告。
- Planning 和重规划具有确定性限制与 Trace。
- 版本迁移、resume/retry/cancel、lease 接管和崩溃点通过自动测试。
- 已提交副作用不会因恢复或重试重复执行。
- Policy、Approval、Capability、Permission Profile、ExecutionBackend 与 Sandbox 的顺序和职责有独立测试。
- `apply_patch` 不能越出项目或绕过审批和基线校验。
- `run_command` 不能绕过命令分类、Sandbox、超时和输出限制。
- Git Tool 保持只读，包安装、网络、项目外写入和 Git 写操作稳定拒绝。
- 权限配置升级或恢复不会产生 Permission Creep（权限悄然扩大）。
- 所有危险动作可见、可拒绝、可取消、可恢复和可追踪。

## 13. 后续规划门禁

本设计已由用户确认，详细实施计划见 [`2026-08-08-phase-2-controllable-coding-agent-plan.md`](2026-08-08-phase-2-controllable-coding-agent-plan.md)。用户将另行让 planner 为单个 Task 生成执行 prompt；计划和 prompt 均不自动授权 executor。实施计划必须：

- 一次只定义和执行一个明确 Task。
- 为每个 Task 指定 evidence 路径、TDD Red/Green、质量门禁和范围审计。
- 不把本设计中的阶段描述当作 executor 授权。
- 不自动安装依赖、调用真实模型、commit、push、创建 PR 或进入下一子里程碑。
