# Structured Chat Message Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render user and assistant messages as safe GitHub-Flavored Markdown, present durable redacted tool activity inside the corresponding conversation turn, and keep full Trace details in Trace Viewer.

**Architecture:** Extend the existing JSONL-first trace pipeline with a best-effort SQLite projection keyed by `(session_id, tool_call_id)`. Recover that projection over HTTP before SSE, merge live events idempotently, project messages/runs/activities into turns, and render each turn with native React components. Keep full tool arguments, results, reasoning, and credentials out of SQLite and the Chat UI.

**Tech Stack:** Python 3.12, Pydantic, SQLite, FastAPI, React 19, TypeScript, Vite, Vitest, Playwright, `react-markdown`, `remark-gfm`, Shiki.

---

## Execution Rules

- Execute exactly one Task per user authorization. Do not begin the next Task automatically.
- Before every Task, read `AGENTS.md`, the approved design at `docs/superpowers/specs/2026-08-08-structured-chat-message-rendering-design.md`, and the Task section below.
- Run `git status --short` before editing and preserve all pre-existing user changes.
- Create or update the named `docs/task-evidence/<task-id>.md` from `docs/task-evidence/_template.md` before production edits.
- Capture a genuine Red before production code. If historical Red is missing, record `unavailable`; never recreate it after implementation.
- Automated tests must use fake providers only. Do not read `.env` values or call a real/paid model API.
- Do not install dependencies until the user explicitly authorizes that installation Task.
- A commit checkpoint is not authorization to commit. Commit only when the user explicitly asks; otherwise record the proposed message in evidence.

## Task 1: Add the Durable Tool Activity Domain Model and Schema Migration

**Task ID:** `structured-chat-rendering-task-1`

**Files:**

- Modify: `src/agent_foundations/chat/models.py`
- Modify: `src/agent_foundations/chat/repository.py`
- Modify: `tests/unit/chat/test_models.py`
- Modify: `tests/unit/chat/test_repository.py`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-1.md`

- [ ] **Step 1: Record the clean-room starting state**

Run:

```powershell
git status --short
if (-not (Test-Path docs/task-evidence/structured-chat-rendering-task-1.md)) {
    Copy-Item docs/task-evidence/_template.md docs/task-evidence/structured-chat-rendering-task-1.md
}
```

Record which dirty files predate this Task. Do not stage, restore, or edit them.

- [ ] **Step 2: Write model and migration tests**

Add tests that require the new typed record and migration from schema version 1:

```python
def test_tool_activity_requires_bounded_safe_summary() -> None:
    activity = ChatToolActivity(
        conversation_id=str(uuid4()),
        session_id=str(uuid4()),
        tool_call_id="call-1",
        tool_name="read_file",
        status=ToolActivityStatus.RUNNING,
        arguments_summary="README.md",
        started_at=datetime.now(UTC),
        last_event_id=str(uuid4()),
    )
    assert activity.status is ToolActivityStatus.RUNNING

    with pytest.raises(ValidationError):
        ChatToolActivity.model_validate(
            {**activity.model_dump(), "arguments_summary": "x" * 241}
        )
```

```python
async def test_initialize_migrates_v1_database_to_v2(tmp_path: Path) -> None:
    database_path = tmp_path / "chat.sqlite3"
    create_version_one_database(database_path)

    repository = ConversationRepository(database_path)
    await repository.initialize()

    assert read_user_version(database_path) == 2
    assert "chat_tool_activities" in read_table_names(database_path)
```

Also update the unsupported-newer-schema test to use version `3`.

- [ ] **Step 3: Run Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_models.py tests/unit/chat/test_repository.py -q
```

Expected: failure because `ChatToolActivity`, `ToolActivityStatus`, and the v1-to-v2 migration do not exist.

- [ ] **Step 4: Add the domain types**

Add to `models.py`:

```python
class ToolActivityStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

    @classmethod
    def terminal(cls) -> set["ToolActivityStatus"]:
        return {cls.COMPLETED, cls.FAILED, cls.INTERRUPTED}


class ChatToolActivity(ChatModel):
    conversation_id: UUIDString
    session_id: UUIDString
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    status: ToolActivityStatus
    arguments_summary: str | None = Field(default=None, max_length=240)
    result_summary: str | None = Field(default=None, max_length=240)
    started_at: UTCDateTime
    finished_at: UTCDateTime | None = None
    last_event_id: UUIDString
```

- [ ] **Step 5: Implement an explicit v1-to-v2 migration**

Set `_SCHEMA_VERSION = 2`, preserve the current v1 statements, and add:

