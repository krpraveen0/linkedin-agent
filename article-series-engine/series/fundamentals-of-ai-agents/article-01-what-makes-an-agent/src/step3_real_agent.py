"""
Step 3: a real, minimal agent. Every iteration:
  1. observes the current state
  2. a decision function picks the next action FROM that observation
     (not from its position in the code)
  3. after acting, checks whether it's done based on the new state

No fixed step count anywhere. No fixed order baked in. Still no API key
- the "decision function" is a deterministic stand-in for what an LLM
would decide, so this is 100% reproducible. Step 6 shows how to swap
in a real model call.
"""

from dataclasses import dataclass, field


@dataclass
class AgentState:
    inbox: list[str]
    fetched: list[str] = field(default_factory=list)
    summary: str | None = None
    sent: bool = False


def decide_next_action(state: AgentState) -> str:
    """This is the part a real LLM call would replace. The decision
    depends on the CURRENT state, not on which line of code we're at."""
    if not state.inbox:
        return "stop"  # nothing to do - decide that immediately
    if not state.fetched:
        return "fetch"
    if state.summary is None:
        return "summarize"
    if not state.sent:
        return "send"
    return "stop"  # done - decided from the state, not a step counter


def run_agent(inbox: list[str], max_steps: int = 10) -> list[str]:
    state = AgentState(inbox=inbox)
    actions_taken = []

    for _ in range(max_steps):  # a safety cap, not the actual stop condition
        action = decide_next_action(state)
        if action == "stop":
            break
        actions_taken.append(action)
        if action == "fetch":
            state.fetched = state.inbox
        elif action == "summarize":
            state.summary = f"{len(state.fetched)} email(s)"
        elif action == "send":
            state.sent = True

    return actions_taken


if __name__ == "__main__":
    print("Environment A (empty inbox):")
    print(" ", run_agent(inbox=[]))
    print("Environment B (one urgent email):")
    print(" ", run_agent(inbox=["urgent: server down"]))
