"""Experiment 1 - OpenAI Agents SDK: what does the receiving agent actually see?

Runs the same triage -> refund handoff under three configurations and prints
the exact input list handed to the *second* agent's model:

  A. default                        (no input filter, nest_handoff_history=False)
  B. input_filter=remove_all_tools
  C. RunConfig(nest_handoff_history=True)

`agents.testing.ScriptedModel` is the SDK's own deterministic test double; its
`.calls` property records every request at the provider-neutral Model boundary,
so nothing here is inferred - it is the payload the SDK built.
"""

from __future__ import annotations

import asyncio
import json

from agents import Agent, RunConfig, Runner, function_tool, handoff
from agents.extensions.handoff_filters import remove_all_tools
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from common import ORDER_JSON, USER_REQUEST, preview, release_tokenizer, rule, tokens_of


@function_tool
def lookup_order(order_id: str) -> str:
    """Fetch the full order record for an order id."""
    return ORDER_JSON


def build_script() -> list[ModelStep]:
    """Turn 1: call the tool. Turn 2: hand off. Turn 3: the refund agent answers."""
    return [
        ModelStep(
            output=[
                function_call(
                    "lookup_order",
                    {"order_id": "A-1183"},
                    call_id="call_lookup_1",
                )
            ]
        ),
        ModelStep(
            output=[
                function_call(
                    "transfer_to_refund_agent",
                    {},
                    call_id="call_handoff_1",
                )
            ]
        ),
        ModelStep(
            output=[
                assistant_message("Refund of $248.50 approved for order A-1183.")
            ]
        ),
    ]


def build_agents(model: ScriptedModel, *, use_filter: bool) -> Agent:
    refund_agent = Agent(
        name="Refund_agent",
        instructions="You process refunds.",
        model=model,
    )
    target = (
        handoff(refund_agent, input_filter=remove_all_tools)
        if use_filter
        else refund_agent
    )
    return Agent(
        name="Triage_agent",
        instructions="You triage support requests.",
        model=model,
        tools=[lookup_order],
        handoffs=[target],
    )


def describe(item) -> str:
    """One readable line per input item, using only what the SDK put there."""
    if not isinstance(item, dict):
        item = item.model_dump() if hasattr(item, "model_dump") else dict(item)
    itype = item.get("type")
    role = item.get("role")
    if itype == "function_call":
        return f"function_call        name={item.get('name')} call_id={item.get('call_id')}"
    if itype == "function_call_output":
        return (
            f"function_call_output call_id={item.get('call_id')} "
            f"output={preview(item.get('output'), 40)}"
        )
    if role:
        content = item.get("content")
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        return f"message role={role:<9} {preview(content, 78)}"
    return f"{itype or '?'}: {preview(json.dumps(item, default=str), 70)}"


def as_dicts(items) -> list[dict]:
    return [it if isinstance(it, dict) else it.model_dump() for it in items]


async def run_config(
    label: str, *, use_filter: bool, nest: bool, dump: bool = False
) -> tuple[int, int]:
    model = ScriptedModel(build_script())
    triage = build_agents(model, use_filter=use_filter)
    await Runner.run(
        triage,
        USER_REQUEST,
        run_config=RunConfig(nest_handoff_history=nest),
    )

    # calls[2] is the first call made *after* the handoff, i.e. the refund agent.
    receiving_call = model.calls[2]
    items = as_dicts(receiving_call.input)
    flat = json.dumps(items, default=str)

    print(rule(label))
    print(f"input items handed to Refund_agent: {len(items)}")
    for i, item in enumerate(items):
        print(f"  [{i}] {describe(item)}")
    n_tokens = tokens_of(items)
    # "C-90422" appears only inside the lookup_order result.
    print(f"  order record reachable by Refund_agent: {'C-90422' in flat}")
    print(f"  handoff plumbing still in history:      {'transfer_to_refund_agent' in flat}")
    print(f"  input tokens (gpt2 bpe): {n_tokens}")
    if dump:
        print("  --- verbatim content of item [0] ---")
        content = items[0].get("content")
        if isinstance(content, list):
            content = "".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        for line in str(content).splitlines():
            print(f"  | {line[:96]}")
    print()
    return len(items), n_tokens


async def main() -> None:
    print(rule("SCENARIO", 74))
    print(f"user: {USER_REQUEST}")
    print(f"tool result (lookup_order) is {tokens_of(ORDER_JSON)} tokens of JSON")
    print()

    results = {}
    results["A default"] = await run_config(
        "A. DEFAULT (no filter, nest_handoff_history=False)",
        use_filter=False,
        nest=False,
    )
    results["B remove_all_tools"] = await run_config(
        "B. input_filter=remove_all_tools",
        use_filter=True,
        nest=False,
    )
    results["C nest_handoff_history"] = await run_config(
        "C. RunConfig(nest_handoff_history=True)",
        use_filter=False,
        nest=True,
        dump=True,
    )

    print(rule("SUMMARY"))
    print(f"{'config':<26}{'items':>7}{'tokens':>9}")
    for name, (items, toks) in results.items():
        print(f"{name:<26}{items:>7}{toks:>9}")
    release_tokenizer()


if __name__ == "__main__":
    asyncio.run(main())
