# What actually makes something an agent? A testable definition, not an analogy

*Every guide to AI agents opens with an analogy. A librarian versus a research assistant. A calculator versus an assistant. They're fine analogies, but none of them are testable. By the end of this article you'll have a function that actually tells you whether something is an agent - and you can run it yourself, no API key required.*

You don't need an API key for any of this. Every example below uses a plain Python stand-in for "the model decided X," so you can copy, paste, and run all of it right now. Step 6 shows you how to swap in a real model call once you're ready.

## Step 0: What you'll need

Python 3.9 or newer. That's genuinely it. Create a folder, and as you go through each step below, save each snippet as its own file - `step1_workflow.py`, `step2_fake_loop.py`, and so on. You'll run each one as soon as you write it.

## Step 1: The real distinction, from the source that actually matters

Before writing any code, here's the definition worth building around. Anthropic's own engineering team drew this line in their guide to building agents: workflows are systems where the model and tools get orchestrated through predefined code paths. Agents are systems where the model dynamically directs its own process and tool use, staying in control of how it accomplishes the task.

That's the real distinction. Not "uses an LLM" versus "doesn't." Not "loops" versus "doesn't." Predefined path versus a path the system actually decides for itself, based on what it observes.

Worth being upfront about something: even Anthropic's own three-way split of "agentic," "workflow," and "agent" isn't perfectly consistent across their own writing, and there's real, reasonable debate about where exactly the lines sit - you'll find serious critiques of the exact wording if you go looking. That's fine, and it's actually the point. This article isn't trying to settle the philosophical question of what "agent" should mean in every possible case. It's building one specific, checkable property - does the action sequence change when the environment does - that you can test against any system, including ones that call themselves agents and aren't, and ones that never use the word and are.

The problem with the analogy-only version of this definition: it gives you a feeling, not a check. This article turns it into something you can run.

## Step 2: Build something that is definitely NOT an agent (a workflow)

Save this as `step1_workflow.py`:

```python
def run_workflow(inbox: list[str]) -> list[str]:
    actions_taken = []

    actions_taken.append("fetch")
    fetched = inbox  # step 1 always runs

    actions_taken.append("summarize")
    summary = f"{len(fetched)} email(s)" if fetched else "no emails"  # step 2 always runs

    actions_taken.append("send")
    # step 3 always runs - even with nothing to say

    return actions_taken
```

Run it against two different inboxes:

```python
print(run_workflow(inbox=[]))
print(run_workflow(inbox=["urgent: server down"]))
```

Here's what you'll actually see:

```
['fetch', 'summarize', 'send']
['fetch', 'summarize', 'send']
```

Same three steps, in the same order, whether or not there's anything to do. This is a workflow by Anthropic's own definition - a predefined code path - and it's worth noticing that it "uses" the inbox as data without ever letting the inbox change *what* it does. That's the tell.

## Step 3: Build something that LOOKS like an agent, but isn't

This is the step most tutorials skip, and it's the one that actually matters. Save this as `step2_fake_loop.py`:

```python
def fake_llm_call(inbox: list[str], step_number: int) -> str:
    return f"model call #{step_number} on {len(inbox)} email(s)"

def run_fake_loop(inbox: list[str], num_iterations: int = 3) -> list[str]:
    actions_taken = []
    for i in range(num_iterations):
        fake_llm_call(inbox, i)
        actions_taken.append(f"model_call_{i}")
    return actions_taken
```

Run the same two-environment test:

```
['model_call_0', 'model_call_1', 'model_call_2']
['model_call_0', 'model_call_1', 'model_call_2']
```

This one has a loop. It "calls the model." It even looks more sophisticated than Step 2's workflow. And it fails the exact same way - `num_iterations` is fixed before the loop ever starts. Nothing about what's actually in the inbox changes how many times this runs, or what happens next. A loop that calls an LLM a predetermined number of times is still a predefined code path. It's just a workflow wearing an agent's clothes.

## Step 4: Build a real, minimal agent

Save this as `step3_real_agent.py`:

```python
from dataclasses import dataclass, field

@dataclass
class AgentState:
    inbox: list[str]
    fetched: list[str] = field(default_factory=list)
    summary: str | None = None
    sent: bool = False

def decide_next_action(state: AgentState) -> str:
    if not state.inbox:
        return "stop"
    if not state.fetched:
        return "fetch"
    if state.summary is None:
        return "summarize"
    if not state.sent:
        return "send"
    return "stop"

def run_agent(inbox: list[str], max_steps: int = 10) -> list[str]:
    state = AgentState(inbox=inbox)
    actions_taken = []
    for _ in range(max_steps):  # a safety cap - not the actual stop condition, more on this in Article 06
        action = decide_next_action(state)
        if action == "stop":
            break
        actions_taken.append(action)
        if action == "fetch":
            state.fetched = state.inbox
        elif action == "summarize":
            state.summary = f"{len(state.fetched)} email(s)"
        elif action == "send":
            state.sent = True
    return actions_taken
```

