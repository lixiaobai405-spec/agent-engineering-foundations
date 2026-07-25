# AGENTS.md

本文件适用于仓库根目录及全部子目录。若未来某个子目录存在更具体的 `AGENTS.md`，则该文件只覆盖其所在子树。

## 1. 项目目标

本项目以系统学习 Agent Engineering（智能体工程）为第一目标。

当前目标是从零实现一个可测试、可观察、安全受控的 Python Agent Runtime（智能体运行时），并以只读代码分析 Agent 作为第一阶段产品验证。

学习优先于交付速度：

- 必须亲自实现核心抽象，不能复制第三方 Agent Runtime 的核心代码。
- 必须解释关键架构决策、边界和取舍。
- 必须保留可重复测试和可审查的实现过程。
- 不为了“尽快跑起来”跳过协议、测试、安全边界或学习笔记。

## 2. 当前权威文档

执行前按以下顺序阅读：

1. `docs/agent-plans/2026-07-20-agent-engineering-learning-design.md`
2. `docs/agent-plans/2026-07-21-phase-1-implementation-plan.md`
3. 当前被用户指定执行的里程碑计划

第一阶段计划：

- Phase 1A：`docs/agent-plans/2026-07-21-phase-1a-foundations-plan.md`
- Phase 1B：`docs/agent-plans/2026-07-21-phase-1b-readonly-agent-plan.md`
- Phase 1C：`docs/agent-plans/2026-07-21-phase-1c-trace-viewer-plan.md`

优先级：

1. 用户当前明确指令
2. 本文件
3. 已确认的设计文档
4. 当前里程碑计划
5. 代码注释和一般性建议

如果计划中的命令或代码与本文件冲突，以本文件为准，并向用户报告冲突。

## 3. 当前阶段边界

除非用户明确切换阶段，否则只执行 Phase 1A。

Phase 1A 允许实现：

- Python 项目骨架
- `Message`、`ToolCall`、`ModelRequest`、`ModelResponse`
- `ModelProvider` 协议与 `FakeModelProvider`
- `Tool`、`ToolResult`、JSON Schema、`ToolRegistry`
- `ContextBudget`、`ContextBuilder`
- 单元测试、契约测试、Ruff、mypy
- `docs/learning-notes/01-foundations.md`

Phase 1A 禁止提前实现：

- 真实 OpenAI-compatible Provider
- 文件系统工具
- Agent Loop、CLI、Trace、FastAPI、SSE、Web Viewer
- 写文件、Shell、Git 工具
- Planning、Memory、Skills、Hooks、MCP、Sandbox、Sub-Agent

只有 Phase 1A 完成条件全部满足并经用户确认后，才进入 Phase 1B。

## 4. 执行模型的角色

项目支持以下显式角色：

- `planner`：只维护目标、范围、步骤和验收标准，不实现代码。
- `executor`：严格执行当前计划，不自行扩展范围。
- `reviewer`：对照计划和验收标准审查，不直接修改代码。
- `tutor`：解释项目中的概念、取舍和错误，不接管实施。
- `context-guardian`：维护跨对话上下文，不替代其他角色。

用户应在每次新对话中明确指定一个角色。一段对话只承担一个角色；未指定时保持中立，不擅自假定为执行者。

交给 Claude、DeepSeek 或其他模型执行 Phase 1A 时，建议使用：

```text
你是 executor。先完整阅读项目根目录 AGENTS.md、已确认设计文档和 Phase 1A 计划。
严格按 Phase 1A 的 Task 顺序执行，一次只处理一个 Task，不扩大范围。
每个 Task 都要先展示失败测试证据，再实现最小代码，然后运行指定验证。
未经我明确授权，不要 commit、push、创建 PR，也不要进入 Phase 1B。
```

## 5. 标准执行流程

每次只执行一个 Task：

1. 阅读该 Task 的目标、文件清单、测试和完成条件。
2. 检查 `git status --short`，识别已有未提交改动。
3. 说明本批修改范围、预期影响和回退方式。
4. 写计划指定的失败测试。
5. 运行最小测试并保存真实失败证据。
6. 编写让该测试通过的最小实现。
7. 运行该 Task 的目标测试。
8. 运行受影响范围的 Ruff 和 mypy。
9. 检查 `git diff`，确认没有无关改动、敏感信息或生成物。
10. 向用户报告结果并等待下一 Task，除非用户已明确授权连续执行。

不得：

- 跳过失败测试直接写实现。
- 同时实现多个尚未验证的 Task。
- 用删除测试、弱化断言、增加 `# type: ignore` 或关闭规则来制造通过。
- 因某个具体错误而做无关重构。
- 把计划示例的预期报错文字当作唯一正确输出；应验证失败原因与目标一致。

