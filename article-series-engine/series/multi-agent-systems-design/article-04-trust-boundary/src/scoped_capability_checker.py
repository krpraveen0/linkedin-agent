"""
scoped_capability_checker.py

A small, runnable tool for Article 04 ("Designing the trust boundary:
authorization between agents that isn't an afterthought").

Models per-agent capabilities as explicit, narrowly-scoped grants rather
than one shared credential for the whole system. Two things it enforces:

1. An agent can never delegate more authority than it was itself granted -
   this is the classical "confused deputy" problem (Hardy, 1988), now
   showing up in multi-agent LLM delegation chains specifically. See:
   "Authorization Propagation in Multi-Agent AI Systems" (2026)
   https://arxiv.org/abs/2605.05440
2. A downstream agent verifies the SPECIFIC scope of a capability before
   acting on it - it never treats "this file exists, written by an agent I
   trust" as an implicit grant of whatever the file's contents request.

Usage:
    python scoped_capability_checker.py
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capability:
    """A narrow, explicit grant - not a role, not a shared credential.
    granted_to: which agent holds this capability
    actions: the exact set of actions this capability permits
    issued_by: who issued it (the root authority, or another agent
        delegating a subset of its own capability)
    """
    granted_to: str
    actions: frozenset[str]
    issued_by: str


class ScopeExceededError(PermissionError):
    """Raised when an agent tries to delegate or exercise more authority
    than it was actually granted - this is the check that prevents the
    confused-deputy pattern from working."""


def delegate(parent: Capability, to_agent: str, requested_actions: frozenset[str]) -> Capability:
    """An agent can only delegate a SUBSET of what it already holds.
    This is the check that stops scope from silently expanding across
    a delegation hop."""
    excess = requested_actions - parent.actions
    if excess:
        raise ScopeExceededError(
            f"{parent.granted_to} cannot delegate {excess} to {to_agent} - "
            f"exceeds {parent.granted_to}'s own granted scope "
            f"({parent.actions})"
        )
    return Capability(granted_to=to_agent, actions=requested_actions, issued_by=parent.granted_to)


def verify(capability: Capability, action: str) -> bool:
    """The action a downstream agent actually wants to perform must be
    explicitly present in its OWN capability - never inferred from
    trusting whoever handed it a file, a message, or a task."""
    return action in capability.actions


def vulnerable_blind_trust(spec_file_path: str, spec_contents: dict) -> str:
    """This is the pattern this article argues against - included so the
    contrast is concrete, not just described. The provisioner treats the
    mere existence of a file, written by an agent it trusts, as sufficient
    authorization for whatever that file requests. No independent
    capability check happens at all."""
    repo_url = spec_contents.get("repo_url")
    return f"cloning and provisioning from {repo_url} - no authorization check performed"


if __name__ == "__main__":
    # Root authority issues narrow, independent capabilities to each agent.
    # Note: neither is derived from the other - this is the fix.
    classifier_cap = Capability(
        granted_to="file-classifier",
        actions=frozenset({"read:downloads", "write:project:PAY-402:spec"}),
        issued_by="root",
    )
    provisioner_cap = Capability(
        granted_to="workspace-provisioner",
        actions=frozenset({"read:project:PAY-402:spec", "exec:docker", "exec:git-clone"}),
        issued_by="root",
    )

    print("Provisioner verifying its own actions against its own capability:")
    print(f"  can read the spec file: {verify(provisioner_cap, 'read:project:PAY-402:spec')}")
    print(f"  can run docker: {verify(provisioner_cap, 'exec:docker')}")
    print(f"  can send email (never granted): {verify(provisioner_cap, 'send:email')}\n")

    print("Attempting the confused-deputy pattern - classifier tries to")
    print("delegate an action it was never granted itself:")
    try:
        delegate(classifier_cap, to_agent="workspace-provisioner", requested_actions=frozenset({"exec:docker"}))
    except ScopeExceededError as e:
        print(f"  BLOCKED: {e}\n")

    print("The correct pattern: provisioner never inherits from the")
    print("classifier at all - it acts only within its own independently")
    print("issued capability, checked before every action:")
    action_requested = "exec:docker"
    if verify(provisioner_cap, action_requested):
        print(f"  ALLOWED: provisioner may {action_requested} (within its own granted scope)\n")

    print("For contrast: the vulnerable pattern, with an untrusted spec.")
    print("An attacker-controlled email that got past the inbox agent")
    print("could plant a spec pointing anywhere - the vulnerable function")
    print("has no way to know, because it never checks a capability at all:")
    attacker_spec = {"repo_url": "https://attacker.example/malicious-payload.git"}
    result = vulnerable_blind_trust("PAY-402/spec.json", attacker_spec)
    print(f"  {result}")
