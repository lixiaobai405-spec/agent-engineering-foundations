from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from agent_foundations.domain.tool import Tool, ToolResult
from agent_foundations.runtime.tool_execution import ToolCallExecutor, ToolExecutionContext
from agent_foundations.tools.patch.models import BaselineEntry, ValidatedPatch
from agent_foundations.tools.patch.repository import PatchProposalRepository, PatchRepositoryError
from agent_foundations.tools.patch.validate_patch import VALIDATE_PATCH_TOOL_NAME, ValidatePatchTool
from agent_foundations.tools.patch.validator import PatchValidationError, parse_and_validate_patch


def build_patch_success_result(patch: ValidatedPatch) -> ToolResult:
    files_summary = tuple(
        {
            "path": file.path,
            "operation": file.operation.value,
            "hunk_count": file.hunk_count,
            "baseline_sha256": file.baseline_sha256,
            "add_line_count": file.add_line_count,
            "remove_line_count": file.remove_line_count,
        }
        for file in patch.files
    )
    total_hunks = sum(file.hunk_count for file in patch.files)
    return ToolResult(
        success=True,
        content="patch proposal validated",
        metadata={
            "patch_id": patch.patch_id,
            "file_count": len(patch.files),
            "total_hunk_count": total_hunks,
            "files": list(files_summary),
            "project_root_fingerprint": patch.project_root_fingerprint,
        },
    )


def sanitize_validate_patch_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    diff = str(arguments.get("diff", ""))
    baselines = arguments.get("baselines", [])
    return {
        "redacted": True,
        "diff_bytes": len(diff.encode("utf-8")),
        "baseline_count": len(baselines) if isinstance(baselines, list) else 0,
    }


def sanitize_validate_patch_tool_call(call_payload: dict[str, Any]) -> dict[str, Any]:
    arguments = call_payload.get("arguments", {})
    if not isinstance(arguments, dict):
        return call_payload
    sanitized = dict(call_payload)
    sanitized["arguments"] = sanitize_validate_patch_arguments(arguments)
    return sanitized


def sanitize_trace_message(message: dict[str, Any]) -> dict[str, Any]:
    if message.get("role") != "assistant":
        return message
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return message
    sanitized = dict(message)
    sanitized["tool_calls"] = [
        sanitize_validate_patch_tool_call(call)
        if isinstance(call, dict) and call.get("name") == VALIDATE_PATCH_TOOL_NAME
        else call
        for call in tool_calls
    ]
    return sanitized


def sanitize_trace_payload_for_tool(
    tool_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if tool_name != VALIDATE_PATCH_TOOL_NAME:
        return payload
    if "arguments" in payload:
        arguments = payload.get("arguments")
        if isinstance(arguments, dict):
            sanitized = dict(payload)
            sanitized["arguments"] = sanitize_validate_patch_arguments(arguments)
            return sanitized
    if "tool_calls" in payload:
        tool_calls = payload.get("tool_calls")
        if isinstance(tool_calls, list):
            sanitized = dict(payload)
            sanitized["tool_calls"] = [
                sanitize_validate_patch_tool_call(call)
                if isinstance(call, dict) and call.get("name") == VALIDATE_PATCH_TOOL_NAME
                else call
                for call in tool_calls
            ]
            return sanitized
    return payload


class PatchProposalExecutor:
    def __init__(
        self,
        downstream: ToolCallExecutor,
        repository: PatchProposalRepository,
    ) -> None:
        self._downstream = downstream
        self._repository = repository

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        if isinstance(tool, ValidatePatchTool):
            if context.tool_name != tool.name:
                return ToolResult(
                    success=False,
                    content="tool name mismatch",
                    error_code="PATCH_CONTEXT_REQUIRED",
                )
            try:
                baselines = tuple(
                    BaselineEntry.model_validate(item)
                    for item in arguments.get("baselines", [])
                )
                patch = parse_and_validate_patch(
                    str(arguments["diff"]),
                    baselines,
                    context.root,
                )
                saved = await self._repository.save(context.session_id, patch)
                return build_patch_success_result(saved)
            except PatchValidationError as exc:
                message = str(exc)[:240]
                return ToolResult(
                    success=False,
                    content=message,
                    error_code=exc.code,
                )
            except ValidationError:
                return ToolResult(
                    success=False,
                    content="invalid baseline entry",
                    error_code="PATCH_BASELINE_MISMATCH",
                )
            except PatchRepositoryError as exc:
                return ToolResult(
                    success=False,
                    content=str(exc)[:240],
                    error_code=type(exc).__name__,
                )
        return await self._downstream.execute(tool, arguments, context)
