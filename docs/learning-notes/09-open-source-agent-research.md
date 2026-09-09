# 09 开源 Coding Agent 研究总结

## 研究定位

本轮研究服务于项目后续的基线比较，不是生产实现任务，也不代表已经进入 Phase 3、选择了 Fork 对象或获得了扩大项目权限的授权。

研究对象为：

- Qwen Code
- OpenCode
- OpenAI Codex
- OpenHands
- goose
- mini-SWE-agent

研究目标不是寻找一个“功能最多”的项目，而是理解不同 Coding Agent 的边界：

1. Agent Loop（智能体循环）如何组织模型调用、工具调用和反馈。
2. Tool、Environment、Execution Backend 如何划分职责。
3. Approval、Policy、Capability 和 Sandbox 如何控制副作用。
4. 状态、事件、Trace、Checkpoint 和恢复之间谁是真实事实源。
5. 扩展协议、Provider、可维护性、许可证和上游同步对后续 Fork 的影响。

本轮遵循第三方参考仓库只读原则。源码只用于学习和验证，没有复制第三方 Runtime 核心实现。

## 研究方法

采用“主题比较 + 固定版本源码阅读 + 独立临时环境离线探针”的方式：

| 层次 | 做法 | 证据强度 |
|---|---|---|
| 架构阅读 | 阅读官方仓库、文档、测试和关键源文件 | 说明设计意图和代码结构 |
| 离线探针 | 使用 Fake Model、Fake Environment 和临时目录 | 证明局部控制流行为 |
| 原始测试 | 在临时环境中调用参考项目测试或等价测试 | 证明固定版本的局部回归 |
| 真实模型验收 | 本轮不执行 | 避免凭据、费用和外部状态影响 |

后续所有第三方实验均采用独立临时环境，不安装到项目的 `agent-foundations` 环境，不在项目目录中运行第三方安装脚本。

## 当前研究状态

下表区分“已阅读”与“已通过离线证据”，不能把未验证项理解为失败。

| 项目 | 当前用途判断 | 本轮证据状态 | 暂定结论 |
|---|---|---|---|
| Qwen Code | 候选 Fork 和产品化 Coding Agent 参考 | 固定提交源码、11/11 静态断言、Core 包安装/tsc、977/981 定向测试通过；4 项 Plan shell routing 测试受 Linux `/tmp` 工作目录夹具影响失败 | 适合参考事件流 Loop、Tool Scheduler、分层权限、Session lease/recovery 和多入口 Runtime；进入统一 Baseline Selection Gate 后再决定是否 Fork |
| OpenCode | CLI、Provider、Tool 和会话架构参考 | 初步比较，未在本轮重新执行完整离线探针 | 重点观察扩展性、权限和运行时边界 |
| OpenAI Codex | Coding Agent 产品与工程流程参考 | 初步比较，未在本轮执行真实模型验证 | 重点观察任务执行、沙箱和审查闭环 |
| OpenHands | Durable Conversation、事件、租约和中断参考 | 已完成 SDK 源码阅读及多组 Fake/单元探针 | 适合研究恢复和控制流，不直接作为本项目 Runtime |
| goose | 扩展系统、Provider、Tool 和协议参考 | 固定提交源码与官方文档研究完成；Docker Rust 1.94.1 依赖解析通过，8/8 源码断言通过；定向 Rust 测试被 crates.io 镜像超时阻断 | 适合参考可重新推导的状态机、扩展状态和 Tool 生命周期；不直接引入其默认权限模型 |
| mini-SWE-agent | 极简 Agent Loop 和 Coding Eval 基线 | 已完成固定提交源码阅读及离线探针 | 适合做复杂度下界和线性 Loop 基线 |

## 分项目研究文档

本总览只负责记录六个项目的比较关系。每个项目完成专项研究后，必须同步形成一份独立文档，并在此处登记：