```python
_MIGRATION_V1_TO_V2_STATEMENTS = (
    """
    CREATE TABLE chat_tool_activities (
        session_id TEXT NOT NULL REFERENCES runs(session_id) ON DELETE CASCADE,
        tool_call_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN ('running', 'completed', 'failed', 'interrupted')
        ),
        arguments_summary TEXT CHECK (
            arguments_summary IS NULL OR length(arguments_summary) <= 240
        ),
        result_summary TEXT CHECK (
            result_summary IS NULL OR length(result_summary) <= 240
        ),
        started_at TEXT NOT NULL,
        finished_at TEXT,
        last_event_id TEXT NOT NULL,
        PRIMARY KEY (session_id, tool_call_id)
    )
    """,
    """
    CREATE INDEX idx_chat_tool_activities_session_started
    ON chat_tool_activities(session_id, started_at, tool_call_id)
    """,
)

_MIGRATIONS = {
    0: _SCHEMA_V1_STATEMENTS,
    1: _MIGRATION_V1_TO_V2_STATEMENTS,
}
```

Replace the version short-circuit with a transaction that applies each migration in order and updates `PRAGMA user_version` after each successful step. A failed migration must roll back entirely.

- [ ] **Step 6: Run Green and local quality checks**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_models.py tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/models.py src/agent_foundations/chat/repository.py tests/unit/chat/test_models.py tests/unit/chat/test_repository.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/models.py src/agent_foundations/chat/repository.py tests/unit/chat/test_models.py tests/unit/chat/test_repository.py
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 7: Audit and checkpoint**

Verify the migration does not alter existing messages, runs, or approvals. Update evidence with Red, Green, gate outputs, diff scope, and proposed commit message:

```text
feat: add durable chat tool activity schema
```

## Task 2: Implement Idempotent Activity Persistence and Atomic Interruption

**Task ID:** `structured-chat-rendering-task-2`

**Files:**

- Modify: `src/agent_foundations/chat/repository.py`
- Modify: `tests/unit/chat/test_repository.py`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-2.md`

- [ ] **Step 1: Write repository contract tests**

Cover insert, terminal update, duplicate replay, cross-conversation rejection, ordering, and startup recovery:

```python
async def test_upsert_tool_activity_merges_by_session_and_call_id(
    repository: ConversationRepository,
) -> None:
    requested = make_activity(status=ToolActivityStatus.RUNNING)
    completed = requested.model_copy(
        update={
            "status": ToolActivityStatus.COMPLETED,
            "result_summary": "1 match",
            "finished_at": datetime.now(UTC),
            "last_event_id": str(uuid4()),
        }
    )

    await repository.upsert_tool_activity(requested)
    await repository.upsert_tool_activity(completed)

    assert await repository.list_tool_activities(requested.conversation_id) == [completed]
```

```python
async def test_interrupt_unfinished_updates_run_and_activity_atomically(...) -> None:
    await repository.interrupt_unfinished()
    recovered = await repository.list_tool_activities(conversation.conversation_id)
    assert recovered[0].status is ToolActivityStatus.INTERRUPTED
    assert (await repository.get_run(run.session_id)).status is RunStatus.INTERRUPTED
```

- [ ] **Step 2: Run Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py -q
```

Expected: missing repository methods and missing interruption update.

- [ ] **Step 3: Add public asynchronous methods**

Implement:

```python
async def upsert_tool_activity(
    self,
    activity: ChatToolActivity,
) -> ChatToolActivity:
    return await asyncio.to_thread(self._upsert_tool_activity_sync, activity)

async def list_tool_activities(
    self,
    conversation_id: str,
) -> list[ChatToolActivity]:
    return await asyncio.to_thread(self._list_tool_activities_sync, conversation_id)
```

The SQL upsert must:

- verify the run belongs to `activity.conversation_id`;
- key by `(session_id, tool_call_id)`;
- retain the original `started_at`;
- merge non-null summaries;
- never downgrade `completed`, `failed`, or `interrupted` to `running`;
- update `last_event_id` only when the accepted state changes.

- [ ] **Step 4: Add deterministic listing and atomic recovery**

List through a join with `runs` so `conversation_id` is derived, not duplicated:

```sql
SELECT r.conversation_id, a.*
FROM chat_tool_activities AS a
JOIN runs AS r ON r.session_id = a.session_id
WHERE r.conversation_id = ?
ORDER BY r.created_at, a.started_at, a.tool_call_id
```

Inside the existing `_interrupt_unfinished_sync` transaction, update activity rows before updating their runs:

```sql
UPDATE chat_tool_activities
SET status = 'interrupted', finished_at = COALESCE(finished_at, ?)
WHERE status = 'running'
  AND session_id IN (
      SELECT session_id FROM runs
      WHERE status IN ('queued', 'running', 'waiting_approval')
  )
```

Keep the existing return value `(interrupted_runs, invalidated_approvals)` unchanged.

