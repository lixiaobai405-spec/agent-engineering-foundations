# 01 Foundations 学习笔记

## 本周实现

### Message 统一保存角色、内容和工具调用关系

`Message` 使用 `Role`（`StrEnum`：SYSTEM/USER/ASSISTANT/TOOL），`content` 保存文本内容，`tool_call_id` 关联到工具调用。Pydantic `frozen=True` 阻止顶层属性赋值。

### ModelProvider 隔离 Runtime 与具体 SDK

`ModelProvider` 是 `@runtime_checkable` Protocol，只声明 `async def complete(self, request: ModelRequest) -> ModelResponse`。Agent Loop 只依赖此接口。

### Tool 通过 JSON Schema 公开参数契约

`Tool` Protocol 要求 `input_schema()` 返回标准 JSON Schema。`ToolDefinition` 打包 name、description 和 parameters。

### ToolRegistry 集中执行工具发现与参数校验

`validate_call()` 先查工具存在 → 复用同一 JSON Schema 校验参数 → 返回 Tool。`execute()` 先校验再异步执行。

### ContextBuilder 进行确定性的字符预算

算法：截断 TOOL → SYSTEM 全保留 → 非 SYSTEM 从最新向前选 → 恢复时间顺序。硬预算超限（强制保留项放不下）抛 `ContextBudgetExceededError`。

### FakeModelProvider 提供可重复测试

`deque` FIFO 脚本，`complete()` 追加到 `requests`，耗尽抛 `FakeModelExhaustedError`。

### 领域模型的不可变层次

**第一层：Pydantic 顶层 frozen** — `ConfigDict(frozen=True)` 阻止属性赋值。

**第二层：FrozenJSON 递归深层冻结** — pydantic `frozen` 不阻止嵌套 dict/list 原地修改。本项目实现 `FrozenJSON`（继承 `collections.abc.Mapping`），递归将 dict → FrozenJSON、list → tuple。只接受 JSON 兼容值（str/int/有限 float/bool/None/dict/list）；tuple/set/bytes/bytearray 以及 `NaN`、`Infinity`、`-Infinity` 在构造时被 ValidationError 拒绝，避免非标准数值在序列化时静默变成 `null`。

启用字段：`ToolCall.arguments`、`ToolDefinition.parameters`、`ToolResult.metadata`、`ModelResponse.raw_response`。

**公共 API 影响** — 四个字段的静态类型从 `dict[str, Any]` 调整为 `Mapping[str, Any]`。`isinstance(x, dict)` 返回 False。`Mapping` 协议方法（`__getitem__`、`__iter__`、`__len__`、`__contains__`、`__eq__`）完全支持。`model_dump(mode="json")` 输出普通 dict。

**model_copy 安全路径** — Pydantic 默认的 `model_copy(update=...)` 会跳过校验。本项目的相关领域模型共享一个验证式复制基类：有 update 时先从当前模型导出普通字段 payload，再合并 update，最后通过具体模型类的 `model_validate()` 重新构造，因此四个 JSON 字段会再次执行递归冻结和 JSON 验证；`deep=True` 也不能绕过这条路径。无 update 的 `model_copy()` / `model_copy(deep=True)` 保持正常复制语义，`FrozenJSON.__deepcopy__` 支持深拷贝。

**model_construct 排除** — `model_construct()` 绕过全部 Pydantic 校验，不运行 `PlainValidator`，可产生未冻结字段。它明确不属于本项目受支持的安全构造路径，不可用于可信运行路径（如 Agent Loop）。若未来加入写工具，应在注册边界显式校验。

### Protocol 的运行时检查与静态检查

| 机制 | 工具 | 验证范围 |
|---|---|---|
| `isinstance(obj, Protocol)` | pytest（运行时） | 只验证成员名是否存在，不检查方法签名、参数类型或返回类型 |
| `_var: Protocol = ConcreteImpl()` | mypy（静态） | 检查完整方法签名，包括 async、参数类型、返回类型 |

本项目同时使用两者：契约测试用 `isinstance` 做运行时快速检查，静态赋值让 mypy 做完整签名验证。

## 关键取舍

### 1. 为什么领域模型不直接使用 OpenAI SDK 类型

独立定义后，每个 Provider Adapter 职责缩小为单向转换。openai-agents-python 的 `FunctionTool` 直接 import `openai.types.responses`——如果切换 Anthropic 或本地模型，需要修改工具层。

### 2. 为什么 Registry 在执行前统一校验参数

smolagents 的 `validate_tool_arguments()` 是独立函数，可在执行前调用。openai-agents-python 有 `ToolInputGuardrail`/`ToolOutputGuardrail` 作为前后钩子。本项目选择在 Registry 层集中校验，具体 Tool 不重复承担。

### 3. 为什么第一版使用字符预算

不同模型 tokenizer 不同。字符预算零依赖、确定性可重复。Token 预算留到后期。

### 4. 为什么 FakeModel 是测试基础设施

FakeModel 不做推理/重试/降级。测试基础设施 ≠ 线上降级。

### 5. 为什么 Protocol 适合当前设计

smolagents 使用 ABC 继承（`class Tool(BaseTool)`），openai-agents-python 使用 dataclass。Protocol 不需要实现者显式继承，`isinstance` 运行时可用。但 `isinstance` 只验证成员存在性 —— 签名正确性由 mypy 静态赋值保证。

### 6. FrozenJSON 替代 MappingProxyType 的原因

`MappingProxyType` 是 dict 的只读视图但不支持 `copy.deepcopy`（抛 TypeError），值类型无约束（可包裹 tuple/set），Pydantic 默认序列化不识别。FrozenJSON 继承 `Mapping` 协议，实现 `__deepcopy__`，拒绝非 JSON 值，支持 equality/iteration/contains，`PlainSerializer` 输出纯 dict。

