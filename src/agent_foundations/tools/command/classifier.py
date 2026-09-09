from __future__ import annotations

import re
from typing import Literal

from agent_foundations.tools.command.models import (
    CommandCategory,
    CommandClassification,
    CommandGate,
    CommandSpec,
    ProjectCommandManifest,
)

_SHELLS = frozenset({"bash", "cmd", "cmd.exe", "powershell", "pwsh", "sh"})
_NETWORK = frozenset({"curl", "ftp", "nc", "ncat", "netcat", "scp", "ssh", "wget"})
_INSTALL_WORDS = frozenset({"add", "ci", "install", "uninstall", "update"})
_META_TOKENS = frozenset({"&&", "||", "|", ">", ">>", "<", "<<", ";"})
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9_.,=+\-\[\]]+$")


class CommandClassifier:
    def __init__(self, *, project_fingerprint: str) -> None:
        self._project_fingerprint = project_fingerprint

    def classify(
        self,
        spec: CommandSpec,
        manifest: ProjectCommandManifest,
    ) -> CommandClassification:
        if manifest.project_fingerprint != self._project_fingerprint:
            return self._deny(
                spec,
                CommandCategory.DENIED,
                "builtin.command.project-fingerprint-mismatch",
            )

        denial = self._known_denial(spec.argv)
        if denial is not None:
            return self._deny(spec, CommandCategory.DENIED, denial)

        for gate in manifest.gates:
            if spec.argv[: len(gate.argv_prefix)] != gate.argv_prefix:
                continue
            if self._matches_gate(spec.argv, gate):
                return CommandClassification(
                    category=gate.category,
                    rule_id=gate.rule_id,
                    normalized_argv=spec.argv,
                    sandbox_profile=gate.sandbox_profile,
                    hard_denied=False,
                )
            return self._deny(
                spec,
                CommandCategory.DENIED,
                "builtin.command.invalid-arguments",
                profile=gate.sandbox_profile,
            )

        return self._deny(
            spec,
            CommandCategory.UNKNOWN,
            "builtin.command.unknown",
            profile="node" if spec.argv[0] == "npm" else "python",
        )

    @staticmethod
    def _known_denial(argv: tuple[str, ...]) -> str | None:
        executable = argv[0].casefold()
        if executable in _SHELLS:
            return "builtin.command.shell-denied"
        if executable == "git":
            return "builtin.command.git-denied"
        if executable in _NETWORK:
            return "builtin.command.network-denied"
        if any(_has_metacharacter(token) for token in argv):
            return "builtin.command.metacharacter-denied"
        if executable == "python":
            if len(argv) > 1 and argv[1] == "-c":
                return "builtin.command.inline-code-denied"
            if len(argv) > 1 and not argv[1].startswith("-"):
                return "builtin.command.script-denied"
            if tuple(part.casefold() for part in argv[:4]) == (
                "python",
                "-m",
                "pip",
                "install",
            ):
                return "builtin.command.install-denied"
        if executable == "npm" and len(argv) > 1 and argv[1].casefold() in _INSTALL_WORDS:
            return "builtin.command.install-denied"
        return None

    @staticmethod
    def _matches_gate(argv: tuple[str, ...], gate: CommandGate) -> bool:
        suffix = argv[len(gate.argv_prefix) :]
        if gate.exact:
            return not suffix
        if not suffix:
            return False

        targets: list[str] = []
        seen_flags: set[str] = set()
        for token in suffix:
            if token.startswith("-"):
                if token not in gate.allowed_flags or token in seen_flags:
                    return False
                seen_flags.add(token)
            else:
                targets.append(token)
        return bool(targets) and all(
            _is_allowed_target(target, gate.allowed_targets) for target in targets
        )

    @staticmethod
    def _deny(
        spec: CommandSpec,
        category: CommandCategory,
        rule_id: str,
        *,
        profile: Literal["python", "node"] = "python",
    ) -> CommandClassification:
        return CommandClassification(
            category=category,
            rule_id=rule_id,
            normalized_argv=spec.argv,
            sandbox_profile=profile,
            hard_denied=True,
        )


def _has_metacharacter(token: str) -> bool:
    return (
        token in _META_TOKENS
        or any(marker in token for marker in ("&&", "||", "$(`", "$(", "`"))
        or any(character in token for character in "|<>;")
    )


def _is_allowed_target(target: str, allowed_roots: tuple[str, ...]) -> bool:
    if _has_metacharacter(target) or "\\" in target:
        return False
    path_part, separator, node_id = target.partition("::")
    if ":" in path_part:
        return False
    if separator and (not node_id or _NODE_ID_RE.fullmatch(node_id) is None):
        return False
    if path_part.startswith("/"):
        return False
    parts = tuple(part for part in path_part.split("/") if part)
    if not parts or any(part in {".", ".."} for part in parts):
        return path_part == "." and "." in allowed_roots and not separator
    return parts[0] in allowed_roots
