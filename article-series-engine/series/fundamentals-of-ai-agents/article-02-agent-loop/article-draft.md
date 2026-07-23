# The agent loop, built from scratch: observe, decide, act, and actually stop

*Article 01 built a real agent in about 20 lines and proved it was real with a runnable test. This article takes that same loop and builds it out properly - because "it stopped" and "it worked" are not the same thing, and most tutorials never show you the difference.*

Same deal as Article 01: no API key needed anywhere in this one. Everything runs as plain Python, and you'll see real output at every step.

## Step 0: What you'll need

Python 3.9+, and the four files from Article 01 if you want to compare - though this article is self-contained if you're starting fresh here.

## Step 1: The academic version of what you already built

Article 01's `decide_next_action` function - look at the current state, pick the next action - is a small, working version of something with a real name. In 2022, a paper called ReAct ("Synergizing Reasoning and Acting in Language Models," Yao et al., presented at ICLR 2023) formalized exactly this pattern: a model interleaves reasoning traces and actions in a repeating cycle - Thought, then Action, then Observation - using each action's result to update what it does next, continuing until a designated "finish" action signals it's done.

Line those three up against Article 01's loop and they match almost exactly: Thought is `decide_next_action` reasoning about the state, Action is calling `apply_action`, and Observation is reading the new state back before deciding again. The paper's actual contribution was showing that interleaving reasoning *with* actions - rather than planning everything up front, or acting without reasoning at all - measurably improved performance on tasks requiring external information, tested across question answering, fact verification, and interactive environments.

That's worth knowing, because it means the loop you built in Article 01 wasn't a toy simplification of something more sophisticated - it's structurally the same idea real agent research is built on. What Article 01 didn't do is handle the "continuing until it's done" part properly. That's this article.

## Step 2: Why "the loop ended" isn't good enough

Here's the gap. Article 01's loop had a `max_steps=10` safety cap, and a `decide_next_action` that could return `"stop"` on its own. Two ways to exit the loop. But if you only look at "did the loop end," you can't tell which one actually happened - and those two things mean completely different things about whether your agent is healthy.

This article gives you three distinct, labeled stop reasons instead of one silent loop exit:

```python
class StopReason(Enum):
    GOAL_ACHIEVED = "goal_achieved"       # decided it was done, on its own
    STUCK = "stuck_no_progress"           # repeating the same action, nothing changing
    MAX_STEPS = "max_steps_reached"       # the safety cap - NOT the same as done
```

Only one of these three actually means "it worked."

## Step 3: Add a way to detect no progress

Save this as `agent_loop.py`. The new piece, compared to Article 01, is a `snapshot()` method that captures everything about the state worth comparing, and a check in the loop itself:

```python
@dataclass
class AgentState:
    inbox: list[str]
    fetched: list[str] = field(default_factory=list)
    summary: str | None = None
    sent: bool = False

    def snapshot(self) -> tuple:
        return (tuple(self.fetched), self.summary, self.sent)

def run_agent(inbox: list[str], max_steps: int = 10) -> tuple[list[str], StopReason]:
    state = AgentState(inbox=inbox)
    history: list[str] = []
    last_snapshot = state.snapshot()

    for _ in range(max_steps):
        action = decide_next_action(state)
        if action == "stop":
            return history, StopReason.GOAL_ACHIEVED

        apply_action(state, action)
        new_snapshot = state.snapshot()

        if history and history[-1] == action and new_snapshot == last_snapshot:
            return history, StopReason.STUCK

        history.append(action)
        last_snapshot = new_snapshot

    return history, StopReason.MAX_STEPS
```

Run it on both of Article 01's environments:

```
Normal run, real task:
  actions: ['fetch', 'summarize', 'send']
  stopped because: goal_achieved

Normal run, nothing to do:
  actions: []
  stopped because: goal_achieved
```

Both correct, both labeled correctly. Neither of these is the interesting case, though. The interesting case is what happens when something's actually broken.

## Step 4: Introduce a real bug, on purpose

Save this as `broken_agents.py`. Here's a bug that's genuinely realistic - a typo where `apply_action` never actually updates the state it's supposed to:

```python
def buggy_decide_next_action(state: AgentState) -> str:
    if not state.inbox:
        return "stop"
    if not state.fetched:
        return "fetch"
    return "stop"

def buggy_apply_action(state: AgentState, action: str) -> None:
    if action == "fetch":
        pass  # BUG: forgot to actually set state.fetched
```

`decide_next_action` keeps seeing `state.fetched` as empty, forever, because the bug never sets it. Run this through the loop from Step 3:

```
Buggy agent, WITH loop detection:
  actions: ['fetch']
  stopped because: stuck_no_progress
  caught after just 2 identical, no-progress actions.
```

Two steps. Caught, labeled, done. Now run the *exact same bug* through a version of the loop that only has the `max_steps` cap and no snapshot comparison at all:

