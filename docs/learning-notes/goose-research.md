# goose 专项研究笔记

> 研究对象：`aaif-goose/goose`
> 固定提交：`8ae4e4ba02836529790f47109b8785e8b42843a7`
> 提交时间：`2026-08-28`
> Workspace 版本：`1.48.0`
> 许可证：Apache-2.0
> 研究状态：源码与官方文档研究完成；已在独立 Docker Rust 1.94.1 环境完成依赖解析和源码断言，定向 Rust 测试因 crates.io 镜像索引超时未进入编译。

## 1. 本轮问题

本轮围绕四个问题研究 `goose`：

1. Extension（扩展）如何装配、加载、更新和持久化。
2. Provider（模型提供商）如何抽象模型调用、上下文和权限能力。
3. Tool（工具）请求如何经过审批、执行、通知、取消和结果回写。
4. Session（会话）如何持久化，以及恢复时事实源是什么。

本轮没有调用真实模型、真实凭据或付费 API，也没有在本项目中安装依赖或修改生产代码。

## 2. 总体架构判断

`goose` 当前最值得学习的部分，是把 Agent Loop（智能体循环）组织成可重新推导的状态机，而不是把所有状态藏在一个长期运行的内存循环中：

```text
SQLite Session
    -> reload conversation
    -> ordered StateMachine steps
    -> first applicable Operation / Inference
    -> GooseEffect
    -> SessionManager durable write
    -> AgentEvent
    -> reload Session for next pass
```

`goose-agent` 的 README 将这一设计描述为“可以自行组装的 Agent Loop 状态机”。`StateMachine::step` 按顺序检查每个 `Operation` 或 `Inference`，只应用第一个适用步骤；`run` 在每次 pass 前重新加载会话，应用 Effect 后再决定是否继续。因此，下一步主要由已持久化的会话和消息决定，而不是由上一次函数调用留下的隐式内存状态决定。

这与普通的：

```text
模型 -> 解析工具 -> 执行工具 -> 把结果塞回上下文 -> 再调用模型
```

相比，增加了明确的恢复边界、操作优先级、取消出口和可观察事件。

## 3. Extension 系统

### 3.1 扩展配置类型

`ExtensionConfig` 当前包含四类扩展：

| 类型 | 运行位置 | 主要用途 | 研究判断 |
|---|---|---|---|
| `stdio` | 独立子进程 | 连接外部 MCP Server | 适合第三方工具和本地服务，但需要命令、环境变量和进程边界控制 |
| `builtin` | 内置 MCP Server，必要时可放入 Docker | goose 自带能力 | 便于统一内置工具协议 |
| `platform` | Agent 进程内 | 宿主平台能力，如调度或 UI 集成 | 能力强，必须由宿主显式提供上下文 |
| `streamable_http` | HTTP MCP Server | 连接远程扩展 | 需要处理 endpoint、headers、OAuth、超时和网络信任边界 |

扩展以 MCP（Model Context Protocol，模型上下文协议）为主要边界，除 Tools 外还支持 Prompts、Resources 和 Instructions。模型请求准备阶段会从已加载的扩展中聚合工具和提示片段，并对扩展信息排序，避免 HashMap 顺序变化造成提示缓存不稳定。

### 3.2 ExtensionManager 的职责

`ExtensionManager` 持有已加载扩展、MCP client（客户端）、工具缓存、缓存版本和平台上下文：

- 加载时根据配置创建 stdio、HTTP、builtin 或 platform client。
- 加载前解析环境变量、secret（密钥）引用、工作目录和超时。
- 对每个扩展发现工具，再统一加上扩展名前缀，形成可路由的工具名。
- 使用缓存减少反复 `list_tools`；新增、删除或配置变化时递增缓存版本并失效缓存。
- Tool dispatch（工具分发）时先解析工具所有者，再检查该工具是否在扩展允许列表中，然后交给对应 MCP client 执行。
- 支持 MCP notification（通知）、Action Required（需要用户动作）流和 MCP App 资源附件。

这个分层把“发现有哪些工具”和“执行某个工具”分开，便于在工具清单变化后重新构建模型输入，也便于在执行层统一处理取消、通知和动作请求。