- [OpenHands 研究笔记](<D:/codex-pj/search_agent/docs/learning-notes/openhands-research.md>)：已完成源码阅读、事件匹配、租约和中断探针。
- [mini-SWE-agent 研究笔记](<D:/codex-pj/search_agent/docs/learning-notes/mini-swe-agent-research.md>)：已完成固定提交源码阅读和离线执行探针。
- [goose 研究笔记](<D:/codex-pj/search_agent/docs/learning-notes/goose-research.md>)：已完成固定提交源码阅读、扩展/Provider/Tool/Session 结构分析；Docker 依赖解析和 8/8 静态断言通过，Rust 定向测试受镜像索引阻断。
- [Qwen Code 研究笔记](<D:/codex-pj/search_agent/docs/learning-notes/qwen-code-research.md>)：已完成固定提交源码阅读、Core Loop/Tool Scheduler/权限/Provider/Session/恢复分析；独立 Node 22 容器完成依赖与 tsc，静态断言 11/11，Core 定向测试 977/981 通过，4 项失败已记录为 Linux `/tmp` 夹具差异。
- OpenCode：待专项研究。
- OpenAI Codex：待专项研究。

未完成专项研究的项目暂不创建结论性文档，避免把研究计划误写成事实结论。`goose` 文档明确区分了依赖解析、源码断言和未进入编译的 Rust 测试，避免把部分证据写成完整测试通过。

因此目前没有“哪个项目胜出”的结论，也没有把任一项目作为主项目 Fork。

## OpenHands：事件、恢复与中断

### 观察到的结构

OpenHands SDK 的重要学习点不是某个具体工具，而是把会话执行拆成事件和派生视图：

- ActionEvent 表示 Agent 请求执行动作。
- ObservationEvent 表示环境对动作的反馈。
- 原始事件记录和给模型使用的派生上下文视图不是同一个东西。
- `tool_call_id` 用于把 Observation 与对应 Action 关联起来。
- `ConversationLease` 使用 owner、generation、TTL 和受保护写入控制单个会话的所有权。
- 中断通过 CancellationToken 和任务取消协作传播，并在恢复运行时建立新的取消上下文。

### 离线验证结果

在临时 OpenHands SDK 环境中完成了以下验证：

1. 官方 `get_unmatched_actions` 相关测试函数共 9 个，使用隔离对象手动执行，全部通过。
2. Action 与 Observation 写入后重新加载，未完成动作集合能够保持一致。
3. 正常 Observation、用户拒绝 Observation 和 AgentErrorEvent 都能按动作 ID 关闭对应 Action。
4. 重复的错误 Observation 不会造成重复执行。
5. `ConversationLease` 的纯单元探针 10 项中 9 项通过。
6. Windows 上“伪造死亡 PID 后接管”的一项测试因 `os.kill` 返回平台特有的 `WinError 87` 而未通过；实现对未知系统错误采取保守的“仍然存活”判断，因此不能直接归类为项目逻辑错误。
7. 中断相关官方测试使用 Fake LLM 执行 16 项，全部通过。

### 对本项目的启发

OpenHands 证明了以下边界值得保留：

- Action 的身份必须稳定，Observation 不能只靠消息顺序匹配。
- “原始事件已记录”与“模型上下文如何重建”应分层处理。
- 会话所有权需要 generation 或等价版本号，否则旧进程可能覆盖新进程状态。
- 取消不仅是 UI 信号，还必须传递到模型等待、工具执行和恢复逻辑。

但 OpenHands 的会话服务集成探针曾触发无凭据默认模型的重试行为，因此立即终止了相关子进程，没有继续真实 API 调用。后续研究必须显式注入 Fake LLM，不能依赖默认 Provider 配置。

## mini-SWE-agent：极简线性基线

### 核心结构

固定提交 `25941c89cfbc91eb40b3f8756348c91d9977d57e` 对应版本 `2.4.6`。其核心结构可以概括为：

```text
Model.query
    -> Agent.execute_actions
    -> Environment.execute
    -> Model.format_observation_messages
    -> 下一轮 query
```

