"""Experiment 2 — OpenAI Agents SDK: the same failing parallel batch, under the
SDK's default tool-error handling and with that handling switched off.

Uses a scripted fake model, so it needs no API key and no network.

Run:  python 02_openai_agents_isolation.py
"""

import asyncio
from collections.abc import AsyncIterator
from importlib.metadata import version
from typing import Any

from agents import Agent, Model, ModelSettings, ModelTracing, Runner, function_tool
from agents.items import ModelResponse
from agents.usage import Usage
from agents import set_tracing_disabled
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

set_tracing_disabled(True)

COMPLETED: list[str] = []
CURRENT_RUN = "none"


class ScriptedModel(Model):
    """Emits two parallel tool calls on turn 1, then plain text on turn 2."""

    def __init__(self) -> None:
        self.turn = 0
        self.inputs_seen: list[Any] = []

    async def get_response(self, system_instructions, input, model_settings,
                           tools, output_schema, handoffs, tracing, **kwargs) -> ModelResponse:
        self.turn += 1
        self.inputs_seen.append(input)
        if self.turn == 1:
            output = [
                ResponseFunctionToolCall(
                    type="function_call", name="lookup_user",
                    arguments='{"user_id": "u_1"}', call_id="call_a", id="fc_a"),
                ResponseFunctionToolCall(
                    type="function_call", name="charge_card",
                    arguments='{"amount": "99"}', call_id="call_b", id="fc_b"),
            ]
        else:
            output = [
                ResponseOutputMessage(
                    type="message", id="msg_1", role="assistant", status="completed",
                    content=[ResponseOutputText(type="output_text", text="done", annotations=[])],
                )
            ]
        return ModelResponse(output=output, usage=Usage(), response_id=f"resp_{self.turn}")

    def stream_response(self, *a, **k) -> AsyncIterator[Any]:  # not used here
        raise NotImplementedError


async def _lookup_user(user_id: str) -> str:
    try:
        await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        COMPLETED.append(f"lookup_user({user_id}) CANCELLED during run={CURRENT_RUN!r}")
        raise
    COMPLETED.append(f"lookup_user({user_id}) finished during run={CURRENT_RUN!r}")
    return f"user {user_id}: ok"


async def _charge_card(amount: str) -> str:
    raise ValueError("gateway timeout")


def describe(items: list[dict]) -> None:
    """Print the run's input list and whether a provider would accept it."""
    calls, answered = {}, set()
    for it in items:
        if it.get("type") == "function_call":
            calls[it["call_id"]] = it["name"]
        elif it.get("type") == "function_call_output":
            answered.add(it["call_id"])
    print(f"  items in history: {len(items)}")
    for it in items:
        t = it.get("type")
        if t == "function_call":
            print(f"    function_call        call_id={it['call_id']!r} name={it['name']!r}")
        elif t == "function_call_output":
            out = str(it["output"])
            out = out if len(out) < 54 else out[:51] + "..."
            print(f"    function_call_output call_id={it['call_id']!r} output={out!r}")
    orphans = sorted(set(calls) - answered)
    print(f"  orphaned call_ids: {orphans or 'none'}  -> provider would have "
          f"{'REJECTED' if orphans else 'accepted'}")


async def run(label: str, failure_error_function) -> None:
    global CURRENT_RUN
    COMPLETED.clear()
    CURRENT_RUN = label
    kw = {} if failure_error_function == "default" else {
        "failure_error_function": failure_error_function}
    agent = Agent(
        name="billing",
        model=ScriptedModel(),
        model_settings=ModelSettings(),
        tools=[
            function_tool(_lookup_user, name_override="lookup_user", **kw),
            function_tool(_charge_card, name_override="charge_card", **kw),
        ],
    )
    print(f"--- {label} ---")
    try:
        result = await Runner.run(agent, "charge the card and look up the user")
        print(f"  run completed: final_output={result.final_output!r}")
        describe(result.to_input_list())
    except Exception as exc:
        print(f"  run RAISED {type(exc).__name__}: {exc}")
        print("  no RunResult was produced, so the caller has no history object to persist")
    print(f"  at the moment the run returned, completed tool bodies: {COMPLETED or 'none'}")
    CURRENT_RUN = f"after {label!r} returned"
    await asyncio.sleep(0.3)
    print(f"  after draining the event loop:  {COMPLETED or 'none'}")
    print()


async def main() -> None:
    print(f"openai-agents=={version('openai-agents')} openai=={version('openai')}\n")
    await run("default failure_error_function", "default")
    await run("failure_error_function=None", None)


if __name__ == "__main__":
    asyncio.run(main())