## 6. 计划状态维护

- 只有步骤真实完成且有验证证据后，才能把 `- [ ]` 改为 `- [x]`。
- 测试失败、未运行或被跳过时，不得勾选完成。
- 更新计划勾选状态属于当前 Task 的一部分，但不要改写目标、范围或验收标准。
- 如果现实代码与计划冲突，先报告差异，不自行重写计划。
- 如果依赖 API 已变化，先查阅对应官方文档，再提出最小计划修订建议。

## 7. Python 与 Anaconda

- 使用 Python 3.12。
- 使用已确认的 Anaconda 环境名：`agent-foundations`。
- 不使用全局 Python，不把依赖安装到系统环境。
- 执行 Python 命令优先使用：

```powershell
conda run -n agent-foundations python -m pytest
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
```

- 创建环境或联网安装依赖前，先说明会创建或修改什么，并取得用户确认。
- 自动测试不得调用真实模型、真实付费 API 或外部项目。

## 8. TDD 与质量门禁

TDD（测试驱动开发）顺序不可改变：

```text
Red：写一个因缺少目标行为而失败的测试
Green：实现使该测试通过的最小代码
Refactor：只在测试持续通过时进行必要整理
```

每个 Task 的最低验证：

- 指定的 pytest 测试通过。
- 受影响文件通过 Ruff。
- 受影响模块通过 mypy strict。
- `git diff --check` 无空白错误。

Phase 1A 完成前必须运行：

```powershell
conda run -n agent-foundations python -m pytest tests/unit tests/contract -q
conda run -n agent-foundations python -m ruff check src tests
conda run -n agent-foundations python -m mypy src tests
git diff --check
```

没有最新命令输出，不得声称“完成”“修复”或“全部通过”。

## 9. 安全与敏感信息

- 不读取或打印真实 `.env`、API Key、Token、Cookie、密码或私钥。
- 配置示例只能使用明显的占位符。
- 不把敏感信息写入代码、测试、文档、Trace 或 Git 历史。
- 不执行真实付费 API Smoke Test，除非用户在当前任务中明确确认。
- 不删除文件、不覆盖重要配置、不修改系统环境变量。
- 发现疑似密钥泄露时立即停止，说明文件和风险，不继续提交或传播。

## 10. Git 规则

- 默认分支为 `main`。
- 修改前和完成后都检查 `git status` 与 `git diff`。
- 保留用户已有未提交改动，不覆盖、不回滚、不重置。
- 不使用 `git reset --hard`、强制 push 或跳过 Hooks。
- 当前计划中的 `git commit` 步骤是建议检查点，不构成自动授权。
- 只有用户明确要求时才执行 `git commit`。
- `push`、创建 PR、合并或发布前必须再次获得用户确认。
- Commit message 使用英文。

## 11. 第三方参考仓库

第三方参考仓库只读：

- 可阅读源码、文档和测试。
- 可运行其原始测试。
- 不在参考仓库中实现本项目功能。
- 不复制第三方核心实现并伪装为原创代码。
- 引用设计时记录来源、许可证和本项目的独立取舍。

## 12. 每个 Task 的交付格式

执行者完成一个 Task 后，用中文报告：

```text
Task：
状态：完成 / 部分完成 / 阻塞

修改文件：
- path：修改目的

TDD 证据：
- 失败命令：
- 失败原因：
- 通过命令：
- 通过结果：

质量检查：
- pytest：
- Ruff：
- mypy：
- git diff --check：

关键学习点：
- 这个抽象解决什么问题
- 为什么放在这一层
- 当前实现刻意没有解决什么

Git 状态：
- 已修改但未提交的文件
- 是否存在用户原有改动

下一步：
- 下一 Task 或需要用户决定的问题
```

不得只回复“已完成”或只提供代码摘要。

## 13. 阻塞处理

出现以下情况时停止扩大修改并报告：

- 计划引用的类型或文件在前序 Task 中不存在。
- 依赖版本导致计划 API 不可用。
- 测试失败原因与当前 Task 无关。
- 工作区存在会与本 Task 重叠的用户改动。
- 需要新增依赖、修改架构或扩大权限。
- 需要真实凭据、付费 API、删除、覆盖或系统级变更。

报告必须包含：

1. 实际观察到的命令、错误或文件证据。
2. 对当前 Task 的影响。
3. 最小可行选项及其取舍。
4. 推荐选项，但不替用户做高风险决定。