- [ ] **Step 5: Run Green and gates**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_repository.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/repository.py tests/unit/chat/test_repository.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/repository.py tests/unit/chat/test_repository.py
git diff --check
```

- [ ] **Step 6: Audit and checkpoint**

Confirm SQLite stores no tool content, file contents, match text, external absolute path, or credential. Proposed commit:

```text
feat: persist redacted chat tool activities
```

## Task 3: Project Safe Semantic Activity and Make Chat Projection Best-Effort

**Task ID:** `structured-chat-rendering-task-3`

**Files:**

- Modify: `src/agent_foundations/chat/events.py`
- Modify: `src/agent_foundations/chat/runner.py`
- Modify: `src/agent_foundations/cli/main.py`
- Modify: `tests/unit/chat/test_events.py`
- Modify: `tests/unit/chat/test_runner.py`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-3.md`

- [ ] **Step 1: Write projection and failure-isolation tests**

Require source identifiers, semantic summaries, persistence-before-publish, duplicate tolerance, and cancellation propagation:

```python
def test_projector_preserves_source_event_and_tool_call_ids() -> None:
    projected = projector.project(make_tool_requested_event())
    assert projected is not None
    assert projected.event_id == source.event_id
    assert projected.data["tool_call_id"] == "call-1"
```

```python
async def test_projection_failure_does_not_fail_jsonl_run() -> None:
    repository.upsert_tool_activity.side_effect = sqlite3.OperationalError("closed")
    await sink.emit(make_tool_requested_event())
    broker.publish.assert_not_awaited()
```

Also assert that `read_file` content, `search_text` match lines, list entries, external absolute paths, and injected secrets never appear in projected data or persisted records.

- [ ] **Step 2: Run Red**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_events.py tests/unit/chat/test_runner.py -q
```

- [ ] **Step 3: Replace generic JSON summaries with allowlisted semantic summaries**

Add `tool_call_id` to `_ALLOWED_DATA_KEYS`, preserve `event.event_id`, and build bounded summaries by known tool:

```python
def _summarize_arguments(name: str, arguments: Mapping[str, Any], project_root: Path) -> str:
    if name == "read_file":
        return _safe_path_summary(arguments.get("path"), project_root)
    if name == "list_directory":
        return _safe_path_summary(arguments.get("path", "."), project_root)
    if name == "search_text":
        query = arguments.get("query")
        return f"query={_safe_scalar(query)}"
    return "arguments hidden"
```

```python
def _summarize_result(name: str, result: Mapping[str, Any]) -> str:
    if result.get("success") is not True:
        error_code = result.get("error_code")
        return f"failed: {_safe_scalar(error_code)}"
    metadata = result.get("metadata")
    if name == "read_file" and isinstance(metadata, Mapping):
        return f"{_safe_count(metadata.get('returned_lines'))} lines"
    content = result.get("content")
    payload = _parse_json_object(content) if isinstance(content, str) else None
    if name == "list_directory" and payload is not None:
        entries = payload.get("entries")
        return f"{len(entries) if isinstance(entries, list) else 0} entries"
    if name == "search_text" and payload is not None:
        matches = payload.get("matches")
        count = len(matches) if isinstance(matches, list) else 0
        scanned = _safe_count(payload.get("scanned_files"))
        return f"{count} matches in {scanned} files"
    return "completed"
```

`_parse_json_object` must return only a decoded mapping or `None`; callers read
only list lengths and numeric count fields, then discard every entry, path, query,
and match-text value. Normalize project paths to project-relative POSIX form;
emit `[external path]` for anything outside the project.

- [ ] **Step 4: Convert projected events into durable activity rows**

Add a pure merger that maps requested/completed/failed events to `ChatToolActivity`. Requested creates `running`; completed/failed supply terminal status and `finished_at`. Terminal events without a prior requested event must still produce a minimal row.

```python
def activity_from_chat_event(event: ChatEvent) -> ChatToolActivity | None:
    if event.type not in {
        ChatEventType.TOOL_REQUESTED,
        ChatEventType.TOOL_COMPLETED,
        ChatEventType.TOOL_FAILED,
    }:
        return None
    return ChatToolActivity(
        conversation_id=event.conversation_id,
        session_id=event.session_id,
        tool_call_id=_required_string(event.data, "tool_call_id"),
        tool_name=_required_string(event.data, "name"),
        status=_activity_status(event.type),
        arguments_summary=_optional_string(event.data, "arguments_summary"),
        result_summary=_optional_string(event.data, "result_summary"),
        started_at=event.occurred_at,
        finished_at=None if event.type is ChatEventType.TOOL_REQUESTED else event.occurred_at,
        last_event_id=event.event_id,
    )
