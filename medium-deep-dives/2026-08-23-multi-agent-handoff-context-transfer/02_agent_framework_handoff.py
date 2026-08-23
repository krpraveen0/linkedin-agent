"""Experiment 2 - Microsoft Agent Framework: HandoffBuilder strips tool traffic.

Same scenario as experiment 1, built with `HandoffBuilder` from
`agent-framework-orchestrations`. Each participant gets a recording fake chat
client, so we can print the exact `messages` list the *refund* agent's client
received - the framework's own output, not a reconstruction.
"""

from __future__ import annotations

import asyncio

from agent_framework import Agent, BaseChatClient, ChatResponse, Content, Message, tool
from agent_framework._middleware import ChatMiddlewareLayer
from agent_framework._tools import FunctionInvocationLayer
from agent_framework.observability import ChatTelemetryLayer
from agent_framework.orchestrations import HandoffBuilder, clean_conversation_for_handoff

from common import ORDER_JSON, USER_REQUEST, preview, release_tokenizer, rule, tokens_of


class RecordingClient(
    FunctionInvocationLayer, ChatMiddlewareLayer, ChatTelemetryLayer, BaseChatClient
):
    """A scripted chat client that records every request it is handed."""

    OTEL_PROVIDER_NAME = "recording-fake"

    def __init__(self, script):
        super().__init__()
        object.__setattr__(self, "_script", list(script))
        object.__setattr__(self, "seen", [])

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        self.seen.append([m for m in messages])
        contents = self._script.pop(0) if self._script else [Content.from_text("done")]
        return ChatResponse(
            messages=[Message(role="assistant", contents=contents)],
            response_id=f"fake-{len(self.seen)}",
        )


@tool
def lookup_order(order_id: str) -> str:
    """Fetch the full order record for an order id."""
    return ORDER_JSON


def describe(msg: Message) -> str:
    kinds = [c.type for c in msg.contents]
    text = " ".join(c.text for c in msg.contents if c.type == "text" and c.text)
    author = f" author={msg.author_name}" if msg.author_name else ""
    return f"role={str(msg.role):<20}{author} contents={kinds} {preview(text, 60)}"


def dump_messages(msgs: list[Message]) -> int:
    for i, m in enumerate(msgs):
        print(f"  [{i}] {describe(m)}")
    payload = [m.to_dict() for m in msgs]
    n = tokens_of(payload)
    print(f"  input tokens (gpt2 bpe): {n}")
    return n


async def main() -> None:
    print(rule("SCENARIO"))
    print(f"user: {USER_REQUEST}")
    print(f"lookup_order returns {tokens_of(ORDER_JSON)} tokens of JSON")
    print()

    triage_client = RecordingClient([
        [Content.from_function_call(
            call_id="c1", name="lookup_order", arguments={"order_id": "A-1183"}
        )],
        [
            Content.from_text("Damaged on delivery, sending to refunds."),
            Content.from_function_call(
                call_id="c2", name="handoff_to_refund", arguments={}
            ),
        ],
    ])
    refund_client = RecordingClient([
        [Content.from_text("Refund of $248.50 approved for order A-1183.")],
    ])

    triage = Agent(
        triage_client, "You triage support requests.", name="triage",
        description="Triage agent", tools=[lookup_order],
        require_per_service_call_history_persistence=True,
    )
    refund = Agent(
        refund_client, "You process refunds.", name="refund",
        description="Refund agent",
        require_per_service_call_history_persistence=True,
    )

    workflow = (
        HandoffBuilder(participants=[triage, refund])
        .with_start_agent(triage)
        .add_handoff(triage, [refund])
        .build()
    )

    await workflow.run(USER_REQUEST)

    print(rule("WHAT THE TRIAGE AGENT'S CLIENT SAW"))
    for i, msgs in enumerate(triage_client.seen):
        print(f"call {i}: {len(msgs)} messages")
        dump_messages(msgs)
        print()

    print(rule("WHAT THE REFUND AGENT'S CLIENT SAW"))
    assert refund_client.seen, "refund agent was never called"
    received = refund_client.seen[0]
    print(f"call 0: {len(received)} messages")
    n_tokens = dump_messages(received)

    flat = str([m.to_dict() for m in received])
    print()
    print(rule("VERDICT"))
    print(f"  order record reachable by refund agent: {'C-90422' in flat}")
    print(f"  any function_call content present:      "
          f"{any(c.type == 'function_call' for m in received for c in m.contents)}")
    print(f"  any function_result content present:    "
          f"{any(c.type == 'function_result' for m in received for c in m.contents)}")
    print(f"  refund agent input tokens:              {n_tokens}")

    # Same helper the executor calls, applied directly, to show it is the cause.
    print()
    print(rule("clean_conversation_for_handoff() APPLIED TO TRIAGE'S OWN VIEW"))
    triage_last = triage_client.seen[-1]
    cleaned = clean_conversation_for_handoff(triage_last)
    print(f"  before: {len(triage_last)} messages, "
          f"{tokens_of([m.to_dict() for m in triage_last])} tokens")
    print(f"  after : {len(cleaned)} messages, "
          f"{tokens_of([m.to_dict() for m in cleaned])} tokens")
    for i, m in enumerate(cleaned):
        print(f"    [{i}] {describe(m)}")

    release_tokenizer()


if __name__ == "__main__":
    asyncio.run(main())
