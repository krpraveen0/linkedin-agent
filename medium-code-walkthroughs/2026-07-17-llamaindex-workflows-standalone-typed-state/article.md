# LlamaIndex Workflows Is Now a Standalone Package. Its Typed State Is What Makes That Matter.

If you learned to build LlamaIndex agents by writing `from llama_index.core.workflow import Workflow`, that import is now a compatibility shim. The orchestration engine underneath it has moved out on its own. As of the [Workflows 1.0 announcement](https://www.llamaindex.ai/blog/announcing-workflows-1-0-a-lightweight-framework-for-agentic-systems), the code that routes events between your agent's steps lives in a separate package — `pip install llama-index-workflows` — that imports as plain `workflows` and does not depend on `llama_index` at all.

That sounds like packaging trivia. It isn't. When I installed the package and inspected what actually came down the wire, the interesting part wasn't the new import path. It was that the run state your steps read and write is now a typed Pydantic model you can freeze to JSON mid-run and rebuild later. That single property is what turns an event loop into something you can pause for human review, checkpoint before a risky step, or recover after a crash.

This walkthrough installs the real package, verifies the split against the installed code rather than the blog copy, and runs a small event-driven workflow — with zero LLM calls — to show what typed, serializable state buys you.

## First, the version gotcha nobody mentions

The blog calls it "Workflows 1.0." The package does not agree.

```
$ pip install llama-index-workflows
$ python -c "import importlib.metadata as m; print(m.version('llama-index-workflows'))"
2.22.2
```

I tested version **2.22.2**, published to [PyPI on June 30, 2026](https://pypi.org/project/llama-index-workflows/). The package's history runs back to `0.1.0` on June 10, 2025, so the "1.0" in the announcement is a *framework* milestone — Workflows graduating to a standalone project with its own repo and release cadence — not the version string you get from `pip`. If you pin a dependency expecting `llama-index-workflows==1.*`, you will pin nothing that exists. Pin what the resolver actually installs.

The split itself is easy to confirm. In a fresh virtualenv with only `llama-index-workflows` installed:

```python
from workflows import Workflow, step, Context
from workflows.events import StartEvent, StopEvent, Event

try:
    import llama_index.core.workflow          # the old home
    print("llama_index.core.workflow present")
except ModuleNotFoundError:
    print("llama_index.core NOT installed - workflows stands alone")
```

Running that prints `llama_index.core NOT installed - workflows stands alone`. The engine no longer drags the rest of LlamaIndex in behind it. Existing code keeps working because `llama_index` re-exports the new library through the old paths, per the [announcement](https://www.llamaindex.ai/blog/announcing-workflows-1-0-a-lightweight-framework-for-agentic-systems), but a greenfield project can now adopt the orchestration layer alone.

## What a workflow is, mechanically

A workflow is a set of `@step`-decorated async methods. Each step accepts one event type and returns another. The engine wires steps together by matching the return type of one step to the parameter type of another — there is no explicit graph you hand-build. `StartEvent` kicks a run off, `StopEvent` ends it, and a shared `Context` object carries state between steps. That much has been true for a while.

The 2026 headline is [typed state](https://developers.llamaindex.ai/python/workflows-api-reference/context/). I checked how it is implemented rather than trusting the phrase. In the installed package, `Context` is generic:

```python
from workflows import Context
print(Context.__parameters__)   # (~MODEL_T,)
```

`Context[MODEL_T]` is parameterized by *your* state model, and the store hanging off it is typed to match. `Context.store.get_state()` returns your model, and `Context.store.edit_state()` is an async context manager that yields the model for mutation. So the state your steps touch is a real Pydantic object with fields and validation, not a bag of untyped keys you hope you spelled right.

## A workflow that branches, loops, and streams — no model required

Here is a deterministic triage workflow. It stands in a length-based score for a model call so the whole thing runs offline, but it exercises the parts that matter: typed state, event branching, a bounded retry loop, and live event streaming.

```python
import asyncio
from pydantic import BaseModel, Field
from workflows import Workflow, step, Context
from workflows.events import StartEvent, StopEvent, Event

class TriageState(BaseModel):
    attempts: int = 0
    decisions: list[str] = Field(default_factory=list)

class ScoredEvent(Event):
    text: str
    score: float

class RetryEvent(Event):
    text: str

class ProgressEvent(Event):        # streamed to the caller, not consumed by a step
    note: str

class TriageWorkflow(Workflow):
    @step
    async def score(self, ev: StartEvent, ctx: Context[TriageState]) -> ScoredEvent | RetryEvent:
        async with ctx.store.edit_state() as state:
            state.attempts += 1
            attempt = state.attempts
        ctx.write_event_to_stream(ProgressEvent(note=f"scoring attempt #{attempt}"))
        if attempt < 2:                      # first pass "fails" to show the loop
            return RetryEvent(text=ev.text)
        return ScoredEvent(text=ev.text, score=float(len(ev.text)))

    @step
    async def retry(self, ev: RetryEvent, ctx: Context[TriageState]) -> StartEvent:
        ctx.write_event_to_stream(ProgressEvent(note="transient miss -> looping back"))
        return StartEvent(text=ev.text)

    @step
    async def route(self, ev: ScoredEvent, ctx: Context[TriageState]) -> StopEvent:
        verdict = "escalate" if ev.score > 20 else "auto-approve"
        async with ctx.store.edit_state() as state:
            state.decisions.append(verdict)
        return StopEvent(result=verdict)
```

Three things worth pointing at. The `score` step returns a union — `ScoredEvent | RetryEvent` — and the engine dispatches to whichever step consumes the returned type; that union *is* the branch. The `retry` step returns a `StartEvent`, feeding the run back to the top: that is the loop, expressed as an ordinary return, with the `attempts` counter in typed state stopping it from running forever. And `write_event_to_stream` emits a `ProgressEvent` that no step consumes — it goes straight to whoever is watching the run.

The driver streams those progress events as they happen, then awaits the final result and reads state back:

```python
async def main():
    wf = TriageWorkflow(timeout=10)
    handler = wf.run(start_event=StartEvent(text="please review this flagged comment"))
    async for ev in handler.stream_events():
        if isinstance(ev, ProgressEvent):
            print(f"[stream] {ev.note}")
    result = await handler
    print("final verdict:", result)
    state = await handler.ctx.store.get_state()
    print("state.attempts:", state.attempts)
    print("state.decisions:", state.decisions)
```

## Try It Yourself

Two files, no API keys, no GPU. Create a virtualenv, `pip install llama-index-workflows pydantic`, save the workflow above as `triage.py` with the `main()` driver, and run it:

```
$ python triage.py
[stream] scoring attempt #1
[stream] transient miss -> looping back
[stream] scoring attempt #2
final verdict: escalate
state.attempts: 2
state.decisions: ['escalate']
```

The stream shows the loop happening in real time: attempt #1 misses, the workflow routes back through `retry`, attempt #2 scores, and the router escalates because the comment is longer than 20 characters. `attempts` reached 2 and one decision was recorded — read straight out of the typed `TriageState`, not reconstructed by hand.

Now the part that justifies the whole packaging change. `Context` serializes to a plain dict, and you can rebuild a fresh `Context` from it without rerunning a single step:

```python
import asyncio, json
from workflows import Context
from workflows.events import StartEvent
from triage import TriageWorkflow, TriageState

async def main():
    handler = TriageWorkflow(timeout=10).run(
        start_event=StartEvent(text="please review this flagged comment"))
    await handler

    frozen = handler.ctx.to_dict()                 # -> plain dict
    blob = json.dumps(frozen)
    print("frozen JSON size (bytes):", len(blob))

    restored = Context.from_dict(TriageWorkflow(), json.loads(blob))
    state: TriageState = await restored.store.get_state()
    print("restored attempts:", state.attempts)
    print("restored decisions:", state.decisions)

asyncio.run(main())
```

Running it:

```
$ python resume.py
frozen JSON size (bytes): 737
restored attempts: 2
restored decisions: ['escalate']
```

The entire run state fit in 737 bytes of JSON, and the restored `Context` handed back a `TriageState` with `attempts=2` and the same decision list. That round trip — `to_dict` to storage, `from_dict` back — is the primitive under human-in-the-loop pauses (freeze while a person reviews, thaw when they answer) and crash recovery (persist after each step, resume from the last good snapshot). Because the state is a typed model, what you reload is validated on the way back in, not a dict you cross your fingers over.

## Where this fits, and where it doesn't

Workflows stayed deliberately small. It is control flow and state — event routing, typed context, streaming, serialization — and nothing about models, retrieval, or prompts. That is the point of the split: you can drop the orchestration engine into a codebase that has never heard of LlamaIndex, wire your own model calls into the steps, and add [optional observability](https://www.llamaindex.ai/blog/announcing-workflows-1-0-a-lightweight-framework-for-agentic-systems) through `llama-index-instrumentation` (OpenTelemetry, Arize Phoenix) only if you want it. There is a TypeScript sibling, `@llamaindex/workflow-core`, for the same model on the Node side.

If you want a batteries-included agent with prebuilt tool-calling and RAG, this package alone is not that; you would reach for the wider LlamaIndex stack or a higher-level agent class. But if what you actually need is a durable, inspectable state machine for an agent you control, the standalone package is a smaller dependency than it used to be, and the typed state is the reason to care.

## Key Takeaways

- **The engine moved.** `pip install llama-index-workflows`, then `from workflows import Workflow, step, Context`. It no longer pulls in `llama_index` — I confirmed `llama_index.core` is absent in a clean install.
- **"1.0" is the framework, not the version.** The package I tested reports **2.22.2** (PyPI, June 30, 2026), carrying a semver line that predates the standalone milestone. Pin what `pip` installs.
- **State is a typed Pydantic model.** `Context[YourState]` with `store.get_state()` / `edit_state()` gives you validated fields instead of loose keys — verified against the installed generic `Context`.
- **Branching and loops are just return types.** A `ScoredEvent | RetryEvent` union is a branch; returning a `StartEvent` is a loop. A counter in typed state bounds it.
- **Runs are serializable.** `Context.to_dict()` / `from_dict()` froze a full run to 737 bytes of JSON and restored the typed state without rerunning — the basis for human-in-the-loop and recovery.

*Sources:* [Announcing Workflows 1.0 — LlamaIndex blog](https://www.llamaindex.ai/blog/announcing-workflows-1-0-a-lightweight-framework-for-agentic-systems); [llama-index-workflows on PyPI (v2.22.2, June 30, 2026)](https://pypi.org/project/llama-index-workflows/); [Context API reference — LlamaIndex docs](https://developers.llamaindex.ai/python/workflows-api-reference/context/); [run-llama/llama-agents — packages/llama-index-workflows](https://github.com/run-llama/llama-agents/tree/main/packages/llama-index-workflows). All code was run against `llama-index-workflows==2.22.2` on Python 3.11.
