"""
coordination_model_classifier.py

A small, runnable tool for Article 02 ("The coordination primitives:
control, state, and communication").

Given a design's choice on each of the three axes, names the resulting
coordination pattern and flags combinations that are internally
inconsistent - the kind of thing that is easy to design accidentally and
hard to debug later.

Usage:
    python coordination_model_classifier.py
"""

from dataclasses import dataclass
from enum import Enum


class Control(Enum):
    CENTRALIZED = "centralized"
    DECENTRALIZED = "decentralized"


class State(Enum):
    LOCAL = "local"
    SHARED = "shared"


class Communication(Enum):
    MESSAGE_PASSING = "message_passing"
    BLACKBOARD = "blackboard"
    DIRECT_CALL = "direct_call"


@dataclass
class CoordinationChoice:
    control: Control
    state: State
    communication: Communication


# Named patterns for combinations that show up often in real systems.
# Missing combinations are not wrong by definition - they are just less
# common, and worth a second look before committing to one.
_KNOWN_PATTERNS = {
    (Control.CENTRALIZED, State.LOCAL, Communication.DIRECT_CALL):
        ("Supervisor-dispatched local agents",
         "A single process, a supervisor calling each agent directly. "
         "This is Article 01's DevPulse case for three of its four agents."),
    (Control.CENTRALIZED, State.SHARED, Communication.BLACKBOARD):
        ("Supervisor-mediated blackboard",
         "A supervisor still decides sequencing, but agents coordinate "
         "through a shared store rather than direct calls or messages. "
         "This is Article 01's DevPulse case for the classifier-to-"
         "provisioner handoff specifically - the filesystem is the "
         "blackboard."),
    (Control.CENTRALIZED, State.LOCAL, Communication.MESSAGE_PASSING):
        ("Orchestrator with message-passed workers",
         "Common in distributed deployments - a lead agent dispatches "
         "work over a structured protocol (for example A2A) to workers "
         "that keep their own state."),
    (Control.DECENTRALIZED, State.LOCAL, Communication.MESSAGE_PASSING):
        ("Peer-to-peer negotiation",
         "No single agent owns the plan. Agents negotiate directly over "
         "a message protocol. Harder to reason about, but necessary when "
         "no single agent has enough context to plan centrally."),
    (Control.DECENTRALIZED, State.SHARED, Communication.BLACKBOARD):
        ("Classic blackboard architecture",
         "The original blackboard pattern - agents opportunistically "
         "read and write a shared workspace with no central planner. "
         "Coordination emerges from the state, not from control."),
}


def classify(choice: CoordinationChoice) -> dict:
    key = (choice.control, choice.state, choice.communication)
    if key in _KNOWN_PATTERNS:
        name, note = _KNOWN_PATTERNS[key]
        return {"pattern": name, "note": note, "flagged": False}

    # Not a listed pattern - not necessarily wrong, but worth a second look.
    flag_note = _flag_reason(choice)
    return {
        "pattern": "Unlabeled combination",
        "note": flag_note,
        "flagged": True,
    }


def _flag_reason(choice: CoordinationChoice) -> str:
    if choice.control == Control.DECENTRALIZED and choice.communication == Communication.DIRECT_CALL:
        return (
            "Decentralized control with direct function calls is unusual - "
            "direct calls usually imply one process deciding the order. "
            "Worth checking whether control is actually centralized."
        )
    if choice.state == State.SHARED and choice.communication == Communication.MESSAGE_PASSING:
        return (
            "Shared state plus message passing is not wrong, but it is "
            "redundant unless the messages and the shared store are "
            "carrying different information - worth checking they are not "
            "duplicating the same synchronization job two ways."
        )
    return "Uncommon combination - not necessarily wrong, worth a second look before committing to it."


if __name__ == "__main__":
    devpulse_parallel_agents = CoordinationChoice(
        control=Control.CENTRALIZED,
        state=State.LOCAL,
        communication=Communication.DIRECT_CALL,
    )
    result = classify(devpulse_parallel_agents)
    print("Inbox / Classifier / Calendar agents:")
    print(f"  Pattern: {result['pattern']}")
    print(f"  {result['note']}\n")

    devpulse_handoff = CoordinationChoice(
        control=Control.CENTRALIZED,
        state=State.SHARED,
        communication=Communication.BLACKBOARD,
    )
    result = classify(devpulse_handoff)
    print("Classifier -> Provisioner handoff:")
    print(f"  Pattern: {result['pattern']}")
    print(f"  {result['note']}\n")

    unusual = CoordinationChoice(
        control=Control.DECENTRALIZED,
        state=State.LOCAL,
        communication=Communication.DIRECT_CALL,
    )
    result = classify(unusual)
    print("A design someone might propose without checking:")
    print(f"  Pattern: {result['pattern']}")
    print(f"  Flagged: {result['flagged']}")
    print(f"  {result['note']}")
