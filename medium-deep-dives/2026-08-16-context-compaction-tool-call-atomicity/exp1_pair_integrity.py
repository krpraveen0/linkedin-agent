"""Experiment 1: does "keep the last N" actually keep N?

Both LangChain's SummarizationMiddleware and Microsoft Agent Framework's
compaction refuse to split an assistant tool-call from its tool results.
They pay for that invariant in different currencies. This measures the bill.
"""

import asyncio

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain.agents.middleware.summarization import SummarizationMiddleware

from agent_framework._compaction import (
    annotate_message_groups,
    project_included_messages,
    SlidingWindowStrategy,
)

from common import (
    langchain_history,
    maf_history,
    lc_label,
    find_orphans_langchain,
    find_orphans_maf,
)


def rule(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def langchain_cutoffs() -> None:
    rule("1. LangChain SummarizationMiddleware._find_safe_cutoff")

    model = GenericFakeChatModel(messages=iter(["summary"] * 50))
    mw = SummarizationMiddleware(model=model, trigger=("messages", 1), keep=("messages", 4))

    msgs = langchain_history()
    print(f"history length: {len(msgs)} messages\n")
    for i, m in enumerate(msgs):
        print(f"  [{i:2d}] {lc_label(m)}")

    print("\n  keep=N   cutoff   summarized   kept   overshoot   split-pair?")
    print("  " + "-" * 62)
    for n in range(1, len(msgs) + 1):
        cutoff = mw._find_safe_cutoff(msgs, n)
        kept = msgs[cutoff:]
        dangling, orphaned = find_orphans_langchain(kept)
        broken = "YES" if (dangling or orphaned) else "no"
        overshoot = len(kept) - n
        print(
            f"  {n:>5}   {cutoff:>6}   {cutoff:>10}   {len(kept):>4}   "
            f"{overshoot:>+9}   {broken:>11}"
        )


async def maf_window() -> None:
    rule("2. Agent Framework SlidingWindowStrategy (group-based)")

    print("  keep_groups   kept msgs   dropped msgs   split-pair?   kept ids")
    print("  " + "-" * 76)
    for k in range(1, 10):
        msgs = maf_history()
        annotate_message_groups(msgs)
        await SlidingWindowStrategy(keep_last_groups=k, preserve_system=True)(msgs)
        kept = project_included_messages(msgs)
        dangling, orphaned = find_orphans_maf(kept)
        broken = "YES" if (dangling or orphaned) else "no"
        ids = ",".join(m.message_id for m in kept)
        print(f"  {k:>11}   {len(kept):>9}   {len(msgs) - len(kept):>12}   {broken:>11}   {ids}")


def group_structure() -> None:
    rule("3. How Agent Framework groups the same history")
    msgs = maf_history()
    annotate_message_groups(msgs)
    seen = {}
    for m in msgs:
        ann = m.additional_properties["_group"]
        seen.setdefault(ann["index"], []).append((m.message_id, ann["kind"]))
    for idx in sorted(seen):
        kind = seen[idx][0][1]
        ids = ", ".join(mid for mid, _ in seen[idx])
        print(f"  group {idx:>2}  kind={kind:<14} members=[{ids}]")
    print(f"\n  {len(msgs)} messages collapse into {len(seen)} atomic groups.")


def main() -> None:
    langchain_cutoffs()
    asyncio.run(maf_window())
    group_structure()


if __name__ == "__main__":
    main()
