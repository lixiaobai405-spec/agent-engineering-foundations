# OpenCode 专项研究笔记

## 研究范围

本轮研究对象是 [anomalyco/opencode](https://github.com/anomalyco/opencode)，重点分析 Provider（模型提供方）、Plugin（插件）、Tool 生命周期、Session 持久化、权限与审批，以及 CLI、TUI、SDK、HTTP/SSE 之间的服务化边界。

本轮只读固定版本的第三方源码，没有修改本项目生产代码，没有创建 Fork，也没有调用真实模型、真实 Provider、付费 API、OAuth、MCP 服务或任何真实凭据。研究完成仅表示 OpenCode 专项材料已形成，不表示六个项目全部完成、Baseline Selection Gate 已通过或 Phase 3 已完成。

### 固定版本与实验环境

| 项目 | 结果 |
|---|---|
| 上游仓库 | `https://github.com/anomalyco/opencode.git` |
| 固定 tag | `v1.18.29` |
| 固定 commit | `16747470f976aca3d362ad730bcd3fe82ecc2c9a` |
| commit 时间 | `2026-09-04T23:47:00Z` |
| 包版本 | `packages/opencode/package.json` 为 `1.18.29` |
| 包管理器 | `bun@1.3.14` |
| 许可证 | MIT；未来若进入 Fork 选择，仍需保留许可证与版权声明并记录上游同步策略 |
| 源码临时目录 | `C:\Users\32159\AppData\Local\Temp\search-agent-opencode-lab-20260909-001\opencode` |
| 隔离环境 | Docker Engine `29.4.3`，`node:22-bookworm-slim` 容器，容器内单独安装 `bun@1.3.14`、依赖和 `git` |
| 源码状态 | detached HEAD；`git status --short` 无输出 |

权威源码快照固定在 tag 对应 commit，而不是跟随 `dev` 或文档站的最新内容。官方文档用于核对外部接口，源码结论以该 commit 为准。[1][2]

### 关键命令

```powershell
git clone --branch v1.18.29 --depth 1 https://github.com/anomalyco/opencode.git `
  C:\Users\32159\AppData\Local\Temp\search-agent-opencode-lab-20260909-001\opencode

git -C C:\Users\32159\AppData\Local\Temp\search-agent-opencode-lab-20260909-001\opencode `
  show -s --format='%H%n%D%n%cI%n%s'
git -C C:\Users\32159\AppData\Local\Temp\search-agent-opencode-lab-20260909-001\opencode `
  status --short

docker run -d --name oclab node:22-bookworm-slim sleep infinity
docker exec oclab npm install -g bun@1.3.14
docker exec -w /work oclab bun install --frozen-lockfile --ignore-scripts
```

固定源码在宿主机临时目录中保持 clean；依赖安装和测试发生在可丢弃的容器副本中，没有向本项目或系统 Python/Node 环境安装依赖。第一次使用一次性容器安装依赖后容器随 `--rm` 被销毁，不能作为可复现实验环境；随后重新建立持久实验容器并从头完成安装和测试，本报告只把后者作为有效环境证据。

## 一、总体架构：一个 Core，多种客户端入口

OpenCode 的外部形态不是“CLI 直接包住一个模型调用”，而是客户端—服务端结构：TUI 会启动本地 HTTP Server 并作为客户端连接；`opencode serve` 可以单独暴露同一服务；TypeScript SDK 既能启动本地实例，也能只连接已有 `baseUrl`。官方 Server 文档把 OpenAPI 3.1、SSE 事件、Session、Permission、Provider、Tool、File、MCP 和 PTY 等接口暴露为程序化边界。[3][4]

```text
TUI / CLI run / Web / SDK
          |
          v
    HTTP + SSE Server
          |
          v
 Project / Instance scoped runtime
    |        |         |
 Provider  Session   Tool + Permission
    |
 Plugin hooks / custom tools
```

这带来两个重要结论：

- UI 不是 Session、权限或 Tool 状态的事实源；多个入口应通过同一 Runtime 和服务接口观察状态。
- “可远程访问”不等于“远程安全执行”。HTTP Server 只是控制面边界，Shell、文件 Tool 和进程内 Plugin 的实际权限仍由运行该 Server 的主机、工作区和策略决定。

固定源码中还同时存在 `packages/opencode` 的现行实现与 `packages/core` 的 V2 子系统。Provider、Plugin、Permission、Session 都能看到迁移中的两套抽象，因此不能把某个 V2 类型误写成所有入口已经统一采用的稳定协议。

## 二、Provider：目录、配置、凭据和 SDK 装配分层

官方 Provider 文档说明 OpenCode 基于 AI SDK 和 `models.dev` 模型目录支持多种 Provider；认证信息由 `/connect` 写入用户数据目录下的 `auth.json`，Provider 配置则位于 OpenCode 配置文件中。[5]

固定源码中的 `packages/opencode/src/provider/provider.ts` 展示了更具体的装配过程：

1. `BUNDLED_PROVIDERS` 把已内置的 Provider npm 包映射到 SDK factory。
2. `models.dev` 目录、用户 `provider` 配置、环境凭据、认证存储和 Plugin 提供的模型/认证信息被合并。
3. `enabled_providers`、`disabled_providers` 和模型 allow/deny 配置决定可见范围。
4. 内置包走 bundled loader；非内置 SDK 包可通过 `Npm.add(model.api.npm)` 动态取得并加载。
5. Provider SDK 与 Language Model 实例按 Provider、npm 包和 options 等输入缓存。
6. Provider options、timeout、代理 fetch 和认证逻辑在真正构造 Language Model 前集中装配。

这是一种“目录与运行时分离”的设计：目录回答有哪些模型及元数据，配置和认证决定哪些模型在当前实例可用，SDK loader 才负责把模型标识变成可调用对象。

### 安全与可测试性观察

- `auth.json` 是真实凭据存储边界，不能因为配置文件中没有 key 就认为运行环境无凭据。
- 动态 npm Provider 扩大了供应链与代码执行面；“支持自定义 Provider”不是纯数据配置。
- 本轮只执行离线单元测试并禁用了自动更新、模型目录抓取和分享，没有调用任何 Provider。
- 对本项目可借鉴的是 Provider resolver 的来源归因、allow/deny 和可替换 loader；当前 Phase 2 不应因此增加网络 Tool、包安装或真实模型能力。

## 三、Plugin：强扩展点，不是安全沙箱

官方 Plugin 文档列出全局/项目级 Plugin、npm Plugin、加载顺序和大量 Hook。Plugin 入口会收到 `project`、`directory`、`worktree`、SDK client 以及 Bun shell；Hook 覆盖命令、文件、安装、LSP、消息、权限、Session、Todo、Tool 和 TUI。[6]

### 3.1 V1 生命周期

`packages/opencode/src/plugin/index.ts` 的固定源码显示：

- 内部 Plugin 先装配，外部 Plugin 按确定顺序串行加载，以稳定 Hook 顺序。
- Plugin 初始化结果进入 hooks 集合，随后运行 `config` Hook 并订阅总线事件。
- Runtime finalizer 会取消事件订阅，并调用可选的 `hook.dispose()`。
- 外部 Plugin 加载失败会发布/记录错误；pure mode 可以不加载外部 Plugin。
- Plugin 输入直接包含 SDK client、Server URL、项目/工作区路径和 `Bun.$`。

### 3.2 V2 生命周期

`packages/core/src/plugin.ts` 进一步提供按 Plugin ID 的 add、replace、remove、wait 和关闭语义：

- `KeyedMutex` 串行化同一 ID 的生命周期变更。
- 每个 Plugin 拥有独立 Scope，替换前关闭旧 Scope。
- 激活过程检测循环依赖，等待者可以观察成功或 defect。
- Core scope 结束时关闭所有 Plugin scope。

V2 的资源所有权更清晰，但它与 V1 并存，说明 OpenCode 正处于边界演进中。本轮不推断所有 CLI/Server 路径已经完全切换到 V2。

### 3.3 Plugin 与权限的真实边界

Plugin 可以注册 Tool，并通过 `tool.execute.before`/`tool.execute.after` 观察或修改 Tool 参数和输出。固定源码的普通 Tool、Plugin Tool 和 MCP Tool 包装路径中，`tool.execute.before` 在 Tool 内部的 `ctx.ask(...)` 之前运行。

因此：

- 审批保护的是统一 Tool 调用路径上的受控动作，不会自动沙箱化任意 Plugin 初始化代码。
- Plugin 已经是被信任的进程内代码；它拿到 `Bun.$` 后可绕开普通 Tool 的审批路径直接发起 Shell 动作。
- Before Hook 会看到尚未获批的请求并能改变参数，所以最终审批必须针对 Hook 处理后的参数，而审计应同时保留原始参数与最终参数。

这是本项目后续设计 Plugin/Hook 时最需要保留的安全结论：扩展发现、扩展信任、Tool permission 和 OS sandbox 是四个不同层次。

## 四、Tool 生命周期：发现、Hook、审批、执行与持久化状态

固定源码可以把一次普通 Tool 调用概括为：

```text
ToolRegistry 汇总工具
  -> schema/参数解码
  -> ToolPart: pending
  -> ToolPart: running
  -> plugin tool.execute.before
  -> Tool 内部 ctx.ask(...)（若该 Tool 声明资源权限）
  -> execute
  -> 输出标准化、截断与附件整理
  -> plugin tool.execute.after
  -> ToolPart: completed / error
```

`ToolRegistry` 汇总内置 Tool、配置目录中的自定义 Tool、Plugin Tool 和 MCP Tool，并根据模型选择 `edit` 或 `apply_patch` 等变体。Plugin 的 `tool.definition` 还可改变 Tool 描述或 schema；全局 deny 可以让 Tool 不进入暴露给模型的集合。

Session Tool wrapper 将 AI SDK tool call 与 `sessionID`、`messageID`、稳定的 `callID`、AbortSignal、metadata 更新和 `ask()` 回调关联。Processor 将 ToolPart 从 `pending` 推进到 `running`，再写成 `completed` 或 `error`；中断、解析错误和 Provider 侧 Tool 结果也进入显式状态。连续三次相同调用会触发 doom-loop 权限询问。

两个不能忽略的限制：

- 内置 Tool 由各自实现决定何时、以什么资源模式调用 `ctx.ask()`，统一 wrapper 并不是先于所有 Hook 的单一审批闸门。
- Plugin Tool 属于已信任扩展；注册成 Tool 的执行路径可以纳入状态机，但 Plugin 自身仍拥有进程内能力。

## 五、权限与审批：规则持久，待决交互主要在内存

官方 Permission 文档定义 `allow`、`ask`、`deny`，支持通配 pattern，并采用“最后匹配的规则获胜”。文档默认值中，大多数 Tool 为 allow，`doom_loop` 和 `external_directory` 为 ask，`.env` 读取有专门限制；`edit`、`bash`、`task`、`webfetch` 等可分别配置。[7]

固定源码的 V1 `Permission` Service 进一步显示：

- `evaluate()` 对合并后的规则按顺序评估，最后匹配项决定结果；无匹配时为 ask。
- `ask()` 会先检查 deny，再跳过 allow，只有 ask 项才发布 Permission requested event 并等待 Deferred。
- `reply=once` 只解决本次请求；`reply=always` 把允许规则放进当前 Instance 的 `approved` 数组，并自动解决同一 Session 中匹配的其他 pending 请求。
- reject 会取消同一 Session 的待决请求；Instance dispose/reload 会拒绝仍在等待的请求。

关键持久化边界是：V1 的 `pending Map` 和 `approved` 数组由 InstanceState 持有；它们不是 SQLite 中的 Durable Approval 记录。Session 表可以保存配置的 permission ruleset，但运行中“正在等待哪次批准”和 `always` 形成的当前实例批准，会随 Instance 销毁而结束。

V2 `packages/core/src/permission.ts` 也使用内存 pending map，但同时把 saved resources 与项目/Agent 规则结合。它改善了领域表达，不等于已经拥有跨进程的待决审批恢复协议。

对本项目的启发不是照搬 `allow/ask/deny` 字符串，而是明确区分：

```text
静态 Policy / Session rules
    != 当前进程中的 pending request
    != once/always 的交互决定
    != 可恢复的 Durable Approval 账本
```

本项目已有 Durable Run 与 Approval 分层时，应继续把 request ID、精确资源、决定者、决定时间、适用范围和恢复行为持久化，避免把 UI 内存状态当作可恢复事实。

## 六、Session 持久化：SQLite 事实与进程内协调并存

### 6.1 SQLite 数据层

固定源码把数据库放在用户数据目录的 `opencode.db`，启用 WAL、`synchronous=NORMAL`、`busy_timeout=5000` 和 foreign keys。Session 相关表包括：

- `SessionTable`：Session 元数据、工作区、状态和 permission ruleset。
- V1 `MessageTable` / `PartTable`：消息与 ToolPart 等投影。
- V2 `SessionMessageTable`：带 Session 内唯一 sequence 的事件式消息记录。
- `SessionInputTable`：admitted/promoted sequence、queue/steer 交付状态。
- Todo、Context Epoch 等辅助状态。

ToolPart 的 `pending`、`running`、`completed`、`error` 等状态可以进入消息/Part 持久化；V2 还使用有序 sequence 支持 history 分页和输入晋升。迁移测试明确覆盖旧 Drizzle journal、V1 状态、V2 event stream 重建和 Windows/POSIX 路径归一化。

### 6.2 执行协调不是分布式 Lease

`SessionRunCoordinator` 会在一个进程内按 Session key 合并并发 resume、合并 wake、处理 interrupt，并让不同 Session 并行。`packages/core/src/session/execution/local.ts` 的注释明确称它是 current-process routing，未来 remote placement 应放在这一层。

所以固定版本已经具备较强的数据库持久化和单进程协调，但当前证据不能证明：

- 多 Server 进程对同一 Session 存在数据库级 writer lease 或 fencing token。
- pending Tool/Approval 能在进程崩溃后恢复到可安全继续的状态。
- Tool 副作用拥有跨进程 exactly-once 保证。
- remote worker placement 已经实现。

这与本项目的 Durable Run 研究直接相关：SQLite 记录“发生了什么”与 Lease 证明“谁现在有权继续执行”是不同能力。

## 七、服务化边界：HTTP 控制面不等于执行隔离

官方文档给出的默认 Server 参数是 `127.0.0.1:4096`，mDNS 默认关闭，CORS 需要显式配置。设置 `OPENCODE_SERVER_PASSWORD` 后启用 Basic Auth，用户名默认 `opencode`；未设置 password 时，源码不会生成 Authorization header，也不构成默认远程认证。[3]

服务化形态包括：

- TUI 自己启动 Server 并通过客户端访问。
- `opencode serve` 启动独立无界面 Server。
- `opencode run --attach` 连接已有 Server。
- SDK 的 `createOpencode()` 启动本地 Server 和 client，`createOpencodeClient()` 只连接已有 URL。[4][8]

Server API 覆盖的不只是聊天消息，还包括 Permission reply、Tool IDs、Provider/Auth、文件搜索、MCP 和 PTY。这意味着把 hostname 改成非 loopback、开放 CORS 或部署反向代理，会同时扩大控制面和执行面暴露范围。Basic Auth 只能解决最基础的请求认证，不能替代 TLS、租户隔离、工作区授权、Plugin 信任、进程沙箱、审计与网络策略。

固定源码中的 workspace/instance scope 和 HTTP API 分组为多工作区控制面提供了基础，但 `local.ts` 仍明确把执行定位在当前进程。本轮因此把 OpenCode 归类为“已服务化的本地/自托管 Agent Runtime”，而不是已经证明安全的分布式多租户执行平台。

## 八、离线验证结果

### 8.1 环境准备与修正

最初 Provider/Plugin/Tool/Permission 组合测试得到 `182 pass / 21 fail`。21 个失败全部落在需要创建临时 Git 仓库的 Permission 测试，错误为容器找不到 `git`（`ENOENT`），不是权限断言失败。给持久实验容器安装 `git 2.39.5` 后，单独重跑该文件得到 `79 pass / 0 fail`。

这次修正改变的是隔离实验环境，不是上游源码；因此报告同时保留初始失败和修正后的结果，不用后者抹去前者。

### 8.2 已运行场景

所有命令都设置了：

```text
OPENCODE_DISABLE_AUTOUPDATE=1
OPENCODE_DISABLE_MODELS_FETCH=1
OPENCODE_DISABLE_SHARE=1
```

| 场景 | 结果 | 证据与边界 |
|---|---|---|
| 固定源码快照 | pass | tag `v1.18.29`，commit `16747470...`，宿主机源码 clean |
| 依赖安装 | pass | 容器副本执行 `bun install --frozen-lockfile --ignore-scripts`，4709 packages；没有在项目内安装 |
| 静态源码断言 | pass | 12/12：Provider registry/dynamic package、Plugin shell/dispose、Before Hook、Permission pending/approved、SQLite WAL/path、Session sequence、local routing、Server password |
| Provider/Plugin/Tool/Permission 目标组 | partial -> pass | 初次 203 项为 182 pass/21 环境失败；补齐容器 `git` 后 Permission 79/79，其他 124 项在初次运行已通过 |
| Server auth/event/authorization/session processor/schema 组 | pass | 38 项通过；未调用真实网络服务或模型 |
| Server listen/PTY 组 | partial -> pass | 默认 5 秒超时下 11 项中 4 项 timeout；改用该包配置对应的 30 秒 timeout 后 11/11 通过，耗时约 46 秒 |
| V2 Permission/Plugin/Session coordinator/history/database migration 组 | partial | 55 项中 54 项通过，1 项 migration schema freshness 检查失败 |

### 8.3 未通过项

唯一仍未通过的目标用例是：

```text
DatabaseMigration > declared schema has no ungenerated migrations
```

命令返回 `Current database schema is stale. Run bun script/migration.ts from packages/core.`。同一组的空库迁移、旧 journal 导入、V1/V2 Session 状态重建、并发初始化和路径归一化测试均通过。本轮没有运行会重写生成文件的命令，因为第三方源码只读；也没有把该失败直接定性为上游产品缺陷。它可能涉及固定 tag 中的生成物、平台输出或发布时 schema 同步，需要在上游原生开发环境/CI 证据中进一步复核。

### 8.4 未执行与验证边界

- 没有运行完整 monorepo 测试、lint、typecheck 或 build；本轮只能称目标范围验证，不能称完整测试通过。
- 没有运行真实 `opencode serve` 对外监听、浏览器/TUI、OAuth、MCP、PTY 交互或跨进程恢复实验。
- 没有测试 Windows 原生 Bun Runtime；执行测试的是 Linux 容器。
- 没有故障注入验证 Tool 副作用、pending approval 或 Session resume 的 crash consistency。
- 没有调用真实 Provider、真实模型或真实凭据。
- 没有审计全部依赖、Plugin 包或 Provider npm 包的供应链安全。

## 九、与本项目的映射

### 可借鉴

- 把 Core Runtime 与 TUI/CLI/SDK/HTTP 入口分开，让 Session 与 Permission 成为统一事实。
- Provider 分为目录、配置/凭据解析、SDK loader 和模型实例缓存，并保留来源与 allow/deny。
- ToolPart 使用显式 pending/running/completed/error 状态，并把 call ID、取消和 metadata 更新贯穿生命周期。
- Plugin 生命周期拥有顺序、Scope、dispose 和替换语义；Hook 顺序必须成为可测试协议。
- Session 使用数据库 sequence 和 migration，而进程内 coordinator 只负责本地并发。
- 服务默认 loopback，远程暴露必须单独设计认证、授权、工作区隔离和执行 Sandbox。

### 需要更保守地设计

- Plugin 拿到 SDK 与原生 Shell 后属于高信任代码，不能让 Plugin 信任继承普通 Tool 的 Approval 结论。
- Before Hook 与 Approval 的参数绑定必须清楚，避免“批准 A，执行被 Hook 改写后的 B”。
- `always` approval 若只存在 Instance 内存中，不足以支持 Durable Run 的重启恢复和审计。
- SQLite history 与单进程 coordinator 不能替代 writer lease、fencing 和幂等副作用协议。
- 开放 HTTP Server 会暴露 Permission、PTY、文件与 Provider 管理面，不能只靠 CORS 或可选 Basic Auth。

### 当前明确不引入

- 不复制 OpenCode 的 Provider、Plugin、Tool、Permission 或 Session 核心实现。
- 不提前实现 MCP、ACP、Plugin、Sub-Agent、网络 Tool 或远程 Server。
- 不扩大 Phase 2 的 Capability、Permission Profile、Sandbox 或命令权限。
- 不把 OpenCode 的配置类型、SQLite schema 或 HTTP API 当作本项目既定协议。
- 不创建 OpenCode Fork，也不改变原定的 Qwen Code Fork 候选方向。

## 十、研究结论

OpenCode 最有价值的研究点，是它把 Provider、Plugin、Tool、Permission、SQLite Session 与 HTTP/SSE 服务放在同一个产品化 Runtime 中；最值得警惕的点，也正是这些边界相互穿透：Plugin 是进程内强权限代码，Before Hook 早于 Tool 内审批，Server 能暴露 PTY/文件/Permission 控制面，而 pending approval 和执行协调仍有明显的进程内状态。

与 Qwen Code 相比，OpenCode 的 HTTP/SDK 服务接口和 SQLite/V2 event 序列更直接；但从本轮固定版本证据看，不能据此推导出跨进程 writer lease、可恢复审批、远程 worker placement 或多租户安全边界已经成立。

OpenCode 专项研究到此完成。下一步仍应先完成 OpenAI Codex 专项研究，再把六个项目放入统一任务集、Fake Backend、安全检查表、许可证与维护成本矩阵中执行 Baseline Selection Gate。此结论不授权 Fork，不表示 Phase 3 实施已开始，也不改变 Phase 2 Step 10/11 尚未完成的事实。

## 官方资料与固定源码入口

1. [OpenCode 官方仓库](https://github.com/anomalyco/opencode)
2. [固定 tag `v1.18.29`](https://github.com/anomalyco/opencode/tree/16747470f976aca3d362ad730bcd3fe82ecc2c9a)
3. [Server 文档](https://opencode.ai/docs/server/)
4. [SDK 文档](https://opencode.ai/docs/sdk/)
5. [Providers 文档](https://opencode.ai/docs/providers/)
6. [Plugins 文档](https://opencode.ai/docs/plugins/)
7. [Permissions 文档](https://opencode.ai/docs/permissions/)
8. [CLI 文档](https://opencode.ai/docs/cli/)
9. [Provider source](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/opencode/src/provider/provider.ts)
10. [Plugin V1 source](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/opencode/src/plugin/index.ts)
11. [Tool wrapper source](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/opencode/src/session/tools.ts)
12. [Permission V1 source](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/opencode/src/permission/index.ts)
13. [Database source](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/core/src/database/database.ts)
14. [Session SQL source](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/core/src/session/sql.ts)
15. [Local execution routing source](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/core/src/session/execution/local.ts)

