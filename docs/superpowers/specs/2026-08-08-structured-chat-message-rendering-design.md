# Structured Chat Message Rendering Design

## Status

Confirmed by the user on 2026-08-08.

## Goal

Replace the Chat UI's current plain-text message presentation with a safe,
message-first rendering layer that supports Markdown, readable code blocks, and
compact structured tool activity without moving full Trace content into Chat.

The target is a lightweight Codex-style experience:

- user and assistant messages render safe Markdown;
- code blocks are readable, copyable, and horizontally contained;
- each run has one compact tool activity group;
- tool summaries survive browser refresh and service restart;
- approvals remain interactive and exact-path scoped;
- the full event record remains in Trace Viewer.

## Current State

`MessageTimeline` renders every message as a plain React text child inside a
`<p>` element. CSS preserves whitespace, but no Markdown parser or structured
message renderer is present. As a result, headings, emphasis, tables, lists,
and fenced code blocks appear as literal punctuation.

The project already provides most of the run identity and control-plane data
needed by the new renderer:

- `ChatMessage` persists user and assistant text;
- `RunRecord` connects a user message, a session, and an assistant message;
- `ChatEvent` distinguishes tool, approval, model, and run lifecycle events;
- `TraceToChatProjector` already redacts, allowlists, and truncates event data;
- `ApprovalCard` and exact `conversation_id + session_id` Trace links exist;
- the frontend reducer already receives live activity events over SSE.

The missing boundary is a durable, typed Chat projection for tool activity.
The current `ChatEventBroker` is memory-only, so tool activity disappears after
refresh or restart.

## Confirmed Decisions

1. Implement the feature incrementally in the existing React and Python
   architecture. Do not replace the Chat runtime with `assistant-ui` or another
   end-to-end framework.
2. Persist only redacted, bounded Chat activity summaries in SQLite.
3. Keep complete Trace events in JSONL and detailed inspection in Trace Viewer.
4. Render one tool activity group per run/session.
5. Automatically expand the group while the run is active or waiting for
   approval, then collapse it when the run reaches a terminal state.
6. Respect a user's manual expand/collapse choice for the remainder of the
   current page lifecycle. After refresh, completed groups default to collapsed.
7. Do not reconstruct missing historical activity rows from JSONL.
8. Do not render remote images, raw HTML, executable content, full tool payloads,
   model reasoning, or full Trace data in Chat.

## Architecture

The existing raw event and the new Chat projection have separate purposes:

```text
TraceEvent
  |-- JSONL Trace sink
  |     `-- complete redacted observability record
  |
  `-- Chat activity projector
        |-- strict field allowlist
        |-- Redactor
        |-- bounded display summaries
        `-- SQLite chat_tool_activities
              |-- HTTP recovery snapshot
              `-- persist-before-publish SSE update
```

JSONL remains the observability source. SQLite becomes the source of truth only
for the smaller, safe Chat presentation model. A failure in Chat projection must
not corrupt JSONL, prevent the assistant message from being stored, or turn a
successful Agent run into a failed run.

## Backend Domain Model

Add a typed `ChatToolActivity` model with these fields:

```text
conversation_id
session_id
tool_call_id
tool_name
status: running | completed | failed | interrupted
arguments_summary: string | null
result_summary: string | null
started_at
finished_at: string | null
last_event_id
```

The public model contains only display-safe data. It does not expose the raw
Trace payload.

`TraceToChatProjector` must preserve the source `TraceEvent.event_id` and include
the source `tool_call_id` in the internal projected event. These identifiers are
required for deterministic deduplication and request/completion pairing; they
are not a reason to expose raw tool arguments.

## SQLite Projection

Add a `chat_tool_activities` table with a composite primary or unique key on:

```text
(session_id, tool_call_id)
```

Each row belongs to an existing run and conversation. Repository operations
must execute in transactions and provide:

- upsert a requested tool call as `running`;
- merge a completion into the same row as `completed`;
- merge a failure into the same row as `failed`;
- mark remaining `running` activities as `interrupted` when startup recovery
  interrupts their owning run;
- list all activities for a conversation in deterministic run and start order;
- tolerate duplicate delivery of the same source event;
- prevent a terminal activity from reverting to `running` because of a stale or
  out-of-order event.

The repository may accept a completion event that arrives without a locally
observed request, but it must still apply the same redaction and field allowlist.
Unknown or missing display fields remain null rather than falling back to raw
JSON.

The schema addition must be backward-compatible with an existing local Chat
database. It creates a new table without rewriting messages, runs, approvals,
or existing conversation identifiers.

Startup recovery must update interrupted runs and their still-running activity
rows consistently. This update belongs in the same recovery transaction so the
HTTP state cannot expose an interrupted run with a tool that still claims to be
running.

