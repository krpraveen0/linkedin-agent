# Preventing the MAST failure modes by design, not by autopsy

*Nearly every "why multi-agent systems fail" post is the same listicle: cite MAST's 14 failure modes, restate the taxonomy, move on. This article does the thing that listicle never does - maps the 3 root categories to specific design-time decisions that prevent them, with code, before the autopsy is ever needed.*

## The taxonomy everyone cites and nobody builds against

MAST is real, rigorous research, not a marketing taxonomy. Cemri and colleagues built it using grounded theory - close analysis of an initial 150 execution traces, each averaging over 15,000 lines, refined iteratively across expert human annotators until reaching strong inter-annotator agreement (Cohen's kappa of 0.88). They then scaled annotation to over 1,600 traces across 7 popular multi-agent frameworks using an LLM-as-judge pipeline validated against that same human-annotated baseline. The result: 14 distinct failure modes clustered into 3 root categories. System Design Issues account for roughly 41.8% of observed failures. Inter-Agent Misalignment accounts for roughly 36.9%. Task Verification failures make up the remaining 21.3%.

Search for content referencing this taxonomy and the overwhelming majority does one thing with it: restates the categories, maybe lists a few of the 14 named modes, and stops. That is a diagnostic tool, useful after a system has already failed and someone is trying to figure out which bucket the failure belongs in. It is not a design tool. Nobody reading one of these posts comes away knowing what to actually build differently before the failure happens - the taxonomy explains what went wrong in hindsight far more often than it changes what gets built next time.

<image src="file-upload://3a5c633a-e23a-8150-8e3f-00b2d79a69bf"></image>

*MAST's three categories, each mapped to a specific design-time prevention - not a diagnosis performed afterward.*

## One category, one concrete prevention - not fourteen modes restated

This article does not re-catalog all 14 named failure modes. That would be the same listicle with better formatting. Instead, one prevention per root category, concrete enough to run.

**System Design Issues, prevented by validated spec templates.** The largest category, at roughly 41.8% of observed failures, includes modes like disobeying the task specification and losing track of termination conditions. The design-time fix is not "write clearer prompts." It is refusing to let an agent act on a spec that is ambiguous or incomplete in the first place. A spec with a vague action field, an unspecified target, or no constraints should never reach an agent at all - it should fail validation before execution starts.

**Inter-Agent Misalignment, prevented by structured handoff contracts.** At roughly 36.9% of observed failures, this category covers context loss during handoffs and agents effectively ignoring what a previous agent established. The design-time fix is not "improve the prompt that describes the handoff." It is a handoff contract with required fields that cannot be silently omitted - if the required context is missing, the handoff itself fails, rather than silently proceeding with an incomplete picture.

**Task Verification, prevented by explicit verifier checkpoints.** The remaining roughly 21.3% covers premature termination and incomplete or incorrect verification of results. The design-time fix is not "add better error handling." It is refusing to treat the absence of an exception as proof of success - a verifier checkpoint has to produce actual evidence that a task completed correctly, not just that nothing crashed along the way.

## Applying all three to DevPulse

**System Design Issues, applied to the file classifier.** `mast_prevention_checks.py`, in this folder's `src/`, implements a `TaskSpec` that must name an explicit action, a target path, and at least one constraint:

```python
good_spec = TaskSpec(
    task_id="PAY-402",
    action="provision-from-spec",
    target_path="~/Projects/PaymentService",
    constraints=frozenset({"branch:fix/PAY-402-timeout"}),
    completion_criteria="container health check returns 200",
)
validate_spec(good_spec)
# -> passes

vague_spec = TaskSpec(
    task_id="PAY-403", action="handle it", target_path="",
    constraints=frozenset(), completion_criteria="",
)
validate_spec(vague_spec)
# -> InvalidSpecError: action is missing or too vague to act on: 'handle it'
```

A classifier that tries to write a vague spec like "handle it" never gets the chance to hand that off. The failure is caught at the point the spec is created, not discovered later when the provisioner does something nobody intended.

Notice the `completion_criteria` field specifically. This is not decorative - it directly addresses one of the largest individual modes inside the System Design Issues category: an agent unaware of its own termination conditions, which shows up in production as an agent that keeps working past the point where the task was actually done, or stops before it was. A spec without an explicit "done" condition is not just incomplete paperwork. It is the exact shape of failure this specific mode describes, prevented by refusing to accept a spec that omits it.

**Inter-Agent Misalignment, applied to the classifier-provisioner handoff.** Articles 02 and 04 both examined this relationship - a blackboard, then a trust boundary. This is the third and different question: does the handoff actually carry what the provisioner needs, or just a bare file path?

```python
complete_handoff = HandoffContract(
    from_agent="file-classifier",
    to_agent="workspace-provisioner",
    artifact_path="PAY-402/spec.json",
    required_context={"ticket_id": "PAY-402", "urgency": "high", "requested_by": "alex.rivera"},
)
verify_handoff_complete(complete_handoff)
# -> passes

bare_handoff = HandoffContract(
    from_agent="file-classifier", to_agent="workspace-provisioner",
    artifact_path="PAY-402/spec.json", required_context={},
)
verify_handoff_complete(bare_handoff)
# -> IncompleteHandoffError: missing required context: {'urgency', 'ticket_id', 'requested_by'}
```

A bare file path is not a complete handoff, even if the file itself is well-formed. Without urgency and ticket context, the provisioner has no way to prioritize competing requests or explain later why a specific container got spun up when it did.

**Task Verification, applied to the provisioner's own completion check.** This is the sharpest of the three, because the naive pattern looks completely reasonable until you watch it fail:

```python
naive_result = provisioner_action_no_verification("payment-service-dev")
# -> "docker run payment-service-dev - command issued, no exception raised"
```

That line is true and also useless. The command not raising an exception says nothing about whether the container is actually running. The verified version checks the real state:

```python
verified = provisioner_action_with_verification("payment-service-dev", actually_running=False)
# -> VerificationResult(passed=False, evidence="docker ps shows payment-service-dev is not running")
```

Same underlying scenario - a container that failed to start - and two completely different outcomes depending on whether anything actually checked. The naive version reports success. The verified version catches the exact failure MAST's Task Verification category describes, because it asked for evidence instead of accepting silence.

## Why one prevention per category, not fourteen

The temptation with a 14-mode taxonomy is to build 14 separate defenses, one per named failure. That is how you end up with a system so encrusted in special-case handling that the original design intent is unrecoverable. The three prevention mechanisms above are deliberately structural, not mode-specific: a validated spec template does not just catch "disobey task specification" - it structurally prevents an entire class of specification-shaped failures, including the termination-condition mode covered above, because an agent that never receives an ambiguous or incomplete instruction cannot disobey a specification it was never actually given. The same logic applies to handoff contracts, which cover context loss, ignored inputs, and conversation derailment in one mechanism rather than three, and to verifier checkpoints, which cover premature, incomplete, and incorrect verification in one mechanism rather than three. Three mechanisms, each addressing a root cause rather than a symptom, cover more of the 14 named modes between them than 14 individually bolted-on patches would - and they do it without anyone needing to memorize which of the 14 modes applies to which situation before writing the fix.

Worth being explicit about how this relates to Article 04's trust boundary, since both concern the classifier-provisioner relationship and it would be easy to conflate them. Article 04 asked whose authority an action is performed under - whether the provisioner is exercising its own granted scope or inheriting the classifier's by accident. This article asks a different question about the same relationship: even when the authority is correctly scoped, did the task actually get specified clearly, handed off completely, and verified honestly? A system can pass every check in Article 04 and still fail every check in this one. Authorization and correctness are separate failure surfaces, and conflating them is itself a design-time mistake.

## Watching all three work in sequence

It is worth seeing these three checks operate as one pipeline, not three isolated demos, since that is how they actually run in a real system. Take the PAY-402 ticket through all three gates in order.

First, the classifier drafts a spec. If it produces something like `action="handle it"` with no completion criteria, `validate_spec` rejects it immediately - the task never gets far enough to become anyone's problem but the classifier's own retry logic. Only a spec with an explicit action, target, constraint, and completion criteria proceeds.

Second, the classifier hands that validated spec to the provisioner. If the handoff carries only the file path with no ticket ID, urgency, or requesting party, `verify_handoff_complete` rejects it - even though the underlying spec passed its own check a moment earlier. Passing stage one does not exempt a task from stage two; each gate checks a different failure surface.

Third, once the provisioner acts, `provisioner_action_with_verification` is what actually gets asked whether the container is running, not merely whether the `docker run` command returned control. Only a real, checked positive result lets the task be marked complete.

Three independent gates, each catching a different category, each blind to what the other two already checked. A task that clears all three has meaningfully different reliability guarantees than one that just did not happen to hit an exception anywhere along the way.

## What this looks like Monday morning

Before adding error handling for a specific failure you just watched happen, ask which of the three root categories it actually belongs to, and whether the fix belongs at the mechanism level or the incident level. A try/except around one specific crash is an incident-level fix. A verifier checkpoint that would have caught that crash and every other silent failure in the same category is a mechanism-level fix.

Go check whether your own system has all three mechanisms in place, not whether it has handled the last failure you happened to notice. A system with zero spec validation, zero handoff contracts, and zero verifier checkpoints is not one bug away from MAST's statistics - it is already living inside them, just not caught yet.

Pick the relationship in your own system most likely to fail next - not the one that already has, the one that has not yet, because nobody has looked closely at it. Run it through all three questions: is the spec it receives specific enough to be disobeyed correctly, does its handoff carry everything the next step needs, and does its completion get verified with actual evidence or just the absence of an error. Most systems fail at least one of the three on the first honest check.

The next article in this series picks up from here: once failures are being prevented by design rather than diagnosed after the fact, the next question is what to actually monitor to know the prevention is working - observability and evaluation for multi-agent systems.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Design Multi-Agent Systems

1. Multi-agent or overkill? A decision framework before you add a second agent — not yet published
2. The coordination primitives: control, state, and communication — a vendor-neutral model — not yet published
3. The four canonical orchestration patterns, and how to actually choose one — not yet published
4. Designing the trust boundary: authorization between agents that isn't an afterthought — not yet published
5. **Preventing the MAST failure modes by design, not by autopsy** *(this article)*
6. Observability and evaluation for multi-agent systems: what to actually measure — not yet published
7. Shared-resource contention: when your agents fight over the same database row — not yet published
8. Putting it together: designing a production multi-agent system end to end — not yet published

## References

1. Cemri, M. et al. Why Do Multi-Agent LLM Systems Fail?, 2025
   https://arxiv.org/abs/2503.13657
2. When to use multi-agent systems (and when not to), Anthropic
   https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them
