"""
orchestration_pattern_recommender.py

A small, runnable tool for Article 03 ("The four canonical orchestration
patterns, and how to actually choose one").

Two things it does:
1. Simulates the control flow of all four patterns with toy "agents"
   (plain functions), so the difference in execution order is visible,
   not just described.
2. Recommends a pattern from task properties, using the actual predictive
   features from Google Research's 180-configuration study ("Towards a
   Science of Scaling Agent Systems", Jan 2026):
   https://arxiv.org/abs/2512.08296
   - genuinely sequential dependencies predict a 39-70% degradation for
     EVERY multi-agent variant tested, not just some
   - independent/parallel agents gave a real +80.9% gain on parallelizable
     tasks, but amplified errors 17.2x with nothing checking any agent's work
   - centralized/hierarchical agents contained that same error amplification
     to 4.4x, at the cost of the orchestrator becoming the bottleneck

Usage:
    python orchestration_pattern_recommender.py
"""

from dataclasses import dataclass
from typing import Callable


# --- Part 1: simulating the four control-flow topologies ---

def run_sequential(agents: list[Callable[[str], str]], initial_input: str) -> str:
    """Each agent's output becomes the next agent's input. Strict order."""
    value = initial_input
    for agent in agents:
        value = agent(value)
    return value


def run_parallel(agents: list[Callable[[str], str]], shared_input: str) -> list[str]:
    """Every agent gets the same input, runs independently, no agent sees
    another's output. Aggregation happens only at the end, by the caller."""
    return [agent(shared_input) for agent in agents]


def run_hierarchical(
    supervisor_decompose: Callable[[str], list[str]],
    workers: list[Callable[[str], str]],
    supervisor_synthesize: Callable[[list[str]], str],
    task: str,
) -> str:
    """A supervisor decomposes the task, dispatches to workers, then
    synthesizes their outputs itself - the synthesis step is where errors
    get caught, which is why this pattern contains error amplification
    better than pure parallel/independent."""
    subtasks = supervisor_decompose(task)
    results = [worker(subtask) for worker, subtask in zip(workers, subtasks)]
    return supervisor_synthesize(results)


def run_decentralized(
    agents: list[Callable[[str, list[str]], str]], task: str, rounds: int
) -> list[str]:
    """Agents see each other's previous-round outputs and can change their
    position - a debate/negotiation pattern, not a fixed hierarchy."""
    positions = [task] * len(agents)
    for _ in range(rounds):
        positions = [agent(task, positions) for agent in agents]
    return positions


# --- Part 2: recommending a pattern from task properties ---

@dataclass
class TaskProperties:
    has_sequential_dependency: bool
    subtasks_are_independent: bool
    error_containment_critical: bool
    needs_open_ended_consensus: bool


def recommend_pattern(props: TaskProperties) -> tuple[str, str]:
    if props.has_sequential_dependency:
        return (
            "single-agent-or-sequential-with-caution",
            "Every multi-agent variant tested degraded 39-70% on genuinely "
            "sequential tasks (Google Research, PlanCraft benchmark). Prefer "
            "one agent with a good loop unless the stages truly need "
            "different specialized tools no single agent can hold.",
        )

    if props.needs_open_ended_consensus and not props.subtasks_are_independent:
        return (
            "decentralized",
            "No single agent has enough context to plan centrally - use a "
            "peer mesh with debate rounds to reach consensus.",
        )

    if props.subtasks_are_independent and props.error_containment_critical:
        return (
            "hierarchical",
            "Independent subtasks, but errors are costly. A centralized "
            "orchestrator contains error amplification to 4.4x versus 17.2x "
            "for independent parallel agents (Google Research).",
        )

    if props.subtasks_are_independent:
        return (
            "parallel",
            "Independent subtasks, errors are checkable or cheap. Parallel/"
            "independent agents gave +80.9% accuracy on parallelizable "
            "tasks in Google Research's Finance-Agent benchmark.",
        )

    return (
        "hierarchical",
        "Subtasks have some dependency but are not strictly sequential - a "
        "supervisor can manage that dependency without the fragility of a "
        "full sequential pipeline.",
    )


if __name__ == "__main__":
    # DevPulse's three parallel agents (inbox, classifier, calendar)
    parallel_case = TaskProperties(
        has_sequential_dependency=False,
        subtasks_are_independent=True,
        error_containment_critical=False,
        needs_open_ended_consensus=False,
    )
    print("Inbox / Classifier / Calendar agents:")
    pattern, reason = recommend_pattern(parallel_case)
    print(f"  Recommended: {pattern}\n  {reason}\n")

    # DevPulse's classifier -> provisioner relationship
    sequential_case = TaskProperties(
        has_sequential_dependency=True,
        subtasks_are_independent=False,
        error_containment_critical=False,
        needs_open_ended_consensus=False,
    )
    print("Classifier -> Provisioner handoff:")
    pattern, reason = recommend_pattern(sequential_case)
    print(f"  Recommended: {pattern}\n  {reason}\n")

    # A high-stakes financial reasoning task where mistakes are costly
    finance_case = TaskProperties(
        has_sequential_dependency=False,
        subtasks_are_independent=True,
        error_containment_critical=True,
        needs_open_ended_consensus=False,
    )
    print("High-stakes financial analysis, independent subtasks:")
    pattern, reason = recommend_pattern(finance_case)
    print(f"  Recommended: {pattern}\n  {reason}\n")

    # Simulate the sequential pattern with toy agents
    print("--- Simulating sequential pipeline ---")
    result = run_sequential(
        agents=[
            lambda x: f"{x} -> classified",
            lambda x: f"{x} -> provisioned",
        ],
        initial_input="spec file",
    )
    print(f"Result: {result}")