```
Same bug, WITHOUT loop detection (max_steps=10):
  actions: ['fetch', 'fetch', 'fetch', 'fetch', 'fetch', 'fetch', 'fetch', 'fetch', 'fetch', 'fetch']
  stopped because: max_steps_reached
  ran all 10 steps doing the exact same useless thing, and the
  stop reason gives you no signal that anything was wrong.
```

Same bug. Same starting inbox. Ten wasted steps instead of two, and a stop reason - `max_steps_reached` - that looks *identical* to what you'd see from a genuinely hard task that legitimately needed all ten steps. That's the actual danger of only having a step cap: it can't tell you "this broke" apart from "this was just hard." Every real API call those extra eight steps make is a real cost, for zero additional information.

Scale that up and it stops being an academic distinction. A single wasted loop costing eight extra model calls is a rounding error. A production agent hitting the same bug on a busy day, across hundreds of requests, with a step cap set to 25 instead of 10 "just to be safe," is a real, unplanned bill - and worse, one where the logs all say `max_steps_reached` and nobody can tell which of those runs were legitimately hard tasks and which were the exact same silent bug repeating itself hundreds of times. The two extra lines of loop-detection code in Step 3 are the entire difference between those two futures.

<image src="file-upload://3a6c633a-e23a-8187-83c4-00b2815b98af"></image>

## Step 5: What "actually stop" means, precisely

Three rules worth taking away from this, concretely:

1. **A step cap is not a stop condition. It's a circuit breaker.** Its job is to guarantee the loop ends eventually, not to tell you anything about whether the task succeeded.
2. **"Same action, same resulting state" is a cheap, real signal.** You don't need anything fancy to catch a stuck agent - a snapshot comparison and one `if` statement, as shown above, catches a real bug in two steps instead of ten.
3. **Every stop needs a reason attached, not just an exit.** `GOAL_ACHIEVED`, `STUCK`, and `MAX_STEPS` are not cosmetic labels - they're the difference between a log line you can act on and one you can't.

The obvious-looking wrong fix, worth naming directly: raising `max_steps` to something bigger. It feels like it should help - more chances for the agent to figure itself out - but it does the opposite for the specific bug in Step 4. A higher cap just means more wasted steps before the eventual, equally uninformative `max_steps_reached`. The fix was never about giving the loop more room. It was about the loop actually noticing when it wasn't going anywhere.

What you do with each stop reason once you have it also differs, and that's the other half of the point. `GOAL_ACHIEVED` needs no special handling - the task is done. `STUCK` is worth retrying once with a nudge (a different starting action, or a note in the next prompt that the previous approach didn't work) before giving up, since a real model's decision function might genuinely do better on a second attempt in a way this article's deterministic stand-in never will. `MAX_STEPS` is the one that deserves the most suspicion: it means the loop ran its full course without either finishing or getting caught as stuck, which is either a genuinely hard task or a failure mode this article's simple snapshot check didn't happen to catch - worth logging distinctly and looking at by hand, not silently retried the same way.

## What this looks like today

Take whatever loop you're running right now - a real agent, or even Article 01's toy version - and ask: if it got stuck in a way you haven't anticipated, would you be able to tell that apart from it simply taking a while? If the honest answer is "the logs would look the same either way," you've got exactly the gap this article closes, and the fix is smaller than it sounds: one snapshot method, one comparison, three labeled reasons instead of one silent exit.

Try it on purpose before you need it for real. Take your own loop, deliberately break one thing the way Step 4 did here - comment out a line that's supposed to update state, or hardcode a value that should change - and watch what your current stop-condition logic actually reports. If it says something as unhelpful as "completed" or just stops without telling you why, that's the same gap, in your own code, waiting for a real bug to find it instead of a deliberate one you planted yourself in five minutes.

The next article in this series picks up right where this one's loop leaves off: giving the agent real actions to take, not the hardcoded `if action == "fetch"` branches this article used as stand-ins - actual tool use, the mechanism behind "agents can call APIs."

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Fundamentals of AI Agents

1. What actually makes something an agent? A testable definition, not an analogy — not yet published
2. **The agent loop, built from scratch: observe, decide, act, and actually stop** *(this article)*
3. Tool use, for real: the mechanism behind "agents can take actions" — not yet published
4. Two things people call "memory," and why conflating them breaks agents — not yet published
5. Reactive vs. planning agents, and how to actually choose — not yet published
6. Stopping conditions: why "cap max_steps" is the least of it — not yet published
7. Evaluating a single agent: what to actually measure before you add a second one — not yet published
8. Building one real agent end to end, and what comes after it: multi-agent systems — not yet published

## References

1. Yao, S. et al. ReAct: Synergizing Reasoning and Acting in Language Models, ICLR 2023
   https://arxiv.org/abs/2210.03629
