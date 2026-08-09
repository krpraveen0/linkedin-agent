"""Experiment 4 — A framework-agnostic pairing check and repair, over raw
OpenAI chat-completions message dicts.

This is the pass to run immediately before a request goes out, on any stack that
does not already do it for you.

Run:  python 04_reconcile.py
"""

INTERRUPTED = "The tool call was interrupted before a result was produced."


def find_orphans(messages: list[dict]) -> list[str]:
    """Return ids of tool_calls that never receive a matching tool message.

    Matching is an ordered walk: a tool message only answers a call that is
    already open and not yet answered at that point, so a duplicate or
    out-of-order result does not mask a genuinely dangling call.
    """
    open_calls: dict[str, int] = {}
    orphans: list[str] = []
    for i, m in enumerate(messages):
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                open_calls[tc["id"]] = i
        elif m.get("role") == "tool":
            open_calls.pop(m.get("tool_call_id"), None)
    orphans.extend(open_calls)
    return orphans


def repair(messages: list[dict]) -> list[dict]:
    """Insert a synthetic tool message for every dangling call, in place order."""
    orphans = set(find_orphans(messages))
    if not orphans:
        return messages
    out: list[dict] = []
    for m in messages:
        out.append(m)
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                if tc["id"] in orphans:
                    out.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": INTERRUPTED,
                    })
    return out


# A history shaped exactly like the one LangGraph persisted in experiment 1:
# the assistant asked for two tools, neither result was recorded.
CRASHED = [
    {"role": "user", "content": "charge the card and look up the user"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_a", "type": "function",
         "function": {"name": "lookup_user", "arguments": '{"user_id":"u_1"}'}},
        {"id": "call_b", "type": "function",
         "function": {"name": "charge_card", "arguments": '{"amount":"99"}'}},
    ]},
]

# A history where one sibling landed and the other did not, as in experiment 3.
HALF_DONE = CRASHED + [
    {"role": "tool", "tool_call_id": "call_a", "content": "user u_1: ok"},
]


def show(label: str, messages: list[dict]) -> None:
    print(f"--- {label} ---")
    orphans = find_orphans(messages)
    print(f"  {len(messages)} messages, orphans: {orphans or 'none'}")
    if orphans:
        print("  a provider would reject this with, in OpenAI's wording:")
        print("    An assistant message with 'tool_calls' must be followed by tool")
        print("    messages responding to each 'tool_call_id'. The following")
        print(f"    tool_call_ids did not have response messages: {', '.join(orphans)}")
    fixed = repair(messages)
    print(f"  after repair: {len(fixed)} messages, orphans: {find_orphans(fixed) or 'none'}")
    print(f"  repair is idempotent: {repair(fixed) == fixed}")
    print()


if __name__ == "__main__":
    show("crashed before any result was recorded", CRASHED)
    show("one sibling landed, one did not", HALF_DONE)
