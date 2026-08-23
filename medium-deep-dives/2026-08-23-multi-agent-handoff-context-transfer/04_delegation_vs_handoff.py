"""Experiment 4 - handoff versus delegation, and what each costs for a whole run.

`Agent.as_tool()` is the other way to involve a second agent: it runs nested,
sees only the arguments the caller generated, and returns a string. The caller
keeps the loop.

This script measures, for one identical task:

  * how many model calls each architecture makes
  * total input tokens summed across every call in the run
  * what the second agent could actually read
"""

from __future__ import annotations

import asyncio
import json

from agents import Agent, RunConfig, Runner, function_tool, handoff
from agents.extensions.handoff_filters import remove_all_tools
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from common import ORDER_JSON, USER_REQUEST, release_tokenizer, rule, tokens_of


@function_tool
def lookup_order(order_id: str) -> str:
    """Fetch the full order record for an order id."""
    return ORDER_JSON


def as_dicts(items) -> list[dict]:
    return [it if isinstance(it, dict) else it.model_dump() for it in items]


def run_totals(model: ScriptedModel) -> tuple[int, int]:
    """(number of model calls, total input tokens across the run)."""
    calls = model.calls
    return len(calls), sum(tokens_of(as_dicts(c.input)) for c in calls)


async def handoff_run(label: str, *, use_filter: bool, nest: bool) -> None:
    model = ScriptedModel([
        ModelStep(output=[function_call(
            "lookup_order", {"order_id": "A-1183"}, call_id="call_lookup_1")]),
        ModelStep(output=[function_call(
            "transfer_to_refund_agent", {}, call_id="call_handoff_1")]),
        ModelStep(output=[assistant_message(
            "Refund of $248.50 approved for order A-1183.")]),
    ])
    refund = Agent(name="Refund_agent", instructions="You process refunds.", model=model)
    target = handoff(refund, input_filter=remove_all_tools) if use_filter else refund
    triage = Agent(
        name="Triage_agent",
        instructions="You triage support requests.",
        model=model,
        tools=[lookup_order],
        handoffs=[target],
    )
    result = await Runner.run(
        triage, USER_REQUEST, run_config=RunConfig(nest_handoff_history=nest)
    )
    n_calls, total = run_totals(model)
    sub_input = as_dicts(model.calls[2].input)
    sees_order = "C-90422" in json.dumps(sub_input, default=str)
    print(f"{label:<34}{n_calls:>7}{total:>9}{str(sees_order):>10}"
          f"   owner after: {result.last_agent.name}")


async def delegation_run() -> None:
    """Agent.as_tool(): the sub-agent runs nested on generated input."""
    refund_model = ScriptedModel([
        ModelStep(output=[assistant_message(
            "Refund of $248.50 approved for order A-1183.")]),
    ])
    refund = Agent(
        name="Refund_agent", instructions="You process refunds.", model=refund_model
    )

    triage_model = ScriptedModel([
        ModelStep(output=[function_call(
            "lookup_order", {"order_id": "A-1183"}, call_id="call_lookup_1")]),
        ModelStep(output=[function_call(
            "run_refund_agent",
            {"input": "Approve a damaged-goods refund for order A-1183, total $248.50."},
            call_id="call_delegate_1")]),
        ModelStep(output=[assistant_message(
            "Your refund of $248.50 has been approved.")]),
    ])
    triage = Agent(
        name="Triage_agent",
        instructions="You triage support requests.",
        model=triage_model,
        tools=[
            lookup_order,
            refund.as_tool(
                tool_name="run_refund_agent",
                tool_description="Ask the refund specialist to decide a refund.",
            ),
        ],
    )
    result = await Runner.run(triage, USER_REQUEST)

    caller_calls, caller_total = run_totals(triage_model)
    sub_calls, sub_total = run_totals(refund_model)
    sub_input = as_dicts(refund_model.calls[0].input)
    sees_order = "C-90422" in json.dumps(sub_input, default=str)
    print(f"{'as_tool() delegation':<34}{caller_calls + sub_calls:>7}"
          f"{caller_total + sub_total:>9}{str(sees_order):>10}"
          f"   owner after: {result.last_agent.name}")

    print()
    print(rule("WHAT THE DELEGATED AGENT RECEIVED"))
    for i, item in enumerate(sub_input):
        content = item.get("content")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        print(f"  [{i}] role={item.get('role')} {content}")
    print(f"  sub-agent input tokens: {sub_total}")
    print(f"  caller's own calls: {caller_calls}, "
          f"caller input tokens: {caller_total}")


async def main() -> None:
    print(rule("WHOLE-RUN COST, ONE IDENTICAL TASK"))
    print(f"{'architecture':<34}{'calls':>7}{'in-tok':>9}{'sub sees':>10}")
    await handoff_run("handoff, default", use_filter=False, nest=False)
    await handoff_run("handoff, remove_all_tools", use_filter=True, nest=False)
    await handoff_run("handoff, nest_handoff_history", use_filter=False, nest=True)
    await delegation_run()
    print()
    print("'sub sees' = whether the second agent could read the order record")
    print("'in-tok'   = input tokens summed over every model call in the run")
    release_tokenizer()


if __name__ == "__main__":
    asyncio.run(main())
