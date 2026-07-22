# The four canonical orchestration patterns, and how to actually choose one

*Some guides list five or six orchestration patterns. This article argues for four, and explains exactly why the other two are compositions of these four rather than new topologies — because a decision procedure with four choices is one you can actually use, and one with six named variants usually is not.*

## Four topologies, not a growing list of names

Industry writing on orchestration patterns has not converged on one taxonomy. Some guides count four. Some count five, adding "handoff" (dynamic routing to a specialist) as its own pattern. Some count six, adding "debate" or "loop" (iterative critique with an evaluator) as a separate category from hierarchical.

Here is the position this article takes, stated plainly rather than assumed: handoff is a routing decision made inside a sequential or hierarchical structure, not a new control-flow topology. Debate is a hierarchical structure with an evaluator added as one of the workers. Naming them separately describes what the system is *for*, not how information actually flows through it. Collapsing them keeps the decision procedure to four real choices instead of an ever-growing list of named variants that are, underneath, doing one of four things.

Concretely: a "handoff" pattern — a support conversation routed to the right specialist — is a supervisor (hierarchical) making one decision (which specialist) and then behaving sequentially from that point on, one specialist handling the conversation until it resolves or hands off again. A "debate" pattern is a supervisor dispatching the same question to several workers in parallel, then adding one more worker whose job is specifically to judge the others' answers — which is hierarchical with an evaluator role, not a fifth topology. Naming these separately is useful for describing what a product does. It is not useful for deciding how to build the coordination itself, which is this article's actual job.

The four: **sequential** (a pipeline, each agent depending on the last), **parallel** (independent agents, no communication until results are aggregated), **hierarchical** (a supervisor decomposing and synthesizing), and **decentralized** (a peer mesh, no fixed owner of the plan).

