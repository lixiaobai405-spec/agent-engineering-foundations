# OpenAI Codex 专项研究笔记

## 研究范围

本轮研究对象是 [openai/codex](https://github.com/openai/codex)，重点分析 Agent task（任务）执行、Tool 生命周期、Session 持久化、sandbox（沙箱）、权限、审批、代码 review（审查）和服务化边界。

本轮只读固定版本的第三方源码，没有修改本项目生产代码，没有创建 Fork，也没有调用真实模型、真实凭据、付费 API、OAuth、MCP 服务或外部网络 Tool。研究完成仅表示 OpenAI Codex 专项材料已形成；即使六个候选项目的独立笔记均已存在，也不表示 Baseline Selection Gate 已通过、Fork 已获授权或 Phase 3 已完成。

### 固定版本与实验环境

| 项目 | 结果 |
|---|---|
| 上游仓库 | `https://github.com/openai/codex.git` |
| 固定 tag | `rust-v0.153.4` |
| annotated tag object | `042fb41b7c813ac7999105e886b2b7aa715b5081` |
| 固定 commit | `3d2ee51ca2d5db578f328aa75e20aa22c0197c9a` |
| commit 时间 | `2026-09-04T15:41:04-07:00` |
| Rust workspace 版本 | `0.153.4` |
| Rust toolchain | `1.95.0`，edition 2024 |
| 许可证 | Apache-2.0；未来若选择 Fork，仍须保留 LICENSE/NOTICE、版权与上游同步记录 |
| 源码临时目录 | `C:\Users\32159\AppData\Local\Temp\search-agent-openai-codex-lab-20260909-001\codex` |
| 隔离环境 | Docker Engine `29.4.3`；`rust:1.95-bookworm`，image ID `sha256:6258907abe69656e41cd992e0b705cdcfabcbbe3db374f92ed2d47121282d4a1` |
| 挂载方式 | 固定源码挂载到 `/src:ro`；`CARGO_HOME` 与 `CARGO_TARGET_DIR` 位于项目外实验目录 |
| 源码状态 | detached HEAD；研究前后 `git status --short` 均无输出 |

权威源码快照固定在 tag 的 peeled commit，而不是跟随 `main`。官方文档用于核对公开产品合同，源码结论只适用于上述 commit。[1][2]

### 关键命令

```powershell
git clone --branch rust-v0.153.4 --depth 1 --filter=blob:none `
  https://github.com/openai/codex.git `
  C:\Users\32159\AppData\Local\Temp\search-agent-openai-codex-lab-20260909-001\codex

git -C C:\Users\32159\AppData\Local\Temp\search-agent-openai-codex-lab-20260909-001\codex `
  rev-parse 'rust-v0.153.4^{}'
git -C C:\Users\32159\AppData\Local\Temp\search-agent-openai-codex-lab-20260909-001\codex `
  status --short

docker run -d --name codex-study `
  -e CARGO_HOME=/cargo -e CARGO_TARGET_DIR=/target `
  -v C:\Users\32159\AppData\Local\Temp\search-agent-openai-codex-lab-20260909-001\codex:/src:ro `
  -v C:\Users\32159\AppData\Local\Temp\search-agent-openai-codex-lab-20260909-001\cargo-home:/cargo `
  -v C:\Users\32159\AppData\Local\Temp\search-agent-openai-codex-lab-20260909-001\target:/target `
  rust:1.95-bookworm sleep infinity

docker exec -w /src/codex-rs codex-study `
  cargo metadata --locked --no-deps --format-version 1

docker exec -w /src/codex-rs codex-study `
  cargo test -p codex-execpolicy -p codex-sandboxing --locked
```

实验结束后已删除 `codex-study` 容器。宿主机保留固定源码；约 217 MB 的 Cargo 下载缓存仍位于实验目录，因为递归清理命令被本机策略在执行前阻止。它不在项目目录中，也不含真实凭据；可在后续经确认后清理或用于同一固定版本复验。

## 一、开源边界：可研究的是 Runtime 与协议，不是整个 Codex 产品

官方 Open Source 文档把 Codex CLI、SDK 和 app-server 列为开源组件；IDE extension（IDE 扩展）与 Codex cloud（云端执行）不在该开源范围内。[3]

因此本报告能直接验证的是：

- Rust CLI/Core 的本地任务与 Tool 执行路径。
- 本地 rollout、thread-store 和 state DB 的持久化结构。
- app-server 的公开协议与本地服务入口。
- 固定源码中的 review task、审批路由与 OS sandbox 选择。

本报告不能把这些结论外推为 IDE 扩展、Codex cloud、多租户服务或 OpenAI 内部基础设施的完整实现。尤其是云端容器隔离、远程 worker 调度、账号鉴权和平台级审计，只能按官方公开合同描述，不能声称已通过源码验证。

## 二、Task 生命周期：Session 统一拥有后台工作流

固定源码的 `SessionTask` 是一个很小的异步协议，regular chat、review、ghost snapshot 等工作流都通过它运行。它要求 task 提供 `kind()`、trace span 名、`run()` 和可选 `abort()`；具体 task 被一个 `Session` 拥有并在 Tokio 后台任务中执行。[4]

一次 task 的主要生命周期是：

```text
Session::spawn_task
  -> 取消已有 task（TurnAbortReason::Replaced）
  -> 清理 connector selection
  -> 建立 CancellationToken 与 ActiveTurn
  -> drain mailbox，发出 turn start lifecycle
  -> Tokio 后台执行 SessionTask::run
  -> flush rollout
  -> on_task_finished / aborted lifecycle
```

这套设计的优点是 regular turn 与 review 等特殊工作流共享同一套取消、事件、trace 和完成语义，而不是每个入口自己维护状态机。

但固定源码也暴露了一个重要 durability（持久性）取舍：task 返回后会先尝试 `flush_rollout()`；如果 flush 失败，系统发出 warning 并继续 `on_task_finished()`，而不是把整个 turn 强制改为失败。[4] 这提升了交互可用性，却意味着“客户端看到了完成”与“transcript 已持久化成功”不是严格等价。若本项目需要恢复后可证明的一致性，应让完成事件携带 persistence status，或把 durable commit 作为特定高风险状态转换的门槛。

## 三、Tool 生命周期：Registry、Router 与 Orchestrator 分层

Codex 的 Tool 路径不是一个巨大的 `match`：

```text
Tool specs / Registry
  -> model-visible schema
  -> Router 将 ResponseItem 转成 ToolCall
  -> ToolRuntime / ToolHandler
  -> Orchestrator：approval -> sandbox -> attempt -> controlled retry
  -> Tool item/event + rollout
```

`tools/router.rs` 负责把模型响应中的 function、custom、local shell 和 MCP 等调用解析成统一 Tool call，并按 registry 中的 handler 分派。Registry 同时保存暴露给模型的 spec、handler 和是否支持并行等元数据。[5]

更值得借鉴的是 `tools/orchestrator.rs`：审批、sandbox 选择、首次执行和 sandbox-denial retry（沙箱拒绝后的重试）被集中在一个位置，而不是散落在 Shell、Patch 等 Tool 里。它先根据 approval policy、permission profile、workspace roots、网络请求和 Tool 自身策略得到 `Skip`、`NeedsApproval` 或 `Forbidden`，再选择 sandbox 并执行。[6]

固定版本对 retry 有两层约束：

- `Never` 或普通 `OnRequest` 下，不会因为 sandbox denial 自动退回无沙箱执行；网络审批有单独受控分支。
- strict auto-review 对沙箱内尝试的批准，不能自动覆盖无沙箱重试；升级执行需要新的 Guardian review。[6]

这说明“模型允许调用某 Tool”“用户/Reviewer 批准某动作”“OS 允许该进程实际访问资源”是三个独立判断。对本项目最重要的迁移原则是：Tool handler 不应自行拼装权限升级路径；approval decision、sandbox capability 和 retry provenance 必须在统一执行层产生并进入 trace。

## 四、权限与审批：静态 Policy、会话缓存和待决请求不是同一种状态

官方文档把 sandbox mode（技术上能做什么）与 approval policy（何时需要确认）明确分开。常见本地组合是 workspace-write 加 on-request；也可以使用 read-only，或在明确风险下使用 danger-full-access。审批者可以是用户，也可以在 eligible approval 上使用 auto-review。[7][8]

固定源码进一步显示三种不同生命周期：

1. **静态/持久 Policy**：`exec_policy.rs` 会加载 `~/.codex/rules/*.rules`，其中包括 `default.rules`；被接受的命令前缀或网络规则修订可以写回规则文件。[9]
2. **会话内批准缓存**：`ApprovalStore` 缓存 `ApprovedForSession`，由当前 Session services 持有，用于避免同一适用 key 重复询问。[10]
3. **当前 turn 的待决审批**：`TurnState` 使用 `HashMap<String, oneshot::Sender<ReviewDecision>>` 保存 pending approval，并在 turn 清理时清空。[11]

因此不能把 `ApprovedForSession` 或 pending sender 描述成 crash-resumable approval ledger（崩溃可恢复审批账本）。固定证据只支持“持久规则文件 + 进程/Session 内批准缓存 + turn 内等待通道”的分层。

另一个容易混淆的概念是：

- **auto-review / Guardian review**：判断一次动作能否被批准。
- **code review task**：分析 Git diff 并输出代码审查发现。

二者都叫 review，但一个属于 action authorization（动作授权），另一个属于代码质量工作流，不应共用状态或审计含义。

## 五、Sandbox：OS 强制边界与审批交互分离

固定源码的 `SandboxType` 包含：

- macOS：`MacosSeatbelt`。
- Linux：`LinuxSeccomp`；当前 helper 默认组合 bubblewrap 与 seccomp，legacy Landlock 是兼容路径。
- Windows：`WindowsRestrictedToken`，由 Windows sandbox 子系统实现受限 token/AppContainer 等机制。
- `None`：没有 OS sandbox。

Linux 的 proxy-only networking 需要 bubblewrap 提供隔离 network namespace（网络命名空间）；文件、网络和 workspace roots 则由 permission profile 转换成 sandbox policy。[12]

官方安全文档同样强调：本地 Codex 默认关闭网络，sandbox 依赖 OS 机制限制文件和进程；approval 只是要求交互确认的策略，不能替代 sandbox。[7][8]

对本项目的启发是保留四层：

```text
Capability：这个 Runtime 是否拥有某类能力
Policy：这次动作按规则是否允许/需审批/禁止
Approval：谁对哪组精确参数作了什么决定
Sandbox：即使上层出错，OS 最终允许访问什么
```

仅有 allow/ask/deny 枚举不能证明隔离；同样，进程运行在容器或受限 token 中，也不能证明越权动作经过了正确审批。

## 六、Session 持久化：JSONL 事实记录、索引投影与内存 live state

### 6.1 Rollout recorder

`RolloutRecorder` 是后台 JSONL writer。`RolloutCmd` 至少区分 `AddItems`、`Persist`、`Flush` 和 `Shutdown`；`flush()` 等待之前排队的写入由 writer task 提交，并对首次写失败进行 reopen/retry。[13]

rollout 参数记录的范围不只是消息，还包括 conversation/thread ID、fork 来源、parent thread、基础指令、dynamic tools、capability roots、multi-agent version 和 history mode。这让恢复具有较强的 provenance（来源信息），也说明 dynamic tool 配置属于会话历史的一部分。

### 6.2 ThreadStore 与 state DB

`ThreadStore` 把 create、resume、append、flush、shutdown、read/list、archive 和 revert 等能力放在 storage-neutral（存储无关）接口后。Local 实现用 rollout JSONL 保存 canonical history，并用 state DB 提供索引、分页、扫描与修复。[14]

这是一种值得借鉴的分层：

```text
JSONL rollout：可追加、可审查的会话事实/历史
State DB：列表、查询、分页、索引与修复投影
Live Session：当前 task、CancellationToken、pending approval、writer handle
```

固定源码存在 scan-and-repair 与历史 materialization，但本轮没有找到足以证明跨进程 single-writer lease、fencing token 或 Tool 副作用 exactly-once 的证据。这是证据边界，不是断言这些能力在任何闭源服务中都不存在。

此外，task 完成前 flush 失败只产生 warning 的行为说明：如果上层需要 durable state machine，不能仅依赖 `TurnComplete` 作为持久化提交证明。

## 七、代码 Review：独立 task、受限能力、结果进入会话历史

官方文档描述 `/review` 会启动专门 reviewer，支持 uncommitted changes、base branch、指定 commit 或自定义 review instructions；review 自身不修改 working tree，若用户之后选择修复，则进入普通 turn 并重新遵守正常 sandbox/approval。[15]

固定源码的 `tasks/review.rs` 进一步显示：

- review 是 `SessionTask` 的一种实现，启动 one-shot sub-agent。
- review sub-agent 显式禁用 web search、Collab 和 MultiAgentV2，并把 approval policy 限制为 `Never`。
- review 使用专门 rubric，优先解析结构化 `ReviewOutputEvent`；解析失败时保留普通解释文本。
- exit review mode 与 review output 会作为 item/message 发出并写入 conversation history。
- 即使 review 发生在首个 regular turn 前，也会显式 `ensure_rollout_materialized()`。[16]

需要保留一个谨慎边界：固定的 `review.rs` 片段明确证明了禁用能力和 `Never` 审批，但没有在同一处显式把整个 OS permission profile 改成 read-only。本报告因此把“不修改 working tree”视为官方行为合同，并把源码中的 review prompt/能力约束/测试看作支撑，不把它夸大成已单独证明的 OS 级只读不变量。

## 八、服务化边界：app-server 是本地控制面协议，不自动成为安全远程平台

app-server 默认通过 stdio 交换 newline-delimited JSON（JSONL）消息，并要求客户端先完成 `initialize` / `initialized` 握手；WebSocket 和 Unix socket 等传输在当前文档中仍带 experimental（实验性）边界。[17]

公开协议覆盖：

- `thread/start`、`thread/resume`、`thread/fork`、list/read/archive/revert。
- `turn/start`、`turn/steer`、`turn/interrupt`。
- `review/start`，可 inline 或 detached。
- 双向 approval request/response。
- `command/exec`，在不创建 thread 的情况下按 sandbox 配置执行一次命令。
- item、turn、token usage、error 等事件通知。

非交互 `codex exec --json` 也输出 JSONL 事件，如 `thread.started`、`turn.started`、`item.*`、`turn.completed`/`turn.failed`，并支持 resume。[18]

这种边界适合把 UI、IDE 或其他客户端与 Runtime 解耦，但它本身不等于多租户远程安全：

- app-server protocol 暴露的是控制面和事件面；实际 Shell/文件权限仍由运行 app-server 的主机、工作区、approval policy 与 OS sandbox 决定。
- dynamic tools 会进入 rollout metadata，不等于任意客户端声明的 Tool 都应被信任。
- history pagination、某些传输和 experimental field 需要按协议版本和 capability negotiation（能力协商）处理。
- IDE extension 与 Codex cloud 不开源，不能用本地 app-server 源码推断其完整鉴权和隔离模型。

对本项目而言，未来服务化应先稳定 thread/turn/item/approval 协议，再考虑 transport；不要让 HTTP/WebSocket 层成为领域事实源，也不要把“能远程调用”误写成“已具备远程执行安全”。

## 九、离线验证结果

### 9.1 已运行场景

| 场景 | 结果 | 证据与边界 |
|---|---|---|
| 固定源码快照 | pass | tag `rust-v0.153.4` peeled 到 commit `3d2ee51c...`；源码前后 clean |
| 只读隔离 | pass | Docker inspect 显示 `/src` mount `RW:false`；Cargo cache/target 在项目外独立目录 |
| Rust workspace metadata | pass | `cargo metadata --locked --no-deps --format-version 1` exit 0；只证明 manifest/lock 元数据可解析 |
| 架构静态断言 | pass | 15/15：task lifecycle、flush、orchestrator、approval cache/pending、rules、三平台 sandbox、rollout、ThreadStore、review 与 app-server method |
| `codex-execpolicy` + `codex-sandboxing` 定向测试尝试 | unavailable | 两次都在测试收集/编译前因 Cargo 判断 `Cargo.lock` 需要更新而 exit 1；`--locked` 阻止改写只读源码 |
| 真实模型/Provider/API | not-run | 明确禁止；未配置或读取任何真实凭据 |
| app-server/CLI 端到端 | not-run | 构建未完成，且不引入认证或真实模型；只做协议源码与官方文档核对 |
| 全仓 Rust test/nextest | not-run | 非本轮必要范围；上游要求使用 `just test`/nextest，环境未预装对应工具，且不能把未跑写成通过 |

### 9.2 锁文件阻塞与证据解释

尝试的命令为：

```text
cargo test -p codex-execpolicy -p codex-sandboxing --locked
```

关键原始结果：

```text
error: cannot update the lock file /src/codex-rs/Cargo.lock because --locked was passed to prevent this
help: to generate the lock file without accessing the network, remove the --locked flag and use --offline instead.
```

这不是单元测试断言失败，因为没有进入测试执行；也不是通过。固定源码以只读方式挂载，去掉 `--locked` 会允许 Cargo 尝试改写上游 lockfile，因此本轮没有绕过。第一次直接调用 `cargo test` 也不符合该仓库 `AGENTS.md` 推荐的 `just test`/nextest 入口，所以无论锁文件结果如何，都不能当作上游标准测试门禁证据。

后续若要提高动态验证强度，应在新的独立实验中：固定同一 commit，准备上游要求的 `just` 与 `cargo-nextest`，先解释 lockfile drift 的来源，再决定是否使用不改变 canonical checkout 的 overlay。任何生成后的 lockfile 都必须单独标注，不能冒充 tag 原始内容。

### 9.3 静态断言覆盖与局限

15/15 静态断言确认的是架构锚点仍存在，例如 `SessionTask`、replace cancellation、flush-before-finish、approval→sandbox→retry、`ApprovalStore`、pending oneshot、`default.rules`、三个 OS sandbox backend、JSONL rollout、ThreadStore、review restrictions 和 app-server 方法。

它不能证明：

- Tool 的真实 OS 隔离在三个平台均正确生效。
- 崩溃时每个 JSONL/DB 边界都满足期望的 durability。
- Guardian 或 code reviewer 的模型质量。
- 网络 proxy、MCP、OAuth、登录和云端工作流。
- 整个 workspace tests、lint、clippy 或 end-to-end test 通过。

因此本轮验证结论是 `partial`，不能写成“OpenAI Codex 全部测试通过”。

## 十、与本项目的对照与可借鉴点

| Codex 设计 | 可借鉴原则 | 当前不应照搬/扩权 |
|---|---|---|
| `SessionTask` 统一 regular/review 工作流 | 让 task lifecycle、取消、事件和 trace 入口统一 | 不在 Phase 2 提前引入 sub-agent 或 review agent |
| Registry + Router + Orchestrator | Tool schema、分派、审批/sandbox/retry 分层 | 不复制第三方核心实现；不开放任意 Tool |
| approval policy 与 sandbox 分开 | Policy 决定是否问，OS sandbox 决定实际可达资源 | 不把用户一次批准解释成 host full access |
| rules + session cache + pending channel | 明确静态规则、临时批准、待决请求的不同生命周期 | 本项目已有 durable approval 时，不退化为内存事实源 |
| JSONL rollout + state DB | 事件事实与查询投影分层，可扫描修复 | 没有 lease/fencing 证据时，不声称跨进程安全恢复 |
| review task 进入同一 transcript | 审查结果可追踪，并与后续修复 turn 分开授权 | code review 不等于 approval reviewer |
| app-server thread/turn/item 协议 | Runtime 与 UI/transport 解耦 | 本地协议不能直接当生产远程多租户边界 |

一个尤其重要的学习点是 completion 与 durability 的关系。Codex 固定源码选择“flush 失败告警但仍可完成 turn”，适合交互产品的可用性；本项目若把 run state 用于恢复、审批或副作用重放，则应对关键状态采用更严格的 durable transition，并在协议中显式区分 `completed`、`completed_with_persistence_warning` 或等价状态。

## 十一、Baseline Selection Gate 前的定位

本轮完成后，计划列出的 OpenHands、mini-SWE-agent、goose、Qwen Code、OpenCode 与 OpenAI Codex 六份独立专项研究材料均已形成。但下一步仍应是一次单独授权的 baseline comparison（基线比较）与 Selection Gate，而不是自动创建 Fork。

就本轮观察，OpenAI Codex 的强项信号是：

- approval、sandbox、Tool retry 的集中编排清晰。
- thread/turn/item 与 app-server 边界适合程序化客户端。
- JSONL rollout、ThreadStore 和 state DB 分层对可观察性与恢复研究很有价值。
- code review 被建模为独立但可持久化的 workflow。

需要在 Gate 中扣分或单列风险的信号是：

- 开源边界不覆盖 IDE extension 与 cloud，不能把整个产品作为可 Fork baseline。
- 固定 tag 的目标 Rust 测试在只读 `--locked` 环境下未能进入执行，动态证据弱于静态证据。
- 交互完成与 rollout flush 成功不是强一致绑定。
- 当前证据不能证明跨进程 lease/fencing、pending approval crash recovery 或 Tool exactly-once。

这些只是候选评分输入，不是 baseline 选择结论。不得据此绕过 Selection Gate，也不得提前 Fork。

## 十二、结论

OpenAI Codex 的核心工程价值，不只是“能在终端写代码”，而是把 task、Tool、approval、sandbox、rollout、review 与 app-server 协议拆成相互约束的层。它特别适合作为本项目研究统一 Tool 编排、OS 强制隔离、会话事件记录和服务化控制面的参考。

同时，固定源码明确提醒我们：临时批准不等于 durable approval，turn complete 不必然等于 transcript durable，app-server 不等于安全远程平台，开源 CLI/Core 也不等于整个 Codex 产品。后续 Baseline Selection Gate 应把这些边界与其他五个候选放在同一评分矩阵中比较；在用户明确授权前，本轮不进入 Fork 或 Phase 3 实施。

## 参考资料

1. [OpenAI Codex GitHub repository](https://github.com/openai/codex)
2. [Fixed tag `rust-v0.153.4`](https://github.com/openai/codex/tree/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a)
3. [OpenAI Codex: Open source](https://learn.chatgpt.com/docs/open-source)
4. [`SessionTask` and task completion lifecycle](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/core/src/tasks/mod.rs#L171-L219)
5. [Tool router](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/core/src/tools/router.rs)
6. [Tool approval/sandbox orchestrator](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/core/src/tools/orchestrator.rs)
7. [Agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)
8. [Codex sandboxing](https://learn.chatgpt.com/docs/sandboxing)
9. [Persistent exec policy rules](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/core/src/exec_policy.rs)
10. [Session approval cache](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/core/src/tools/sandboxing.rs)
11. [Turn pending approvals](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/core/src/state/turn.rs)
12. [Sandbox manager](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/sandboxing/src/manager.rs)
13. [Rollout recorder](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/rollout/src/recorder.rs)
14. [Thread store](https://github.com/openai/codex/tree/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/thread-store)
15. [Codex code review](https://learn.chatgpt.com/docs/code-review)
16. [Review task implementation](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/core/src/tasks/review.rs)
17. [Codex app-server](https://learn.chatgpt.com/docs/app-server)
18. [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