## Projection and Publication Order

For each supported tool Trace event:

1. redact the payload and status with the existing `Redactor`;
2. select only explicitly allowed display fields;
3. convert project-internal paths to project-relative display values where the
   event contract allows it;
4. truncate each summary to the configured display limit;
5. persist or merge the activity row in SQLite;
6. publish the safe projected event over SSE.

Persistence must precede SSE publication. Live delivery is an acceleration path;
SQLite remains the recovery path.

Project-external canonical paths continue to be shown only by the existing
approval model where the user must make an exact-path decision. General activity
summaries must not duplicate external absolute paths.

## HTTP API and Recovery

Add this read-only endpoint:

```http
GET /api/chat/conversations/{conversation_id}/activities
```

It returns a JSON array of `ChatToolActivity` records. The endpoint follows the
existing Chat API behavior for malformed identifiers, valid-but-missing
conversations, stable response shapes, and credential-safe errors.

Conversation recovery loads these resources together:

- conversation;
- messages;
- runs;
- activities;
- conversation state;
- conversation list.

The client then establishes SSE and performs one activity catch-up request. This
snapshot-subscribe-catch-up sequence closes the gap in which an event could be
persisted after the initial HTTP snapshot but before the SSE listener becomes
active. Client merges use `(session_id, tool_call_id)` and never append blindly.

SSE reconnect continues to use HTTP recovery before reconnecting. Terminal run
events also trigger a final activity refresh so the completed tool group matches
SQLite even if a live event was missed.

## Conversation Turn Projection

Add a pure frontend projection such as `buildConversationTurns()` that combines:

```text
user ChatMessage
  -> RunRecord / session_id
  -> ChatToolActivity[]
  -> assistant ChatMessage, when present
  -> exact Trace link
```

The projection returns typed view models and does not perform HTTP requests,
mutate reducer state, or touch the DOM. It must support queued, active,
waiting-approval, completed, failed, and interrupted runs.

Historical behavior is explicit:

- all old and new message strings receive safe Markdown rendering;
- an old run with no `chat_tool_activities` rows renders no synthetic activity
  group;
- the run's exact Trace link remains available;
- Chat does not parse historical JSONL to manufacture missing summaries.

## Frontend Component Structure

Each run renders through this hierarchy:

```text
ConversationTurn
|-- UserMessage
|-- ToolActivityGroup
|     |-- ToolActivityRow
|     `-- ApprovalCard, when required
|-- AssistantMessage, when present
`-- TraceLink
```

### MarkdownRenderer

Use `react-markdown` with `remark-gfm` and an explicit component map. Both user
and assistant text use the same safe parser. The renderer supports:

- paragraphs and bounded heading styles;
- emphasis and block quotes;
- ordered and unordered lists;
- GFM tables inside a horizontal overflow wrapper;
- inline code;
- fenced code blocks;
- user-initiated safe links.

Raw HTML is not parsed. The implementation must not use
`dangerouslySetInnerHTML`. A rendering error falls back to plain text for the
affected message rather than breaking the whole conversation.

### CodeBlock

Fenced code blocks show a language label, copy button, syntax highlighting, and
contained horizontal overflow. Shiki loads lazily and may cache a highlighter;
unsupported languages or highlighter failures fall back to a normal
`<pre><code>` block.

The first version does not include Monaco Editor, execution, download, editable
diffs, forced line numbers, or automatic language-driven actions.

### ToolActivityGroup

The group appears between the user message and assistant message. Its default
behavior is:

- active or waiting approval: expanded;
- completed, failed, or interrupted: collapsed;
- manual user toggle: authoritative until page reload;
- completed group after reload: collapsed.

A collapsed group uses a compact title such as:

```text
Explored project | 3 actions | completed
```

Expanded rows show only a status icon, tool name, safe short argument summary,
and safe short result summary. Known read-only filesystem tools may receive
specific labels; unknown tools use a generic label and never expose raw JSON.

An active `ApprovalCard` is visually nested under the corresponding tool row.
The existing approval API, exact-path scope, one-time lifecycle, and deny path do
not change.

## Markdown and Browser Security

The renderer uses a fixed allowlist and must enforce all of these rules:

- no raw HTML, scripts, iframes, styles, forms, or event attributes;
- no `javascript:`, `data:`, `file:`, `vscode:`, or equivalent unsafe URLs;
- no rendered images in this phase, including remote and data-URI images;
- no automatic network fetch caused by model output;
- external links are user initiated and use `noopener noreferrer`;
- code blocks can be displayed and copied but never executed;
- the model and provider cannot choose Markdown or rehype plugins dynamically.

