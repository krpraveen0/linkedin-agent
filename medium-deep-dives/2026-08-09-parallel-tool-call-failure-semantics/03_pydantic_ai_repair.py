"""Experiment 3 — Pydantic AI: cancel a run while a parallel tool batch is in
flight, then send the resulting history back to the model and see what the
provider would actually receive.

Uses FunctionModel, so it needs no API key and no network.

Run:  python 03_pydantic_ai_repair.py
"""

import asyncio
from importlib.metadata import version

from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

SENT_TO_MODEL: list[list[ModelMessage]] = []


def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Turn 1 asks for two tools at once; later turns just answer."""
    SENT_TO_MODEL.append(messages)
    calls = sum(
        1 for m in messages if isinstance(m, ModelResponse)
        for p in m.parts if isinstance(p, ToolCallPart)
    )
    if calls == 0:
        return ModelResponse(parts=[
            ToolCallPart(tool_name="lookup_user", args={"user_id": "u_1"}, tool_call_id="call_a"),
            ToolCallPart(tool_name="charge_card", args={"amount": "99"}, tool_call_id="call_b"),
        ])
    return ModelResponse(parts=[TextPart(content="done")])


agent = Agent(FunctionModel(script))


@agent.tool_plain
async def lookup_user(user_id: str) -> str:
    """Look up a user by id."""
    await asyncio.sleep(0.02)
    return f"user {user_id}: ok"


@agent.tool_plain
async def charge_card(amount: str) -> str:
    """Charge a card. Slow enough that the run gets cancelled mid-flight."""
    await asyncio.sleep(5)
    return f"charged {amount}"


def describe(messages: list[ModelMessage], indent: str = "    ") -> list[str]:
    """Print the history and return the ids of tool calls with no result."""
    open_calls: list[str] = []
    answered: set[str] = set()
    for m in messages:
        if isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, ToolCallPart):
                    open_calls.append(p.tool_call_id)
                    print(f"{indent}ToolCallPart   id={p.tool_call_id!r} name={p.tool_name!r}")
                elif isinstance(p, TextPart):
                    print(f"{indent}TextPart       {p.content!r}")
        elif isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, ToolReturnPart):
                    answered.add(p.tool_call_id)
                    synth = "SYNTHESIZED " if (p.metadata or {}).get(
                        "pydantic_ai_synthesized_tool_return") else ""
                    body = str(p.content)
                    body = body if len(body) < 52 else body[:49] + "..."
                    print(f"{indent}ToolReturnPart id={p.tool_call_id!r} "
                          f"outcome={p.outcome!r} {synth}{body!r}")
                elif isinstance(p, RetryPromptPart) and p.tool_call_id:
                    answered.add(p.tool_call_id)
                    print(f"{indent}RetryPromptPart id={p.tool_call_id!r}")
    return [c for c in open_calls if c not in answered]


async def main() -> None:
    print(f"pydantic-ai-slim=={version('pydantic-ai-slim')}\n")

    print("--- run 1: cancelled while charge_card is still running ---")
    captured: list[ModelMessage] = []
    with capture_run_messages() as messages:
        task = asyncio.create_task(agent.run("charge the card and look up the user"))
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            print("  run cancelled")
        captured = list(messages)

    orphans = describe(captured)
    print(f"  dangling tool calls in the captured history: {orphans or 'none'}")
    print(f"  -> provider would have {'REJECTED' if orphans else 'accepted'} this history\n")

    print("--- run 2: same history handed back to the agent ---")
    SENT_TO_MODEL.clear()
    result = await agent.run("what happened?", message_history=captured)
    print(f"  run completed: {result.output!r}")
    print("  what the model actually received on its first call of run 2:")
    sent = describe(SENT_TO_MODEL[0], indent="      ")
    print(f"  dangling tool calls in what was sent: {sent or 'none'}")
    print(f"  -> provider would have {'REJECTED' if sent else 'accepted'} this history")


if __name__ == "__main__":
    asyncio.run(main())
