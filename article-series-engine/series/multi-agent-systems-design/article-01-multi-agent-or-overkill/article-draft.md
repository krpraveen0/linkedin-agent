# Multi-agent or overkill? A decision framework before you add a second agent

*Most teams reach for a second agent before they've exhausted what one agent with the right tools can do. This is the framework I use to catch that, before the coordination bill comes due.*

[PLACEHOLDER — Praveen: drop in the real moment here. A specific point on
AEGIS-v2, or any project, where you were about to add another agent and
either caught yourself or didn't. The skill's own rule: no anecdote, no
article — this needs your real detail before it ships.]

## The question nobody asks before the design doc

Multi-agent architecture diagrams are everywhere right now — boxes, arrows, a supervisor node with three or four workers hanging off it. What's missing from almost all of them is the one paragraph that should come *before* the diagram: why does this need to be more than one agent?

Anthropic's own engineering team, who have shipped more production multi-agent systems than almost anyone, put a number on what skipping that question costs: multi-agent implementations typically use 3 to 10 times more tokens than single-agent approaches for the same task. Not a marginal tax — a multiplier. Every additional agent is another prompt to maintain, another context boundary where information gets lossy, another thing that can silently misbehave.

That's not an argument against multi-agent systems. It's an argument for making the "why" explicit before you pay the cost.

## The coordination-cost model

Here's the part of the math that's easy to miss when you're staring at a clean architecture diagram: coordination cost doesn't grow linearly with agent count. The number of potential coordination links between agents grows as *n(n−1)/2* — the classic pairwise-interaction count.

- 2 agents → 1 potential link
- 4 agents → 6 potential links
- 10 agents → 45 potential links

That's not a measured failure rate — it's a lower bound on surface area, the number of places a handoff, a race, or a context-loss bug *can* occur. Real failure rates will vary by design. But the shape of the curve doesn't lie: it's quadratic, not linear, and it's the reason a system that worked cleanly at 3 agents can become genuinely hard to reason about at 8.

[DIAGRAM: multi-agent-or-overkill-decision-tree — see /diagrams, source linked in this folder's README]

## The three legitimate reasons to add an agent

Strip away the hype and there are exactly three defensible reasons to go multi-agent, and each one earns the coordination cost differently:

**1. The task exceeds a single agent's context window.** Not "it would be cleaner to split this up" — it genuinely doesn't fit. A coding agent reasoning across a 500-file codebase while running tests and tracking a long task history will hit a wall no matter how good the model is. Splitting by bounded, focused scope is the fix, and it's a real fix, not an aesthetic one.

**2. You have independent, parallelizable subtasks, and the speedup is worth the coordination cost.** The operative word is *independent*. If agent B needs agent A's output before it can start, you don't have parallelism — you have a slower, more expensive sequential pipeline wearing a parallel architecture's clothes. Anthropic's own framing here is useful: multi-agent parallelism buys you *thoroughness*, not speed — total token spend goes up even when wall-clock time goes down, because you're covering more ground, not doing the same work faster.

**3. You need failure isolation.** One agent's mistake must not be able to cascade into another's work. This is the one reason that's about blast radius, not throughput — and it's worth naming separately, because "isolation" and "parallelism" get conflated constantly, and they justify very different architectures.

If none of these three apply to what you're building, the extra agent isn't solving a problem — it's decoration on an architecture diagram.

## The go/no-go checklist, made concrete

Run the actual decision through code, not vibes. `agent_decision_calculator.py` (in this folder's `src/`) implements exactly the three-question tree above:

```python
inputs = DecisionInputs(
    exceeds_single_context_window=False,
    has_independent_parallelizable_subtasks=True,
    speedup_worth_coordination_cost=False,   # <- this is the honest answer that kills most designs
    needs_failure_isolation=False,
)
decision, reason = should_use_multi_agent(inputs)
# -> (False, "stay single-agent - add tools, not agents")
```

The line that matters most in that checklist isn't "are there parallel subtasks" — plenty of tasks look parallelizable on a whiteboard. It's the next question: is the speedup *actually worth* the coordination cost you just modeled above? Most teams answer the first question honestly and skip the second.

Full runnable code: `github.com/krpraveen0/linkedin-agent/tree/main/article-series-engine/series/multi-agent-systems-design/article-01-multi-agent-or-overkill`

## What this looks like Monday morning

Before you open a new file for `agent_2.py`, run your own design through the three questions. If you land on "stay single-agent," the fix usually isn't a smaller version of the multi-agent system you were about to build — it's giving your one agent a better tool, a bigger context window, or a tighter loop. Adding tools is cheap. Adding agents is quadratic.

The next article in this series picks up from here: once you've decided you genuinely need more than one agent, the next decision is *how they coordinate* — control, state, and communication, the three axes every orchestration pattern reduces to.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

*Part 1 of "Design Multi-Agent Systems." Next: The coordination primitives — control, state, and communication.*
