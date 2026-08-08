# Milestone 3 Trace and Web Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为只读 Agent 增加脱敏 JSONL 持久化、历史回放、本机实时事件广播和可交互 Web Trace Viewer，使每一步模型与工具行为可学习、可调试。

**Architecture:** Agent Runtime 将事件交给 `CompositeEventSink`；`JsonlEventSink` 是可靠本地记录，`LiveEventSink` 仅把脱敏事件发送到 `127.0.0.1` Viewer。Viewer 使用 `EventBroker` 将事件转为 SSE，并从同一 Trace 目录加载历史 Session；前端只能观察，不提供 Agent 控制接口。

**Tech Stack:** Python 3.12、FastAPI、Uvicorn、HTTPX、SSE、Pydantic 2、原生 HTML/CSS/TypeScript、Playwright、pytest、Anaconda

---

## 前置条件与文件结构

先完成 [Milestone 2](2026-07-21-phase-1b-readonly-agent-plan.md)，并确认 CLI 的 FakeModel 端到端测试通过。

```text
src/agent_foundations/runtime/redaction.py     # 递归脱敏
src/agent_foundations/runtime/sinks.py         # JSONL、组合、实时 Sink
src/agent_foundations/runtime/replay.py        # 历史加载
src/agent_foundations/viewer/stream.py         # EventBroker 与 SSE 编码
src/agent_foundations/viewer/app.py            # FastAPI API 与静态文件
src/agent_foundations/viewer/static/index.html
src/agent_foundations/viewer/static/styles.css
src/agent_foundations/viewer/static/app.ts
src/agent_foundations/viewer/static/dist/app.js
package.json
tsconfig.json
tests/unit/runtime/test_redaction.py
tests/unit/runtime/test_sinks.py
tests/unit/runtime/test_replay.py
tests/unit/viewer/test_stream.py
tests/integration/test_viewer_api.py
tests/e2e/test_trace_viewer.py
docs/learning-notes/03-observability.md
README.md
```

## Task 1: 实现 Trace 深度脱敏

**Files:**
- Create: `src/agent_foundations/runtime/redaction.py`
- Test: `tests/unit/runtime/test_redaction.py`

- [x] **Step 1: 写密钥、Header、绝对路径与嵌套对象测试**

```python
# tests/unit/runtime/test_redaction.py
from pathlib import Path

from agent_foundations.runtime.redaction import Redactor


def test_redacts_sensitive_keys_values_and_project_root(tmp_path: Path) -> None:
    redactor = Redactor(project_root=tmp_path, secrets=("live-secret-value",))
    provider_key = "sk-" + "example1234567890"
    source = {
        "api_key": "live-secret-value",
        "headers": {"Authorization": "Bearer abc.def"},
        "payload": [f"read {tmp_path / 'src' / 'main.py'}", provider_key],
        "safe": "token is a source-code variable",
    }
    result = redactor.redact(source)
    rendered = str(result)
    assert "live-secret-value" not in rendered
    assert "abc.def" not in rendered
    assert str(tmp_path) not in rendered
    assert provider_key not in rendered
    assert result["safe"] == "token is a source-code variable"
```

- [x] **Step 2: 验证 Redactor 尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_redaction.py -v`

Expected: FAIL，错误包含 `No module named ...runtime.redaction`。

- [x] **Step 3: 实现递归且不修改源对象的脱敏器**

```python
# src/agent_foundations/runtime/redaction.py
import re
from pathlib import Path
from typing import Any


class Redactor:
    _sensitive_keys = frozenset({
        "api_key", "apikey", "authorization", "cookie", "password",
        "private_key", "secret", "token",
    })
    _bearer = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+")
    _openai_like_key = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")

    def __init__(self, project_root: Path, secrets: tuple[str, ...] = ()) -> None:
        self._root_variants = {
            str(project_root.resolve()),
            str(project_root.resolve()).replace("\\", "/"),
        }
        self._secrets = tuple(secret for secret in secrets if secret)

    def redact(self, value: Any, *, key: str | None = None) -> Any:
        if key and key.lower() in self._sensitive_keys:
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(item_key): self.redact(item, key=str(item_key)) for item_key, item in value.items()}
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            return self._redact_text(value)
        return value

    def _redact_text(self, text: str) -> str:
        result = text
        for secret in self._secrets:
            result = result.replace(secret, "[REDACTED]")
        for root in sorted(self._root_variants, key=len, reverse=True):
            result = result.replace(root, "<PROJECT_ROOT>")
        result = self._bearer.sub("Bearer [REDACTED]", result)
        return self._openai_like_key.sub("[REDACTED]", result)
```

- [x] **Step 4: 验证脱敏测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_redaction.py -v`

Expected: `1 passed`。

- [ ] **Step 5: 提交脱敏器**

```powershell
git add src/agent_foundations/runtime/redaction.py tests/unit/runtime/test_redaction.py
git commit -m "feat: redact sensitive trace data"
```

## Task 2: 实现 JSONL 与 CompositeEventSink

**Files:**
- Create: `src/agent_foundations/runtime/sinks.py`
- Test: `tests/unit/runtime/test_sinks.py`

- [x] **Step 1: 写逐行持久化、脱敏和组合顺序测试**

