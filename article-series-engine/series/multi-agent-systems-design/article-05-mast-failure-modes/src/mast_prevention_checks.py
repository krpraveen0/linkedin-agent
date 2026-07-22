"""
mast_prevention_checks.py

A small, runnable tool for Article 05 ("Preventing the MAST failure modes
by design, not by autopsy").

MAST (Cemri et al., 2025 - https://arxiv.org/abs/2503.13657) identifies
14 failure modes across 3 root categories from 1600+ annotated traces
across 7 multi-agent frameworks: System Design Issues (~41.8%),
Inter-Agent Misalignment (~36.9%), and Task Verification (~21.3%).

This file implements one concrete, design-time prevention per category -
not a diagnostic checklist run after something has already gone wrong:

1. Spec validation (prevents System Design Issues like FM-1.1 Disobey Task
   Specification) - an ambiguous or incomplete task spec is rejected
   before any agent acts on it.
2. Handoff contracts (prevents Inter-Agent Misalignment failures like
   context loss during handoffs) - a handoff is incomplete, and blocked,
   if required context fields are missing.
3. Verifier checkpoints (prevents Task Verification failures like
   premature or incorrect completion) - "the command didn't raise an
   exception" is never treated as proof that the task actually succeeded.

Usage:
    python mast_prevention_checks.py
"""

from dataclasses import dataclass, field


# --- 1. Spec validation: prevents System Design Issues ---

class InvalidSpecError(ValueError):
    """Raised when a task spec is ambiguous or missing required fields -
    this is the check that stops FM-1.1-style failures (disobeying or
    misinterpreting the task) before they can happen, by refusing to let
    an underspecified task reach an agent at all."""


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    action: str
    target_path: str
    constraints: frozenset[str]
    completion_criteria: str


def validate_spec(spec: TaskSpec) -> None:
    if not spec.action or spec.action.strip().lower() in {"", "do the thing", "handle it"}:
        raise InvalidSpecError(f"{spec.task_id}: action is missing or too vague to act on: {spec.action!r}")
    if not spec.target_path:
        raise InvalidSpecError(f"{spec.task_id}: no target_path specified - cannot determine scope")
    if not spec.constraints:
        raise InvalidSpecError(f"{spec.task_id}: no constraints specified - an unconstrained spec is how scope creep starts")
    if not spec.completion_criteria:
        raise InvalidSpecError(
            f"{spec.task_id}: no completion_criteria specified - an agent with no defined "
            f"'done' condition is how termination-condition failures happen"
        )


# --- 2. Handoff contracts: prevents Inter-Agent Misalignment ---

class IncompleteHandoffError(ValueError):
    """Raised when a handoff between agents is missing required context -
    this is the check that stops context-loss-style misalignment, where
    an agent silently drops information the next agent actually needed."""


@dataclass(frozen=True)
class HandoffContract:
    from_agent: str
    to_agent: str
    artifact_path: str
    required_context: dict


REQUIRED_HANDOFF_FIELDS = frozenset({"ticket_id", "urgency", "requested_by"})


def verify_handoff_complete(contract: HandoffContract) -> None:
    missing = REQUIRED_HANDOFF_FIELDS - contract.required_context.keys()
    if missing:
        raise IncompleteHandoffError(
            f"handoff from {contract.from_agent} to {contract.to_agent} is missing "
            f"required context: {missing} - a bare file path is not a complete handoff"
        )


# --- 3. Verifier checkpoints: prevents Task Verification failures ---

@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    evidence: str


def provisioner_action_no_verification(container_name: str) -> str:
    """The vulnerable pattern: the action runs, raises no exception, and
    the caller treats that as success. This is exactly how FM-3.x-style
    verification failures happen - nothing here actually confirms the
    container is running."""
    return f"docker run {container_name} - command issued, no exception raised"


def provisioner_action_with_verification(container_name: str, actually_running: bool) -> VerificationResult:
    """The fix: a verifier checkpoint that checks the actual state, not
    the absence of an exception. Passing this check requires evidence,
    not silence."""
    if not actually_running:
        return VerificationResult(passed=False, evidence=f"docker ps shows {container_name} is not running")
    return VerificationResult(passed=True, evidence=f"docker ps confirms {container_name} is running and healthy")


if __name__ == "__main__":
    print("1. Spec validation (prevents System Design Issues):")
    good_spec = TaskSpec(
        task_id="PAY-402",
        action="provision-from-spec",
        target_path="~/Projects/PaymentService",
        constraints=frozenset({"branch:fix/PAY-402-timeout"}),
        completion_criteria="container health check returns 200",
    )
    validate_spec(good_spec)
    print("  good spec: passed validation")
    try:
        vague_spec = TaskSpec(
            task_id="PAY-403", action="handle it", target_path="",
            constraints=frozenset(), completion_criteria="",
        )
        validate_spec(vague_spec)
    except InvalidSpecError as e:
        print(f"  vague spec: BLOCKED - {e}\n")

    print("2. Handoff contracts (prevents Inter-Agent Misalignment):")
    complete_handoff = HandoffContract(
        from_agent="file-classifier",
        to_agent="workspace-provisioner",
        artifact_path="PAY-402/spec.json",
        required_context={"ticket_id": "PAY-402", "urgency": "high", "requested_by": "alex.rivera"},
    )
    verify_handoff_complete(complete_handoff)
    print("  complete handoff: passed validation")
    try:
        bare_handoff = HandoffContract(
            from_agent="file-classifier",
            to_agent="workspace-provisioner",
            artifact_path="PAY-402/spec.json",
            required_context={},
        )
        verify_handoff_complete(bare_handoff)
    except IncompleteHandoffError as e:
        print(f"  bare handoff: BLOCKED - {e}\n")

    print("3. Verifier checkpoints (prevents Task Verification failures):")
    naive_result = provisioner_action_no_verification("payment-service-dev")
    print(f"  naive pattern says: {naive_result!r}")
    print("  ...but the container actually crashed on startup. The naive")
    print("  pattern has no way to know that. The verified pattern does:")
    verified = provisioner_action_with_verification("payment-service-dev", actually_running=False)
    print(f"  verified result: passed={verified.passed}, evidence={verified.evidence!r}")