```

- [ ] **Step 5: Persist before publish without breaking the core run**

Construct `ChatProjectionSink(projector, repository, broker)`. In `emit`, project, persist activity when present, then publish the event. Re-raise cancellation, but log only safe exception metadata for other projection/storage/broker failures:

```python
try:
    chat_event = self._projector.project(event)
    if chat_event is None:
        return
    activity = activity_from_chat_event(chat_event)
    if activity is not None:
        await self._repository.upsert_tool_activity(activity)
    await self._broker.publish(chat_event)
except asyncio.CancelledError:
    raise
except Exception as exc:
    logger.warning("chat projection skipped: %s", type(exc).__name__)
    return
else:
    self._seen_event_ids.add(event.event_id)
```

Keep `JsonlEventSink` first in `CompositeEventSink`. Pass the repository and resolved project root from the existing service wiring; do not make JSONL dependent on SQLite projection success.

- [ ] **Step 6: Run Green and gates**

```powershell
conda run -n agent-foundations python -m pytest tests/unit/chat/test_events.py tests/unit/chat/test_runner.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/events.py src/agent_foundations/chat/runner.py src/agent_foundations/cli/main.py tests/unit/chat/test_events.py tests/unit/chat/test_runner.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/events.py src/agent_foundations/chat/runner.py src/agent_foundations/cli/main.py tests/unit/chat/test_events.py tests/unit/chat/test_runner.py
git diff --check
```

- [ ] **Step 7: Audit and checkpoint**

Inspect generated SQLite rows and `ChatEvent.model_dump_json()` using fake secrets. The secret, raw file content, match text, and external absolute path must have zero hits. Proposed commit:

```text
feat: project safe chat activity summaries
```

## Task 4: Expose the Activity Recovery API

**Task ID:** `structured-chat-rendering-task-4`

**Files:**

- Modify: `src/agent_foundations/chat/api.py`
- Modify: `tests/integration/test_chat_api.py`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-4.md`

- [ ] **Step 1: Write endpoint contract and security tests**

Add exact-shape probes for present, empty, malformed, and valid-but-missing IDs:

```python
def test_list_activities_returns_redacted_ordered_rows(client: TestClient) -> None:
    response = client.get(f"/api/chat/conversations/{conversation_id}/activities")
    assert response.status_code == 200
    assert response.json() == [expected_activity]
    assert secret not in response.text
```

Expected validation:

- malformed UUID: `422`;
- well-formed missing UUID: `404`;
- existing conversation without activities: `200` and `[]`;
- response has only the approved `ChatToolActivity` fields.

- [ ] **Step 2: Run Red**

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_chat_api.py -q
```

Expected: endpoint returns `404` because it does not exist.

- [ ] **Step 3: Add the typed endpoint**

```python
@router.get(
    "/conversations/{conversation_id}/activities",
    response_model=list[ChatToolActivity],
)
async def list_tool_activities(
    conversation_id: UUID,
) -> list[ChatToolActivity]:
    normalized_id = str(conversation_id)
    try:
        return await repository.list_tool_activities(normalized_id)
    except ChatNotFoundError as exc:
        raise _stable_http_error(exc) from exc
```

- [ ] **Step 4: Run Green and gates**

```powershell
conda run -n agent-foundations python -m pytest tests/integration/test_chat_api.py -q
conda run -n agent-foundations python -m ruff check src/agent_foundations/chat/api.py tests/integration/test_chat_api.py
conda run -n agent-foundations python -m mypy src/agent_foundations/chat/api.py tests/integration/test_chat_api.py
git diff --check
```

- [ ] **Step 5: Audit and checkpoint**

Confirm the endpoint does not read JSONL and cannot expose raw trace payloads. Proposed commit:

```text
feat: expose chat activity recovery endpoint
```

## Task 5: Recover and Merge Activity State in the Chat Client

**Task ID:** `structured-chat-rendering-task-5`

**Files:**

- Modify: `web/chat/state/types.ts`
- Modify: `web/chat/state/api.ts`
- Modify: `web/chat/state/reducer.ts`
- Modify: `web/chat/App.tsx`
- Modify: `tests/chat/reducer.test.ts`
- Modify: `tests/chat/app.test.tsx`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-5.md`

- [ ] **Step 1: Write reducer and recovery ordering tests**

Require idempotent merge and HTTP-before-SSE recovery with an immediate catch-up fetch:

```typescript
it("merges terminal activity into the matching requested activity", () => {
  const loaded = reduceChatState(initialState, {
    type: "activities.loaded",
    conversationId,
    activities: [runningActivity],
  });
  const completed = reduceChatState(loaded, {
    type: "event.received",
    event: toolCompletedEvent,
  });
  expect(completed.activitiesByConversation[conversationId]).toEqual([
    completedActivity,
  ]);
});
```

