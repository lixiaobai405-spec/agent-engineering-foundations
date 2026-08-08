import assert from "node:assert/strict";
import test from "node:test";

import {
  autoScrollBehavior,
  formatUiError,
  nextLiveEvents,
  viewFor,
} from "../../src/agent_foundations/viewer/static/dist/state.js";

function event(sessionId, eventId, payload = {}) {
  return {
    event_id: eventId,
    session_id: sessionId,
    step_id: 1,
    event_type: "model.request.started",
    status: "started",
    timestamp: "2026-08-01T00:00:00Z",
    duration_ms: null,
    summary: "Requesting model",
    payload,
  };
}

test("Model Input exposes the runtime context and tool schemas", () => {
  const context = [{ role: "user", content: "Explain auth" }];
  const tools = [{ name: "read_file" }];

  assert.deepEqual(
    viewFor(event("session-a", "event-1", { context, tools }), "Model Input"),
    { messages: context, tools },
  );
});

test("historical mode ignores incoming live events", () => {
  const history = [event("session-a", "event-1")];

  assert.strictEqual(
    nextLiveEvents(history, event("session-b", "event-2"), "session-a"),
    history,
  );
});

test("live mode starts a new timeline when the session changes", () => {
  const previous = [event("session-a", "event-1")];
  const incoming = event("session-b", "event-2");

  assert.deepEqual(nextLiveEvents(previous, incoming, null), [incoming]);
});

test("live mode appends events from the active session", () => {
  const first = event("session-a", "event-1");
  const second = event("session-a", "event-2");

  assert.deepEqual(nextLiveEvents([first], second, null), [first, second]);
});

test("UI errors include a recovery action", () => {
  assert.equal(
    formatUiError("Load session", new Error("HTTP 422")),
    "Load session failed: HTTP 422. Check the Viewer and try again.",
  );
});

test("auto-scroll disables smooth motion when reduced motion is preferred", () => {
  assert.equal(autoScrollBehavior(true), "auto");
  assert.equal(autoScrollBehavior(false), "smooth");
});
