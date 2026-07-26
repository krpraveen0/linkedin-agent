# CrewAI's `or_()` Fires Once on the First Branch — code walkthrough

Runnable code for the 2026-07-26 Medium article. Demonstrates, with no LLM or
API key, that CrewAI Flows' `@listen(or_(a, b))` fires **once** on the first
branch to complete (not once per branch), that `and_()` waits for all, and that
a method may not listen for its own completion event.

Verified against **`crewai` 1.15.6** (published to PyPI 2026-07-24).

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install crewai            # installs 1.15.6
export CREWAI_TRACING_ENABLED=false OTEL_SDK_DISABLED=true
```

`OTEL_SDK_DISABLED=true` suppresses CrewAI's telemetry export attempts.
CrewAI still prints its own Rich status panels (one per flow method) to stdout;
the meaningful result is the tail printed by each script, shown below.

## Files

- `triggers.py` — `or_()` vs `and_()` trigger semantics.
- `per_branch.py` — one `@listen` per branch, the fix when you need every branch.
- `selflisten.py` — a method listening for its own name is rejected at `kickoff()`.
- `article.md` — the full article.
- `fig1-racing.svg`, `fig2-fix.svg` — diagrams.

## Run + captured output

All output below was captured on 2026-07-26 from `crewai` 1.15.6. Only the
tail (after CrewAI's Rich status panels) is shown.

### `python triggers.py`

```text
execution order:
  1. fast
  2. slow
  3. on_any<-fast-done
  4. on_all

on_any fired 1 time(s)
on_all fired 1 time(s)
```

`on_any` (the `or_()` listener) fires exactly once, carrying `fast-done` — the
payload of the first branch to finish. It does not fire again for `slow`.
`on_all` (the `and_()` listener) fires once, after both branches complete.
Deterministic across repeated runs.

### `python per_branch.py`

```text
handlers that ran: ['on_fast<-fast-done', 'on_slow<-slow-done']
count: 2
```

Two branches, two separate listeners, two handler runs — each with the right
payload.

### `python selflisten.py`

```text
ValidationError: 1 validation error for LoopFlow
  Value error, methods.tick.listen must not reference itself [type=value_error, ...]
```

A method named `tick` that does `@listen("tick")` is rejected during
`FlowDefinition` validation, before any method runs.

## Why (source references, `crewai` 1.15.6)

- `crewai/flow/runtime/__init__.py` — `_build_racing_groups`: "Events of a
  multi-event `or_()` listener race: only the first to fire should trigger it."
  The `_fired_or_listeners` set records already-fired `or_()` listeners so they
  do not re-fire (cleared/re-armed for cyclic flows driven by a `@router`).
- `crewai/flow/dsl/_conditions.py` — `or_` "fires when any trigger fires";
  `and_` "fires after all triggers fire".
- `crewai/flow/flow_definition.py` — `_validate_trigger_namespace` raises
  `methods.{name}.listen must not reference itself`.
