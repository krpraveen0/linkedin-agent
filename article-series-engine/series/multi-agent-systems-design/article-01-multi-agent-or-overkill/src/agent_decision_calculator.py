"""
agent_decision_calculator.py

ClaimGuard: an insurance claims processing and fraud-detection system.
This file implements the three-question decision framework this
article walks through, applied to whether specific agent relationships
in ClaimGuard actually justify being multi-agent.

Five nodes: a claim router (supervisor), an intake agent, a fraud-risk
agent, a policy-verification agent, and a payment-processing agent.
"""

from dataclasses import dataclass


def pairwise_coordination_links(num_agents: int) -> int:
    """n choose 2 - the number of potential coordination links between
    n agents. A lower bound on complexity, not a prediction of failure
    rate."""
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
    if inputs.exceeds_single_context_window:
        return True, "context-limit split: the task genuinely doesn't fit one agent"
    if inputs.has_independent_parallelizable_subtasks and inputs.speedup_worth_coordination_cost:
        return True, "parallel workers: subtasks are independent and the speedup earns the cost"
    if inputs.needs_failure_isolation:
        return True, "isolated agents: one agent's failure must not cascade into another's work"
    return False, "stay single-agent - add tools, not agents"


if __name__ == "__main__":
    print("Coordination cost by agent count:\n")
    for n in range(1, 6):
        print(f"  {n} agents -> {pairwise_coordination_links(n)} potential links")

    print("\nClaimGuard: intake, fraud-risk, and policy-verification agents")
    print("(independent checks that can run on the same claim simultaneously):")
    parallel_case = DecisionInputs(
        exceeds_single_context_window=False,
        has_independent_parallelizable_subtasks=True,
        speedup_worth_coordination_cost=True,
        needs_failure_isolation=False,
    )
    decision, reason = should_use_multi_agent(parallel_case)
    print(f"  -> {decision}, {reason}")

    print("\nClaimGuard: fraud-risk score feeding payment processing")
    print("(a genuine sequential dependency, not a parallel relationship):")
    sequential_case = DecisionInputs(
        exceeds_single_context_window=False,
        has_independent_parallelizable_subtasks=False,
        speedup_worth_coordination_cost=False,
        needs_failure_isolation=True,
    )
    decision, reason = should_use_multi_agent(sequential_case)
    print(f"  -> {decision}, {reason}")

    print("\nA proposed sixth agent: a 'claim summarizer' that just reformats")
    print("what the intake agent already produced (looks parallel, isn't worth it):")
    unnecessary_case = DecisionInputs(
        exceeds_single_context_window=False,
        has_independent_parallelizable_subtasks=True,
        speedup_worth_coordination_cost=False,
        needs_failure_isolation=False,
    )
    decision, reason = should_use_multi_agent(unnecessary_case)
    print(f"  -> {decision}, {reason}")
