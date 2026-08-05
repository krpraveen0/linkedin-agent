"""demo2: a Haystack Agent whose exit condition is never met does NOT crash.

It runs up to `max_agent_steps`, logs a warning, and returns the partial
result. No model, no API key, no network: the chat generator is a stub that
always asks to call a tool, so the default "text" exit is never triggered.

Run:  python demo2_agent_stops_quietly.py
"""
import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from haystack import component
from haystack.dataclasses import ChatMessage, ToolCall
from haystack.tools import Tool
from haystack.components.agents import Agent


@component
class NeverStopsGenerator:
    """A stand-in LLM that always requests a tool call and never returns a
    plain-text reply, so the Agent's default exit condition ('text') never fires."""

    @component.output_types(replies=list[ChatMessage])
    def run(self, messages, tools=None, **kwargs):
        call = ToolCall(tool_name="noop", arguments={}, id="call-1")
        return {"replies": [ChatMessage.from_assistant(tool_calls=[call])]}


def noop() -> str:
    return "ok"


tool = Tool(
    name="noop",
    description="does nothing",
    parameters={"type": "object", "properties": {}},
    function=noop,
)

agent = Agent(chat_generator=NeverStopsGenerator(), tools=[tool], max_agent_steps=5)
agent.warm_up()

result = agent.run(messages=[ChatMessage.from_user("go")])

print("RETURNED NORMALLY (no exception raised)")
print(f"step_count:       {result.get('step_count')}")
print(f"messages collected: {len(result.get('messages', []))}")
print(f"tool_call_counts: {result.get('tool_call_counts')}")