```typescript
expect(callOrder.indexOf("connect-sse")).toBeGreaterThan(
  Math.max(
    callOrder.indexOf("messages-resolved"),
    callOrder.indexOf("runs-resolved"),
    callOrder.indexOf("activities-resolved"),
    callOrder.indexOf("state-resolved"),
  ),
);
expect(callOrder.indexOf("activities-catch-up")).toBeGreaterThan(
  callOrder.indexOf("connect-sse"),
);
```

- [ ] **Step 2: Run Red**

```powershell
npm run test:chat -- --run tests/chat/reducer.test.ts tests/chat/app.test.tsx
```

- [ ] **Step 3: Add frontend activity types and API**

```typescript
export type ToolActivityStatus =
  | "running"
  | "completed"
  | "failed"
  | "interrupted";

export interface ChatToolActivity {
  conversation_id: string;
  session_id: string;
  tool_call_id: string;
  tool_name: string;
  status: ToolActivityStatus;
  arguments_summary: string | null;
  result_summary: string | null;
  started_at: string;
  finished_at: string | null;
  last_event_id: string;
}
```

```typescript
export function listActivities(conversationId: string): Promise<ChatToolActivity[]> {
  return requestJson(`/api/chat/conversations/${conversationId}/activities`);
}
```

- [ ] **Step 4: Replace append-only events with activity upserts**

Change `activitiesByConversation` to `Record<string, ChatToolActivity[]>`. Add `activities.loaded`, `activities.error`, and a pure merge keyed by `${session_id}:${tool_call_id}`. Terminal state wins over a late `running` replay:

```typescript
function mergeActivities(
  existing: ChatToolActivity[],
  incoming: ChatToolActivity[],
): ChatToolActivity[] {
  const byKey = new Map(existing.map((item) => [activityKey(item), item]));
  for (const candidate of incoming) {
    const current = byKey.get(activityKey(candidate));
    byKey.set(activityKey(candidate), preferTerminal(current, candidate));
  }
  return [...byKey.values()].sort(compareActivities);
}
```

Convert only `tool.requested`, `tool.completed`, and `tool.failed` SSE events into activity updates. Ignore malformed tool events without corrupting the prior state.

- [ ] **Step 5: Implement gap-free recovery**

For each selected conversation:

1. fetch messages, runs, activities, and current state;
2. dispatch all snapshots;
3. connect SSE;
4. immediately fetch activities again and merge;
5. refetch activities after terminal run events.

Use the existing abort/unmount protections so a late response from a previously selected conversation cannot replace current state.
If either activity snapshot fails, preserve already loaded messages and runs, set a
conversation-scoped non-blocking error, and expose an action that retries only
`listActivities(conversationId)`.

- [ ] **Step 6: Run Green and gates**

```powershell
npm run test:chat -- --run tests/chat/reducer.test.ts tests/chat/app.test.tsx
npm run typecheck:chat
git diff --check
```

- [ ] **Step 7: Audit and checkpoint**

Confirm no raw `ChatEvent[]` is rendered as transcript content. Proposed commit:

```text
feat: recover durable chat activity state
```

## Task 6: Project Conversation Data into Turns and Render Tool Groups

**Task ID:** `structured-chat-rendering-task-6`

**Files:**

- Create: `web/chat/state/turns.ts`
- Create: `web/chat/components/ToolActivityGroup.tsx`
- Modify: `web/chat/components/ApprovalCard.tsx`
- Modify: `tests/chat/activity.test.tsx`
- Create: `tests/chat/turns.test.ts`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-6.md`

- [ ] **Step 1: Write turn projection and interaction tests**

Test multiple runs in one conversation, out-of-order inputs, active/default expansion, terminal/default collapse, manual override, approval nesting, and fallback approval:

```typescript
it("keeps every run and its activity in the matching conversation turn", () => {
  expect(buildConversationTurns(messages, runs, activities)).toEqual([
    expect.objectContaining({
      run: firstRun,
      userMessage: firstUserMessage,
      activities: [firstActivity],
    }),
    expect.objectContaining({
      run: secondRun,
      userMessage: secondUserMessage,
      activities: [secondActivity],
    }),
  ]);
});
```

```typescript
expect(screen.getByRole("button", { name: /2 tool activities/i })).toHaveAttribute(
  "aria-expanded",
  "false",
);
```

- [ ] **Step 2: Run Red**

```powershell
npm run test:chat -- --run tests/chat/turns.test.ts tests/chat/activity.test.tsx
```

- [ ] **Step 3: Add deterministic turn projection**

```typescript
export interface ConversationTurn {
  run: RunRecord;
  userMessage: ChatMessage;
  assistantMessage: ChatMessage | null;
  activities: ChatToolActivity[];
}