## Credential and Data-Minimization Rules

Provider credentials must not enter:

- `chat_tool_activities`;
- Chat HTTP responses;
- SSE payloads;
- frontend reducer state;
- rendered DOM;
- frontend test snapshots.

The Chat projection stores neither full tool arguments nor full tool results.
It reuses the existing Redactor, applies an independent output field allowlist,
and enforces per-field length limits. Missing data is omitted rather than
replaced by a less-safe source.

## Error Handling

- Markdown parse failure: render plain text.
- Shiki load or language failure: render plain code.
- unknown tool: render a generic safe row.
- duplicate event: idempotent merge.
- stale running event after terminal event: ignore the status regression.
- Activity API failure: keep messages usable and show a non-blocking retry state.
- SSE disconnect: restore from HTTP, reconnect, and catch up from SQLite.
- missing historical activity: omit the group and retain the Trace link.
- Chat projection failure: preserve Runtime, JSONL Trace, and assistant-message
  completion behavior; expose a diagnosable non-secret failure path.

## Automated Verification

### Backend unit and repository tests

- schema creation against a new and existing database;
- requested/completed/failed merge behavior;
- startup interruption of active tool rows in the same recovery transaction as
  their run;
- deterministic ordering;
- duplicate and out-of-order events;
- restart persistence;
- Redactor use, field allowlist, path minimization, and truncation;
- projection failure isolation from Runtime and JSONL.

### API integration tests

- exact success response shape;
- malformed conversation ID;
- valid-but-missing conversation ID;
- activity recovery after restart;
- snapshot-SSE-catch-up deduplication;
- provider credentials absent from SQLite, HTTP, and SSE.

### Frontend component and state tests

- headings, lists, tables, quotes, inline code, and fenced code;
- raw HTML is inert and unsafe URL schemes are blocked;
- images do not render;
- Shiki and Markdown failure fallbacks;
- copy button behavior;
- run-to-turn and session-to-activity grouping;
- active expansion and terminal collapse;
- manual toggle precedence;
- approval placement under its tool;
- HTTP recovery and event deduplication.

### Browser E2E

- multiple read-only tool calls form one group;
- refresh and service restart preserve safe activity summaries;
- completed groups collapse automatically;
- Chat opens the exact turn in Trace Viewer;
- approval flows remain exact, one-time, and non-bypassable;
- 390 x 844 has no page-level horizontal overflow;
- long tables and code scroll only inside their content containers;
- automatic follow-latest behavior remains correct;
- fake providers only; no real model or paid API call.

The normal Python, Viewer, Chat, TypeScript, build, dependency, and diff quality
gates remain required.

## Non-goals

- Full Trace rendering inside Chat.
- Raw model reasoning or hidden chain-of-thought presentation.
- File writing, Shell, Git, network tools, or broader approvals.
- Monaco Editor, executable code blocks, editable diffs, file preview, image
  rendering, Mermaid, math, citations, attachments, voice, or multimodal input.
- Replacing the existing Chat runtime with a third-party chat framework.
- Backfilling historical tool summaries from JSONL.
- Changing conversation, session, or exact Trace navigation identity.

## Third-party References and Independent Choices

| Project | License | Use in this design |
| --- | --- | --- |
| [OpenAI Codex](https://github.com/openai/codex) | Apache-2.0 | Reference for separating protocol types from presentation; no TUI code is copied. |
| [react-markdown](https://github.com/remarkjs/react-markdown) | MIT | Candidate focused dependency for safe Markdown-to-React rendering. |
| [remark-gfm](https://github.com/remarkjs/remark-gfm) | MIT | Candidate focused dependency for tables and other GFM syntax. |
| [Shiki](https://github.com/shikijs/shiki) | MIT | Candidate focused dependency for code highlighting with a plain-code fallback. |
| [assistant-ui](https://github.com/assistant-ui/assistant-ui) | MIT | Reference for typed message parts, grouped tools, and approvals; not adopted as the runtime. |
| [Vercel AI Elements](https://github.com/vercel/ai-elements) | Apache-2.0 | Reference for composable AI UI components; not adopted wholesale. |

Cursor is a visual and interaction reference only. Its product-specific Agent UI
is not treated as an available implementation source. The project continues to
implement its own Chat projection, security boundary, lifecycle, and tests.

## Rollback

Before release, rollback consists of removing the new renderer, projection API,
activity table initialization, and focused dependencies while restoring the
plain-text `MessageTimeline`. Existing messages, runs, approvals, JSONL Trace,
and conversation identifiers remain unchanged.

After release, leaving the additive `chat_tool_activities` table unused is safer
than deleting user data. A UI rollback can ignore the table without migrating or
rewriting existing conversations.
