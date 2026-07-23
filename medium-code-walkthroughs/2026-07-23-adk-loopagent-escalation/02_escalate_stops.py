"""ADK 2.5.0: EventActions(escalate=True) is the ONLY per-event signal that
breaks a LoopAgent early. Here the critic escalates on pass 2, so the loop
stops long before max_iterations=10."""
import asyncio
from google.adk.agents import BaseAgent, LoopAgent
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types

class Critic(BaseAgent):
    async def _run_async_impl(self, ctx):
        n = ctx.session.state.get("passes", 0) + 1
        good_enough = n >= 2                       # our quality gate
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta={"passes": n},
                                 escalate=good_enough),
            content=types.Content(role="model", parts=[types.Part(
                text=f"pass {n}: {'APPROVED -> escalate' if good_enough else 'revise'}")]),
        )

async def main():
    loop = LoopAgent(name="reviewer", sub_agents=[Critic(name="critic")],
                     max_iterations=10)
    runner = InMemoryRunner(agent=loop, app_name="demo")
    await runner.session_service.create_session(
        app_name="demo", user_id="u", session_id="s")
    fired = 0
    async for ev in runner.run_async(
            user_id="u", session_id="s",
            new_message=types.Content(role="user", parts=[types.Part(text="go")])):
        if ev.content and ev.content.parts and ev.content.parts[0].text:
            fired += 1
            print(f"[{ev.author}] {ev.content.parts[0].text}")
    print(f"\nCritic turns executed: {fired}  (max_iterations was 10)")

asyncio.run(main())