```python
# tests/unit/runtime/test_sinks.py
import json
from pathlib import Path

import pytest

from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import CompositeEventSink, JsonlEventSink
from agent_foundations.runtime.trace import InMemoryEventSink, TraceEvent


@pytest.mark.asyncio
async def test_jsonl_sink_writes_one_redacted_event_per_line(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    sink = JsonlEventSink(traces, Redactor(tmp_path, secrets=("secret-value",)))
    event = TraceEvent(
        session_id="session-1", step_id=1, event_type="model.request.started",
        status="started", summary="calling", payload={"api_key": "secret-value"},
    )
    await sink.emit(event)
    lines = (traces / "session-1.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["payload"]["api_key"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_composite_emits_to_every_sink_in_order() -> None:
    first = InMemoryEventSink()
    second = InMemoryEventSink()
    composite = CompositeEventSink((first, second))
    event = TraceEvent(
        session_id="s", step_id=0, event_type="session.started",
        status="started", summary="started",
    )
    await composite.emit(event)
    assert first.events == second.events == [event]
```

- [x] **Step 2: 验证 Sinks 尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_sinks.py -v`

Expected: FAIL，错误包含 `No module named ...runtime.sinks`。

- [x] **Step 3: 实现持久化与组合**

```python
# src/agent_foundations/runtime/sinks.py
import asyncio
import json
from collections.abc import Iterable
from pathlib import Path

from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.trace import EventSink, TraceEvent


