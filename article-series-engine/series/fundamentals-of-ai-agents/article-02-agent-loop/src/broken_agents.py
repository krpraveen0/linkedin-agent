"""
Two broken agents, showing what each of the OTHER two stop reasons
actually catches. Both import the same run_agent loop from
agent_loop.py - only the decision/action functions are swapped out.
"""

import sys
sys.path.insert(0, ".")
from agent_loop import AgentState, StopReason
from dataclasses import dataclass, field


# --- Broken agent #1: a bug causes it to get stuck ---

def buggy_decide_next_action(state: AgentState) -> str:
    """A realistic bug: this checks state.fetched, but a typo means
    apply_action (below) never actually sets it. The decision function
    keeps asking for the same action forever."""
    if not state.inbox:
        return "stop"
    if not state.fetched:
        return "fetch"
    return "stop"


def buggy_apply_action(state: AgentState, action: str) -> None:
    if action == "fetch":
        pass  # BUG: forgot to actually set state.fetched - this is the typo


def run_buggy_agent(inbox: list[str], max_steps: int = 10):
    state = AgentState(inbox=inbox)
    history: list[str] = []
    last_snapshot = state.snapshot()

    for _ in range(max_steps):
        action = buggy_decide_next_action(state)
        if action == "stop":
            return history, StopReason.GOAL_ACHIEVED
        buggy_apply_action(state, action)
        new_snapshot = state.snapshot()
        if history and history[-1] == action and new_snapshot == last_snapshot:
            return history, StopReason.STUCK
        history.append(action)
        last_snapshot = new_snapshot

    return history, StopReason.MAX_STEPS


# --- Broken agent #2: no loop detection at all, hits the raw cap ---

def run_agent_no_loop_detection(inbox: list[str], max_steps: int = 10):
    """Same bug as above, but WITHOUT the loop-detection check. This is
    what happens if you only ever cap max_steps and call it a day."""
    state = AgentState(inbox=inbox)
    history: list[str] = []

    for _ in range(max_steps):
        action = buggy_decide_next_action(state)
        if action == "stop":
            return history, StopReason.GOAL_ACHIEVED
        buggy_apply_action(state, action)
        history.append(action)

    return history, StopReason.MAX_STEPS


if __name__ == "__main__":
    print("Buggy agent, WITH loop detection:")
    history, reason = run_buggy_agent(inbox=["urgent: server down"])
    print(f"  actions: {history}")
    print(f"  stopped because: {reason.value}")
    print("  caught after just 2 identical, no-progress actions.\n")

    print("Same bug, WITHOUT loop detection (max_steps=10):")
    history, reason = run_agent_no_loop_detection(inbox=["urgent: server down"], max_steps=10)
    print(f"  actions: {history}")
    print(f"  stopped because: {reason.value}")
    print("  ran all 10 steps doing the exact same useless thing, and the")
    print("  stop reason gives you no signal that anything was wrong.")
