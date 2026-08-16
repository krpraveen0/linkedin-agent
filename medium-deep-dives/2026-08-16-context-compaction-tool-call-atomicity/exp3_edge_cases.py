"""Experiment 3: the edge cases each design leaves open.

Three failure paths, all reachable from ordinary configuration:

  1. LangChain's pair-repair falls back to a *forward* scan when the matching
     AIMessage is no longer in the list - which is exactly the state a second
     compaction pass sees.
  2. Agent Framework refuses to emit an empty projection, so an impossible
     token budget silently returns a context larger than the budget.
  3. Clearing tool results (Anthropic-style context editing) reclaims tokens
     without ever touching message structure - a different point on the curve.
"""

import asyncio

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware.context_editing import ClearToolUsesEdit

from agent_framework._compaction import (
    CharacterEstimatorTokenizer,
    TokenBudgetComposedStrategy,
    TruncationStrategy,
    annotate_message_groups,
    annotate_token_counts,
    included_token_count,
    project_included_messages,
)

from common import langchain_history, maf_history, lc_label, find_orphans_langchain


def rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def orphaned_tool_fallback() -> None:
    rule("1. LangChain: what happens when the AIMessage is already gone")

    # The state a *second* compaction pass sees: a summary HumanMessage where
    # the tool-calling AIMessage used to be, but its ToolMessages still present.
    msgs = [
        SystemMessage(content="You are a travel planning agent.", id="sys-0"),
        HumanMessage(content="Here is a summary of the conversation to date: ...", id="sum-0"),
        ToolMessage(content="{'rows': [1,2,3]}", tool_call_id="call-x-0", name="search_flights", id="tm-x-0"),
        ToolMessage(content="{'rows': [4,5,6]}", tool_call_id="call-x-1", name="search_hotels", id="tm-x-1"),
        AIMessage(content="Answer.", id="final-x"),
        HumanMessage(content="Another request.", id="h-y"),
        AIMessage(content="", tool_calls=[{"name": "get_weather", "args": {}, "id": "call-y-0"}], id="ai-y"),
        ToolMessage(content="{'temp': 21}", tool_call_id="call-y-0", name="get_weather", id="tm-y-0"),
        AIMessage(content="Final answer.", id="final-y"),
    ]
    print("  input history (an already-compacted conversation):")
    for i, m in enumerate(msgs):
        print(f"    [{i}] {m.id:<9} {lc_label(m)}")

    d, o = find_orphans_langchain(msgs)
    print(f"\n  before compaction: dangling={d} orphaned={o}")
    print("  -> the input is ALREADY invalid: two tool results with no tool call.\n")

    model = GenericFakeChatModel(messages=iter(["summary"] * 50))
    mw = SummarizationMiddleware(model=model, trigger=("messages", 1), keep=("messages", 4))

    for n in (6, 7, 8):
        cutoff = mw._find_safe_cutoff(msgs, n)
        kept = msgs[cutoff:]
        d, o = find_orphans_langchain(kept)
        direction = "backward" if cutoff < len(msgs) - n else ("forward" if cutoff > len(msgs) - n else "exact")
        print(f"  keep={n}: target={len(msgs) - n} -> cutoff={cutoff} ({direction:>8}), "
              f"kept={len(kept)}, dangling={d}, orphaned={o}")

    print("\n  keep=7 targets index 2 (a ToolMessage with no matching AIMessage).")
    print("  The backward scan finds nothing, so the fallback advances FORWARD")
    print("  past both tool results - dropping them rather than orphaning them.")


async def impossible_budget() -> None:
    rule("2. Agent Framework: an impossible token budget is not an error")

    tk = CharacterEstimatorTokenizer()
    for budget in (10_000, 200, 50, 5, 1):
        msgs = maf_history()
        annotate_message_groups(msgs)
        annotate_token_counts(msgs, tokenizer=tk)
        total = included_token_count(msgs)

        strategy = TokenBudgetComposedStrategy(
            token_budget=budget,
            tokenizer=tk,
            strategies=[TruncationStrategy(max_n=budget, compact_to=budget, tokenizer=tk)],
        )
        await strategy(msgs)
        kept = project_included_messages(msgs)
        final = included_token_count(msgs)
        status = "within budget" if final <= budget else f"OVER by {final - budget}"
        roles = ",".join(m.role for m in kept)
        print(f"  budget={budget:>6}  start={total:>4} tok  end={final:>4} tok  "
              f"kept={len(kept):>2} msgs  {status:<16} [{roles}]")

    print("\n  _minimum_retained_group_ids() guarantees a non-empty projection,")
    print("  so the budget is best-effort: below a floor it is silently exceeded.")


def context_editing() -> None:
    rule("3. Clearing tool results instead of dropping messages")

    msgs = langchain_history()
    before_tokens = count_tokens_approximately(msgs)
    before_len = len(msgs)

    edit = ClearToolUsesEdit(trigger=1, keep=2, clear_at_least=0)
    edit.apply(msgs, count_tokens=count_tokens_approximately)

    after_tokens = count_tokens_approximately(msgs)
    d, o = find_orphans_langchain(msgs)

    print(f"  messages : {before_len} -> {len(msgs)}  (structure untouched)")
    print(f"  tokens   : {before_tokens} -> {after_tokens} "
          f"({(before_tokens - after_tokens) / before_tokens * 100:.0f}% reclaimed)")
    print(f"  dangling={d} orphaned={o}\n")
    for m in msgs:
        if isinstance(m, ToolMessage):
            cleared = m.response_metadata.get("context_editing", {}).get("cleared", False)
            print(f"    {m.id:<8} cleared={str(cleared):<5} content={m.content!r:.44}")

    print("\n  Every tool_call still has a matching result, so the request stays")
    print("  valid - but the model can no longer read what those tools returned.")


def main() -> None:
    orphaned_tool_fallback()
    asyncio.run(impossible_budget())
    context_editing()


if __name__ == "__main__":
    main()