### 3.3 扩展生命周期

扩展生命周期可以概括为：

```text
ExtensionConfig
    -> resolve 环境/密钥/结构变化
    -> create MCP client
    -> initialize / list tools / list resources
    -> cache prefixed tools
    -> dispatch calls
    -> invalidate cache on add/remove/change
    -> persist enabled config in session
```

当前源码有几个值得注意的细节：

- `resolved_config` 只保存在内存，用于检测 keyring（密钥环）中的 secret 轮换；不会把解析后的 secret 序列化到磁盘。
- 扩展配置变化时，即使名称相同，也会重新启动/建立 client；比较同时覆盖原始配置和解析后的配置。
- `add_extensions_bulk` 并行加载多个扩展，统一在全部结果结束后持久化一次。
- 批量加载失败时，持久化的是“实际成功加载的扩展集合”，失败扩展不会一直留在会话 enabled list 中并在每次恢复时重复失败。
- `load_extensions_from_session` 会跳过已经加载的扩展；对 provider 自己管理上下文的 CLI 型 provider，会跳过 stdio/HTTP 扩展，避免 goose 与 provider 同时管理同一上下文。
- 扩展命令的环境变量有显式黑名单，包括 `PATH`、`PATHEXT`、`SystemRoot`、动态链接器变量、`PYTHONPATH`、`NODE_OPTIONS`、`TEMP`、`USERPROFILE` 等，目的是减少路径劫持、动态库劫持和运行时注入风险。
- stdio 扩展启动前还执行恶意包/命令参数检查；这属于扩展装配阶段的前置安全门。

### 3.4 会话级扩展状态

扩展状态使用扁平化的版本键保存：

```text
<extension_name>.<version> -> JSON value
```

当前启用扩展列表使用 `enabled_extensions.v0`。`ExtensionState` trait（特征）统一提供序列化/反序列化入口，未来不同扩展可以分别占用自己的版本键。

恢复时优先使用会话中的扩展配置；会话没有对应状态时才回退到全局配置。这样可以支持：

- 全局默认扩展。
- 某个会话动态启用或禁用扩展。
- 从旧版本读取不同的扩展状态格式。
- 扩展状态与对话内容一起导出、复制或恢复。

### 3.5 对本项目的启发

可以借鉴：

- 扩展配置与运行时 client 分离。
- 解析后的 secret 只在内存存在，持久化配置只保留引用和非敏感结构。
- 工具清单缓存必须有明确的失效版本。
- 扩展状态使用带版本的命名空间，而不是把所有状态塞进一个不可演进的 JSON。
- 加载失败后保存实际状态，避免恢复循环反复失败。

不应直接照搬：

- `platform` 扩展的进程内高权限模型。
- `stdio`/HTTP 扩展直接连接用户环境的默认信任假设。
- 将 MCP 扩展能力等同于本项目 Phase 2 的可用 Tool。当前项目计划明确禁止提前引入 MCP、ACP、A2A、Skills 和 Sub-Agent。

## 4. Provider 抽象

### 4.1 Provider trait 的核心边界

`Provider` trait（提供商接口）把具体模型 SDK、CLI harness（外部模型控制器）和 Agent Runtime 隔开。核心入口是：

```rust
stream(model_config, system, messages, tools)
```

Provider 接收已经整理好的系统提示、消息和工具定义，并返回由消息/用量组成的异步流。默认 `complete` 只是收集 `stream`，说明 streaming（流式）是主路径而不是附加能力。

除了调用本身，Provider 还统一表达以下能力：

- provider 名称和可选的 provider session ID。
- `resume`，用于恢复 provider 自己的会话。
- 上下文限制和重试配置。
- 支持模型发现、模型信息和推荐模型筛选。
- 根据 canonical registry（规范模型注册表）过滤不支持工具调用的模型。
- 是否由 provider 自己管理上下文。
- 是否支持 builtin tools。
- OAuth 配置与 credential refresh（凭据刷新）。
- Goose mode、thinking effort（思考强度）和模型选择同步。
- Provider 自己的权限路由以及权限确认处理。

