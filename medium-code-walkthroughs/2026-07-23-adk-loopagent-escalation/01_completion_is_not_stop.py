"""ADK 2.5.0: a sub-agent finishing its turn does NOT stop a LoopAgent.
Only EventActions(escalate=True) or max_iterations ends the loop."""
import asyncio
from google.adk.agents import BaseAgent, LoopAgent
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types

class Worker(BaseAgent):
    """Runs, reports, and simply returns. It never escalates."""
    async def _run_async_impl(self, ctx):
        n = ctx.session.state.get("passes", 0) + 1
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta={"passes": n}),
            content=types.Content(role="model",
                                  parts=[types.Part(text=f"pass {n} done")]),
        )

async def main():
    loop = LoopAgent(name="reviewer", sub_agents=[Worker(name="worker")],
                     max_iterations=3)
    runner = InMemoryRunner(agent=loop, app_name="demo")
    await runner.session_service.create_session(
        app_name="demo", user_id="u", session_id="s")
    fired = 0
    async for ev in runner.run_async(
            user_id="u", session_id="s",
            new_message=types.Content(role="user",
                                      parts=[types.Part(text="go")])):
        if ev.content and ev.content.parts and ev.content.parts[0].text:
            fired += 1
            print(f"[{ev.author}] {ev.content.parts[0].text}")
    print(f"\nWorker turns executed: {fired}  (max_iterations was 3)")

asyncio.run(main())