Run it:

```
[]
['fetch', 'summarize', 'send']
```

Look at that first line. Empty list. Given an empty inbox, this system decided - correctly - that there was nothing to do, and stopped immediately. It never even tried to fetch, summarize, or send. `decide_next_action` looked at the *current state* every single time, not a line number in the code, and the sequence of actions actually changed shape based on what it found.

`max_steps=10` up there is a safety cap, not the real stop condition - the real one is `decide_next_action` returning `"stop"` on its own. That distinction is worth sitting with for a second, because Article 06 in this series is entirely about what happens when that safety cap is the *only* thing standing between an agent and an infinite bill.

## Step 5: Write the actual test

This is the payoff. Save this as `step4_the_test.py`:

```python
def is_agentic(system, empty_env, real_task_env):
    actions_empty = system(empty_env)
    actions_real = system(real_task_env)

    if actions_empty == actions_real:
        return False, f"identical action sequence in both environments ({actions_empty})"
    return True, f"different action sequences: {actions_empty} vs {actions_real}"
```

Run it against all three systems from Steps 2 through 4:

```
Testing the workflow:      agentic: False - identical action sequence in both environments (['fetch', 'summarize', 'send'])
Testing the fake loop:     agentic: False - identical action sequence in both environments (['model_call_0', 'model_call_1', 'model_call_2'])
Testing the real agent:    agentic: True  - different action sequences: [] vs ['fetch', 'summarize', 'send']
```

That's the whole definition, made runnable. Not "does it use an LLM." Not "does it loop." Does the sequence of actions actually change shape when what's being observed actually changes? If yes, something is deciding at runtime. If no, no matter how many API calls happen inside it, it's a predefined path with extra steps.

<image src="file-upload://3a6c633a-e23a-8135-ad10-00b2f04a085e"></image>

## Step 6: Swapping in a real model (optional, for when you're ready)

Everything above runs with zero API calls on purpose - the point was the structure, not the model. When you're ready to make `decide_next_action` genuinely intelligent instead of a fixed if/else chain, the shape barely changes:

```python
def decide_next_action(state: AgentState) -> str:
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=50,
        messages=[{"role": "user", "content": f"Given this state: {state}, what should happen next: fetch, summarize, send, or stop? Answer with one word."}],
    )
    return response.content[0].text.strip().lower()
```

Same `is_agentic` test still applies. Same distinction still holds. The only thing that changed is which decision-maker is doing the deciding - a real model now, instead of a deterministic stand-in. You'll need your own API key for this part; everything else in this article runs without one.

## What this looks like today, not just Monday morning

Go look at something you've built, or something you're about to build, and ask honestly: if you fed it two meaningfully different situations, would the sequence of things it does actually change - or would it run the same steps either way, just with different data plugged in? If you're not sure, `is_agentic` from Step 5 will tell you in about ten lines.

That's the test to reach for the next time someone calls something an "agent" and you want to know if that's actually true, or just the word being used because it sounds better than "script." It's also worth reaching for before you reach for a framework. Every major agent framework out there - and you'll meet several of them across this series - is, underneath its own vocabulary, either giving you Step 4's shape (a real decision loop) or Step 1's shape (a configurable pipeline) wearing an agent-shaped name. Knowing which one you're actually looking at, in ten seconds, is worth more than memorizing what any single framework calls itself.

The next article in this series builds directly on the real agent from Step 4 - taking that same observe-decide-act loop and building it out properly, with real termination logic instead of a bare safety cap, and a bit more of an environment than a toy inbox to work with.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Fundamentals of AI Agents

1. **What actually makes something an agent? A testable definition, not an analogy** *(this article)*
2. The agent loop, built from scratch: observe, decide, act, and actually stop — not yet published
3. Tool use, for real: the mechanism behind "agents can take actions" — not yet published
4. Two things people call "memory," and why conflating them breaks agents — not yet published
5. Reactive vs. planning agents, and how to actually choose — not yet published
6. Stopping conditions: why "cap max_steps" is the least of it — not yet published
7. Evaluating a single agent: what to actually measure before you add a second one — not yet published
8. Building one real agent end to end, and what comes after it: multi-agent systems — not yet published

## References

1. Building Effective Agents, Anthropic
   https://www.anthropic.com/engineering/building-effective-agents
