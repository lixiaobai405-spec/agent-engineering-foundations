# mini-SWE-agent 研究笔记

## 研究定位

本笔记记录 mini-SWE-agent 作为极简 Coding Agent 基线的源码阅读和离线探针结果。它用于校准本项目的最低复杂度和线性 Agent Loop，不是生产安全验收，也不是对 mini-SWE-agent 的完整发行版测试报告。

## 研究版本与环境

- 参考仓库：[SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)
- 固定提交：`25941c89cfbc91eb40b3f8756348c91d9977d57e`
- 版本：`mini-swe-agent 2.4.6`
- 实验根目录：`C:\Users\32159\AppData\Local\Temp\search-agent-miniswe-lab-20260830-001`
- 模型：Fake Model；未调用真实模型或付费 API
- 环境：Fake Environment 和临时目录
- 项目状态：没有修改 `D:\codex-pj\search_agent` 的代码

官方 v2 文档把 Model 的 action 解析和 observation 格式化职责独立出来，使 Agent 保持为简单协调器。[v2 migration guide](https://mini-swe-agent.com/latest/advanced/v2_migration/)

## 核心执行结构

mini-SWE-agent 的最小执行链路是：

```text
Model.query
    -> Agent.execute_actions
    -> Environment.execute
    -> Model.format_observation_messages
    -> 下一轮 query
```

### Model Protocol

Model 负责：

- 调用模型。
- 解析文本或 native tool call 中的 action。
- 把环境输出转换成下一轮消息。
- 暴露模板变量和序列化信息。

### Environment Protocol

Environment 负责：

- 接收 action。
- 在指定环境中执行命令。
- 返回输出、返回码和异常信息。
- 在任务完成信号出现时抛出提交控制流。
- 暴露配置和序列化信息。

### DefaultAgent

`DefaultAgent` 负责初始化 system/user 消息、循环调用、限制检查、错误处理和 trajectory 保存。提交、限制、超时、用户中断和格式错误都通过控制流异常携带消息，最终转换为带 `exit_status` 的退出消息。

## 离线探针结果

### 最小任务流程

Fake Model 依次返回检查、修改和提交动作，Fake Environment 记录调用并在提交动作时抛出 `Submitted`：

```text
EXIT_STATUS=Submitted
SUBMISSION=final-patch
ENV_CALLS=inspect,fix,submit
MODEL_CALLS=3
TRAJECTORY_FORMAT=mini-swe-agent-1.1
TRAJECTORY_EXISTS=True
RESULT=PASS
```

这证明最小 Agent 是线性的，没有额外的 Planner、Recovery Controller 或多 Agent 协调层。

### 格式错误重试

Fake Model 第一次抛出 `FormatError`，第二次返回提交动作：

- 第一次格式错误被写入消息历史。
- 错误成本被计入总成本。
- Agent 继续下一轮模型调用。
- 最终返回 `Submitted`。
- 中间轨迹被保存。

### 连续格式错误上限

当连续格式错误达到配置阈值时，Agent 返回 `RepeatedFormatError`。这说明 mini-SWE-agent 将“格式错误重试”作为简单的局部计数器，而不是独立的失败分类器或重规划流程。

### 步数限制

设置 `step_limit=2` 且模型始终不提交：

- 模型实际调用 2 次。
- 第 3 次查询前触发 `LimitsExceeded`。
- 退出消息被加入 trajectory。
- 已完成的消息和模型统计仍被保存。

### LocalEnvironment

在临时目录执行无害本地命令和超时命令：

- 普通命令返回 `returncode=0`。
- 超时返回 `returncode=-1`。
- 已产生的部分 stdout 被保留。
- 异常类型记录为 `TimeoutExpired`。

官方环境文档明确说明 `LocalEnvironment` 直接使用本地子进程，本身不提供隔离。[Environment classes](https://mini-swe-agent.com/latest/advanced/environments/)

### InteractiveAgent

在进程内模拟确认输入：

1. 第一个危险动作被用户拒绝。
2. 环境调用列表中没有该动作。
3. 拒绝原因被记录为用户中断消息。
4. 下一轮重新询问。
5. 用户确认提交动作后，环境只执行允许的 `submit`。

这证明其确认层能阻止当前进程中的执行，但还不能等同于项目所需的持久化 Approval 请求、权限版本和恢复语义。

## 优点

- 组件少，适合学习 Agent Loop。
- Protocol 和 duck typing 让 Fake Model/Fake Environment 很容易注入。
- 线性消息历史便于调试和构造 Coding Eval。
- `finally` 保存 trajectory，限制和错误不会轻易丢失。
- Environment 可以替换为 Docker、Singularity 或其他执行后端。

## 局限与安全边界

- 基础 Agent 没有 durable state machine（持久状态机）。
- trajectory 保存不等同于 Checkpoint、Lease 或副作用账本。
- 基础 action 语义不能单独证明幂等、重放和恢复安全。
- `InteractiveAgent` 的确认依赖终端进程，不能替代持久化 Approval 生命周期。
- `LocalEnvironment` 使用 `subprocess.Popen(..., shell=True)`，官方也明确标注其不隔离。
- 完整发行版还包含模型、CLI、评测和 UI 依赖；本轮为了控制范围采用最小依赖安装，`pip check` 会报告未安装的全量依赖。

## 与本项目的对照

| mini-SWE-agent 设计 | 本项目对应层 | 采用决策 |
|---|---|---|
| Model/Environment Protocol | Provider、Tool、Execution Backend | 借鉴接口解耦思想 |
| 线性 `query -> execute -> observe` | Runtime Agent Loop | 作为最小基线，不替代持久状态机 |
| `FormatError` 重试 | Failure classifier 和 retry budget | 只借鉴显式错误类别，保留项目级预算和恢复 |
| `finally` 保存 trajectory | Trace/Checkpoint | 保留“异常也保存”的思想，但事实源仍是 Checkpoint 与账本 |
| LocalEnvironment | Docker/Execution Backend | 不把本机 shell 当生产 Sandbox |
| 终端 confirm | ApprovalCoordinator | 不把进程内输入当持久化审批 |

本项目已有相关实现入口：

- [loop.py](<D:/codex-pj/search_agent/src/agent_foundations/runtime/loop.py>)
- [state_machine.py](<D:/codex-pj/search_agent/src/agent_foundations/runtime/state_machine.py>)
- [execution/backend.py](<D:/codex-pj/search_agent/src/agent_foundations/execution/backend.py>)
- [chat/approvals.py](<D:/codex-pj/search_agent/src/agent_foundations/chat/approvals.py>)
- [context/compaction.py](<D:/codex-pj/search_agent/src/agent_foundations/context/compaction.py>)

## 研究结论

mini-SWE-agent 最适合作为复杂度下界：先用最少组件解释清楚模型调用、动作执行、反馈、限制和轨迹保存，再逐层增加持久化、审批、权限、恢复和沙箱。

本项目应吸收：

- 小型 Protocol 边界。
- 清晰的线性执行骨架。
- 每轮异常后的轨迹保存。
- 可替换的 Model、Environment 和 Backend。

本项目不应吸收：

- 仅用异常消息代替持久状态机。
- 仅用消息列表代替副作用账本。
- 仅用终端确认代替 Approval。
- 使用本机 shell 作为受控生产执行环境。

## 官方参考

- [mini-SWE-agent GitHub](https://github.com/SWE-agent/mini-swe-agent)
- [v2 migration guide](https://mini-swe-agent.com/latest/advanced/v2_migration/)
- [environment classes](https://mini-swe-agent.com/latest/advanced/environments/)
- [固定研究提交](https://github.com/SWE-agent/mini-swe-agent/tree/25941c89cfbc91eb40b3f8756348c91d9977d57e)
- [固定版本 `default.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/agents/default.py)
- [固定版本 `local.py`](https://github.com/SWE-agent/mini-swe-agent/blob/25941c89cfbc91eb40b3f8756348c91d9977d57e/src/minisweagent/environments/local.py)
