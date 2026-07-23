"""
Step 2: something that LOOKS agent-like - it loops, it "calls the model"
- but isn't, by the real definition. The loop count is fixed in advance,
not derived from what's actually observed.
"""


def fake_llm_call(inbox: list[str], step_number: int) -> str:
    """Stands in for an API call. Deterministic on purpose - this whole
    article never needs a real key to make its point."""
    return f"model call #{step_number} on {len(inbox)} email(s)"


def run_fake_loop(inbox: list[str], num_iterations: int = 3) -> list[str]:
    """Looks agentic - it's a loop, it calls 'the model' repeatedly.
    But num_iterations is fixed in advance. Nothing about what's
    OBSERVED changes how many times this runs or what happens next."""
    actions_taken = []
    for i in range(num_iterations):
        fake_llm_call(inbox, i)
        actions_taken.append(f"model_call_{i}")
    return actions_taken


if __name__ == "__main__":
    print("Environment A (empty inbox):")
    print(" ", run_fake_loop(inbox=[]))
    print("Environment B (one urgent email):")
    print(" ", run_fake_loop(inbox=["urgent: server down"]))