这说明 goose 没有把 Provider 简化为一个 `call_llm()` 函数，而是把模型生态的生命周期能力也纳入接口。

### 4.2 自管理上下文是重要分叉

`manages_own_context()` 是一个关键开关。对于 Claude Code、Gemini CLI 一类自身拥有会话上下文的外部 harness：

- goose 跳过自己的部分 context compaction（上下文压缩）和 Tool Pair summarization（工具对摘要）。
- goose 可以跳过某些 stdio/HTTP 扩展装配。
- provider 内部状态成为模型上下文的事实源，goose 主要维护外层 session、事件和控制协议。

这个设计避免两个系统同时压缩、重排或持有同一段上下文。

### 4.3 Provider 生命周期的研究结论

Provider 的生命周期可以抽象为：

```text
provider config
    -> credentials / OAuth
    -> instantiate Provider
    -> apply session model selection
    -> optional resume(provider session)
    -> stream with messages + tools
    -> usage / tool calls / errors
    -> mode or thinking update
```

本项目可以借鉴“能力接口化”和 `manages_own_context` 这种明确分叉，但仍应让项目自己的 `ModelProvider` 保持更小、更容易测试。模型 SDK 类型不应进入 Policy、Approval、Capability 或持久化领域层。

## 5. Tool 生命周期

### 5.1 状态机中的操作顺序

本固定提交的 Agent 状态机大致按以下优先级组织：

```text
EntryHook
  -> SlashCommand
  -> Steer
  -> MaxTurns
  -> BangShell
  -> Compaction
  -> ToolPairCompaction
  -> ToolApproval
  -> Doctor / Project / Skill / Recipe
  -> ToolExecution
  -> UnknownTool
  -> Retry
  -> StopHook
  -> ExitOnError
  -> Status
  -> Inference
```

每个步骤可以返回 `NotApplicable` 或 `Applied`。一轮只应用第一个适用步骤，Effect 写入完成后再重新加载会话。这个顺序使审批、执行、未知工具、重试和最终模型调用成为可审查的阶段，而不是埋在一次大型函数中。

### 5.2 正常 Tool 调用路径

正常 Tool 调用大致经历：

```text
Provider stream
    -> assistant ToolRequest(tool_call_id)
    -> ToolApprovalOperation
    -> persist executable / ActionRequired metadata
    -> user confirmation when needed
    -> ToolExecutionOperation
    -> pre-tool hooks
    -> ExtensionManager.dispatch_tool_call
    -> MCP client.call_tool
    -> notifications / action-required stream / result
    -> user ToolResponse with same tool_call_id
    -> next Inference
```

`ToolApprovalOperation` 从持久化消息推导 `ApprovalState`：

- 已经有 ToolResponse 的请求不再处理。
- 已产生 ActionRequired 的请求不会重复产生审批。
- 已有确认响应的请求会根据 Allow/Deny 状态更新执行标记。
- 工具是否可执行通过 `goose.executable` 写入 ToolRequest metadata。
- 需要用户确认的请求会产生 user-only 的 ActionRequired 消息。

这是一种很有价值的设计：审批状态不是只有内存中的 Promise 或 channel，而是会话消息和 Tool metadata 的派生状态，因此进程恢复后可以继续判断请求是否已经审批、执行或回答。

### 5.3 执行、通知和取消

`ToolExecutionOperation` 只接收已知且可执行的待处理请求，并为每个请求建立带 session ID、工作目录和 request ID 的 `ToolCallContext`。调用过程还包括：

- pre-tool hook 和 post-tool hook。
- 扩展 client 的通知流。
- MCP action-required 流。
- MCP App 结果资源的二次读取与可信元数据封装。
- 用户取消时停止等待，并为未回答请求写入“执行在完成前被中断”的 ToolResponse。
- 多个 Tool 可以通过 stream 合并并发接收结果。

执行结果最终以 user ToolResponse 写入会话；因此模型下一轮看到的是稳定的 Tool Call/Tool Response 对，而不是仅在 UI 中显示的一次性输出。

### 5.4 动态扩展变化

