"""Experiment 1 — LangGraph ToolNode: what happens to the sibling tool call
when one tool in a parallel batch raises, and what ends up persisted.

Run:  python 01_langgraph_toolnode.py
"""

import asyncio
from importlib.metadata import version

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

# Observable side effect: proves whether a tool body actually ran, independently
# of whether its result survived into the message history. Each entry is tagged
# with the run that was active when the tool body finished, so a tool that
# outlives the graph invocation that started it is visible as such.
COMPLETED: list[str] = []
CURRENT_RUN = "none"


@tool
async def lookup_user(user_id: str) -> str:
    """Look up a user by id."""
    await asyncio.sleep(0.05)
    COMPLETED.append(f"lookup_user({user_id}) finished during run={CURRENT_RUN!r}")
    return f"user {user_id}: ok"


@tool
async def charge_card(amount: str) -> str:
    """Charge a card."""
    raise ValueError("gateway timeout")


def seed() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "lookup_user", "args": {"user_id": "u_1"}, "id": "call_a"},
            {"name": "charge_card", "args": {"amount": "99"}, "id": "call_b"},
        ],
    )


def build(node: ToolNode):
    g = StateGraph(MessagesState)
    g.add_node("tools", node)
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    return g.compile(checkpointer=InMemorySaver())


def describe(messages) -> None:
    """Print the persisted history and whether a provider would accept it."""
    open_calls = {}
    answered = set()
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                open_calls[tc["id"]] = tc["name"]
        elif getattr(m, "tool_call_id", None):
            answered.add(m.tool_call_id)
    print(f"  persisted messages: {len(messages)}")
    for m in messages:
        if isinstance(m, AIMessage):
            ids = [tc["id"] for tc in m.tool_calls]
            print(f"    AIMessage tool_calls={ids}")
        else:
            body = m.content if len(m.content) < 54 else m.content[:51] + "..."
            print(f"    ToolMessage id={m.tool_call_id!r} status={m.status!r} {body!r}")
    orphans = sorted(set(open_calls) - answered)
    verdict = "REJECTED" if orphans else "accepted"
    print(f"  orphaned tool_call_ids: {orphans or 'none'}  -> provider would have {verdict}")


async def run(label: str, node: ToolNode) -> None:
    global CURRENT_RUN
    COMPLETED.clear()
    CURRENT_RUN = label
    graph = build(node)
    cfg = {"configurable": {"thread_id": label}}
    print(f"--- {label} ---")
    try:
        await graph.ainvoke({"messages": [seed()]}, cfg)
        print("  graph completed")
    except Exception as exc:
        print(f"  graph RAISED {type(exc).__name__}: {exc}")
    print(f"  at the moment the graph returned, completed tool bodies: {COMPLETED or 'none'}")
    describe((await graph.aget_state(cfg)).values["messages"])
    # Give any task the node abandoned a chance to finish, and see if it does.
    CURRENT_RUN = f"after {label!r} returned"
    await asyncio.sleep(0.3)
    print(f"  after draining the event loop:  {COMPLETED or 'none'}")
    print()


async def main() -> None:
    print(
        f"langgraph=={version('langgraph')} "
        f"langgraph-prebuilt=={version('langgraph-prebuilt')} "
        f"langchain-core=={version('langchain-core')}\n"
    )
    tools = [lookup_user, charge_card]
    await run("default handle_tool_errors", ToolNode(tools))
    await run("handle_tool_errors=True", ToolNode(tools, handle_tool_errors=True))


if __name__ == "__main__":
    asyncio.run(main())