export function buildConversationTurns(
  messages: ChatMessage[],
  runs: RunRecord[],
  activities: ChatToolActivity[],
): ConversationTurn[] {
  const messagesById = new Map(messages.map((message) => [message.message_id, message]));
  return [...runs]
    .sort(compareRuns)
    .flatMap((run) => {
      const userMessage = messagesById.get(run.user_message_id);
      if (!userMessage) return [];
      return [{
        run,
        userMessage,
        assistantMessage: run.assistant_message_id
          ? messagesById.get(run.assistant_message_id) ?? null
          : null,
        activities: activities.filter((item) => item.session_id === run.session_id),
      }];
    });
}
```

Do not synthesize old activity rows from JSONL. Runs without activity records render messages and the exact Trace link, but omit the tool group.

- [ ] **Step 4: Add the accessible collapsible tool group**

Use one group per run. Track `manualExpanded: boolean | null`; derive initial state from run status and reset the override when `session_id` changes:

```typescript
const active = runStatus === "queued" || runStatus === "running" || runStatus === "waiting_approval";
const expanded = manualExpanded ?? active;
```

Each row shows only tool name, status, safe argument summary, safe result summary, and timing. Put an approval under the row whose `tool_call_id` matches. If the pending approval has no activity row, render one group-level fallback approval so the user cannot be blocked.

- [ ] **Step 5: Run Green and gates**

```powershell
npm run test:chat -- --run tests/chat/turns.test.ts tests/chat/activity.test.tsx
npm run typecheck:chat
git diff --check
```

- [ ] **Step 6: Audit and checkpoint**

Verify `aria-expanded`, keyboard activation, status text independent of color, and no detail duplicating Trace Viewer. Proposed commit:

```text
feat: group tool activity by conversation turn
```

## Task 7: Add Safe Markdown and Shiki Code Rendering

**Task ID:** `structured-chat-rendering-task-7`

**Files:**

- Modify: `package.json`
- Modify: `package-lock.json`
- Create: `web/chat/components/MarkdownMessage.tsx`
- Create: `web/chat/components/CodeBlock.tsx`
- Create: `tests/chat/markdown-message.test.tsx`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-7.md`

- [ ] **Step 1: Request dependency-install authorization**

Explain that this Task will add `react-markdown`, `remark-gfm`, and `shiki`, modifying `package.json`, `package-lock.json`, and local `node_modules`. Do not run installation until the user explicitly approves.

- [ ] **Step 2: Install focused dependencies after approval**

```powershell
npm install react-markdown remark-gfm shiki
```

Record exact installed versions and license checks in evidence. Do not add a full chat framework.

- [ ] **Step 3: Write security, semantics, fallback, and copy tests**

```typescript
it("renders GFM but never renders raw html, images, or unsafe urls", async () => {
  render(
    <MarkdownMessage content={'|a|b|\n|-|-|\n|1|2|\n<img src="x">\n[bad](javascript:alert(1))'} />,
  );
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
  expect(document.querySelector("script")).toBeNull();
  expect(screen.getByText("bad").closest("a")).toBeNull();
});
```

Also test headings, lists, task lists, blockquotes, inline code, fenced language labels, exact copy text, Shiki rejection fallback, unknown language fallback, and code containment.
Force the Markdown renderer itself to throw in one test and require a plain-text
message fallback. Require every external link to have `target="_blank"` and
`rel="noopener noreferrer"`.

- [ ] **Step 4: Run Red**

```powershell
npm run test:chat -- --run tests/chat/markdown-message.test.tsx
```

- [ ] **Step 5: Implement the safe Markdown boundary**

```typescript
const blockedElements = ["img", "iframe", "object", "embed", "video", "audio"];

function safeUrl(url: string): string | undefined {
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.protocol === "http:" || parsed.protocol === "https:"
      ? parsed.href
      : undefined;
  } catch {
    return undefined;
  }
}

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <MarkdownErrorBoundary fallback={<p className="message-plain">{content}</p>}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        disallowedElements={blockedElements}
        urlTransform={(url) => safeUrl(url) ?? ""}
        components={{
          ...markdownComponents,
          a: ({ children, href }) => href ? (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ) : <>{children}</>,
        }}
      >
        {content}
      </ReactMarkdown>
    </MarkdownErrorBoundary>
  );
}
```

Do not use `dangerouslySetInnerHTML`, `rehype-raw`, image renderers, or plugins that fetch network content.

- [ ] **Step 6: Implement lazy token rendering without HTML injection**

Use Shiki's token API and render React spans:

