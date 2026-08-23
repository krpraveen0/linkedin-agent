"""Experiment 3 - LangGraph: handoff as a Command over shared state.

LangGraph has no handoff primitive. The documented pattern is a tool that
returns `Command(goto=..., graph=Command.PARENT)`; the destination node reads
the same `messages` channel everyone else writes to.

Four configurations are measured: a Command that writes only the ToolMessage,
one that writes nothing, the pattern the LangChain handoffs documentation
actually prescribes (AIMessage + ToolMessage), and a control in which the
triage node is allowed to finish normally and a static edge does the routing.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langchain_core.tools.base import InjectedToolCallId
from langgraph.prebuilt import InjectedState, create_react_agent
from langgraph.types import Command

from common import ORDER_JSON, USER_REQUEST, preview, release_tokenizer, rule, tokens_of


class RecordingFakeModel(BaseChatModel):
    """A scripted chat model that records the message list it is given."""

    responses: list[AIMessage]
    seen: list[list[BaseMessage]] = []
    label: str = "model"

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        idx = min(len(self.seen) - 1, len(self.responses) - 1)
        return ChatResult(generations=[ChatGeneration(message=self.responses[idx])])

    def bind_tools(self, tools, **kwargs: Any):  # noqa: ANN401
        # The scripted output does not depend on the tool schemas.
        return self


@tool
def lookup_order(order_id: str) -> str:
    """Fetch the full order record for an order id."""
    return ORDER_JSON


def make_handoff_tool(*, mode: str):
    """`mode` selects how the transfer is expressed.

    command_toolmessage_only - Command(goto=..., PARENT) writing just a ToolMessage
    command_no_toolmessage   - same, minus the ToolMessage write
    command_docs_pattern     - the pattern in the LangChain handoffs docs: the
                               ToolMessage *and* the AIMessage that requested it
    plain_tool               - an ordinary tool result; the parent graph routes
                               with a static edge, so the triage node finishes
                               normally instead of being short-circuited
    """

    @tool("transfer_to_refund")
    def transfer_to_refund(
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        """Hand the conversation to the refund agent."""
        if mode == "plain_tool":
            return "Transferred to refund agent."

        transfer_message = ToolMessage(
            content="Transferred to refund agent.",
            name="transfer_to_refund",
            tool_call_id=tool_call_id,
        )
        if mode == "command_no_toolmessage":
            update = {}
        elif mode == "command_docs_pattern":
            last_ai_message = next(
                m for m in reversed(state["messages"]) if isinstance(m, AIMessage)
            )
            update = {"messages": [last_ai_message, transfer_message]}
        else:  # command_toolmessage_only
            update = {"messages": [transfer_message]}
        return Command(goto="refund", update=update, graph=Command.PARENT)

    return transfer_to_refund


def describe(m: BaseMessage) -> str:
    kind = m.__class__.__name__
    extra = ""
    if isinstance(m, AIMessage) and m.tool_calls:
        extra = " tool_calls=" + ",".join(tc["name"] for tc in m.tool_calls)
    if isinstance(m, ToolMessage):
        extra = f" tool_call_id={m.tool_call_id}"
    return f"{kind:<12}{extra} {preview(m.content, 56)}"


def dangling_tool_calls(messages: list[BaseMessage]) -> list[str]:
    """Provider-side validity check: every tool_call needs a matching result."""
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    missing = []
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                if tc["id"] not in answered:
                    missing.append(f"{tc['name']}({tc['id']})")
    return missing


def orphan_tool_messages(messages: list[BaseMessage]) -> list[str]:
    """The mirror-image defect: a tool result with no tool_call that asked for it."""
    requested = {
        tc["id"]
        for m in messages
        if isinstance(m, AIMessage)
        for tc in m.tool_calls
    }
    return [
        m.tool_call_id
        for m in messages
        if isinstance(m, ToolMessage) and m.tool_call_id not in requested
    ]


def build_graph(*, mode: str):
    triage_model = RecordingFakeModel(
        label="triage",
        seen=[],
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "lookup_order",
                    "args": {"order_id": "A-1183"},
                    "id": "call_lookup_1",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "transfer_to_refund",
                    "args": {},
                    "id": "call_handoff_1",
                }],
            ),
            AIMessage(content="Routing to refunds."),
        ],
    )
    refund_model = RecordingFakeModel(
        label="refund",
        seen=[],
        responses=[AIMessage(content="Refund of $248.50 approved for order A-1183.")],
    )

    triage = create_react_agent(
        triage_model,
        tools=[lookup_order, make_handoff_tool(mode=mode)],
        prompt="You triage support requests.",
    )
    refund = create_react_agent(
        refund_model, tools=[], prompt="You process refunds."
    )

    builder = (
        StateGraph(MessagesState)
        .add_node("triage", triage)
        .add_node("refund", refund)
        .add_edge(START, "triage")
        .add_edge("refund", END)
    )
    if mode == "plain_tool":
        # The triage node runs to completion and writes its whole transcript
        # into the shared channel before the static edge fires.
        builder = builder.add_edge("triage", "refund")
    graph = builder.compile()
    return graph, triage_model, refund_model


def run(label: str, *, mode: str) -> None:
    graph, triage_model, refund_model = build_graph(mode=mode)
    result = graph.invoke({"messages": [("user", USER_REQUEST)]})

    print(rule(label))
    final = result["messages"]
    print(f"final shared channel: {len(final)} messages")
    for i, m in enumerate(final):
        print(f"  [{i}] {describe(m)}")

    if refund_model.seen:
        received = refund_model.seen[0]
        payload = [m.model_dump() for m in received]
        print(f"  refund agent's model received {len(received)} messages, "
              f"{tokens_of(payload)} tokens")
        flat = str(payload)
        print(f"  order record reachable by refund agent: {'C-90422' in flat}")
        print(f"  triage's tool calls visible to refund:  "
              f"{'call_lookup_1' in flat}")
    else:
        print("  refund agent was never reached")

    missing = dangling_tool_calls(final)
    orphans = orphan_tool_messages(final)
    print(f"  dangling tool_calls in final transcript: {missing or 'none'}")
    print(f"  orphan ToolMessages in final transcript: {orphans or 'none'}")
    print()


def main() -> None:
    print(rule("SCENARIO"))
    print(f"user: {USER_REQUEST}")
    print(f"lookup_order returns {tokens_of(ORDER_JSON)} tokens of JSON")
    print()
    run("A. Command(PARENT) writing only the ToolMessage",
        mode="command_toolmessage_only")
    run("B. Command(PARENT) writing nothing",
        mode="command_no_toolmessage")
    run("C. Command(PARENT) writing AIMessage + ToolMessage (docs pattern)",
        mode="command_docs_pattern")
    run("D. CONTROL: plain tool result, triage node runs to completion",
        mode="plain_tool")
    release_tokenizer()


if __name__ == "__main__":
    main()
