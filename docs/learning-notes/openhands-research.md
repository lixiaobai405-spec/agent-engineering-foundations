# OpenHands 研究笔记

## 研究定位

本笔记记录 OpenHands 在事件关联、会话所有权、持久化和中断控制方面的研究结果。它是项目后续架构比较的输入，不是 OpenHands 的生产验收，也不代表要把 OpenHands SDK 复制进本项目。

研究对象包含 OpenHands 的 `software-agent-sdk`，重点放在 Conversation（会话）控制流，而不是 UI 或真实模型效果。

## 研究版本与环境

- 参考仓库：[OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk)
- 固定提交：`9a24f6c8866f353042a57df0514ccc900e3a0691`
- SDK 版本：`openhands-sdk 1.44.0`
- 实验环境：独立临时 venv
- 模型：Fake LLM；未执行真实模型验收
- 项目状态：没有修改 `D:\codex-pj\search_agent` 的生产代码

## 核心设计观察

### Action 与 Observation 是可关联事件

OpenHands 不只把工具调用当作消息文本，而是把 Agent 的动作和环境反馈作为事件处理：

- `ActionEvent` 表示需要执行的动作。
- `ObservationEvent` 表示动作执行后的反馈。
- `tool_call_id` 用于把 Observation 关联到对应 Action。
- 用户拒绝和 Agent 错误也可以作为关闭动作的反馈事件。
- 重复的错误反馈不会自动造成第二次动作执行。

这使“动作是否已经得到反馈”可以从事件关系推导，而不必完全依赖消息数组的相邻顺序。

### 原始事件与模型上下文是两层

实验中直接注入不适合派生视图的合成事件后，重建上下文会发出警告并丢弃不支持的视图事件，但原始事件文件仍然保留。

这说明：

- 原始事件是审计和恢复的材料。
- 给模型的消息视图是可重建、可裁剪的派生数据。
- 派生视图不能反过来成为唯一事实源。

这与本项目“Trace 是观察面，Checkpoint 和副作用账本是恢复事实源”的设计方向一致。

### ConversationLease 保护会话所有权

租约包含 owner instance、generation 和 TTL，并通过受保护写入避免旧进程覆盖新进程状态。接管会递增 generation，旧 owner 继续写入时应收到 ownership lost 错误。

该机制解决的不是普通文件锁，而是：

1. 旧进程可能在租约过期后恢复运行。
2. 新进程接管后，旧进程不能继续提交状态。
3. 读取状态和写入状态之间需要可检测的版本变化。

### 中断是控制流和取消传播

中断逻辑包括：

- 先设置线程安全的 CancellationToken。
- 再通过事件循环线程安全地取消异步任务。
- `CancelledError` 被转换成暂停状态和中断事件。
- 工作线程保留已取消 token，避免继续执行后续动作。
- 下一次运行创建新的 token。
- 被取消的工具不会被静默当作成功完成。

这比单独设置一个 UI 标志更完整，因为它覆盖模型等待、Agent Loop 和工具执行边界。

## 离线验证证据

### Action/Observation 匹配

官方 `get_unmatched_actions` 相关测试函数共 9 个，在 Fake 对象和临时数据上手动执行，9/9 通过。另有合成持久化探针验证：事件写入后重新加载，未匹配动作集合保持一致。

验证过的反馈类型包括：

- 正常 `ObservationEvent`
- `UserRejectObservation`
- `AgentErrorEvent`

其中 `AgentErrorEvent` 可以依据 `tool_call_id` 关闭相应 Action，避免相同失败被重复执行。

### Lease

纯 `ConversationLease` 单元探针 10 项中 9 项通过。唯一未通过场景是 Windows 上使用极大无效 PID 判断进程死亡：系统返回平台特有的 `WinError 87`，实现采取保守策略把未知系统错误视为进程仍然存活，因此没有执行接管。

这项结果应记录为跨平台测试差异，不能直接当作项目逻辑缺陷，也不能据此宣称 Lease 已完成跨平台验收。

### Interrupt

中断相关官方测试使用 Fake `SlowLLM` 和 `CountingLLM` 执行 16 项，16/16 通过。验证内容覆盖：暂停状态、取消 token、任务取消、工具跳过、错误事件和下一轮重新创建 token。

### 安全边界事件

ConversationService 集成探针意外启动了子进程，并尝试使用无凭据的默认模型进行重试。没有成功的真实 API 调用；发现该行为后立即终止了对应的精确子进程，没有继续扩大实验。

该结果形成一个重要实验规则：参考项目集成测试必须显式注入 Fake LLM 和 Fake Runtime，不能依赖默认 Provider 配置。

## 与本项目的对照

| OpenHands 设计 | 本项目对应边界 | 结论 |
|---|---|---|
| Action/Observation 事件匹配 | Runtime 事件和 Tool Call 关联 | 保留稳定 ID 和重复执行保护 |
| 原始事件与派生上下文分离 | Trace、Checkpoint、Context Builder | 不把 Trace 或上下文视图当恢复事实源 |
| Lease owner + generation | Durable run lease | 保留版本化所有权和旧 owner 拒绝写入 |
| CancellationToken | Runtime cancellation + Backend cancel | 继续做协作式取消和执行层取消的双重保护 |
| ConversationService | Durable controller | 仅吸收控制流思想，不直接替换项目控制器 |

本项目已有相关实现入口：

- [state_machine.py](<D:/codex-pj/search_agent/src/agent_foundations/runtime/state_machine.py>)
- [durable/controller.py](<D:/codex-pj/search_agent/src/agent_foundations/durable/controller.py>)
- [durable/repository.py](<D:/codex-pj/search_agent/src/agent_foundations/durable/repository.py>)
- [runtime/recovery.py](<D:/codex-pj/search_agent/src/agent_foundations/runtime/recovery.py>)

## 不直接采用的部分

- 不把 OpenHands 的事件类直接复制到项目领域模型。
- 不把派生 Conversation View 作为唯一恢复输入。
- 不把进程内取消标志当作持久化取消状态。
- 不在没有 Fake Provider、进程清理和敏感配置隔离的情况下运行参考项目集成服务。
- 不因为 OpenHands 具有更丰富的控制面，就扩大当前 Phase 2 的 MCP、Sub-Agent 或远程 Runtime 范围。

## 研究结论

OpenHands 最值得借鉴的是“事件身份 + 派生视图 + 会话所有权 + 中断传播”的组合。它补充了 mini-SWE-agent 线性 Loop 基线中缺少的恢复和并发控制视角。

对本项目的直接结论是：动作反馈必须可关联，恢复必须依赖版本化事实源，取消必须穿过 Agent、模型等待和执行 Backend；但这些能力应继续由本项目自研的状态机、Checkpoint、Lease 和副作用账本承载。

## 官方参考

- [OpenHands](https://github.com/OpenHands/OpenHands)
- [OpenHands software-agent-sdk](https://github.com/OpenHands/software-agent-sdk)
- [固定研究提交](https://github.com/OpenHands/software-agent-sdk/tree/9a24f6c8866f353042a57df0514ccc900e3a0691)
