"""
Step 1: build a "workflow" - fixed steps, same order, every time.

No API key needed for this whole article. We're testing STRUCTURE, not
model quality, so a plain Python stand-in for "the model decided X" is
fine and actually clearer to follow.
"""


def run_workflow(inbox: list[str]) -> list[str]:
    """A fixed, three-step pipeline: fetch, summarize, send.
    It runs these three steps in this order NO MATTER what's in the
    inbox - even if there's nothing to summarize or send."""
    actions_taken = []

    actions_taken.append("fetch")
    fetched = inbox  # step 1 always runs

    actions_taken.append("summarize")
    summary = f"{len(fetched)} email(s)" if fetched else "no emails"  # step 2 always runs

    actions_taken.append("send")
    # step 3 always runs - even with nothing to say
    result = f"Sent summary: {summary}"

    return actions_taken


if __name__ == "__main__":
    print("Environment A (empty inbox):")
    print(" ", run_workflow(inbox=[]))
    print("Environment B (one urgent email):")
    print(" ", run_workflow(inbox=["urgent: server down"]))
