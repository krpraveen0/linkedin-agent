# Reactive vs. planning agents, and how to actually choose

*Every guide mentions "reactive agents" and "planning agents" as two named things, side by side, and stops there. This article gives you a decision procedure - and shows one task where planning genuinely wins, and one where it genuinely fails, both verified by running actual code.*

## Step 0: What you'll need

Python 3.9+. No API key, same as the rest of this series.

## Step 1: The two real approaches, from the research behind them

Article 02 grounded this series' agent loop in ReAct - decide one step, act, observe the result, decide the next step. That's the reactive approach: the decision-maker gets consulted every single step, using the latest observation each time.

The alternative has its own name and its own paper: ReWOO ("Reasoning WithOut Observation," Xu et al., 2023) generates the *entire* plan up front - every step decided in one pass, before any tool actually runs - and only then executes the whole thing. The paper's own numbers make the appeal concrete: on a multi-step reasoning benchmark, this cut token usage by roughly 5x compared to the interleaved, reactive approach, because you're no longer paying for a full decision-maker call after every single step.

ReWOO's actual architecture has three named roles, worth knowing because they map cleanly onto real production systems: a Planner composes the full sequence of steps up front, using placeholders (like `#E1`, `#E2`) for results that don't exist yet; a Worker executes each step against the real tools and fills in those placeholders with actual data; a Solver takes the completed plan, now filled with real evidence, and produces the final answer. Nothing here goes back to the Planner mid-execution. That's the entire design, and it's also exactly where the tradeoff in Step 3 comes from.

Same underlying model, same tools available, two fundamentally different control structures. This article builds both and shows exactly where each one is the right call.

## Step 2: The case where planning wins, counted for real

Save this as `efficiency_case.py`. The task: fetch the weather for three cities, then compute the average.

```python
WEATHER_DATA = {"NYC": 68, "LA": 75, "Chicago": 61}

def fetch_weather(city: str) -> int:
    return WEATHER_DATA[city]

def run_reactive(cities: list[str]) -> tuple[list[str], int]:
    decision_calls = 0
    actions = []
    for city in cities:
        decision_calls += 1  # a real decision-maker call, every step
        actions.append(f"fetch({city})")
    decision_calls += 1
    actions.append("compute_average")
    return actions, decision_calls

def run_planning(cities: list[str]) -> tuple[list[str], int]:
    decision_calls = 1  # the entire plan, decided once
    plan = [f"fetch({city})" for city in cities] + ["compute_average"]
    return plan, decision_calls
```

Run both on the same three cities:

```
Reactive: ['fetch(NYC)', 'fetch(LA)', 'fetch(Chicago)', 'compute_average']
  decision-maker calls: 4

Planning: ['fetch(NYC)', 'fetch(LA)', 'fetch(Chicago)', 'compute_average']
  decision-maker calls: 1
```

Identical actions. Identical result. Four decision-maker calls versus one, because nothing about fetching NYC's weather changes what needs to happen for LA or Chicago - the whole sequence was knowable before any of it ran. This is exactly the shape of task ReWOO's real efficiency gain comes from: no branching, no step depending on a previous step's actual content, just a fixed sequence that happens to need external data plugged in.

## Step 3: The case where planning genuinely fails

Save this as `adaptability_case.py`. The task: check a server's status, and restart it only if it's actually down.

```python
def run_reactive(server_status: str) -> list[str]:
    actions = ["check_status"]
    observed = server_status  # standing in for a real health check
    if observed == "down":
        actions.append("restart")
    else:
        actions.append("no_action_needed")
    return actions

def run_planning_forced_upfront() -> list[str]:
    # the whole plan has to be committed BEFORE the real status is known
    return ["check_status", "restart"]
```

Run both when the server is actually fine:

```
Server is actually UP (the interesting case):
  reactive plan:  ['check_status', 'no_action_needed']  (correct - observed 'up', does nothing)
  fixed plan:     ['check_status', 'restart']  (WRONG - restarts a server that was never down,
                   because the plan was committed before the real status was ever known)
```

This is not a contrived weakness. It's ReWOO's own documented limitation, named directly in the research behind it: plans are sequential and pre-committed, so they cannot adapt mid-execution to something that was never known when the plan was made. The planning approach isn't broken in general - it's answering a question ("what's the whole sequence") that this specific task never actually has a fixed answer to, because the correct second step depends entirely on what the first step reveals.

<image src="file-upload://3a6c633a-e23a-8180-ba37-00b2fab8c2fd"></image>

## Step 4: The actual decision procedure

One question does almost all the work: **does the correct next step depend on what an earlier step actually returns?**

If no - if the whole sequence is knowable in advance, the way three independent weather lookups are - plan upfront. You get the same result for a fraction of the decision-maker calls, which is real money and real latency saved, not a theoretical benefit.

If yes - if there's a genuine branch where the right move depends on an observation that doesn't exist until a previous step has actually run - stay reactive. A fixed plan will guess, and guessing wrong here isn't a rare edge case, it's the default outcome whenever the plan's assumption doesn't match reality.