如果 Tool 调用是管理扩展的请求，执行成功后会产生 `SetExtensionData` Effect，把当前 ExtensionManager 配置保存到会话。扩展变化后工具缓存也会失效，下一次 Inference 会重新发现工具并重新生成扩展提示片段。

这形成了一个闭环：

```text
Tool call manages extension
    -> extension manager changes
    -> tool cache invalidated
    -> extension state persisted
    -> next provider request uses new tool set
```

### 5.5 对本项目的启发

值得吸收：

- Tool request 使用稳定 ID，Approval、Execution、Response 全部按 ID 关联。
- 执行资格是可持久化元数据，而不是只存在于 UI 回调中。
- ActionRequired、ToolResponse、取消结果都应成为恢复可见的事件/状态。
- 工具发现、审批判断、执行分发和结果回写应由不同层负责。
- 多个工具的通知流和结果流可以合并，但每个结果必须保留 request ID。

本项目需要保持更严格的安全边界：`goose` 文档中的 Developer 扩展默认偏向 autonomous（自主执行），并允许用户权限范围内的 shell/file write；本项目仍应坚持 `Policy -> Approval -> Capability -> ExecutionBackend -> Sandbox`，不能因为有稳定 Tool 生命周期就默认开放本机 Shell 或项目外文件访问。

## 6. 持久化会话设计

### 6.1 SQLite 是当前事实源

当前 SessionManager 使用 `sessions.db`，源码中的 schema version（模式版本）为 `16`。数据库设置包括：

- SQLite WAL journal mode（预写日志模式）。
- 30 秒 busy timeout。
- 初始化、迁移和写入使用 `BEGIN IMMEDIATE`，串行化竞争写入。
- `schema_version` 表负责迁移版本。
- `sessions`、`messages`、`usage_ledger` 等表分别保存会话、消息和用量。

会话对象本身包括工作目录、名称、时间戳、扩展数据、recipe、conversation、provider name、model config、goose mode、父会话 ID、归档状态和消息摘要等信息。

### 6.2 EffectHandler 的持久化职责

状态机不直接操作 SQLite，而是产生 `GooseEffect`，由 `SessionManager` 实现的 `EffectHandler` 统一处理：

| Effect | 持久化动作 |
|---|---|
| `AppendMessage` | 插入一条消息 |
| `ReplaceConversation` | 替换完整对话并更新上下文用量 |
| `PatchToolRequestMeta` | 按 Tool Call ID 合并更新 Tool metadata |
| `SetMessageVisibility` | 更新用户/Agent 可见性 |
| `SetRecipe` | 更新 recipe |
| `SetExtensionData` | 更新会话扩展状态 |
| `RecordUsage` | 写入用量账本并发出 Usage event |

在 Effect 应用前，系统会补齐缺失的 message ID；在写入后再发出 MessageUsage、HistoryReplaced 或 Usage 事件。这使“持久化事实”和“UI/Trace 观察面”保持了清晰分层。

### 6.3 每轮 reload 的意义

`run` 的循环不是把一份 Session 引用一直留在内存，而是：

1. 从 SessionManager 重新读取会话。
2. 根据当前 conversation 计算第一个适用步骤。
3. 应用 Effect 并持久化。
4. 如果没有 yield，则再次 reload。

收益是：

- 状态机可以从持久化消息恢复。
- 外部输入或审批消息写入后，下一轮能看到最新状态。
- 进程崩溃时，已完成的 Effect 有机会留下可审计的中间状态。
- Operation 不需要依赖上一次调用的隐式局部变量。

代价是更多数据库读取和更复杂的消息状态建模；对于本项目，这个代价值得用于高风险 Tool 和 Approval 路径，但简单只读推理任务可以谨慎减少不必要的写入。

### 6.4 Resume、Fork、Export

官方 CLI 文档提供 `--resume`、`--fork`、`--edit` 和 `session export` 等会话操作。源码同时提供会话复制、导入、导出、截断和替换 conversation 的能力。

这里需要区分：

- `resume` 是在原会话事实源上继续。
- `fork/copy` 是创建新的父子关系和独立持久化对象。
- `edit/truncate` 改变后续模型可见的历史边界。
- `export` 是外部交接/审计格式，不应自动等同于内部恢复格式。

