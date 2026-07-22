# Multi-agent or overkill? A decision framework before you add a second agent

*Most teams reach for a second agent before they have exhausted what one agent with the right tools can do. Here is a framework for catching that, before the coordination bill comes due — walked through against a real-shaped case study, not a toy example.*

## A case worth running the framework against

*(A composite, illustrative case study — not a specific product — built to be concrete enough to actually test a framework against, rather than staying abstract.)*

Picture a developer-productivity system. Call it a daily-work OS for engineers.

Five pieces: a supervisor, an inbox-triage agent, a file-classifier agent that sorts what lands in `~/Downloads`, a calendar and focus-planning agent, and a workspace provisioner that clones repos, spins up containers, and opens the IDE.

Five nodes. Mathematically, that is 10 possible pairwise links between them.

The question worth asking before any of it gets built is not whether five agents sounds reasonable. It is how many of those 10 links this design actually uses, and whether each one earns its place.

## The question nobody asks before the design doc

Multi-agent architecture diagrams are everywhere right now. Boxes, arrows, a supervisor node with three or four workers hanging off it.

What is missing from almost all of them is the one paragraph that should come before the diagram: why does this need to be more than one agent?

Anthropic's own engineering team, who have published some of the more detailed production multi-agent write-ups available, put a number on what skipping that question costs. Multi-agent implementations typically use 3 to 10 times more tokens than single-agent approaches for the same task.

Not a marginal tax. A multiplier.

Every additional agent is another prompt to maintain, another context boundary where information gets lossy, another thing that can silently misbehave. That is not an argument against multi-agent systems. It is an argument for making the "why" explicit before you pay the cost.

## The coordination-cost model

Here is the part of the math that is easy to miss when you are staring at a clean architecture diagram: coordination cost does not grow linearly with agent count.

The number of potential coordination links between agents grows as *n(n−1)/2* — the classic pairwise-interaction count.

- 2 agents → 1 potential link
- 4 agents → 6 potential links
- 10 agents → 45 potential links

This is a lower bound on surface area, not a measured failure rate. It is the number of places a handoff, a race, or a context-loss bug can occur. Real failure rates will vary by design. But the shape of the curve does not lie. It is quadratic, not linear. That is why a system that worked cleanly at 3 agents can become genuinely hard to reason about at 8.

One catch worth flagging now, because it matters later in this article: that n(n−1)/2 figure assumes every agent could talk to every other agent. A full mesh. Most real systems are not meshes. They are hub-and-spoke, with a supervisor mediating, which means the actual number of links in use is usually far smaller than the formula's ceiling. The formula tells you the worst case you are capped by, not the coordination cost of any particular design.