```typescript
const result = await codeToTokens(code, {
  lang: language || "text",
  theme: "github-dark-default",
});

return result.tokens.map((line, lineIndex) => (
  <span className="code-line" key={lineIndex}>
    {line.map((token, tokenIndex) => (
      <span key={tokenIndex} style={{ color: token.color }}>
        {token.content}
      </span>
    ))}
    {"\n"}
  </span>
));
```

Load highlighting asynchronously, cache the result by language/code, and fall back to `<code>{code}</code>` on import or language failure. The copy button must call `navigator.clipboard.writeText(code)` with the original, unmodified text.

- [ ] **Step 7: Run Green and gates**

```powershell
npm run test:chat -- --run tests/chat/markdown-message.test.tsx
npm run typecheck:chat
npm run build:chat
npm audit --omit=dev
git diff --check
```

If `npm audit` reports an issue, record the exact package and severity; do not bypass or silently accept it.

- [ ] **Step 8: Audit and checkpoint**

Inspect the dependency diff for unrelated upgrades and scan for `dangerouslySetInnerHTML` and `rehype-raw`. Proposed commit:

```text
feat: render safe markdown chat messages
```

## Task 8: Integrate the Turn Timeline and Responsive Presentation

**Task ID:** `structured-chat-rendering-task-8`

**Files:**

- Modify: `web/chat/components/MessageTimeline.tsx`
- Delete if unused: `web/chat/components/ActivityCard.tsx`
- Modify: `web/chat/App.tsx`
- Modify: `web/chat/styles.css`
- Modify: `tests/chat/app.test.tsx`
- Modify: `tests/chat/activity.test.tsx`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-8.md`

- [ ] **Step 1: Write integrated timeline tests**

Require Markdown for both roles, correct turn/tool placement, exact Trace URL, sticky composer behavior, jump-to-latest behavior, and narrow-screen containment:

```typescript
expect(screen.getByRole("link", { name: /open trace/i })).toHaveAttribute(
  "href",
  `/viewer?conversation_id=${conversationId}&session_id=${sessionId}`,
);
```

Assert the legacy raw activity stream and JSON payloads are absent from the transcript.
Simulate an Activity API failure and verify messages remain readable while a
conversation-scoped “Retry activity” control refetches only the activity endpoint.

- [ ] **Step 2: Run Red**

```powershell
npm run test:chat -- --run tests/chat/app.test.tsx tests/chat/activity.test.tsx tests/chat/markdown-message.test.tsx
```

- [ ] **Step 3: Render the message-centric timeline**

Build turns once and render:

```tsx
{turns.map((turn) => (
  <article className="conversation-turn" key={turn.run.session_id}>
    <MessageBubble role="user">
      <MarkdownMessage content={turn.userMessage.content} />
    </MessageBubble>
    {turn.activities.length > 0 || approvalForRun(turn.run) !== null ? (
      <ToolActivityGroup
        runStatus={turn.run.status}
        sessionId={turn.run.session_id}
        activities={turn.activities}
        approval={approvalForRun(turn.run)}
      />
    ) : null}
    {turn.assistantMessage ? (
      <MessageBubble role="assistant">
        <MarkdownMessage content={turn.assistantMessage.content} />
      </MessageBubble>
    ) : null}
    <TraceLink
      conversationId={turn.run.conversation_id}
      sessionId={turn.run.session_id}
    />
  </article>
))}
```

Delete `ActivityCard.tsx` only after `rg "ActivityCard" web tests` proves it has no callers.

- [ ] **Step 4: Add restrained responsive styling**

Keep the existing full-height shell and sticky composer. Add these containment rules:

```css
.message-markdown,
.tool-activity-group,
.conversation-turn {
  min-width: 0;
  max-width: 100%;
}

.message-markdown pre,
.message-markdown .table-scroll {
  max-width: 100%;
  overflow-x: auto;
}

.message-markdown {
  overflow-wrap: anywhere;
}

@media (max-width: 600px) {
  .conversation-turn {
    padding-inline: 12px;
  }
  .tool-activity-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}