本项目后续若实现恢复，应保留这种区别，不要把“导出的 Markdown”当作唯一恢复事实源。

## 7. 安全和边界观察

官方文档显示，goose 的 Developer 扩展在 autonomous 模式下可以使用 shell 和文件写入；Manual/Smart Approval 模式则通过 Always Allow、Ask Before、Never Allow 管理 Tool 权限。源码还会根据 MCP tool annotation（工具注解）把非只读工具纳入 smart approval。

研究结论不是“goose 不安全”，而是它的默认产品目标与本项目当前目标不同：

| 方面 | goose 的产品取向 | 本项目的取向 |
|---|---|---|
| Tool 执行 | 面向用户本机效率，支持 autonomous | 默认受控，权限必须显式收敛 |
| Extension | MCP 生态优先，支持进程内 platform 扩展 | Phase 2 暂不引入 MCP/ACP/A2A |
| 会话 | SQLite durable session + 动态扩展 | 事件、checkpoint、审批和副作用账本分层 |
| Provider | 兼容多个远程模型和 CLI harness | 保持可替换 Adapter，避免 SDK 进入领域层 |
| Sandbox | 可接 Docker，但产品能力允许用户环境访问 | Sandbox 是权限扩大前的硬边界 |

## 8. 与本项目的映射

### 可以作为设计参考的部分

1. `Operation -> Effect -> durable runtime` 的拆分。
2. 由持久化 conversation 重新推导下一步，而不是依赖隐式内存状态。
3. Tool Call ID 驱动的审批、执行和响应关联。
4. 版本化 ExtensionData 命名空间。
5. 工具缓存的版本化失效机制。
6. Provider 能力接口中的自管理上下文分叉。
7. SQLite 写入的事务化和并发初始化保护。

### 暂不引入的部分

1. MCP Extension 作为项目 Phase 2 的新权限入口。
2. 进程内 platform extension。
3. autonomous 默认执行。
4. 远程 Streamable HTTP 扩展。
5. Provider 自己持有上下文并绕过项目统一 checkpoint 的模式。
6. 直接复制 goose-agent 或 goose 的核心实现。

### 建议的独立实现顺序

如果未来项目完成当前 Phase 2 并进入后续设计，建议先抽象小型、项目自有的协议：

```text
PendingToolCall
    -> ApprovalDecision
    -> ExecutionLease
    -> ToolResult / ToolError / ToolCancelled
    -> durable event + checkpoint
```

先在现有 Policy、Approval、Capability、Backend、Sandbox 体系内验证，再考虑是否提供 MCP Adapter。这样可以学习 goose 的状态机思想，但不让第三方协议反过来决定本项目的安全模型。

## 9. 本轮证据和验证边界

### 已完成

- 在独立临时目录克隆 goose 源码。
- 固定并记录提交 `8ae4e4ba02836529790f47109b8785e8b42843a7`。
- 源码工作区保持 clean，未在参考仓库修改文件。
- 阅读 `goose-agent` 状态机、Provider trait、ExtensionConfig、ExtensionManager、Tool Approval/Execution 和 SessionManager。
- 使用只读静态断言确认以下结构存在：
  - 状态机每轮 reload session。
  - 只应用第一个适用步骤。
  - SQLite `sessions.db`。
  - 版本化扩展状态键。
  - 持久化 Tool executable metadata。
  - Provider 接收工具定义并提供 stream 主入口。
  - 扩展环境变量黑名单。
  - 工具缓存失效和版本递增。
- 在独立 Docker `rust:1.94.1-bookworm` 环境中完成 Cargo 依赖解析，结果为 `METADATA_STATUS=0`。
- 对固定提交重新执行 8 组源码断言，全部通过：状态机重载 Session、首个适用 Operation、SQLite 会话库、版本化 ExtensionData、Tool executable metadata、Provider stream/tools、扩展环境变量清理和缓存失效。

### 离线验证结果