[DIAGRAM: four-orchestration-patterns-comparison — see this folder's README for the source link]

## What a controlled study actually found

Most orchestration guides describe these four patterns and stop there — a taxonomy without a decision procedure, which is exactly the gap this article exists to close. A January 2026 Google Research study changes that. Researchers ran 180 controlled configurations across three model families and four benchmarks, comparing a single agent against independent, centralized, decentralized, and hybrid multi-agent variants — the same four topologies this article names, tested rigorously enough to standardize tools, prompts, and token budgets across every configuration, so that any performance difference could be attributed to the coordination structure itself, not to one setup having better tools.

Three findings from that study do more work than any framework's tutorial defaults:

**The alignment principle.** On parallelizable tasks — their Finance-Agent benchmark, where distinct agents can analyze revenue trends, cost structures, and market comparisons independently — centralized coordination improved performance by 80.9% over a single agent. The task's shape and the pattern's shape matched.

**The sequential penalty.** On tasks requiring strict sequential reasoning — their PlanCraft benchmark — every multi-agent variant tested degraded performance by 39 to 70%. Not some variants. Every one. The overhead of communication fragmented the reasoning process and left insufficient capacity for the actual task.

**Architecture as a safety feature.** Independent multi-agent systems, agents working in parallel without talking, amplified errors by 17.2 times relative to a single agent. Centralized systems, with an orchestrator synthesizing results, contained that same amplification to 4.4 times. The orchestrator functions as a validation bottleneck, catching mistakes before they propagate — the cost of centralization buys something specific and measurable, not just organizational tidiness.

The researchers' own predictive model, using measurable task properties like tool count and decomposability, picked the best-performing architecture for 87% of task configurations it had not seen during training. That is a genuinely different kind of claim than "here are four patterns" — it is a claim about which pattern actually wins, and why, backed by a controlled experiment rather than a framework's convention.

Translated into a self-check you can actually run before drawing a diagram: how many distinct tools does this task need, and does the number of tools grow the coordination tax faster than the task itself grows? Can this task's subtasks be described independently of each other, or does describing subtask two require knowing what subtask one produced? Those two questions, tool count and decomposability, are the same properties the predictive model used — not because this article is reverse-engineering an academic paper into a checklist, but because those properties are what actually predicted the outcome in a controlled test, which is a stronger claim than most orchestration advice gets to make.

## Running Article 01 and 02's case study through the four patterns

DevPulse — the developer-productivity system running through this whole series — is not one pure pattern. Article 02 already established this without naming it: a supervisor at the top, three agents running independently under it, and one genuinely sequential dependency nested inside.

Named against this article's four patterns:

- The whole system is **hierarchical**. A supervisor dispatches to each functional agent and, implicitly, is the thing a human would look at to understand what ran and when.
- Inbox triage, file classification, and calendar planning are **parallel** underneath that supervisor. Independent subtasks, no agent needing another's output, aggregated only in the sense that the supervisor knows all three finished.
- The classifier-to-provisioner relationship is **sequential**. Genuinely, not loosely — the provisioner's input depends on the classifier's completed output.
- Nothing in DevPulse is **decentralized**. No relationship in this system needs agents to negotiate directly with no fixed owner of the plan, which is itself a useful negative data point: not every system needs all four patterns, and forcing a peer mesh into a system that does not need one adds coordination cost for a benefit nobody asked for.

In the research's own vocabulary, DevPulse is a **hybrid**: hierarchical oversight with both a parallel batch and a sequential dependency nested inside it. That word is not a hedge. Hybrid was one of the five architectures the Google study actually tested, and most production systems the researchers and other industry sources describe are hybrids, not single-pattern deployments. A system that is honestly hybrid and says so is more accurate than a system forced into one clean label for the sake of a tidier architecture diagram.

## The decision, made concrete

Run the actual recommendation through code, not a diagram alone. `orchestration_pattern_recommender.py`, in this folder's `src/`, encodes the three findings above as a decision procedure:

```python
parallel_case = TaskProperties(
    has_sequential_dependency=False,
    subtasks_are_independent=True,
    error_containment_critical=False,
    needs_open_ended_consensus=False,
)
recommend_pattern(parallel_case)
# -> ("parallel", "...+80.9% accuracy on parallelizable tasks...")

sequential_case = TaskProperties(
    has_sequential_dependency=True,
    subtasks_are_independent=False,
    error_containment_critical=False,
    needs_open_ended_consensus=False,
)
recommend_pattern(sequential_case)
# -> ("single-agent-or-sequential-with-caution", "...degraded 39-70%...")
```

The first case is DevPulse's inbox/classifier/calendar batch. The second is the classifier-provisioner relationship — and notice the recommendation is not simply "sequential." It is a caution: given the 39-to-70% degradation the research found on genuinely sequential tasks, the honest recommendation is to avoid splitting across agents at all where possible, and only accept a sequential multi-agent pipeline when the stages truly require different specialized tools that one agent cannot hold at once. DevPulse's case meets that bar — classification and provisioning are genuinely different tool surfaces — but the recommendation does not default to "yes, sequential is fine" just because a dependency exists.

A third case worth running: a high-stakes financial analysis task with independent subtasks, where a wrong number is expensive.

```python
finance_case = TaskProperties(
    has_sequential_dependency=False,
    subtasks_are_independent=True,
    error_containment_critical=True,
    needs_open_ended_consensus=False,
)
recommend_pattern(finance_case)
# -> ("hierarchical", "...contains error amplification to 4.4x versus 17.2x...")
```

Same independence property as the DevPulse batch above. Different recommendation, because error cost changes the answer. Independent parallel agents are not automatically the right choice just because subtasks can run independently — whether a mistake is cheap to catch downstream is a separate question the task-shape alone does not answer.

## What the trade-offs actually cost, precisely

This is the part most pattern guides gloss over in favor of a clean diagram: every pattern here has a cost that shows up in a specific place, not a vague "coordination overhead" hand-wave.

Parallel buys speed and thoroughness, at a real and now-measured error cost: 17.2 times the error amplification of a single agent, because nothing checks any agent's work before results get combined. Hierarchical buys error containment at the cost of a bottleneck: every result routes through one synthesis step, and that step's own quality caps the whole system's ceiling. Sequential buys clean, easy-to-trace causality, at the cost the PlanCraft numbers put an exact figure on: a 39-to-70% performance penalty when the task genuinely required this shape, which should make any team reach for a sequential multi-agent split cautiously rather than by default. Decentralized buys genuine exploration and consensus on problems no single agent has enough context to plan centrally, at the cost of debate rounds that can churn without converging — a real cost, just one the January 2026 study did not quantify as precisely as the other three, since none of DevPulse or the parallelizable/sequential benchmarks actually exercised it.

Picture where decentralized would actually earn its place, since DevPulse never needs it: several specialist agents evaluating the same ambiguous decision from genuinely different vantage points — a security reviewer, a performance reviewer, and a maintainability reviewer looking at the same pull request, none of them subordinate to the others, negotiating toward a merge decision none of them could reach alone. No supervisor is well-positioned to make that call centrally, because the supervisor would need all three specialists' judgment simultaneously, which is exactly what a fixed hierarchy cannot cheaply provide. That is a decentralized problem. Triaging an inbox is not, which is why DevPulse's inbox agent runs under a supervisor instead of negotiating with anyone.

None of these four is free. The question the decision procedure above is built to answer is not "which pattern is best" but "which specific cost is this task willing to pay."

## What this looks like Monday morning

Before you name your system's architecture, name each relationship in it separately, the way DevPulse's four relationships got named above. A system is rarely one pattern all the way through, and forcing it into one label hides exactly the trade-off that will surprise you in production: a sequential dependency wearing a parallel diagram's clothes, or a parallel batch that needed error containment it never got. The label on the architecture diagram is not the design decision — the four separate answers underneath it are.

If you take one number from this article into your next design review, make it this one: every multi-agent variant tested degraded performance on genuinely sequential tasks. Not most. Every one. If your task has a real sequential dependency, the default assumption should not be "which multi-agent pattern handles this" — it should be "does this need to be multi-agent at all."

One more number worth carrying forward, because it connects directly to Article 01's coordination-cost math. In an interview about this same study, lead researcher Yubin Kim described a practical team-size limit of roughly three to four agents, driven by communication overhead that grows faster than linearly as agents are added. That is not a new finding contradicting Article 01's n(n−1)/2 model — it is the same quadratic growth, showing up as an empirical ceiling instead of a theoretical one. The math said coordination cost grows faster than agent count. This study is one place that growth actually got measured against real task performance, not just modeled.

The next time you sketch a system with five or more agents talking to each other, do not just check whether each one earns its place by Article 01's three reasons. Check whether the pattern connecting them is the one this article's decision procedure actually recommends, or the one that seemed cleanest on a whiteboard.

The next article in this series picks up from here: once you have chosen a pattern honestly instead of by default, the next question is the one this series keeps returning to — designing the trust boundary between agents so authorization is not an afterthought.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Design Multi-Agent Systems

1. Multi-agent or overkill? A decision framework before you add a second agent — not yet published
2. The coordination primitives: control, state, and communication — a vendor-neutral model — not yet published
3. **The four canonical orchestration patterns, and how to actually choose one** *(this article)*
4. Designing the trust boundary: authorization between agents that isn't an afterthought — not yet published
5. Preventing the MAST failure modes by design, not by autopsy — not yet published
6. Observability and evaluation for multi-agent systems: what to actually measure — not yet published
7. Shared-resource contention: when your agents fight over the same database row — not yet published
8. Putting it together: designing a production multi-agent system end to end — not yet published

## References

1. Kim, Y. and Liu, X. Towards a Science of Scaling Agent Systems, Google Research, January 2026
   https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/
   Paper: https://arxiv.org/abs/2512.08296
2. When to use multi-agent systems (and when not to), Anthropic
   https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them
3. The Orchestration of Multi-Agent Systems: Architectures, Protocols, and Enterprise Adoption
   https://arxiv.org/abs/2601.13671
