"""Unified diff patch preview and validation tools."""

from agent_foundations.tools.patch.execution import (
    PatchProposalExecutor,
    build_patch_success_result,
    sanitize_trace_message,
    sanitize_trace_payload_for_tool,
    sanitize_validate_patch_arguments,
)
from agent_foundations.tools.patch.models import (
    BaselineEntry,
    PatchFile,
    PatchHunk,
    PatchLimits,
    PatchLine,
    PatchLineKind,
    PatchOperation,
    ValidatedPatch,
    build_validated_patch,
    compute_patch_id,
    compute_project_root_fingerprint,
)
from agent_foundations.tools.patch.parser import PatchParseError, parse_unified_diff
from agent_foundations.tools.patch.repository import (
    PatchProposalConflictError,
    PatchProposalNotFoundError,
    PatchProposalRepository,
    PatchRepositoryError,
    PatchRootMismatchError,
    PatchRunNotFoundError,
)
from agent_foundations.tools.patch.schema import PATCH_MIGRATIONS, PATCH_PROPOSAL_MIGRATION
from agent_foundations.tools.patch.validate_patch import VALIDATE_PATCH_TOOL_NAME, ValidatePatchTool
from agent_foundations.tools.patch.validator import PatchValidationError, parse_and_validate_patch

__all__ = [
    "BaselineEntry",
    "PATCH_MIGRATIONS",
    "PATCH_PROPOSAL_MIGRATION",
    "PatchFile",
    "PatchHunk",
    "PatchLimits",
    "PatchLine",
    "PatchLineKind",
    "PatchOperation",
    "PatchParseError",
    "PatchProposalConflictError",
    "PatchProposalExecutor",
    "PatchProposalNotFoundError",
    "PatchProposalRepository",
    "PatchRepositoryError",
    "PatchRootMismatchError",
    "PatchRunNotFoundError",
    "PatchValidationError",
    "ValidatedPatch",
    "VALIDATE_PATCH_TOOL_NAME",
    "ValidatePatchTool",
    "build_patch_success_result",
    "build_validated_patch",
    "compute_patch_id",
    "compute_project_root_fingerprint",
    "parse_and_validate_patch",
    "parse_unified_diff",
    "sanitize_trace_payload_for_tool",
    "sanitize_trace_message",
    "sanitize_validate_patch_arguments",
]