这里的“离线验证”指不调用真实模型、真实 MCP Server、OAuth、付费 API 或外部业务服务；Rust 依赖首次解析仍需要访问 crates.io 镜像，因此不能把它表述为完全断网构建。

| 场景 | 实际结果 | 证据/限制 |
|---|---|---|
| 固定提交和参考仓库完整性 | 通过 | goose `8ae4e4ba02836529790f47109b8785e8b42843a7`，工作区 clean |
| Rust 工具链隔离 | 通过 | Docker `rust:1.94.1-bookworm`；未安装宿主 Rust，不修改项目环境 |
| Cargo 依赖解析 | 通过 | 容器内 `cargo metadata --format-version 1` 返回 `METADATA_STATUS=0`；ACP 与 cudaforge 使用临时只读 clone 的本地 patch |
| 状态机、Provider、ExtensionData、Tool 生命周期 Rust 单元测试 | 未完成 | 两次 `cargo test -p goose-provider-types` 均停在 crates.io sparse index；出现 HTTP/2 `PROTOCOL_ERROR` 与多次 45 秒无数据超时，未进入编译 |
| 源码结构断言 | 通过 | 8/8 断言通过；只能证明固定源码包含目标结构，不能替代 Rust 运行时测试 |
| 真实模型、MCP、OAuth、外部业务服务 | 未执行 | 按安全边界主动排除 |

本轮因此应标记为 `partial / blocked by dependency mirror`，不能声称 goose 的完整测试套件或 Rust 定向测试通过。

### 未完成/不可声称的内容

- Rust 定向测试未进入编译阶段，因此没有 `cargo test` 的通过结论，也没有运行完整 goose 测试套件。
- 依赖解析虽然成功，但测试容器使用的 crates.io 镜像在后续 sparse index 请求中超时；这属于环境/网络证据缺口，不是 goose 代码失败。
- 未启动 goose UI/CLI。
- 未使用真实 Provider、真实 MCP Server、真实 OAuth 或外部网络服务做运行时验证。
- 静态断言只能证明源码结构存在，不能证明所有运行时分支、跨平台进程行为或并发语义都通过测试。

### 临时环境

```text
C:\Users\32159\AppData\Local\Temp\search-agent-goose-lab-20260830-001
C:\Users\32159\AppData\Local\Temp\search-agent-goose-acp-lab-20260908-001
C:\Users\32159\AppData\Local\Temp\search-agent-goose-cudaforge-lab-20260908-001
C:\Users\32159\AppData\Local\Temp\search-agent-goose-cargo-lab-20260908-001
C:\Users\32159\AppData\Local\Temp\search-agent-goose-target-lab-20260908-001
```

上述目录均位于项目之外；Docker 容器已停止并清理。本轮没有修改项目 `agent-foundations` 环境，也没有安装宿主 Rust 工具链或修改系统环境变量。

## 10. 官方来源

- [goose 官方仓库](https://github.com/aaif-goose/goose)
- [goose 固定提交源码](https://github.com/aaif-goose/goose/tree/8ae4e4ba02836529790f47109b8785e8b42843a7)
- [Provider 配置文档](https://github.com/aaif-goose/goose/blob/main/documentation/docs/getting-started/providers.md?plain=1)
- [Extensions 使用文档](https://github.com/aaif-goose/goose/blob/main/documentation/docs/getting-started/using-extensions.md)
- [Developer MCP 与权限文档](https://github.com/aaif-goose/goose/blob/main/documentation/docs/mcp/developer-mcp.md)
- [CLI 会话管理文档](https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/goose-cli-commands.md)
- [goose-agent README](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose-agent/README.md)
- [Provider trait](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose-provider-types/src/base.rs)
- [State machine](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose-agent/src/machine.rs)
- [Extension 配置](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose/src/agents/extension.rs)
- [ExtensionManager](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose/src/agents/extension_manager.rs)
- [Tool Approval](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose/src/agents/state_machine/ops_tool_approval.rs)
- [Tool Execution](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose/src/agents/state_machine/ops_toolcalling.rs)
- [SessionManager](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose/src/session/session_manager.rs)
- [ExtensionData](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/crates/goose/src/session/extension_data.rs)