## 各层职责

### domain

稳定数据结构（`Message`、`ModelRequest`、`ModelResponse`、`ToolCall`、`ToolDefinition`、`ToolResult`、`TokenUsage`）、Protocol（`ModelProvider`、`Tool`）、错误层级（`AgentFoundationsError` 及其子类）、FrozenJSON 深层不可变。不依赖具体实现。

### providers

Provider Adapter。`base.py` 重导出 `ModelProvider`，`fake.py` 提供 FakeModelProvider。未来加真实 Provider。

### tools

`ToolRegistry` 管理注册、Schema 导出、参数校验和执行调度。

### context

`ContextBudget`（frozen dataclass）+ `ContextBuilder`（确定性字符预算）。

### tests/unit

验证每个模块具体行为。不访问网络/文件系统/真实模型。

### tests/contract

运行时 `isinstance`（成员存在性）+ mypy 静态赋值（完整签名）。不测试业务逻辑。

## 当前刻意没有实现

- 真实 OpenAI-compatible Provider（Phase 1B）
- 文件系统工具（Phase 1B）
- Agent Loop、Session、CLI（Phase 1B）
- Trace、Viewer、SSE（Phase 1C）
- Token Budget（需 tokenizer 依赖）
- 消息摘要、自动压缩
- Memory、Skills、MCP、Hooks
- Sub-Agent、Planning、Checkpoint、审批

## 与参考项目对照

以下对照只读取固定提交中的源码与文档，没有修改参考仓库，也没有复制第三方 Runtime 核心实现。smolagents 和 OpenAI Agents SDK 只作为设计比较材料；本项目独立实现并采用自己的深层不可变 JSON 边界。

### smolagents

**仓库**: `huggingface/smolagents`
**提交**: `e3a5b8994b301983b91c0325546e9dc82eab8cf0`
**许可证**: Apache-2.0
**查阅文件**: `src/smolagents/tools.py`

**相同点**: smolagents 的 `Tool` 通过 `name`/`description`/`inputs` 属性声明工具元数据，`validate_tool_arguments()` 独立于执行做参数校验。这与本项目 `Tool` Protocol + `ToolRegistry.validate_call()` 的分层思路一致。

**差异点**: smolagents 使用 ABC 继承（`class Tool(BaseTool)`），要求子类实现 `forward()` 方法。本项目使用 `@runtime_checkable` Protocol，实现者无需显式继承。smolagents 的 `inputs` 是 `dict[str, dict[str, str | type | bool]]`（自定义格式），本项目使用标准 JSON Schema。`validate_after_init` 是验证函数；`Tool.__init_subclass__` 会把它应用到工具子类，包装子类初始化流程，并在实例初始化后调用 `validate_arguments()` 检查工具子类定义是否满足框架要求。本项目则在 Pydantic 验证层统一处理领域数据。

**本项目取舍**: 保持 Protocol 而非 ABC —— 减少继承耦合，更灵活。保持 JSON Schema 而非自定义 input 格式 —— 模型原生理解 JSON Schema，无需转换。

**留到后续**: smolagents 的 `output_schema`（输出结构描述）、`ToolCollection`（从 HuggingFace Hub 或 MCP 加载工具集合）。

### openai-agents-python

**仓库**: `openai/openai-agents-python`
**提交**: `d9d623098e879baf904e869416486f7cc2b93ac8e`
**许可证**: MIT
**查阅文件**: `src/agents/tool.py`、`src/agents/tool_guardrails.py`、`src/agents/tool_context.py`

**相同点**: openai-agents-python 的 `FunctionTool` 通过 `name`/`description`/`params_json_schema` 声明工具接口，使用 JSON Schema 描述参数。这与本项目 `ToolDefinition` 的设计一致。

**差异点**: openai-agents-python 的 `FunctionTool` 是 `@dataclass`，其 `on_invoke_tool` 字段是返回 `Awaitable` 的异步 Callable；`@function_tool` helper 可接收同步或异步函数，并统一包装为这个异步调用接口。工具实例可被多个 Agent 共享。`FunctionTool` 位于 `src/agents/tool.py`；工具前后护栏类型位于 `src/agents/tool_guardrails.py`；工具调用上下文 `ToolContext` 位于 `src/agents/tool_context.py`。本项目 `Tool` 是 Protocol，`execute()` 是固定 async 方法，上下文通过 Agent Loop 管理。openai-agents-python 深度绑定 OpenAI SDK 类型和 Pydantic 校验；本项目没有 Guardrail 概念，校验在 Registry 和 JSON Schema 层完成。

**本项目取舍**: 保持 Protocol + 显式 async 方法 —— 不依赖 Callable 类型体操。不绑定具体 SDK 类型 —— Provider 在更上层隔离。Guardrail 概念有意留到安全工具阶段。

**留到后续**: `ToolInputGuardrail`/`ToolOutputGuardrail`（工具前后安全钩子）、`ToolContext`（共享执行上下文）、`FunctionToolResult`（结构化输出结果）、Agent-as-Tool（Sub-Agent 调用）。

### 不适合当前 Phase 1A 的成熟抽象

- smolagents 的 HuggingFace Hub 工具加载（需要网络和第三方依赖）
- openai-agents-python 的 Agent-as-Tool（Sub-Agent，属于 Phase 5）
- 两者的 Guardrail/Safety 框架（Phase 1A 尚无具体工具；对于 Phase 1B 计划中的三个只读工具仍属过度设计）
- smolagents 的远程 `ToolCollection` 加载（需要网络、MCP 或第三方服务）