mini-SWE-agent v2 使用 Protocol（协议）和 duck typing（鸭子类型）解耦 `Model`、`Environment` 与 `Agent`。Model 负责解析 action 和格式化 observation，Agent 主要负责循环协调和轨迹保存。

### 离线验证结果

在独立临时 venv 中使用 Fake Model 和 Fake Environment 完成了以下探针：

| 探针 | 实际结果 |
|---|---|
| 最小任务流程 | `inspect -> fix -> submit` 三次模型调用，成功提交 |
| 格式错误重试 | 第一次 `FormatError` 后继续调用模型，最终提交成功 |
| 连续格式错误 | 达到配置阈值后退出为 `RepeatedFormatError` |
| 步数限制 | 两次模型调用后退出为 `LimitsExceeded` |
| 轨迹保存 | 每次循环的 `finally` 都保存当前 trajectory，限制和错误状态也可保留 |
| 本地命令 | 临时目录内的安全命令执行成功 |
| 命令超时 | 保留部分输出，返回 `TimeoutExpired` 类型信息 |
| 交互确认 | 拒绝命令时环境调用为 0，下一轮确认后才执行允许动作 |

### 优点

- 组件少，容易阅读和替换。
- Model 与 Environment Protocol 适合构造 Fake 实现。
- 线性消息历史适合作为最小 Coding Agent 教学和 Eval 基线。
- 退出状态、提交结果、模型调用次数和成本可以一起保存。
- Environment 可替换为 Docker、Singularity 或其他执行后端。

### 明确的局限

- 基础 Agent 没有项目级 durable state machine（持久状态机）。
- 轨迹保存不是完整的 Checkpoint、Lease 或副作用账本。
- `InteractiveAgent` 的确认依赖当前终端交互，不是持久化 Approval 生命周期。
- `LocalEnvironment` 使用本机子进程和 `shell=True`，本身不提供安全隔离。
- 基础文本 action 不等同于具备完整幂等、重放和恢复语义的 Tool Call。

因此 mini-SWE-agent 适合作为“复杂度下界”：如果一个设计连它的线性 Loop 都解释不清，就不应直接增加多 Agent、协议和复杂扩展；但本项目不能用它替代已有的权限、恢复和 Sandbox 层。

## 跨项目比较得到的架构结论

| 主题 | 参考项目提供的启发 | 本项目的取舍 |
|---|---|---|
| Agent Loop | mini-SWE-agent 的线性协调器足够作为最小基线 | 保留自研 Loop，并在其上增加持久状态和受控重规划 |
| Model/Provider | 用 Adapter 或 Protocol 隔离具体模型 SDK | 保留 `ModelProvider` 边界，不让 SDK 类型进入领域层 |
| Action/Observation | OpenHands 的稳定动作 ID 和匹配规则 | 保留事件关联、未知状态和重复执行保护 |
| Trace/恢复 | OpenHands 区分原始事件和派生上下文 | Trace 是观察面；Checkpoint 和副作用账本才是恢复事实源 |
| 中断 | 取消应传播到等待中的模型和工具 | 保留 durable cancel status、协作式 token、Backend 取消和 checkpoint |
| Approval | 终端确认适合交互 Demo | 使用持久化 ApprovalCoordinator，不把拒绝/批准简化为进程内输入 |
| 执行环境 | LocalEnvironment 便于实验，Docker 等环境便于隔离 | 继续使用 Policy → Approval → Capability → Backend → Sandbox 分层 |
| 轨迹保存 | 每轮 `finally` 保存可以减少异常丢证据 | 保留该思想，但保存格式必须服从项目事件、脱敏和恢复协议 |
| 扩展协议 | 大型项目的扩展能力值得单独研究 | 在当前 Phase 2 不提前引入 MCP、ACP、A2A、Skills 或 Sub-Agent |

## 对项目现有实现的映射

本轮研究没有修改生产代码。当前项目已经具备与上述结论对应的独立层次：