[DIAGRAM: multi-agent-or-overkill-decision-tree — see this folder's README for the source link]

## The three legitimate reasons to add an agent

Strip away the hype and there are exactly three defensible reasons to go multi-agent. Each one earns the coordination cost differently.

**1. The task exceeds a single agent's context window.** Not "it would be cleaner to split this up." It genuinely does not fit. A coding agent reasoning across a 500-file codebase while running tests and tracking a long task history will hit a wall no matter how good the model is. Splitting by bounded, focused scope is the fix, and it is a real fix, not an aesthetic one.

**2. Independent, parallelizable subtasks exist, and the speedup is worth the coordination cost.** The operative word is independent. If agent B needs agent A's output before it can start, there is no parallelism. There is a slower, more expensive sequential pipeline wearing a parallel architecture's clothes. Anthropic's framing here is useful: multi-agent parallelism buys thoroughness, not speed. Total token spend goes up even when wall-clock time goes down, because more ground gets covered, not the same work done faster.

**3. Failure isolation is required.** One agent's mistake must not be able to cascade into another's work. This reason is about blast radius, not throughput. Worth naming separately, because "isolation" and "parallelism" get conflated constantly, and they justify very different architectures.

If none of these three apply to what is being built, the extra agent is not solving a problem. It is decoration on an architecture diagram.

## Running the case study through the framework

Back to the five-piece developer-productivity system.

None of its agents needs more context than a single agent could hold. Reason one is out immediately.

That leaves reasons two and three, and they split the system in a revealing way.

**Attempt at the parallel case: inbox triage, file classification, and calendar planning.** Each pulls from a separate system — IMAP or notifications, filesystem watchers, CalDAV — and none needs another's output to do its job. Run them as three parallel workers under a supervisor, and the coordination cost buys real thoroughness. Three problems get solved at once instead of in sequence. Verdict: justified.

**Attempt at the same reasoning for the workspace provisioner.** In practice it depends on the file classifier having already run — it looks for a spec file the classifier already sorted into the right project folder. That is a handoff, not a peer relationship. Modeling it as just another parallel agent hides a real dependency. Modeling it explicitly as sequential-after-classification is the more honest design, and it is the detail a clean diagram tends to smooth over. Verdict: not parallel, and should not be modeled as if it were.

**The supervisor itself exists for the third reason: isolation.** If the calendar agent throws an exception, that should not take down file classification or inbox triage. Splitting them into separate processes under a supervisor, rather than one agent doing all four jobs, is what actually buys that isolation.

[DIAGRAM: devpulse-actual-topology-vs-full-mesh — see this folder's README for the source link]

Here is the payoff on the "10 possible links" figure from the introduction. This design uses 5 of them. Four are the supervisor's spokes to each functional agent — the isolation boundary, and the correct use of an agent split for reason three. The fifth is the classifier-to-provisioner handoff, a deliberate sequential dependency, not a peer link. The other 5 mathematically possible pairs — inbox-to-classifier, inbox-to-calendar, and so on — were never going to exist, because this is a hub-and-spoke design, not a mesh. The n(n−1)/2 formula gave the ceiling. Diagramming the real dependencies is what showed how far under that ceiling this design actually sits.

Four functional agents, justified by two different reasons: parallelism for three of them, isolation for the split itself. Plus one honest dependency that is not parallel at all. That is the kind of nuance the three-question framework is supposed to surface. Not "multi-agent good" or "multi-agent bad," but which specific link in this system earned its place, and which links the formula allowed for but the design correctly never used.

## The go/no-go checklist, made concrete

Run the actual decision through code, not vibes. `agent_decision_calculator.py`, in this folder's `src/`, implements exactly the three-question tree above.

**Attempt 1: the inbox-triage agent from the case study.**

```python
inbox_agent = DecisionInputs(
    exceeds_single_context_window=False,
    has_independent_parallelizable_subtasks=True,
    speedup_worth_coordination_cost=True,   # separate mail system, no dependency on the others
    needs_failure_isolation=False,
)
decision, reason = should_use_multi_agent(inbox_agent)
# -> (True, "parallel workers: subtasks are independent and the speedup earns the cost")
```

Verdict: multi-agent, justified.

**Attempt 2: a hypothetical sixth agent someone proposes adding.** A "notification summarizer" that just reformats what the inbox-triage agent already produced.

```python
notification_summarizer = DecisionInputs(
    exceeds_single_context_window=False,
    has_independent_parallelizable_subtasks=True,   # looks parallel on the whiteboard
    speedup_worth_coordination_cost=False,          # it is just reformatting, no real independent work
    needs_failure_isolation=False,
)
decision, reason = should_use_multi_agent(notification_summarizer)
# -> (False, "stay single-agent - add tools, not agents")
```

Verdict: stay single-agent.

Same first answer both times: subtasks look parallelizable. Different verdict, because the second attempt fails the honest follow-up question. Is the speedup actually worth the coordination cost, or does it just look parallel? That is the line most teams skip.

Full runnable code: `github.com/krpraveen0/linkedin-agent/tree/main/article-series-engine/series/multi-agent-systems-design/article-01-multi-agent-or-overkill`

## What this looks like Monday morning

Before opening a new file for `agent_2.py`, run the design through the three questions. The same way this article just ran the developer-OS case study through them.

Landing on "stay single-agent" does not mean building a smaller version of the multi-agent system that was planned. It means giving the one agent a better tool, a bigger context window, or a tighter loop. Adding tools is cheap. Adding agents is quadratic.

Landing on multi-agent means being as honest about the dependencies, like the provisioner's handoff above, as about the parallelism. A design that pretends a sequential handoff is a parallel worker will cost exactly where that pretense breaks.

The next article in this series picks up from here. Once the decision is genuinely multi-agent, the next question is how the agents coordinate — control, state, and communication, the three axes every orchestration pattern reduces to.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

*Part 1 of "Design Multi-Agent Systems." Next: The coordination primitives — control, state, and communication.*

## References

1. When to use multi-agent systems (and when not to), Anthropic
   https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them
