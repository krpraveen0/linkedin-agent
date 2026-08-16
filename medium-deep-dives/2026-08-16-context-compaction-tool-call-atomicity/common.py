"""Shared history builders for the compaction experiments.

Builds the same logical conversation in two message dialects:
  * LangChain  (langchain_core.messages)
  * Microsoft Agent Framework (agent_framework._types.Message)

The conversation is deliberately tool-heavy and includes a *parallel* tool
call fan-out, because that is the shape that breaks naive history trimming.
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from agent_framework import Content, Message


TOOLS = ["search_flights", "search_hotels", "get_weather"]


def _payload(tool: str, i: int) -> str:
    return f"{{'tool': '{tool}', 'turn': {i}, 'rows': [1, 2, 3], 'note': 'result body for {tool}'}}"


def langchain_history(turns: int = 4, parallel_at: int = 2, fanout: int = 3):
    """Build a LangChain message list.

    At turn `parallel_at` the assistant issues `fanout` tool calls in one
    message, followed by `fanout` ToolMessages.
    """
    msgs = [SystemMessage(content="You are a travel planning agent.", id="sys-0")]
    for i in range(turns):
        msgs.append(HumanMessage(content=f"User request number {i}.", id=f"h-{i}"))
        if i == parallel_at:
            calls = [
                {"name": TOOLS[j % len(TOOLS)], "args": {"q": i}, "id": f"call-{i}-{j}"}
                for j in range(fanout)
            ]
            msgs.append(AIMessage(content="", tool_calls=calls, id=f"ai-{i}"))
            for j, c in enumerate(calls):
                msgs.append(
                    ToolMessage(
                        content=_payload(c["name"], i),
                        tool_call_id=c["id"],
                        name=c["name"],
                        id=f"tm-{i}-{j}",
                    )
                )
        else:
            call = {"name": TOOLS[i % len(TOOLS)], "args": {"q": i}, "id": f"call-{i}-0"}
            msgs.append(AIMessage(content="", tool_calls=[call], id=f"ai-{i}"))
            msgs.append(
                ToolMessage(
                    content=_payload(call["name"], i),
                    tool_call_id=call["id"],
                    name=call["name"],
                    id=f"tm-{i}-0",
                )
            )
        msgs.append(AIMessage(content=f"Answer for turn {i}.", id=f"final-{i}"))
    return msgs


def maf_history(turns: int = 4, parallel_at: int = 2, fanout: int = 3):
    """Build the same conversation as Agent Framework Messages."""
    msgs = [Message(role="system", contents=["You are a travel planning agent."], message_id="sys-0")]
    for i in range(turns):
        msgs.append(Message(role="user", contents=[f"User request number {i}."], message_id=f"h-{i}"))
        n = fanout if i == parallel_at else 1
        calls = [
            Content.from_function_call(
                call_id=f"call-{i}-{j}", name=TOOLS[j % len(TOOLS)], arguments={"q": i}
            )
            for j in range(n)
        ]
        msgs.append(Message(role="assistant", contents=list(calls), message_id=f"ai-{i}"))
        for j, c in enumerate(calls):
            msgs.append(
                Message(
                    role="tool",
                    contents=[Content.from_function_result(call_id=c.call_id, result=_payload(c.name, i))],
                    message_id=f"tm-{i}-{j}",
                )
            )
        msgs.append(
            Message(
                role="assistant",
                contents=[Content.from_text(f"Answer for turn {i}.")],
                message_id=f"final-{i}",
            )
        )
    return msgs


def lc_label(m) -> str:
    """Short one-line label for a LangChain message."""
    t = m.__class__.__name__.replace("Message", "")
    if isinstance(m, AIMessage) and m.tool_calls:
        return f"{t}[tool_calls={[c['id'] for c in m.tool_calls]}]"
    if isinstance(m, ToolMessage):
        return f"{t}[for={m.tool_call_id}]"
    return t


def find_orphans_langchain(msgs):
    """Return (dangling_tool_call_ids, orphaned_tool_message_ids).

    A provider rejects a request when either set is non-empty.
    """
    issued, answered = [], []
    for m in msgs:
        if isinstance(m, AIMessage):
            issued.extend(c["id"] for c in m.tool_calls)
        if isinstance(m, ToolMessage):
            answered.append(m.tool_call_id)
    dangling = [i for i in issued if i not in answered]
    orphaned = [a for a in answered if a not in issued]
    return dangling, orphaned


def find_orphans_maf(msgs):
    """Same check over Agent Framework messages."""
    issued, answered = [], []
    for m in msgs:
        for c in m.contents:
            if c.type == "function_call" and c.call_id:
                issued.append(c.call_id)
            if c.type == "function_result" and c.call_id:
                answered.append(c.call_id)
    dangling = [i for i in issued if i not in answered]
    orphaned = [a for a in answered if a not in issued]
    return dangling, orphaned
