from __future__ import annotations

_TRUSTED_SUFFIX: dict[str, tuple[str, ...]] = {
    "manifest.python.pytest": ("--junit-xml=/workspace/.command-feedback/junit.xml",),
    "manifest.python.ruff-check": ("--output-format=json",),
    "manifest.python.mypy": (
        "--no-color-output",
        "--hide-error-context",
        "--show-column-numbers",
        "--show-error-codes",
    ),
    "manifest.node.test-viewer": ("--", "--reporter=json"),
    "manifest.node.test-chat": ("--", "--reporter=json"),
    "manifest.node.typecheck-viewer": ("--", "--pretty", "false"),
    "manifest.node.typecheck-chat": ("--", "--pretty", "false"),
    "manifest.node.build-chat": (),
    "manifest.python.pip-check": (),
}


def inject_trusted_format(argv: tuple[str, ...], rule_id: str) -> tuple[str, ...]:
    """Append controller-owned reporter/format flags after a successful classify."""
    extra = _TRUSTED_SUFFIX.get(rule_id, ())
    return argv + extra