A few more worked examples to sharpen the question, since it's easy to think you know the answer and be wrong about a specific case. "Summarize these five documents, then translate the summary" - plannable, because the translation step doesn't need to know anything about the documents' actual content to know it needs to run; only its input changes, not whether it happens or what shape it takes. "Search for a flight, and if none are under budget, search a different date" - not plannable in the simple sense, because whether the second search happens at all depends entirely on what the first one actually returns. The test is never "does this step use the previous step's output" - almost every step does that. The test is whether the previous step's output could change *which* step comes next, not just what data that next step operates on.

## Step 5: Most real systems are neither, purely

It's worth being honest that a lot of real tasks aren't cleanly one or the other. A system might have three genuinely independent lookups (plan those) followed by one decision that depends on what those lookups actually found (stay reactive for that one step). The right design in that case is a hybrid: plan the decomposable part, and drop back into reactive, step-by-step decisions exactly at the one point where an observation actually needs to change what happens next - not everywhere, just there.

That's not a hedge to avoid picking a side. It's the same shape of finding that shows up constantly once you look closely at a real system: most of a task is one thing, and the interesting part is the one relationship that isn't.

Here's that hybrid, built rather than just described. Save this as `hybrid_case.py`. The task: fetch weather for three cities (nothing about any one fetch depends on another), then decide whether to send a rain alert - which genuinely depends on what actually got fetched.

```python
RAIN_DATA = {"NYC": False, "LA": False, "Chicago": True}

def run_hybrid(cities: list[str]) -> tuple[list[str], int]:
    decision_calls = 1  # ONE call plans the fetches - they don't depend on each other
    actions = [f"fetch({city})" for city in cities]

    rain_observed = any(RAIN_DATA[city] for city in cities)  # the actual observation

    decision_calls += 1  # ONE more call - but only because this step's
    # correct action genuinely depends on what was just observed
    if rain_observed:
        actions.append("send_rain_alert")
    else:
        actions.append("no_alert_needed")

    return actions, decision_calls
```

```
Hybrid: ['fetch(NYC)', 'fetch(LA)', 'fetch(Chicago)', 'send_rain_alert']
  decision-maker calls: 2
```

Two calls. Not Step 2's single planning call, because this task does have one genuine branch point. Not Step 2 reactive's four calls either, because three of the four steps never needed individual decisions in the first place. The plan handled what was actually plannable, and the one step that needed an observation got one. Correctly - Chicago's rain got noticed and the alert fired, which a plan committed before observing anything could not have guaranteed.

## Step 6: Why not just replan when something unexpected happens

A reasonable question at this point: why not plan upfront always, and just re-plan if execution reveals something the original plan didn't account for? This is a real, legitimate middle path production systems use, and it's worth naming honestly rather than pretending the choice is only ever "reactive" or "pure upfront planning."

The real cost of replanning is exactly what you'd expect: it gives back some of Step 2's efficiency gain in exchange for some of Step 3's adaptability. Every replan is a full decision-maker call, the same cost a reactive step pays - the difference is just how often you pay it. A task like Step 2's weather lookup never needs to replan at all, so it keeps its full efficiency advantage. A task shaped like Step 3's server check, if forced through a plan-then-replan structure, ends up paying close to reactive's full cost anyway, because the interesting decision - restart or not - is exactly the one point where the plan will turn out to be wrong and need redoing. Replanning is a genuine option, but it is not a way to avoid Step 4's question. It just moves where you pay for the answer.

## What this looks like today

Take a multi-step task you're building or have already built, and walk through it step by step asking Step 4's question at each transition: could I have known this step was needed before the previous one actually ran? If every single transition answers yes, you're very likely paying for reactive decision-making on a task that never needed it - Step 2's four-calls-versus-one gap, quietly repeating on every request. If even one transition answers no, forcing a fixed plan through it will eventually produce Step 3's exact failure: confidently doing the wrong thing because the plan committed to an answer before the real one existed.

Count your own decision-maker calls the way Step 2 and Step 5 did here, not just informally but as an actual number. It's a genuinely useful exercise to run once: take a real multi-step task your system handles today, and count how many separate decisions it actually made versus how many it strictly needed to make given which steps truly depended on which observations. The gap between those two numbers, if there is one, is exactly the cost this article is about - and it is usually smaller to close than it looks, since most of the fix is Step 5's hybrid pattern: plan what is genuinely plannable, and only drop back to a per-step decision at the one place an observation actually has to change what happens next.

The next article in this series goes deeper on the failure side of this: stopping conditions, and why "cap max_steps" - which Article 02 already showed isn't enough on its own - is really just the smallest piece of a much bigger production concern.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Fundamentals of AI Agents

1. What actually makes something an agent? A testable definition, not an analogy — not yet published
2. The agent loop, built from scratch: observe, decide, act, and actually stop — not yet published
3. Tool use, for real: the mechanism behind "agents can take actions" — not yet published
4. Two things people call "memory," and why conflating them breaks agents — not yet published
5. **Reactive vs. planning agents, and how to actually choose** *(this article)*
6. Stopping conditions: why "cap max_steps" is the least of it — not yet published
7. Evaluating a single agent: what to actually measure before you add a second one — not yet published
8. Building one real agent end to end, and what comes after it: multi-agent systems — not yet published

## References

1. Yao, S. et al. ReAct: Synergizing Reasoning and Acting in Language Models, ICLR 2023
   https://arxiv.org/abs/2210.03629
2. Xu, B. et al. ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models, 2023
   https://arxiv.org/abs/2305.18323
