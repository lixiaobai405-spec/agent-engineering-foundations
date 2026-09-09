# Qwen Code 专项研究笔记

## 研究范围

本轮研究对象是 [QwenLM/qwen-code](https://github.com/QwenLM/qwen-code)，目标是理解它如何组织 Agent Loop、Tool 调度、权限、Provider、会话恢复和服务化入口，并将可迁移的架构思想与本项目现有 Runtime 分层进行比较。

本轮只读第三方源码，没有把 Qwen Code 的核心实现复制到本项目，也没有进行真实模型、真实凭据、付费 API、OAuth 或外部 MCP 服务调用。

### 固定版本与实验环境

| 项目 | 结果 |
|---|---|
| 固定提交 | `a374d1b7f97b6e8a2801451232ecf08ce2f1e594` |
| 仓库状态 | sparse checkout，`git status` clean |
| 包版本 | `0.23.0` |
| 包管理器 | `pnpm 11.24.0` |
| Node 要求 | `>=22.0.0` |
| 许可证 | Apache-2.0；仍需在未来 Fork 前保留 NOTICE、版权和上游同步记录 |
| 源码临时目录 | `C:\Users\32159\AppData\Local\Temp\search-agent-qwen-code-lab-20260908-003\qwen-code` |
| 运行环境 | 独立 Docker `node:22-bookworm-slim`；源码只读挂载并复制到容器临时目录 |

固定提交与 `main` 当前指针在研究开始时一致，但这不替代未来正式复核；开源项目的文档、版本和上游提交会继续变化。

## 一、整体架构

Qwen Code 不是只有一个交互式 CLI，而是把同一套 Core Runtime 暴露给多个入口：

```text
直接 CLI / Headless
        └── packages/cli
                └── packages/core

ACP 客户端
        └── packages/acp-bridge
                └── packages/core

SDK / HTTP + SSE
        └── qwen serve
                └── ACP bridge
                        └── workspace-scoped child runtime
```

主要包的职责边界如下：

| 包 | 主要职责 | 对本项目的启发 |
|---|---|---|
| `packages/core` | UI 无关的 Agent Loop、模型调用、上下文、Tool 注册/执行、权限、Session、Memory 和 Telemetry | Runtime 核心应保持入口无关，CLI 不应成为领域事实源 |
| `packages/cli` | 参数解析、配置装配、Ink TUI、Headless、ACP、`qwen serve` 和通道适配 | 入口层可以很多，但应复用同一个权限和执行内核 |
| `packages/acp-bridge` | ACP 生命周期、Session 多路复用、事件交付、Permission mediation、进程和 Workspace 边界 | 协议桥接层应隔离在 Runtime 外，不把协议类型渗透进领域层 |
| `packages/sdk-typescript` | TypeScript SDK 的 `query()` 以及程序化客户端接口 | 程序化调用应能复用同一 Tool/Approval 语义 |

官方架构文档还区分了两条运行路径：直接调用时，CLI 或 Headless 直接构造 Runtime；服务化调用时，HTTP/SSE 负责工作区解析和控制面，ACP bridge 再连接到长期存在的工作区 Runtime。这种拆分适合后续做多种客户端，但也增加了 Session、权限和进程生命周期的一致性要求。

## 二、Agent Loop：事件流驱动的递归继续

`packages/core/src/core/client.ts` 是理解 Loop 的入口之一。核心控制流可以概括为：

```text
用户消息
  -> sendMessageStream()
  -> Turn.run(model, request, signal)
  -> 消费 LLM event stream
  -> 发现 tool call
  -> CoreToolScheduler 调度 Tool
  -> 追加 Tool result
  -> 继续 sendMessageStream()
  -> stop / compaction / goal / budget 检查
```

观察到的关键设计：

- 模型输出不是一次性字符串，而是按 `LlmEventType` 消费的增量事件。
- Tool call 会先进入待处理集合，再由统一调度器处理结果、错误、取消和后续模型请求。
- Loop detector、Turn budget、停止 Hook、压缩和恢复状态都参与循环终止条件；因此“模型返回了工具调用”不等于“工具立即执行”。
- 递归继续调用让模型可以在工具结果后继续推理，但也要求显式限制深度、轮次和取消传播，否则容易形成无界循环。

Qwen Code 的 Loop 更接近“事件流 + Tool scheduler + 递归 continuation”，而不是 mini-SWE-agent 那种单一的 `query -> action -> observation` 线性函数。它提供了更强的交互能力，但也需要更多状态和审计字段来解释一次 Tool 调用为什么被执行、等待、拒绝或取消。

## 三、Tool 生命周期与并发调度

### 3.1 ToolRegistry 负责发现，Scheduler 负责执行状态

`packages/core/src/tools/tool-registry.ts` 负责维护已注册工具、惰性工厂、延迟工具、禁用工具和 MCP 发现工具。它还处理工具名空间冲突、工厂并发初始化、子进程环境清理和重命名后的禁用检查。

`packages/core/src/core/coreToolScheduler.ts` 则负责一次 Tool 调用的生命周期。源码中的状态包括：

```text
validating
  -> scheduled
  -> executing
  -> success / error / cancelled

scheduled
  -> awaiting_approval
  -> scheduled / error / cancelled
```

实际执行前，Scheduler 还会处理参数校验、权限计算、计划模式、Hook、Host invocation guard、取消信号、输出截断、Telemetry 和 Tool result 序列化。因此 Tool 的 `execute()` 只是生命周期的最后一段，不是完整的权限边界。

### 3.2 读操作并发、写操作串行

Qwen Code 会根据 Tool 类型和 Shell 命令安全分类，将可并发的只读调用与需要顺序执行的修改调用分组。源码中的 `isToolCallConcurrencySafe()` 和 `partitionByConcurrencySafety()` 体现了以下取舍：

- 只读文件、搜索和经过 AST 判断的只读 Shell 调用可以进入安全并发批次。
- 修改文件、可能改变环境的命令和未知 Tool 默认采用更保守的顺序语义。
- Agent 类 Tool 有单独的安全分类，不能简单按普通 Tool 的 `Kind` 判断。

这个设计比“所有 Tool 并行”更安全，也比“所有 Tool 串行”保留了搜索和诊断场景的吞吐量；代价是需要稳定的 Tool kind、命令分类器和批次级事件记录。

## 四、权限、计划模式与 Host Guard

### 4.1 PermissionManager 的层次

`packages/core/src/permissions/permission-manager.ts` 将权限决策组织为多层规则。源码可归纳为：

```text
deny
  > ask
  > allow
  > default
```

它同时区分持久规则、Session 规则、危险规则在 AUTO 模式下的过滤，以及 `coreTools` 这种“工具是否可用”的旧式 allowlist。`tools.eager` 只影响发现/加载时机，不等于禁用工具，这个区分可以避免把“尚未加载”误判成“没有权限”。

官方 SDK 文档给出的外部可见优先级还包括 `excludeTools`、`permissions.deny`、`permissions.ask`、Plan mode、YOLO、`allowedTools` 和自动分类器。由此可见，配置层允许工具与执行层能否执行是两个不同问题。

### 4.2 Plan mode 的 Shell 专门策略

`packages/core/src/core/plan-mode-shell-policy.ts` 对 `run_shell_command` 和 `monitor` 做了独立处理：

- AST 分类为 `read-only`：可以跳过交互确认，但仍可经过后续 Host guard。
- 分类为 `write`：直接拒绝，并返回继续只读调查的提示。
- 分类为 `unknown`：只允许针对这一次精确调用的批准，不能把它变成长期 allow。
- 分类过程中发生异常：保持保守的未知状态，不默认执行。
- 执行前重新检查工作目录、Approval mode、权限上下文和精确参数，防止批准后上下文发生变化。

这是一个很有价值的边界：Plan mode 不是“所有命令都禁止”，而是把可证明的只读命令与未知/写命令分开，并把批准绑定到精确调用。

### 4.3 Host invocation guard

Scheduler 在真正调用 Tool 前读取 `config.getToolInvocationGuard()`。Guard 收到的上下文包含 Tool 名、Call ID、最终参数、Session ID、工作目录、当前取消信号和可选 Invocation context。Guard 可以在执行开始前拒绝调用，拒绝结果会被记录为 `EXECUTION_DENIED` 且 `executionStatus=not_started`。

因此权限模型大致是：

```text
Tool 是否存在/可发现
  -> PermissionManager
  -> Approval mode / Plan mode
  -> PreToolUse / PermissionRequest hooks
  -> Host invocation guard
  -> Tool execute
```

这个顺序对本项目的启发是：Policy、Approval、Capability 和 Backend 不应合并成一个布尔值；每层都要能说明自己的决定和副作用状态。

## 五、Provider 与模型配置

`packages/core/src/models/modelConfigResolver.ts` 提供集中式模型配置解析，源码核对出的优先级为：

```text
modelProvider 参数
  > CLI 参数
  > 环境变量
  > settings
  > 默认值
```

解析结果还保留 source attribution（来源归因），便于解释“当前为什么使用这个模型/Provider”。官方 Provider 文档支持多个 `modelProviders`、运行时 `/model` 切换以及 Provider protocol 改变后的重启语义。凭据配置优先建议使用环境变量名；某些 Coding Plan 配置可以写入设置文件，因此部署时仍需审计本地配置的敏感信息风险。

这一层的优点是把“模型选择”和“模型调用”分开，测试可以注入假的环境变量和配置源，不必读取真实凭据。本项目应继续保留同样的 source-aware resolver，但不应直接复制其配置格式或 SDK 类型。

## 六、Session、写入租约与恢复

### 6.1 JSONL transcript 是会话记录的基础

`packages/core/src/services/sessionService.ts` 使用以 Session ID 命名的 JSONL 文件保存聊天记录和 Tool 相关记录，并提供列表、加载、恢复、分支、截断和导出等操作。JSONL 适合追加写入、故障后保留部分轨迹和对历史进行逐条重建，但它本身不是完整的副作用账本。

### 6.2 Writer lease 防止并发写入

`session-writer-lease.ts` 建立了会话写入者的所有权概念，包含：

- Writer conflict：已有有效写入者时拒绝第二个写入者。
- Writer lost：持有者发现自己的租约已经失效。
- Transcript changed：外部修改导致当前写入基线不再匹配。
- 文件/inode、进程身份、主机名和锁结构检查。

这比单纯用一个 lock 文件更接近可恢复系统所需的并发控制：旧进程不能因为恢复较慢而覆盖新进程写入。

### 6.3 Recovery plan 不是简单重放最后一条消息

`packages/core/src/core/session-recovery.ts` 区分 clean、interrupted prompt、interrupted turn 和 degraded history 等情况，并生成 `SessionRecoveryPlan`。恢复逻辑可以：

- 为孤立的 Tool use 补齐合成 Tool result，使历史结构可重建。
- 发现历史缺口后停止自动继续，并要求用户确认。
- 对中断的 Tool turn 采用显式确认，而不是默认重放可能产生副作用的调用。

本项目已有 Durable Run、Lease、Approval 和恢复层，Qwen Code 的主要可借鉴点是“恢复计划先分类，再决定是否可自动继续”，而不是直接重新调用模型。

## 七、Hooks、Extensions、MCP 与 ACP

### Hooks

官方 Hooks 文档列出的事件覆盖 Tool 前后、Session 起止、用户输入、停止、压缩、通知、权限请求/拒绝、Sub-Agent 起止和 Todo 生命周期。Matcher 允许只对特定 Tool 或事件触发。对于无法交互的 Headless/Background 场景，`ask` 没有可用的确认面时会退化为 deny，这是重要的非交互安全默认值。

### Extensions

`packages/core/src/extension` 是一个相对完整的扩展子系统，包含扩展发现、安装/卸载、设置、网络策略、归档安全和来源注册。它不是简单的“加载一个 JavaScript 文件”：扩展输入本身也要经过压缩包安全检查、网络边界和信任判断。

### MCP 与 ACP

MCP Tool 会通过 ToolRegistry 进入统一生命周期；ACP bridge 则把 Session、事件交付、Permission mediation 和 Workspace 路径作为协议适配边界。这个架构说明协议接入可以放在 Runtime 外围，但最终 Tool 执行仍必须回到统一的权限和调度系统。

本项目当前 Phase 2 明确禁止提前引入 MCP、ACP、A2A、Skills 和 Sub-Agent，因此这些内容只作为后续研究输入，不作为当前实现任务。

## 八、离线验证结果

### 8.1 已完成的验证

| 场景 | 结果 | 证据与边界 |
|---|---|---|
| 固定源码快照 | pass | Commit `a374d1b7...`，sparse checkout，工作树 clean |
| Node/依赖安装 | pass | 独立 Node 22 容器；`pnpm install --filter @qwen-code/qwen-code-core --ignore-scripts --frozen-lockfile` 成功 |
| TypeScript 构建检查 | pass | `packages/core` 的 `tsc --build` 成功 |
| 静态源码断言 | pass | 11/11：Loop、Scheduler、权限、Provider、JSONL、Writer lease、Recovery、Hooks、Extensions、网络策略、ACP bridge |
| Model config resolver 测试 | pass | 56 项通过 |
| Permission manager 测试 | pass | 420 项通过 |
| Hook system 测试 | pass | 95 项通过 |
| Session recovery 测试 | pass | 4 项通过 |
| CoreToolScheduler 测试 | partial | 981 项中 977 项通过，4 项失败 |

### 8.2 Scheduler 的 4 个失败用例

失败用例集中在 `CoreToolScheduler Plan shell routing`：

1. read-only `run_shell_command` 无提示执行。
2. read-only `monitor` 无提示执行。
3. Host guard 等待期间取消，不应执行。
4. 未配置 Host guard 时不应评估 guard。

共同触发路径是测试夹具默认把 `targetDir` 设为容器 `/tmp`。Qwen Code 的 Shell AST 分类对 `git status` 进一步调用 `getLocalGitConfigRisk('/tmp')`；当目标目录存在但不是 Git 工作树时，底层 `git config` 探测返回非预期失败，源码将风险设为保守的 `PROBE_FAILED`，从而把 `git status` 分类为 `unknown`。测试随后进入需要确认的分支，导致预期的直接执行或 Guard 等待没有发生。

这条结果应记录为“当前 Linux 容器夹具下的部分失败”，不能直接归因于网络、依赖安装或 Qwen Code 的生产逻辑缺陷。也不能据此宣称 CoreToolScheduler 完整通过；若要继续，应在实际 Git 工作树、无效目录和受支持的 Windows/Linux CI 组合中分别复核。

### 8.3 未执行内容

- 没有调用真实模型或真实 Provider。
- 没有提供 API key、OAuth、Cookie 或其他凭据。
- 没有运行真实 MCP Server、ACP 客户端、HTTP/SSE daemon 或 Web/IDE 集成。
- 没有执行 Qwen Code 完整 monorepo 测试基线；本轮只安装和验证 Core 包的目标范围。
- 没有在本项目目录安装 Node 依赖或运行第三方安装脚本。

## 九、与本项目的映射

### 可借鉴

- 用 UI 无关的 Core Runtime 同时服务 CLI、Headless、SDK 和协议桥。
- 将 ToolRegistry、PermissionManager、Approval、Host guard 和 Backend 分层。
- 对只读 Shell 做 AST 分类，对未知命令采取 fail-closed（失败即拒绝/需确认）。
- 用精确调用快照绑定 Plan mode 的一次性批准。
- 以 JSONL/事件记录保存可重建历史，以 Writer lease 防止并发 Session 覆盖。
- 生成 Recovery plan，再决定是否允许自动继续。
- Provider resolver 保留配置来源，提升可解释性和测试可替换性。

### 当前不引入

- 不复制 Qwen Code 的核心 Loop、Scheduler、权限或 Session 实现。
- 不因为 Qwen Code 有 ACP、MCP、Extensions 或 Sub-Agent 就提前扩大 Phase 2 权限范围。
- 不把 Qwen Code 的配置格式当成本项目的领域模型。
- 不把 Apache-2.0 许可证等同于“可以无条件 Fork”；未来若选择 Fork，仍需保留许可证、NOTICE、版权归属和上游同步策略。

## 十、研究结论

Qwen Code 适合被视为“产品化 Coding Agent Runtime 参考”和潜在 Fork 候选，而不是本项目的直接实现来源。它最值得研究的不是某个单独 Tool，而是把以下边界组合在一起：

```text
事件流 Agent Loop
  + Tool Scheduler
  + 分层 Permission / Approval / Guard
  + Provider source attribution
  + JSONL Session + writer lease
  + Recovery plan
  + CLI / SDK / ACP / daemon 多入口
```

它的主要复杂度也来自这些组合：入口越多，权限、Session、事件和恢复语义越需要统一。对本项目而言，当前最佳取舍仍是继续自研现有 Runtime 基础，吸收上述可验证的边界设计，等六个项目全部完成后再用统一任务集、Fake Backend、安全检查表和许可证审计进行 Baseline Selection Gate。

## 官方资料与固定源码入口

- [Qwen Code 官方仓库](https://github.com/QwenLM/qwen-code)
- [固定提交源码](https://github.com/QwenLM/qwen-code/tree/a374d1b7f97b6e8a2801451232ecf08ce2f1e594)
- [Architecture](https://qwenlm.github.io/qwen-code-docs/en/developers/architecture/)
- [Tools introduction](https://qwenlm.github.io/qwen-code-docs/en/developers/tools/introduction/)
- [TypeScript SDK](https://qwenlm.github.io/qwen-code-docs/en/developers/sdk-typescript/)
- [Hooks](https://qwenlm.github.io/qwen-code-docs/en/users/features/hooks/)
- [Model providers](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/model-providers.md)
- [Core Loop source](https://github.com/QwenLM/qwen-code/blob/a374d1b7f97b6e8a2801451232ecf08ce2f1e594/packages/core/src/core/client.ts)
- [Tool Scheduler source](https://github.com/QwenLM/qwen-code/blob/a374d1b7f97b6e8a2801451232ecf08ce2f1e594/packages/core/src/core/coreToolScheduler.ts)
- [Session recovery source](https://github.com/QwenLM/qwen-code/blob/a374d1b7f97b6e8a2801451232ecf08ce2f1e594/packages/core/src/core/session-recovery.ts)

