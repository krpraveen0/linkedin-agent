"""
Event-driven triage workflow on the standalone `workflows` package
(installed via `pip install llama-index-workflows`, imported as `workflows`).

Zero LLM calls: this demonstrates the engine itself -- typed state, event
branching, a bounded retry loop, and live event streaming -- deterministically.
"""
import asyncio
from pydantic import BaseModel, Field
from workflows import Workflow, step, Context
from workflows.events import StartEvent, StopEvent, Event


# ---- Typed workflow state (a real Pydantic model, not a loose dict) ----
class TriageState(BaseModel):
    attempts: int = 0
    decisions: list[str] = Field(default_factory=list)


# ---- Custom events that flow between steps ----
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
        # A deterministic stand-in for a model call: score by text length.
        async with ctx.store.edit_state() as state:
            state.attempts += 1
            attempt = state.attempts
        ctx.write_event_to_stream(ProgressEvent(note=f"scoring attempt #{attempt}"))
        # First attempt "fails" to demonstrate the bounded retry loop.
        if attempt < 2:
            return RetryEvent(text=ev.text)
        return ScoredEvent(text=ev.text, score=float(len(ev.text)))

    @step
    async def retry(self, ev: RetryEvent, ctx: Context[TriageState]) -> StartEvent:
        ctx.write_event_to_stream(ProgressEvent(note="transient miss -> looping back"))
        return StartEvent(text=ev.text)

    @step
    async def route(self, ev: ScoredEvent, ctx: Context[TriageState]) -> StopEvent:
        # Branch on the score; record the decision in typed state.
        verdict = "escalate" if ev.score > 20 else "auto-approve"
        async with ctx.store.edit_state() as state:
            state.decisions.append(verdict)
        return StopEvent(result=verdict)


async def main():
    wf = TriageWorkflow(timeout=10)
    handler = wf.run(start_event=StartEvent(text="please review this flagged comment"))

    # Stream engine events live as the workflow runs.
    async for ev in handler.stream_events():
        if isinstance(ev, ProgressEvent):
            print(f"[stream] {ev.note}")

    result = await handler
    print("final verdict:", result)

    # Typed state survived the whole run and is inspectable + serializable.
    state = await handler.ctx.store.get_state()
    print("state.attempts:", state.attempts)
    print("state.decisions:", state.decisions)


if __name__ == "__main__":
    asyncio.run(main())