```

Wrap tables in a contained scroller through the Markdown component map. Do not add page-level horizontal scrolling.

- [ ] **Step 5: Run Green and gates**

```powershell
npm run test:chat -- --run tests/chat/app.test.tsx tests/chat/activity.test.tsx tests/chat/markdown-message.test.tsx tests/chat/turns.test.ts
npm run typecheck:chat
npm run build:chat
git diff --check
```

- [ ] **Step 6: Audit and checkpoint**

Inspect the generated static asset diff, verify no source map or unexpected artifact is committed, and record the proposed commit:

```text
feat: integrate structured chat timeline
```

## Task 9: Complete E2E, Documentation, and Phase-Wide Gates

**Task ID:** `structured-chat-rendering-task-9`

**Files:**

- Modify: `tests/e2e/test_chat_ui.py`
- Modify: `README.md`
- Modify: `docs/learning-notes/04-chat-control-plane.md`
- Create/update: `docs/task-evidence/structured-chat-rendering-task-9.md`

- [ ] **Step 1: Write the browser acceptance test before documentation edits**

Extend the fake-provider E2E to verify:

- GFM headings, lists, tables, inline code, and fenced code render semantically;
- code shows a language label and copies exact source;
- active/waiting tool group is expanded;
- completed/failed/interrupted tool group is collapsed after reload;
- a user manual toggle wins until reload;
- approval is nested under the exact `tool_call_id`, with fallback if the row is absent;
- reload recovers SQLite activity without reconstructing JSONL;
- a gap between HTTP snapshot and SSE is closed by the catch-up fetch;
- Chat-to-Trace link contains exact `conversation_id` and `session_id`;
- restart changes unfinished run and activity to `interrupted`;
- viewport `390x844` has `document.documentElement.scrollWidth <= window.innerWidth`;
- fake provider credential is absent from SQLite, JSONL Trace, Chat API JSON, DOM text, and generated frontend assets.

- [ ] **Step 2: Run E2E Red**

```powershell
conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q
```

Expected: new assertions fail until the integrated feature is complete. If Tasks 1-8 already made every assertion pass, record this Task's Red as `not-applicable` for test-only coverage expansion rather than manufacturing a failure.

- [ ] **Step 3: Make only test-harness fixes required by the acceptance test**

Use the existing fake provider and `127.0.0.1` service fixture. Do not change application behavior in this documentation/gate Task; if a product defect appears, stop and create a separately authorized remediation Task.

- [ ] **Step 4: Update user and learning documentation**

Document in `README.md`:

- Chat renders safe GFM and highlighted fenced code;
- tool details are summarized in one collapsible group per run;
- full details stay in Trace Viewer;
- existing historical runs may omit the tool group;
- local services remain bound to `127.0.0.1`.

Document in `04-chat-control-plane.md`:

- JSONL is the full observability record;
- SQLite activity is a redacted, replaceable UI projection;
- projection failure cannot fail the agent run;
- HTTP snapshot + SSE + catch-up closes recovery gaps;
- why `(session_id, tool_call_id)` is the idempotency key;
- why Markdown AST/token rendering is used instead of raw HTML.

- [ ] **Step 5: Run the complete independent gate set**

```powershell
conda run -n agent-foundations python -m pytest -q
conda run -n agent-foundations python -m ruff check .
conda run -n agent-foundations python -m mypy src tests
conda run -n agent-foundations python -m pip check
npm run test:viewer
npm run typecheck:viewer
npm run test:chat
npm run typecheck:chat
npm run build:chat
conda run -n agent-foundations python -m pytest tests/e2e/test_chat_ui.py -q
git diff --check
git status --short
```

Report exact pass counts. Note that the final E2E command is a focused rerun and must not be double-counted if it was already included in the full pytest count.

- [ ] **Step 6: Perform the final security and scope audit**

Without opening `.env`, scan tracked/source/generated artifacts and the test database/trace fixtures for the fake sentinel credential. Confirm:

- no real provider credential in SQLite, Trace, Chat JSON, DOM, or static assets;
- no raw file content, match text, raw tool arguments/result, or external absolute path in activity rows;
- no `dangerouslySetInnerHTML`, `rehype-raw`, image rendering, or network-fetching Markdown plugin;
- no write, Shell, Git, network, permanent approval, memory, skill, planning, or sub-agent capability was added;
- only intended files differ, and all pre-existing user changes remain untouched.

- [ ] **Step 7: Record final evidence and checkpoint**

Record current correctness, TDD evidence completeness per Task, exact gate counts, manual items still required, and the proposed commit:

```text
feat: complete structured chat rendering
```

Do not claim user acceptance until the user performs the real-model/manual checks separately.

## Manual Acceptance Handoff

After all automated Tasks pass, provide steps for the user to start the local Chat and Trace Viewer on `127.0.0.1`, then manually verify with the configured real provider:

1. Markdown prose, table, list, inline code, and fenced Python code render correctly.
2. A tool-using run shows one expanded activity group while active and a collapsed group when terminal.
3. Approval appears under the exact tool row; approve and deny each once.
4. Reload preserves messages and redacted activity; an unfinished run becomes interrupted after service restart.
5. “Open Trace” selects the exact conversation and turn in Trace Viewer.
6. At `390x844`, the transcript and code block scroll internally with no page-level horizontal overflow.
7. Inspect SQLite, Trace, Chat API JSON, and browser-visible data using a fake sentinel first; real credential values must never be copied into the report.

The real-model smoke test is user-authorized manual acceptance only. It is not part of automated execution and must never be run implicitly.
