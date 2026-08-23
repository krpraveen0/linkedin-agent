"""ADK 2.0 Workflow Runtime: what happens when two parallel nodes write the
same state key. Runs fully offline -- no model, no API key."""
import asyncio
from pydantic import BaseModel
from google.adk.workflow import Workflow, FunctionNode, JoinNode, START
from google.adk.runners import InMemoryRunner
from google.genai import types


class State(BaseModel):
    topic: str = ""
    summary: str = ""          # collision: two branches write this
    sentiment: str = ""        # branch-private key (the fix)
    keywords: str = ""         # branch-private key (the fix)


async def run(workflow: Workflow) -> dict:
    runner = InMemoryRunner(agent=workflow, app_name="demo")
    session = await runner.session_service.create_session(
        app_name="demo", user_id="u", state={"topic": "ai agents"})
    last_output = None
    async for ev in runner.run_async(
        user_id="u", session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="go")])):
        if ev.output is not None:
            last_output = ev.output          # terminal node = JoinNode aggregate
    final = await runner.session_service.get_session(
        app_name="demo", user_id="u", session_id=session.id)
    return {"state": dict(final.state), "joined": last_output}


def shared_key_workflow(delay_sentiment: float, delay_keywords: float) -> Workflow:
    def start(topic: str):
        return {"ok": True}

    async def sentiment(ctx, topic: str):
        await asyncio.sleep(delay_sentiment)
        ctx.state["summary"] = "sentiment=positive"     # same key...

    async def keywords(ctx, topic: str):
        await asyncio.sleep(delay_keywords)
        ctx.state["summary"] = "keywords=[ai,agents]"   # ...as this one

    start_n = FunctionNode(func=start, name="start")
    return Workflow(name="collide", state_schema=State, edges=[
        (START, start_n),
        (start_n, (FunctionNode(func=sentiment, name="sentiment"),
                   FunctionNode(func=keywords, name="keywords"))),
    ])


def join_workflow() -> Workflow:
    def start(topic: str):
        return {"ok": True}

    def sentiment(ctx, topic: str):
        ctx.state["sentiment"] = "positive"             # private key
        return {"sentiment": "positive"}

    def keywords(ctx, topic: str):
        ctx.state["keywords"] = "[ai, agents]"          # private key
        return {"keywords": ["ai", "agents"]}

    start_n = FunctionNode(func=start, name="start")
    sen = FunctionNode(func=sentiment, name="sentiment")
    kw = FunctionNode(func=keywords, name="keywords")
    join = JoinNode(name="join")
    return Workflow(name="fan_in", state_schema=State, edges=[
        (START, start_n), (start_n, (sen, kw)), (sen, join), (kw, join),
    ])


async def main():
    print("A) Two parallel nodes write state['summary'] -- no reducer declared")
    for label, ds, dk in [("equal timing", 0.0, 0.0),
                          ("sentiment finishes last", 0.20, 0.02),
                          ("keywords finishes last", 0.02, 0.20)]:
        out = await run(shared_key_workflow(ds, dk))
        print(f"   {label:24s} -> summary = {out['state']['summary']!r}")
    print("   (no error, no warning -- the last delta committed simply wins)\n")

    print("B) The fix: branch-private keys + a JoinNode that aggregates outputs")
    out = await run(join_workflow())
    print("   final state sentiment:", repr(out["state"]["sentiment"]))
    print("   final state keywords: ", repr(out["state"]["keywords"]))
    print("   JoinNode aggregate:   ", dict(sorted(out["joined"].items())))


if __name__ == "__main__":
    asyncio.run(main())