class JsonlEventSink:
    def __init__(self, trace_dir: Path, redactor: Redactor) -> None:
        self._trace_dir = trace_dir
        self._redactor = redactor

    async def emit(self, event: TraceEvent) -> None:
        data = self._redactor.redact(event.model_dump(mode="json"))
        line = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
        path = self._trace_dir / f"{event.session_id}.jsonl"
        await asyncio.to_thread(self._append, path, line)

    @staticmethod
    def _append(path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(line)


class CompositeEventSink:
    def __init__(self, sinks: Iterable[EventSink]) -> None:
        self._sinks = tuple(sinks)

    async def emit(self, event: TraceEvent) -> None:
        for sink in self._sinks:
            await sink.emit(event)
```

- [x] **Step 4: 验证 Sink 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_sinks.py -v`

Expected: `2 passed`。

- [ ] **Step 5: 提交 Trace Sinks**

```powershell
git add src/agent_foundations/runtime/sinks.py tests/unit/runtime/test_sinks.py
git commit -m "feat: persist trace events as JSONL"
```

## Task 3: 实现严格历史回放加载器

**Files:**
- Create: `src/agent_foundations/runtime/replay.py`
- Test: `tests/unit/runtime/test_replay.py`

- [x] **Step 1: 写顺序加载与损坏行报告测试**

```python
# tests/unit/runtime/test_replay.py
from pathlib import Path

import pytest

from agent_foundations.runtime.replay import TraceReplayError, load_trace, list_sessions
from agent_foundations.runtime.trace import TraceEvent


def event(session: str, step: int) -> TraceEvent:
    return TraceEvent(
        session_id=session, step_id=step, event_type="test.event",
        status="completed", summary=f"step {step}",
    )


def test_loads_events_in_file_order(tmp_path: Path) -> None:
    path = tmp_path / "session-a.jsonl"
    path.write_text("\n".join([event("session-a", 1).model_dump_json(), event("session-a", 2).model_dump_json()]), encoding="utf-8")
    assert [item.step_id for item in load_trace(path)] == [1, 2]
    assert list_sessions(tmp_path) == ["session-a"]


def test_reports_corrupt_line_number(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text(event("broken", 1).model_dump_json() + "\nnot-json", encoding="utf-8")
    with pytest.raises(TraceReplayError, match="line 2"):
        load_trace(path)
```

- [x] **Step 2: 验证 Replay 模块尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_replay.py -v`

Expected: FAIL，错误包含 `No module named ...runtime.replay`。

- [x] **Step 3: 实现验证式回放**

```python
# src/agent_foundations/runtime/replay.py
import json
from pathlib import Path

from pydantic import ValidationError

from agent_foundations.runtime.trace import TraceEvent


class TraceReplayError(ValueError):
    pass


def load_trace(path: Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(TraceEvent.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise TraceReplayError(f"invalid trace at line {line_number}: {path.name}") from exc
    return events


def list_sessions(trace_dir: Path) -> list[str]:
    if not trace_dir.exists():
        return []
    return sorted(path.stem for path in trace_dir.glob("*.jsonl") if path.is_file())
```

- [x] **Step 4: 验证 Replay 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/unit/runtime/test_replay.py -v`

Expected: `2 passed`。

- [ ] **Step 5: 提交历史回放**

```powershell
git add src/agent_foundations/runtime/replay.py tests/unit/runtime/test_replay.py
git commit -m "feat: load and validate trace history"
```

## Task 4: 实现 EventBroker、SSE 与 LiveEventSink

**Files:**
- Modify: `pyproject.toml`
- Create: `src/agent_foundations/viewer/__init__.py`
- Create: `src/agent_foundations/viewer/stream.py`
- Modify: `src/agent_foundations/runtime/sinks.py`
- Test: `tests/unit/viewer/test_stream.py`

- [x] **Step 1: 写多订阅者顺序与 Viewer 离线降级测试**

```python
# tests/unit/viewer/test_stream.py
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from agent_foundations.runtime.sinks import LiveEventSink
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.trace import TraceEvent
from agent_foundations.viewer.stream import EventBroker, encode_sse


def make_event(step: int) -> TraceEvent:
    return TraceEvent(
        session_id="session-1", step_id=step, event_type="test.event",
        status="completed", summary=str(step),
    )


@pytest.mark.asyncio
async def test_broker_preserves_order_for_subscriber() -> None:
    broker = EventBroker()
    subscription = broker.subscribe("session-1")
    first_task = asyncio.create_task(anext(subscription))
    await asyncio.sleep(0)
    await broker.publish(make_event(1))
    assert (await first_task).step_id == 1
    second_task = asyncio.create_task(anext(subscription))
    await asyncio.sleep(0)
    await broker.publish(make_event(2))
    assert (await second_task).step_id == 2
    await subscription.aclose()


def test_sse_encoding_has_event_and_data_fields() -> None:
    encoded = encode_sse(make_event(1))
    assert encoded.startswith("event: test.event\n")
    assert "data: {" in encoded
    assert encoded.endswith("\n\n")


@pytest.mark.asyncio
async def test_live_sink_is_best_effort_when_viewer_is_offline() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    async with httpx.AsyncClient(transport=transport) as client:
        sink = LiveEventSink("http://127.0.0.1:8765", Redactor(Path(".")), client=client)
        await sink.emit(make_event(1))


@pytest.mark.asyncio
async def test_live_sink_redacts_before_transport(tmp_path: Path) -> None:
    received: dict[str, object] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        received.update(json.loads(request.content))
        return httpx.Response(202)

    event = make_event(1).model_copy(update={"payload": {"api_key": "secret-value"}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as client:
        sink = LiveEventSink(
            "http://127.0.0.1:8765",
            Redactor(tmp_path, secrets=("secret-value",)),
            client=client,
        )
        await sink.emit(event)
    assert received["payload"] == {"api_key": "[REDACTED]"}
```

- [x] **Step 2: 增加 Web 依赖并验证测试失败**

在 `pyproject.toml` 的 `dependencies` 增加：

```toml
  "fastapi>=0.115,<1",
  "httpx>=0.28,<1",
  "uvicorn>=0.34,<1",
```

Run: `conda run -n agent-foundations python -m pip install -e ".[dev]"`

Expected: 安装成功。

Run: `conda run -n agent-foundations python -m pytest tests/unit/viewer/test_stream.py -v`

Expected: FAIL，错误包含 `No module named 'agent_foundations.viewer'`。

- [x] **Step 3: 实现 Broker 和 SSE 编码**

```python
# src/agent_foundations/viewer/__init__.py
"""Local-only trace viewer."""
```

```python
# src/agent_foundations/viewer/stream.py
import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator

from agent_foundations.runtime.trace import TraceEvent


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[TraceEvent]]] = defaultdict(set)

    async def publish(self, event: TraceEvent) -> None:
        targets = self._subscribers[event.session_id] | self._subscribers["*"]
        for queue in targets:
            await queue.put(event)

    async def subscribe(self, session_id: str = "*") -> AsyncIterator[TraceEvent]:
        queue: asyncio.Queue[TraceEvent] = asyncio.Queue(maxsize=256)
        self._subscribers[session_id].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[session_id].discard(queue)


def encode_sse(event: TraceEvent) -> str:
    return f"event: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
```

- [x] **Step 4: 在 `runtime/sinks.py` 增加最佳努力 Live Sink**

在 imports 增加：

```python
import httpx
```

在文件末尾增加：

```python
class LiveEventSink:
    def __init__(
        self,
        viewer_url: str,
        redactor: Redactor,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._viewer_url = viewer_url.rstrip("/")
        self._redactor = redactor
        self._client = client

    async def emit(self, event: TraceEvent) -> None:
        data = self._redactor.redact(event.model_dump(mode="json"))
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._viewer_url}/api/events", json=data, timeout=2.0,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self._viewer_url}/api/events", json=data, timeout=2.0,
                    )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
```

Run: `conda run -n agent-foundations python -m pytest tests/unit/viewer/test_stream.py -v`

Expected: `4 passed`。

- [ ] **Step 5: 提交实时事件传输**

```powershell
git add pyproject.toml src/agent_foundations/viewer src/agent_foundations/runtime/sinks.py tests/unit/viewer/test_stream.py
git commit -m "feat: stream live trace events"
```

## Task 5: 实现 Viewer API 与历史 Session 接口

**Files:**
- Create: `src/agent_foundations/viewer/app.py`
- Test: `tests/integration/test_viewer_api.py`

- [x] **Step 1: 写本机事件接收、历史列表和 SSE 响应测试**

```python
# tests/integration/test_viewer_api.py
from pathlib import Path

from fastapi.testclient import TestClient

from agent_foundations.runtime.trace import TraceEvent
from agent_foundations.viewer.app import create_app
from agent_foundations.viewer.stream import EventBroker


def make_event() -> TraceEvent:
    return TraceEvent(
        session_id="session-api", step_id=1, event_type="tool.call.completed",
        status="completed", summary="read_file completed",
    )


def test_accepts_event_and_lists_persisted_session(tmp_path: Path) -> None:
    event = make_event()
    (tmp_path / "session-api.jsonl").write_text(event.model_dump_json() + "\n", encoding="utf-8")
    with TestClient(create_app(tmp_path, EventBroker())) as client:
        assert client.post("/api/events", json=event.model_dump(mode="json")).status_code == 202
        assert client.get("/api/sessions").json() == ["session-api"]
        history = client.get("/api/sessions/session-api").json()
        assert history[0]["event_type"] == "tool.call.completed"


def test_rejects_session_path_traversal(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path, EventBroker())) as client:
        response = client.get("/api/sessions/..%2Foutside")
        assert response.status_code in {404, 422}
```

- [x] **Step 2: 验证 Viewer App 尚不存在**

Run: `conda run -n agent-foundations python -m pytest tests/integration/test_viewer_api.py -v`

Expected: FAIL，错误包含 `No module named ...viewer.app`。

- [x] **Step 3: 实现只读 API、事件入口和 SSE**

```python
# src/agent_foundations/viewer/app.py
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent_foundations.runtime.replay import TraceReplayError, list_sessions, load_trace
from agent_foundations.runtime.trace import TraceEvent
from agent_foundations.viewer.stream import EventBroker, encode_sse


STATIC_DIR = Path(__file__).parent / "static"


def create_app(trace_dir: Path, broker: EventBroker | None = None) -> FastAPI:
    event_broker = broker or EventBroker()
    app = FastAPI(title="Agent Trace Viewer", docs_url=None, redoc_url=None)

    @app.post("/api/events", status_code=status.HTTP_202_ACCEPTED)
    async def receive_event(event: TraceEvent) -> None:
        await event_broker.publish(event)

    @app.get("/api/sessions")
    async def sessions() -> list[str]:
        return list_sessions(trace_dir)

    @app.get("/api/sessions/{session_id}")
    async def session_events(session_id: str) -> list[dict[str, object]]:
        if not _valid_session_id(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        path = trace_dir / f"{session_id}.jsonl"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="session not found")
        try:
            return [event.model_dump(mode="json") for event in load_trace(path)]
        except TraceReplayError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/events/stream")
    async def event_stream(session_id: str = "*") -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            async for event in event_broker.subscribe(session_id):
                yield encode_sse(event)

        return StreamingResponse(generate(), media_type="text/event-stream")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


def _valid_session_id(value: str) -> bool:
    return bool(value) and all(character.isalnum() or character in {"-", "_"} for character in value)
```

- [x] **Step 4: 验证 Viewer API 测试通过**

Run: `conda run -n agent-foundations python -m pytest tests/integration/test_viewer_api.py -v`

Expected: `4 passed`。

- [ ] **Step 5: 提交 Viewer API**

```powershell
git add src/agent_foundations/viewer/app.py tests/integration/test_viewer_api.py
git commit -m "feat: expose local trace viewer API"
```

## Task 6: 构建可交互 Trace Viewer 前端

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Modify: `.gitignore`
- Create: `src/agent_foundations/viewer/static/index.html`
- Create: `src/agent_foundations/viewer/static/styles.css`
- Create: `src/agent_foundations/viewer/static/app.ts`
- Generate: `src/agent_foundations/viewer/static/dist/app.js`

- [x] **Step 1: 创建 TypeScript 构建配置**

```json
{
  "name": "agent-trace-viewer",
  "private": true,
  "scripts": {
    "build:viewer": "tsc --project tsconfig.json",
    "typecheck:viewer": "tsc --project tsconfig.json --noEmit"
  },
  "devDependencies": {
    "typescript": "^5.7.3"
  }
}
```

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "lib": ["ES2022", "DOM"],
    "strict": true,
    "rootDir": "src/agent_foundations/viewer/static",
    "outDir": "src/agent_foundations/viewer/static/dist",
    "skipLibCheck": true
  },
  "include": ["src/agent_foundations/viewer/static/app.ts"]
}
```

在 `.gitignore` 末尾增加：

```gitignore
node_modules/
test-results/
playwright-report/
```

Run: `npm install`

Expected: 安装成功并生成 `package-lock.json`；执行前说明这是联网安装，用户确认后再运行。

- [x] **Step 2: 创建语义化页面结构**

```html
<!-- src/agent_foundations/viewer/static/index.html -->
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Trace Viewer</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">AGENT ENGINEERING LAB</p>
      <h1>Trace Viewer</h1>
    </div>
    <div class="status"><span id="live-dot"></span><span id="connection">Connecting</span></div>
  </header>
  <main class="layout">
    <aside class="sidebar">
      <label for="session-select">Session</label>
      <div class="row">
        <select id="session-select"><option value="">Live events</option></select>
        <button id="load-session" type="button">Load</button>
      </div>
      <label for="event-filter">Event type</label>
      <select id="event-filter"><option value="*">All events</option></select>
      <label class="checkbox"><input id="auto-scroll" type="checkbox" checked> Auto scroll</label>
      <p id="session-summary">No session selected</p>
    </aside>
    <section class="timeline-panel">
      <div class="panel-title"><h2>Timeline</h2><span id="event-count">0 events</span></div>
      <ol id="timeline" aria-live="polite"></ol>
    </section>
    <section class="detail-panel">
      <div class="panel-title">
        <h2>Event detail</h2>
        <button id="copy-json" type="button" disabled>Copy JSON</button>
      </div>
      <nav id="tabs" aria-label="Event details"></nav>
      <pre id="detail">Select an event from the timeline.</pre>
    </section>
  </main>
  <script type="module" src="/static/dist/app.js"></script>
</body>
</html>
```

- [x] **Step 3: 创建克制的三栏调试界面样式**

```css
/* src/agent_foundations/viewer/static/styles.css */
:root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #0b0d10; color: #e8edf2; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; }
button, select { font: inherit; color: inherit; background: #171b21; border: 1px solid #303640; border-radius: 8px; padding: .55rem .7rem; }
button { cursor: pointer; }
button:disabled { cursor: default; opacity: .45; }
.topbar { height: 76px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; border-bottom: 1px solid #252a32; }
.eyebrow { color: #7f8b99; font-size: 11px; letter-spacing: .16em; margin: 0 0 3px; }
h1, h2 { margin: 0; }
h1 { font-size: 22px; }
h2 { font-size: 14px; }
.status { display: flex; gap: 8px; align-items: center; color: #9ca8b6; }
#live-dot { width: 8px; height: 8px; border-radius: 50%; background: #e0a458; }
#live-dot.connected { background: #55c98b; box-shadow: 0 0 10px #55c98b66; }
.layout { height: calc(100vh - 76px); display: grid; grid-template-columns: 250px minmax(320px, 1fr) minmax(360px, 1.25fr); }
.sidebar, .timeline-panel, .detail-panel { min-width: 0; padding: 18px; border-right: 1px solid #252a32; overflow: auto; }
.sidebar { display: flex; flex-direction: column; gap: 10px; background: #0e1115; }
.sidebar label { margin-top: 8px; color: #9ca8b6; font-size: 12px; }
.row { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
.checkbox { display: flex; align-items: center; gap: 8px; }
#session-summary { color: #7f8b99; font-size: 12px; line-height: 1.6; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
#event-count { color: #7f8b99; font-size: 12px; }
#timeline { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.event { width: 100%; text-align: left; display: grid; grid-template-columns: 34px 1fr auto; gap: 9px; align-items: start; padding: 11px; }
.event.active { border-color: #65a9ff; background: #172334; }
.step { color: #65a9ff; font-variant-numeric: tabular-nums; }
.event-type { font-weight: 650; overflow-wrap: anywhere; }
.event-summary { grid-column: 2 / 4; color: #9ca8b6; font-size: 12px; overflow-wrap: anywhere; }
.event-status { color: #7f8b99; font-size: 11px; }
#tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
#tabs button.active { border-color: #65a9ff; color: #9bc7ff; }
#detail { min-height: 240px; white-space: pre-wrap; overflow-wrap: anywhere; background: #080a0d; border: 1px solid #252a32; border-radius: 10px; padding: 14px; color: #cbd5df; }
@media (max-width: 980px) { .layout { grid-template-columns: 220px 1fr; } .detail-panel { grid-column: 1 / 3; border-top: 1px solid #252a32; } body { overflow: auto; } .layout { height: auto; } }
@media (max-width: 640px) { .layout { display: block; } .topbar { padding: 0 14px; } .sidebar, .timeline-panel, .detail-panel { border-right: 0; border-bottom: 1px solid #252a32; } }
```

- [x] **Step 4: 实现历史加载、实时流、筛选和详情标签**

```typescript
// src/agent_foundations/viewer/static/app.ts
type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type TraceEvent = {
  event_id: string;
  session_id: string;
  step_id: number;
  event_type: string;
  status: string;
  timestamp: string;
  duration_ms: number | null;
  summary: string;
  payload: Record<string, Json>;
};

const byId = <T extends HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing element: ${id}`);
  return element as T;
};

const timeline = byId<HTMLOListElement>("timeline");
const detail = byId<HTMLPreElement>("detail");
const tabs = byId<HTMLElement>("tabs");
const eventFilter = byId<HTMLSelectElement>("event-filter");
const sessionSelect = byId<HTMLSelectElement>("session-select");
const autoScroll = byId<HTMLInputElement>("auto-scroll");
const copyButton = byId<HTMLButtonElement>("copy-json");
const eventCount = byId<HTMLElement>("event-count");
const sessionSummary = byId<HTMLElement>("session-summary");
const connection = byId<HTMLElement>("connection");
const liveDot = byId<HTMLElement>("live-dot");

let events: TraceEvent[] = [];
let selected: TraceEvent | null = null;
let activeTab = "Overview";
const tabNames = ["Overview", "Model Input", "Model Output", "Tool Arguments", "Tool Result", "Context Snapshot", "Raw JSON", "Error"];

function viewFor(event: TraceEvent, tab: string): Json {
  const payload = event.payload;
  const views: Record<string, Json> = {
    "Overview": { event_type: event.event_type, status: event.status, step_id: event.step_id, summary: event.summary, duration_ms: event.duration_ms },
    "Model Input": payload.request ?? payload.messages ?? "Not available for this event",
    "Model Output": payload.response ?? payload.content ?? payload.tool_calls ?? "Not available for this event",
    "Tool Arguments": payload.arguments ?? "Not available for this event",
    "Tool Result": payload.result ?? "Not available for this event",
    "Context Snapshot": payload.context ?? "Not available for this event",
    "Raw JSON": event as unknown as Json,
    "Error": payload.error ?? (event.status === "failed" ? payload : "No error"),
  };
  return views[tab];
}

function renderTabs(): void {
  tabs.replaceChildren(...tabNames.map((name) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = name;
    button.classList.toggle("active", name === activeTab);
    button.addEventListener("click", () => { activeTab = name; renderTabs(); renderDetail(); });
    return button;
  }));
}

function renderDetail(): void {
  detail.textContent = selected ? JSON.stringify(viewFor(selected, activeTab), null, 2) : "Select an event from the timeline.";
  copyButton.disabled = selected === null;
}

function renderTimeline(): void {
  const visible = events.filter((event) => eventFilter.value === "*" || event.event_type === eventFilter.value);
  timeline.replaceChildren(...visible.map((event) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "event";
    button.classList.toggle("active", selected?.event_id === event.event_id);
    button.innerHTML = `<span class="step">${event.step_id}</span><span class="event-type"></span><span class="event-status"></span><span class="event-summary"></span>`;
    (button.querySelector(".event-type") as HTMLElement).textContent = event.event_type;
    (button.querySelector(".event-status") as HTMLElement).textContent = event.status;
    (button.querySelector(".event-summary") as HTMLElement).textContent = event.summary;
    button.addEventListener("click", () => { selected = event; renderTimeline(); renderDetail(); });
    item.append(button);
    return item;
  }));
  eventCount.textContent = `${visible.length} events`;
  if (autoScroll.checked) timeline.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function updateFilters(): void {
  const current = eventFilter.value;
  const types = [...new Set(events.map((event) => event.event_type))].sort();
  eventFilter.replaceChildren(new Option("All events", "*"), ...types.map((type) => new Option(type, type)));
  eventFilter.value = types.includes(current) ? current : "*";
}

function setEvents(next: TraceEvent[]): void {
  events = next;
  selected = events.at(-1) ?? null;
  updateFilters();
  renderTimeline();
  renderDetail();
  const session = events[0]?.session_id ?? "none";
  sessionSummary.textContent = `Session: ${session}\nEvents: ${events.length}`;
}

async function loadSessions(): Promise<void> {
  const response = await fetch("/api/sessions");
  if (!response.ok) throw new Error(`Session list failed: ${response.status}`);
  const sessions = await response.json() as string[];
  sessionSelect.replaceChildren(new Option("Live events", ""), ...sessions.map((id) => new Option(id, id)));
}

async function loadSelectedSession(): Promise<void> {
  if (!sessionSelect.value) { setEvents([]); return; }
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionSelect.value)}`);
  if (!response.ok) throw new Error(`Session load failed: ${response.status}`);
  setEvents(await response.json() as TraceEvent[]);
}

function connectLive(): void {
  const source = new EventSource("/api/events/stream");
  source.onopen = () => { connection.textContent = "Live"; liveDot.classList.add("connected"); };
  source.onerror = () => { connection.textContent = "Reconnecting"; liveDot.classList.remove("connected"); };
  source.onmessage = (message) => setEvents([...events, JSON.parse(message.data) as TraceEvent]);
  for (const type of ["session.started", "user.message", "model.request.started", "model.response.received", "tool.call.requested", "tool.call.validated", "tool.call.completed", "tool.call.failed", "agent.final_answer", "agent.loop.stopped", "session.completed", "session.failed"]) {
    source.addEventListener(type, (message) => setEvents([...events, JSON.parse((message as MessageEvent<string>).data) as TraceEvent]));
  }
}

byId<HTMLButtonElement>("load-session").addEventListener("click", () => void loadSelectedSession());
eventFilter.addEventListener("change", renderTimeline);
copyButton.addEventListener("click", () => { if (selected) void navigator.clipboard.writeText(JSON.stringify(selected, null, 2)); });
renderTabs();
renderDetail();
void loadSessions();
connectLive();
```

- [ ] **Step 5: 编译并提交前端**

Run: `npm run typecheck:viewer`

Expected: 退出码 `0`，无 TypeScript 错误。

Run: `npm run build:viewer`

Expected: 生成 `src/agent_foundations/viewer/static/dist/app.js`。

```powershell
git add .gitignore package.json package-lock.json tsconfig.json src/agent_foundations/viewer/static
git commit -m "feat: build interactive trace viewer"
```

## Task 7: 将 Trace 与 Viewer 命令接入 CLI

**Files:**
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `tests/e2e/test_cli.py`

- [x] **Step 1: 扩展 CLI 测试，验证默认 JSONL 和固定本机绑定**

在 `tests/e2e/test_cli.py` 增加：

```python
def test_viewer_command_binds_loopback(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: object, host: str, port: int) -> None:
        captured.update({"host": host, "port": port})

    monkeypatch.setattr(main.uvicorn, "run", fake_run)
    result = CliRunner().invoke(main.app, ["viewer", "--trace-dir", str(tmp_path), "--port", "9001"])
    assert result.exit_code == 0
    assert captured == {"host": "127.0.0.1", "port": 9001}
```

同时把既有 `test_cli_renders_final_answer` 的 monkeypatch 更新为接受新签名：

```python
    monkeypatch.setattr(main, "build_runtime", lambda root, trace_dir, viewer_url: FakeLoop())
```

- [x] **Step 2: 运行测试确认 CLI 尚未支持 Viewer**

Run: `conda run -n agent-foundations python -m pytest tests/e2e/test_cli.py -v`

Expected: FAIL，错误显示没有 `viewer` 命令或 `uvicorn` 属性。

- [x] **Step 3: 用以下完整版本替换 CLI 主模块**

```python
# src/agent_foundations/cli/main.py
import asyncio
import os
from pathlib import Path

import typer
import uvicorn
from openai import AsyncOpenAI
from rich.console import Console

from agent_foundations.cli.renderer import render_result
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.providers.openai_compatible import OpenAICompatibleProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import CompositeEventSink, JsonlEventSink, LiveEventSink
from agent_foundations.runtime.trace import EventSink
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool
from agent_foundations.tools.filesystem.search_text import SearchTextTool
from agent_foundations.tools.registry import ToolRegistry
from agent_foundations.viewer.app import create_app


app = typer.Typer(no_args_is_help=True)
console = Console()


def build_runtime(root: Path, trace_dir: Path, viewer_url: str | None) -> AgentLoop:
    api_key = os.environ["AGENT_API_KEY"]
    model = os.environ["AGENT_MODEL"]
    base_url = os.getenv("AGENT_BASE_URL", "https://api.openai.com/v1")
    policy = PathPolicy(root)
    registry = ToolRegistry([ListDirectoryTool(policy), ReadFileTool(policy), SearchTextTool(policy)])
    redactor = Redactor(root, secrets=(api_key,))
    sinks: list[EventSink] = [JsonlEventSink(trace_dir, redactor)]
    if viewer_url:
        sinks.append(LiveEventSink(viewer_url, redactor))
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=2)
    return AgentLoop(
        provider=OpenAICompatibleProvider(client, model=model),
        registry=registry,
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=CompositeEventSink(sinks),
        config=AgentConfig(),
    )


@app.command()
def analyze(
    root: Path,
    query: str,
    trace_dir: Path = typer.Option(Path("traces"), help="Local JSONL trace directory"),
    viewer_url: str | None = typer.Option(None, help="Optional local viewer URL"),
) -> None:
    """Analyze a local project without modifying it."""
    missing = [name for name in ("AGENT_API_KEY", "AGENT_MODEL") if not os.getenv(name)]
    if missing:
        console.print(f"Missing environment variables: {', '.join(missing)}", style="red")
        raise typer.Exit(code=2)
    try:
        resolved = root.resolve(strict=True)
        result = asyncio.run(build_runtime(resolved, trace_dir.resolve(), viewer_url).run(resolved, query))
    except Exception as exc:
        console.print(f"Agent failed: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    render_result(console, result)


@app.command()
def viewer(
    trace_dir: Path = typer.Option(Path("traces"), help="Local JSONL trace directory"),
    port: int = typer.Option(8765, min=1024, max=65535),
) -> None:
    """Serve the local read-only Trace Viewer."""
    console.print(f"Trace Viewer: http://127.0.0.1:{port}")
    uvicorn.run(create_app(trace_dir.resolve()), host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
```

- [x] **Step 4: 验证 CLI 测试和帮助文本**

Run: `conda run -n agent-foundations python -m pytest tests/e2e/test_cli.py -v`

Expected: 所有 CLI 测试通过。

Run: `conda run -n agent-foundations agent-foundations --help`

Expected: 显示 `analyze` 和 `viewer` 两个命令。

- [ ] **Step 5: 提交 CLI 可观察性接线**

```powershell
git add src/agent_foundations/cli/main.py tests/e2e/test_cli.py
git commit -m "feat: connect CLI tracing and viewer"
```

## Task 8: 自动化浏览器验收、README 和阶段总结

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/e2e/test_trace_viewer.py`
- Modify: `README.md`
- Create: `docs/learning-notes/03-observability.md`

- [x] **Step 1: 增加浏览器测试依赖**

在 `pyproject.toml` 的 `dev` dependencies 增加：

```toml
  "pytest-playwright>=0.6,<1",
```

Run: `conda run -n agent-foundations python -m pip install -e ".[dev]"`

Expected: 安装成功。

Run: `conda run -n agent-foundations python -m playwright install chromium`

Expected: Chromium 安装成功；该命令联网并写入 Playwright 浏览器缓存，执行前说明影响并获得用户确认。

- [x] **Step 2: 写历史 Session 的浏览器端到端测试**

```python
# tests/e2e/test_trace_viewer.py
import socket
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import Page, expect

from agent_foundations.runtime.trace import TraceEvent
from agent_foundations.viewer.app import create_app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_viewer_loads_history_and_shows_event_detail(tmp_path: Path, page: Page) -> None:
    event = TraceEvent(
        session_id="browser-session", step_id=2, event_type="tool.call.completed",
        status="completed", summary="read_file completed",
        payload={"result": {"content": "auth.py line 1"}},
    )
    (tmp_path / "browser-session.jsonl").write_text(event.model_dump_json() + "\n", encoding="utf-8")
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(tmp_path), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    try:
        page.goto(f"http://127.0.0.1:{port}")
        page.locator("#session-select").select_option("browser-session")
        page.locator("#load-session").click()
        expect(page.locator("#timeline")).to_contain_text("tool.call.completed")
        page.get_by_role("button", name="Tool Result").click()
        expect(page.locator("#detail")).to_contain_text("auth.py line 1")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
```

- [x] **Step 3: 编写可执行 README**

```markdown
# Agent Engineering Foundations

一个以学习 Agent Engineering 为目标的只读 Python Agent Runtime。第一阶段实现模型适配、工具调用、文件安全边界、Agent Loop、JSONL Trace 和本地 Web Viewer。

## 安全边界

- 只提供 `list_directory`、`read_file`、`search_text`。
- 不写文件，不运行 Shell 或 Git。
- 所有路径必须位于项目根目录，敏感文件默认拒绝。
- API Key 只从环境变量读取，并在 Trace 写入前脱敏。
- Viewer 只绑定 `127.0.0.1`。

## Anaconda 环境

```powershell
conda create -n agent-foundations python=3.12 -y
conda activate agent-foundations
python -m pip install -e ".[dev]"
npm install
npm run build:viewer
```

复制 `.env.example` 中的变量名，在当前 PowerShell 会话临时设置实际值；不要提交真实 `.env`。

## 运行

终端一启动 Viewer：

```powershell
conda activate agent-foundations
agent-foundations viewer --trace-dir traces --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。终端二启动 Agent：

```powershell
conda activate agent-foundations
$env:AGENT_API_KEY = "你的 Provider Key"
$env:AGENT_BASE_URL = "你的 OpenAI-compatible endpoint"
$env:AGENT_MODEL = "你的模型名"
agent-foundations analyze "D:\path\to\project" "解释项目入口" --viewer-url "http://127.0.0.1:8765"
```

## 验证

```powershell
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
npm run typecheck:viewer
```

自动测试不调用真实模型。真实 API Smoke Test 只在用户主动确认费用后执行。
```

- [x] **Step 4: 写可观察性学习笔记**

```markdown
# 03 Observability 学习笔记

## Event 为什么是一等公民

日志主要供人阅读，`TraceEvent` 同时服务于测试、回放、Viewer 和未来评测。稳定字段描述事件身份和顺序，`payload` 保存事件特有数据。

## 双 Sink 设计

JSONL 是本地事实记录；Live Sink 是最佳努力传输。Viewer 未启动或短暂断开时，Agent 仍继续运行，历史事件仍能从 JSONL 加载。

## 安全顺序

事件先在 Runtime 中形成，再由 Redactor 生成持久化和传输副本。Redactor 不修改 Runtime 原对象，并递归处理嵌套字典、列表、Header、已知密钥和项目绝对路径。

## Viewer 边界

Viewer 只接收事件和读取 Trace，不提供暂停 Agent、修改 Prompt、批准工具或执行命令的 API。控制面留到需要权限模型的第二阶段。

## 后续改进依据

- 事件量超过内存队列上限时，需要明确背压或丢弃策略。
- 多进程并发写同一 Session 前，需要文件锁或单写者。
- Token 与成本展示必须来自 Provider 统一 Usage，而不是前端估算。
```

- [ ] **Step 5: 运行第一阶段总门禁并提交**

Run: `conda run -n agent-foundations python -m pytest -q`

Expected: 所有 unit、contract、integration、e2e 测试通过。

Run: `conda run -n agent-foundations python -m ruff check .`

Expected: `All checks passed!`。

Run: `conda run -n agent-foundations python -m mypy src tests`

Expected: `Success: no issues found`。

Run: `npm run typecheck:viewer`

Expected: 退出码 `0`。

Run: `git diff --check`

Expected: 无输出，退出码 `0`。

```powershell
git add pyproject.toml tests/e2e/test_trace_viewer.py README.md docs/learning-notes/03-observability.md
git commit -m "test: complete phase one acceptance"
```

## 第一阶段人工验收

真实 API 可能产生费用，执行前必须再次获得用户确认。

1. 启动 `agent-foundations viewer --trace-dir traces`，确认只显示 `http://127.0.0.1:8765`。
2. 用另一个 PowerShell 运行一次 fixture 分析任务并传入 `--viewer-url`。
3. Viewer 中确认事件按 step 排列，工具参数和结果可查看，筛选和自动滚动开关有效。
4. 关闭 Viewer 后再次运行 Agent，确认 Agent 正常结束且 JSONL 仍完整。
5. 搜索 Trace，确认真实 API Key、`Authorization` 值和项目绝对路径均不存在。
6. 选择历史 Session 重新加载，确认事件数量、顺序和详情与 JSONL 一致。
7. 运行 `git status --short`，确认 `traces/`、`.env`、`node_modules/`、缓存与浏览器产物未被跟踪。

## Milestone 3 完成条件

- [ ] 每个 Runtime 事件都写入结构化 JSONL，损坏文件给出行号。
- [ ] Redactor 通过嵌套数据、密钥、Bearer Header 和绝对路径测试。
- [ ] Viewer 离线不影响 Agent，在线时 SSE 保持事件顺序。
- [ ] Viewer 可加载历史 Session、筛选事件、暂停自动滚动、切换详情和复制 JSON。
- [ ] Viewer 只有观察接口并固定绑定 `127.0.0.1`。
- [ ] 自动浏览器验收、pytest、Ruff、mypy、TypeScript 全部通过。
- [ ] README 和三篇阶段学习笔记完成。
