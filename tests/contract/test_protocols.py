import importlib.util
from typing import Any

from agent_foundations.domain.model import ModelProvider, ModelResponse
from agent_foundations.domain.tool import Tool, ToolResult
from agent_foundations.providers.fake import FakeModelProvider


class ContractTool:
    name = "contract"
    description = "Contract test tool"

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, content="ok")


# ---- runtime checks ----

def test_fake_model_satisfies_provider_protocol() -> None:
    """isinstance 验证运行时成员存在性（name/methods），不验证签名细节。"""
    assert isinstance(FakeModelProvider([ModelResponse(content="ok")]), ModelProvider)


def test_tool_implementation_satisfies_tool_protocol() -> None:
    """isinstance 验证运行时成员存在性，不验证 async/返回类型。"""
    assert isinstance(ContractTool(), Tool)


# ---- static protocol assignments (verified by mypy) ----

_provider: ModelProvider = FakeModelProvider([ModelResponse(content="ok")])

_tool: Tool = ContractTool()


def test_registered_tool_contract_exists() -> None:
    try:
        spec = importlib.util.find_spec("agent_foundations.security.models")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "agent_foundations.security.models is not implemented"
    from agent_foundations.domain.tool import RegisteredTool
    from agent_foundations.security.models import SideEffectKind, ToolManifest
    from agent_foundations.security.resources import resolve_contract_resource

    registered = RegisteredTool(
        ContractTool(),
        ToolManifest(
            name="contract",
            resource_kind="project_path",
            operations=("read",),
            side_effect=SideEffectKind.NONE,
            sandbox_required=False,
        ),
        resolve_contract_resource,
    )
    assert registered.tool.name == registered.manifest.name
