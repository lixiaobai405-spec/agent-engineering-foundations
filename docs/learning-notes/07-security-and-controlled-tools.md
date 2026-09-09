# 07 Security and Controlled Tools 学习笔记

## 本周实现

安全分层是：Policy → Approval → Capability → ExecutionBackend → Sandbox。Permission Profile 是版本化能力清单，不是「打开电脑」。`PROJECT_FULL_ACCESS` 只表示项目范围内已实现能力可按 Policy 自动执行，仍受硬 Policy 与 Sandbox 限制，不表示任意终端、互联网、家目录或主机完全访问。

受控写入只有项目内 `apply_patch`。命令只有清单内的 `run_command`（测试/lint/typecheck/build）。Git 只有 `git_status` / `git_diff` / `git_log`，在隔离环境变量下经 Backend 执行。Registry 不含 MCP、Memory、Skills、Hooks、Sub-Agent、Browser、network Tool、Git write 或 `HOST_FULL_ACCESS`。

## 关键取舍

### 1. 自研核心 vs Adapter

Agent Loop、状态机、Policy、Capability、账本和 Sandbox 边界是自研核心。OpenAI SDK 只作为 Provider Adapter；Docker 只作为 ExecutionBackend 的一种实现。外部协议（MCP/ACP/A2A）本阶段不接入。

### 2. 为什么 Backend 与 Profile 分离

Profile 回答「这个 conversation 被授权做什么」。Backend 回答「这个动作在哪里执行」。把两者绑在一起会让测试无法用 FakeBackend 证明 Policy，也会让未来的 Backend 替换牵动权限模型。`TrustedHostExecutor` 明确留到更晚的独立安全门。

## 各层职责

| 层 | 职责 |
|---|---|
| PolicyEngine | 硬拒绝敏感路径、项目外写、Git write、network |
| Authorization / Capability | 一次性精确授权，重复访问要新 Capability |
| Controlled*Executor | 把 Tool 调用变成带账本的 Sandbox 请求 |
| DockerBackend | 无网络、非 root、资源受限、filtered snapshot |
| FakeBackend | 上层确定性行为，Eval 与集成测试 |

## 刻意未解决

- 不实现主机完全访问
- 不开放任意 Shell、包安装、项目外写、Git 写
- 不把审批做成会话级 allow-all