- [state_machine.py](<D:/codex-pj/search_agent/src/agent_foundations/runtime/state_machine.py>)：Agent 阶段、取消和可持久化运行状态。
- [durable/controller.py](<D:/codex-pj/search_agent/src/agent_foundations/durable/controller.py>)：Checkpoint、Lease、恢复和重试控制。
- [approvals.py](<D:/codex-pj/search_agent/src/agent_foundations/chat/approvals.py>)：可等待、可拒绝、可追踪的 Approval 生命周期。
- [tools/command/run_command.py](<D:/codex-pj/search_agent/src/agent_foundations/tools/command/run_command.py>)：受控命令调用和授权边界。
- [tools/patch/apply_patch.py](<D:/codex-pj/search_agent/src/agent_foundations/tools/patch/apply_patch.py>)：受控写入与授权决策。
- [context/compaction.py](<D:/codex-pj/search_agent/src/agent_foundations/context/compaction.py>)：模型输入派生视图，不把原始 Artifact 当作 Memory。

研究后的判断是：这些层应继续由本项目自研；第三方项目的优秀设计只通过主题参考或未来 Adapter 进入，不应替换项目的事实源和安全边界。

## 实验环境与验证边界

### mini-SWE-agent 临时环境

- 临时根目录：`C:\Users\32159\AppData\Local\Temp\search-agent-miniswe-lab-20260830-001`
- 固定提交：`25941c89cfbc91eb40b3f8756348c91d9977d57e`
- 版本：`mini-swe-agent 2.4.6`
- 安装方式：源码 editable 安装到独立 venv；只安装离线探针所需的最小依赖。
- 模型：Fake Model；没有真实模型、真实凭据或付费 API 调用。
- 执行目录：临时目录；没有向项目目录写入文件。

因为本轮使用了最小依赖而不是完整发行版依赖集合，`pip check` 会报告未安装的完整 CLI、模型和评测依赖。因此本轮证据应表述为“局部离线探针通过”，不应表述为“mini-SWE-agent 完整测试套件通过”。

### 项目工作区

本轮新增本文件之前，项目已有大量 modified 和 untracked 文件。新增文件是本轮唯一计划内的项目变更；没有执行 reset、restore、clean、commit、push 或项目依赖安装。

## 暂不作出的结论

- 不根据 README、Star 数或单次 Demo 排名。
- 不把局部测试通过当作生产安全性证明。
- 不把 OpenHands 的事件模型或 mini-SWE-agent 的异常控制流直接复制到项目。
- 不在没有统一任务集、统一 Fake Backend 和许可证核验前选择 Fork 对象。
- 不因为研究完成就自动进入 Phase 3 或执行 Qwen Code Fork。

## 下一步建议

`Qwen Code` 和 `goose` 专项研究已经完成。下一轮可以在同样的独立临时环境规则下研究尚未完成的项目：

1. OpenCode：重点观察其插件、Provider、会话、权限和服务化边界。
2. OpenAI Codex：重点观察任务执行、沙箱、审批和审查闭环。

完成六个项目的主题研究后，再建立统一 Baseline Selection Gate：固定各候选版本、同一组离线任务、同一 Fake Backend、同一安全检查表和许可证记录，最后才决定是否创建 `qwen-code-custom` Fork。

完成六个项目的主题研究后，再建立统一 Baseline Selection Gate：固定各候选版本、同一组离线任务、同一 Fake Backend、同一安全检查表和许可证记录，最后才决定是否创建 `qwen-code-custom` Fork。

## 官方参考

- [Qwen Code](https://github.com/QwenLM/qwen-code)
- [OpenCode](https://github.com/anomalyco/opencode)
- [OpenAI Codex](https://github.com/openai/codex)
- [OpenHands](https://github.com/OpenHands/OpenHands)
- [goose](https://github.com/aaif-goose/goose)
- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent)
- [mini-SWE-agent v2 migration guide](https://mini-swe-agent.com/latest/advanced/v2_migration/)
- [mini-SWE-agent environment classes](https://mini-swe-agent.com/latest/advanced/environments/)
- [mini-SWE-agent fixed source: `default.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/agents/default.py)
- [mini-SWE-agent fixed source: `local.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/environments/local.py)
