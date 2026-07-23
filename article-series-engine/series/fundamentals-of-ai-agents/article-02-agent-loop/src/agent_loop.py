"""
agent_loop.py

Article 02: the observe-decide-act loop, built properly - with three
DIFFERENT stop reasons, not one bare loop that just "ends."

Still no API key needed. decide_next_action is a deterministic stand-in,
same as Article 01.
"""

from dataclasses import dataclass, field
from enum import Enum


class StopReason(Enum):
    GOAL_ACHIEVED = "goal_achieved"       # decided it was done, on its own
    STUCK = "stuck_no_progress"           # repeating the same action, state not changing
    MAX_STEPS = "max_steps_reached"       # safety cap - NOT the same thing as done


@dataclass
class AgentState:
    inbox: list[str]
    fetched: list[str] = field(default_factory=list)
    summary: str | None = None
    sent: bool = False

    def snapshot(self) -> tuple:
        """A comparable snapshot of the state, used to detect whether
        an action actually changed anything."""
        return (tuple(self.fetched), self.summary, self.sent)


def decide_next_action(state: AgentState) -> str:
    if not state.inbox:
        return "stop"
    if not state.fetched:
        return "fetch"
    if state.summary is None:
        return "summarize"
    if not state.sent:
        return "send"
    return "stop"


def apply_action(state: AgentState, action: str) -> None:
    if action == "fetch":
        state.fetched = state.inbox
    elif action == "summarize":
        state.summary = f"{len(state.fetched)} email(s)"
    elif action == "send":
        state.sent = True
    # deliberately NOT handling "buggy_fetch" here - see the stuck example below


def run_agent(inbox: list[str], max_steps: int = 10) -> tuple[list[str], StopReason]:
    state = AgentState(inbox=inbox)
    history: list[str] = []
    last_snapshot = state.snapshot()

    for _ in range(max_steps):
        action = decide_next_action(state)

        if action == "stop":
            return history, StopReason.GOAL_ACHIEVED

        apply_action(state, action)
        new_snapshot = state.snapshot()

        if history and history[-1] == action and new_snapshot == last_snapshot:
            # same action, and nothing about the state actually changed -
            # this is the loop-detection check most tutorials skip
            return history, StopReason.STUCK

        history.append(action)
        last_snapshot = new_snapshot

    return history, StopReason.MAX_STEPS


if __name__ == "__main__":
    print("Normal run, real task:")
    history, reason = run_agent(inbox=["urgent: server down"])
    print(f"  actions: {history}")
    print(f"  stopped because: {reason.value}\n")

    print("Normal run, nothing to do:")
    history, reason = run_agent(inbox=[])
    print(f"  actions: {history}")
    print(f"  stopped because: {reason.value}")
