from __future__ import annotations

import re
from pathlib import Path

from agent_foundations.viewer.app import CHAT_BUILD_DIR

REQUIRED_MARKERS = (
    "Controlled command approval",
    "sandbox_command",
    "No stdout",
    "No stderr",
    "tablist",
)
STALE_BUNDLE = "index-k5D9Loaj.js"
MODULE_SCRIPT = re.compile(
    r'<script type="module"[^>]*\ssrc="(/chat-static/assets/[^"]+\.js)"',
)


def _index_and_entry_js() -> tuple[str, Path, str]:
    index_path = CHAT_BUILD_DIR / "index.html"
    assert index_path.is_file(), "Chat UI build is missing"
    html = index_path.read_text(encoding="utf-8")
    match = MODULE_SCRIPT.search(html)
    assert match is not None, "index.html has no module script under /chat-static/assets/"
    src = match.group(1)
    js_path = CHAT_BUILD_DIR / "assets" / Path(src).name
    assert js_path.is_file(), f"entry JS missing: {js_path.name}"
    return html, js_path, js_path.read_text(encoding="utf-8")


def test_served_chat_bundle_includes_accepted_command_ui() -> None:
    html, _js_path, js = _index_and_entry_js()
    missing = [marker for marker in REQUIRED_MARKERS if marker not in js]
    assert missing == []
    assert STALE_BUNDLE not in html
    assert STALE_BUNDLE not in js
    assert "Controlled patch approval" in js
    assert "External read approval" in js


def test_served_chat_bundle_includes_stop_control() -> None:
    _html, _js_path, js = _index_and_entry_js()
    assert "chat-composer__stop" in js
    assert "`Stop`" in js or '"Stop"' in js or "'Stop'" in js
