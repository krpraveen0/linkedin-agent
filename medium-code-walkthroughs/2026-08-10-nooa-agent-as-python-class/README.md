# NOOA: the whole agent is one Python class

Companion code for the Medium article *"NVIDIA's NOOA Turns Your Agent Into One
Python Class — and a `...` Method Body Into an LLM Call"* (2026-08-10).

This demo shows NVIDIA's [NOOA](https://github.com/NVIDIA-NeMo/labs-OO-Agents)
programming model with **no API key required**:

- `nooa.print_prompt()` renders exactly what NOOA would send the model (no
  network call), proving the class docstring becomes the system prompt and the
  class body becomes the context.
- `FakeLLMClient` replays a scripted response so the default `CodeActStrategy`
  loop runs fully offline: the "model" writes a Python cell, the runtime
  executes it, and `return_result` returns a typed value.

## Requirements

NOOA requires Python **3.12–3.13** (`>=3.12,<3.14`). It will not install on
3.11.

## Setup and run

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install nooa
python triage_agent.py
```

(`pip install nooa` works too, inside a 3.12/3.13 virtual environment.)

## Exact captured output

Produced by `python triage_agent.py` with `nooa==0.0.8`. Reproduced verbatim;
nothing edited.

```text
nooa version: 0.0.8
default strategy: CodeActStrategy

========== print_prompt(urgent_count) ==========
=== SYSTEM PROMPT  [TicketTriage] ===

<system_prompt expr="self._resolve_system_prompt()">
You are a customer-support triage agent. You are terse and precise.
</system_prompt>

<strategy_prompt>
## Strategy

Jupyter-like Python session. Parameters pre-loaded as locals; state persists across cells. Use `await` directly, `print`/`pprint` to debug, `doc(obj)` to inspect types. You MUST call a tool each turn — **plain-text responses do NOT end the session**. To finish, call `return_result(value)`. Repeated text-only responses will abort the run with an error.

**Your two tools:**
- `execute_python(code)` — run a code cell
- `return_result(value)` — submit your final answer (also callable from inside `execute_python`)

## When to use which tool

Use `return_result(...)` directly for simple answers determinable from the inputs alone (yes/no, one field, a single lookup).

Use `execute_python(...)` for lists/batches, arithmetic, multi-step computation, transforms, or iteration. Always iterate in code — never construct large arrays by hand.

For language tasks (classification, extraction, interpretation), use LLM reasoning — answer directly via `return_result`, or delegate to a `@strategy(PredictStrategy())` standalone function (see below). Don't keyword-match or regex.

## Returning computed results

After computing in code, call `return_result(variable)` **from within** `execute_python()`. This passes the variable directly. Do NOT re-type computed values in a separate `return_result` tool call.

## Helpers

Define helpers at the top of the cell and call them by name. Existing methods on `self` are usable via `await self.method(...)`. Helpers persist as REPL locals across cells in this session.

```python
def normalize(x):
    return x.strip().lower()

cleaned = [normalize(v) for v in values]
```

## Fan-out generation

For per-item LLM work over a list, decorate a standalone async function with `@strategy(PredictStrategy())` and an ellipsis body. `asyncio.gather` runs the calls in parallel.

```python
@strategy(PredictStrategy())
async def detect_language(message: str) -> str:
    """Return the ISO 639-1 language code for {message} (e.g. 'en', 'fr', 'de', 'ja')."""
    ...

codes = await asyncio.gather(*(detect_language(m) for m in messages))
return_result(codes)
```

For iterative sub-tasks that need code execution, use `@strategy(CodeActStrategy())`. The sub-task must be strictly simpler than the current call to avoid infinite recursion.

## Restrictions (will throw)

- `eval`, `exec`, `compile`, `__import__`, `input`, `breakpoint`
- `globals`, `locals`, `vars`, `asyncio.run`, `loop.run_until_complete`
- Attaching callables to the agent: `self.foo = fn`, `setattr(self, 'foo', fn)`, `type(self).foo = fn`
</strategy_prompt>

<execution_context>
## Execution Context

These names are already in scope inside `execute_python()` (state persists across cells) — call them, don't re-import or re-define. Use `doc(name)` to inspect any type or function in detail.

```python
import asyncio
import json
import nooa
from nooa import LLMResponse
from nooa.unifiedllm import FakeLLMClient, ToolCall

class TicketTriage: ...

async def main():
    ...
async def run_hermetic():
    ...
async def show_prompt():
    ...
```
Always available without import: `self`, `print()`, `pprint()`, `doc()`, `return_result()`, plus stdlib `asyncio` and `typing`.
</execution_context>

<self expr="doc(type(self))">
class TicketTriage:
    """You are a customer-support triage agent. You are terse and precise."""

    async def urgent_count(self, tickets: list[dict]) -> int:
        """Count how many tickets have priority == 'high'."""
</self>

=== TASK PROMPT  [TicketTriage.urgent_count] ===

## Task: urgent_count

Count how many tickets have priority == 'high'.

You are executing `urgent_count` — code runs in the Execution Context above. Calling `self.urgent_count(...)` would recurse.

=== PREFILL  [CodeActStrategy] ===

# Inspecting inputs for urgent_count().
print(f"Task: urgent_count()")
print(f"\ntickets ({type(tickets).__name__}):")
pprint(tickets, max_length=25, max_string=2000, max_depth=4)

========== hermetic CodeAct run ==========
RESULT: 2 | type: int
```

## Notes

- The generation method must be `async def`. NOOA's metaclass only rewrites
  coroutine functions into LLM-backed methods; a synchronous `def` with a `...`
  body is left alone and returns `None`.
- `ToolCall.arguments` must be a JSON **string**, not a dict — the strategy
  calls `json.loads()` on it.
- To use a real model instead of `FakeLLMClient`, install a
  [LiteLLM](https://docs.litellm.ai/)-supported provider and construct a client
  via `nooa`'s registry; the `TicketTriage` class does not change.

## Sources

- [NOOA on PyPI (v0.0.8, July 30, 2026)](https://pypi.org/project/nooa/)
- [NVIDIA-NeMo/labs-OO-Agents](https://github.com/NVIDIA-NeMo/labs-OO-Agents)
- [NVIDIA OO Agents paper, arXiv:2607.20709](https://arxiv.org/abs/2607.20709)

*Auto-generated by the daily-medium-article cloud routine.*
