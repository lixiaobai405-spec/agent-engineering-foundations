# Trace Navigation Scroll Design

## Goal

Make long Conversation and Standalone Trace lists usable without adding a new sidebar-collapse control or changing existing Trace data and APIs.

## Confirmed Interaction

- Keep the current native `<details>/<summary>` interaction.
- Clicking a Conversation heading toggles that Conversation's turns open or closed.
- Clicking `Standalone runs` toggles standalone traces open or closed.
- Do not add a separate arrow, sidebar-collapse button, or persistent collapsed state.
- When expanded navigation content exceeds the available height, the `Trace sessions` navigation region scrolls independently.
- Keep `Event type`, `Auto scroll`, the selected Session summary, and the copy button outside that scrolling region.

## Root Cause

`#trace-navigation` currently uses CSS Grid with a maximum height. Its expanded `.navigation-group` grid item is allowed to shrink, while `.navigation-group` uses `overflow: hidden`. In the reproduced page, the group had `clientHeight=466` and `scrollHeight=823`, but the parent reported equal `clientHeight` and `scrollHeight` of `520`. The overflowing turns were therefore clipped inside the group instead of contributing overflow to the parent scroll container.

## Implementation Design

- Change `#trace-navigation` to a vertical flex or block flow that does not shrink expanded groups.
- Give each `.navigation-group` a non-shrinking size in the navigation flow.
- Keep the navigation region's existing bounded height and apply vertical scrolling there.
- Keep group-level clipping only for rounded-border presentation; it must not become the owner of the long-list scroll.
- Add a stable, narrow, high-contrast scrollbar that fits the existing dark visual style.
- Preserve current responsive layout and avoid horizontal overflow.

No TypeScript behavior or backend response change should be required unless browser testing shows that native toggle behavior regressed.

## Verification

- Add a browser assertion that opening a 10-turn Conversation produces `scrollHeight > clientHeight` on `#trace-navigation`.
- Move the mouse over the navigation region and send a wheel event; assert `scrollTop` increases.
- Confirm clicking the Conversation summary still closes and reopens the turns.
- Confirm `Standalone runs` retains the same native toggle behavior.
- Re-run Viewer build, tests, typecheck, focused Playwright E2E, and `git diff --check`.

## Non-goals

- No new collapse icon or whole-sidebar collapsed mode.
- No backend, SQLite, JSONL, deep-link, Timeline, or Event detail changes.
- No dependency installation, real model calls, commit, or push.

## Rollback

Revert the focused Viewer CSS and browser-test changes. No persisted state or data migration is involved.
