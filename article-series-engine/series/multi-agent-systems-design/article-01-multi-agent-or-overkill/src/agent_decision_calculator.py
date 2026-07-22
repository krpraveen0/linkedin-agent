"""
agent_decision_calculator.py

A small, runnable tool for Article 01 ("Multi-agent or overkill?").

Two things it does:
1. Models the pairwise coordination cost of adding agents (n agents ->
   n*(n-1)/2 potential coordination links) - a first-principles argument,
   not an empirical study, but the math is exact and worth seeing plotted
   against your actual agent count before you add the next one.
2. Scores a proposed multi-agent design against the three legitimate
   justifications from Anthropic's own published guidance on this
   (https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them):
   context-window limits, parallelizable independent subtasks where the
   speedup is worth the coordination cost, and failure isolation.

Usage:
    python agent_decision_calculator.py

No dependencies beyond the standard library.
"""

from dataclasses import dataclass


def pairwise_coordination_links(num_agents: int) -> int:
    """Number of potential pairwise coordination links for n agents.

    This is just n choose 2 - it says nothing about actual message volume
    or failure probability, only the surface area available for things to
    go wrong between agents. Treat it as a lower bound on complexity, not
    a prediction.
    """
    if num_agents < 0:
        raise ValueError("num_agents must be >= 0")
    return num_agents * (num_agents - 1) // 2


@dataclass
class DecisionInputs:
    exceeds_single_context_window: bool
    has_independent_parallelizable_subtasks: bool
    speedup_worth_coordination_cost: bool
    needs_failure_isolation: bool


def should_use_multi_agent(inputs: DecisionInputs) -> tuple[bool, str]:
    """Applies the three-question decision tree from the article's diagram.

    Returns (decision, reason). Only returns True with a specific reason
    attached - never a bare "yes," because the point of this whole article
    is that "yes" without a named reason is how coordination cost creeps in
    unexamined.
    """
    if inputs.exceeds_single_context_window:
        return True, "context-limit split: the task genuinely doesn't fit one agent"

    if inputs.has_independent_parallelizable_subtasks and inputs.speedup_worth_coordination_cost:
        return True, "parallel workers: subtasks are independent and the speedup earns the cost"

    if inputs.needs_failure_isolation:
        return True, "isolated agents: one agent's failure must not cascade into another's work"

    return False, "stay single-agent - add tools, not agents"


def print_coordination_table(max_agents: int = 10) -> None:
    print(f"{'agents':>6} | {'pairwise links (n*(n-1)/2)':>28}")
    print("-" * 37)
    for n in range(1, max_agents + 1):
        print(f"{n:>6} | {pairwise_coordination_links(n):>28}")


def run_interactive_checklist() -> None:
    def ask(prompt: str) -> bool:
        return input(f"{prompt} [y/n]: ").strip().lower().startswith("y")

    inputs = DecisionInputs(
        exceeds_single_context_window=ask("Does the task exceed one agent's context window?"),
        has_independent_parallelizable_subtasks=ask("Are there independent, parallelizable subtasks?"),
        speedup_worth_coordination_cost=ask("Is the speedup worth the coordination cost?"),
        needs_failure_isolation=ask("Do you need failure isolation between agents?"),
    )
    decision, reason = should_use_multi_agent(inputs)
    verdict = "USE MULTI-AGENT" if decision else "STAY SINGLE-AGENT"
    print(f"\n{verdict} - {reason}")


if __name__ == "__main__":
    print("Coordination cost by agent count:\n")
    print_coordination_table()
    print("\nGo/no-go checklist:\n")
    run_interactive_checklist()
