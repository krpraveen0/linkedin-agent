"""
Resume demo: run the workflow, freeze its Context to JSON, then rebuild a
fresh Context from that JSON and read the typed state back. This is the
mechanism behind human-in-the-loop pauses and crash recovery.
"""
import asyncio, json
from workflows import Context
from workflows.events import StartEvent
from triage import TriageWorkflow, TriageState


async def main():
    wf = TriageWorkflow(timeout=10)

    # 1. Run to completion.
    handler = wf.run(start_event=StartEvent(text="please review this flagged comment"))
    await handler

    # 2. Freeze the whole run to a plain dict and serialize to JSON on disk.
    frozen = handler.ctx.to_dict()
    blob = json.dumps(frozen)
    print("frozen JSON size (bytes):", len(blob))

    # 3. Later / elsewhere: rebuild a Context from that JSON, no rerun needed.
    restored = Context.from_dict(TriageWorkflow(), json.loads(blob))
    state: TriageState = await restored.store.get_state()
    print("restored attempts:", state.attempts)
    print("restored decisions:", state.decisions)


if __name__ == "__main__":
    asyncio.run(main())
