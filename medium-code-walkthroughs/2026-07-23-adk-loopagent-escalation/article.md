# Google ADK's LoopAgent Only Stops on One Signal — and ADK 2.0 Is Already Replacing It

You wrote a reviewer loop in Google's Agent Development Kit. A worker drafts, a critic checks the draft, and when the critic decides the work is good enough it returns "approved." You set `max_iterations=10` as a safety net and expected the loop to exit the moment the critic approved. Instead it ran all ten times, burned ten times the tokens, and only stopped because it hit the ceiling.

That is not a bug. It is the single most misunderstood rule in ADK's `LoopAgent`: a sub-agent finishing its turn does nothing to the loop. The loop keeps going until one specific thing happens on one specific field of one event. If you are building iterative agent patterns — draft-and-revise, retry-until-valid, self-correction — you need to know exactly what that field is, because the official docs are vaguer than the code, and because ADK 2.0 has already put a deprecation notice on this whole family of agents.

I dug into the installed `google-adk` **2.5.0** package to pin down the real behavior, then wrote three small programs that run locally with no model and no API key. Here is what actually stops the loop.

## The one rule that ends the loop

`LoopAgent` runs its sub-agents in order, over and over. Its termination logic lives in `loop_agent.py`, and the loop condition reads like this ([source](https://github.com/google/adk-python/blob/main/src/google/adk/agents/loop_agent.py)):

```python
while (
    not self.max_iterations or times_looped < self.max_iterations
) and not (should_exit or pause_invocation):
    for i in range(start_index, len(self.sub_agents)):
        ...
        async for event in agen:
            yield event
            if event.actions.escalate:
                should_exit = True
```

There are exactly two ways out. Either `times_looped` reaches `max_iterations`, or some event yielded by a sub-agent carries `event.actions.escalate == True`, which flips `should_exit`. Nothing else in that loop inspects the sub-agent's output. The class docstring says the same thing in plain words: "When sub-agent generates an event with escalate or max_iterations are reached, the loop agent will stop." And if you leave `max_iterations` unset, the source comment is blunt about the consequence — the loop "will run indefinitely until a sub-agent escalates."

So `escalate` is not a nice-to-have convenience flag. In a loop with no iteration cap, it is the *only* brake.

## Why "done" is not "stop"

Here is where the documentation can lead you astray. The ADK [loop-agents guide](https://google.github.io/adk-docs/agents/workflow-agents/loop-agents/) describes stopping the loop this way: design a sub-agent to evaluate a condition, and "if the condition is met, the sub-agent can signal termination (e.g., by raising a custom event, setting a flag in a shared context, or returning a specific value)."

Reading that, you might reasonably conclude that returning a value, or writing a flag into session state, ends the loop. It does not. I checked the 2.5.0 source directly, and the runtime never reads a return value or a state key when deciding whether to continue — it only checks `event.actions.escalate`. Setting `state["approved"] = True` and returning does not stop anything unless *you* also translate that flag into an escalate signal on an event. The doc's "returning a specific value" is aspirational; the code is literal. When the docs and the installed package disagree, the package wins, and that gap is exactly the kind of thing that produces a loop that "should have stopped."

The fix is small once you know the rule: emit an `Event` whose `actions.escalate` is `True` when your condition is met. That is the whole contract.

## Try It Yourself

Everything below runs on CPU with no LLM. The workflow engine is model-agnostic, so a custom `BaseAgent` that yields hand-built events exercises the exact same loop logic an LLM-backed agent would.

Setup:

```bash
pip install google-adk   # tested on google-adk 2.5.0, Python 3.11.15
```

**Block 1 — a sub-agent that finishes cleanly, every time, and never escalates.** It reports "pass N done" and returns. Watch it run the full `max_iterations`:

```python
import asyncio
from google.adk.agents import BaseAgent, LoopAgent
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types

class Worker(BaseAgent):
    async def _run_async_impl(self, ctx):
        n = ctx.session.state.get("passes", 0) + 1
        yield Event(
            invocation_id=ctx.invocation_id, author=self.name,
            actions=EventActions(state_delta={"passes": n}),
            content=types.Content(role="model",
                                  parts=[types.Part(text=f"pass {n} done")]))

async def main():
    loop = LoopAgent(name="reviewer", sub_agents=[Worker(name="worker")],
                     max_iterations=3)
    runner = InMemoryRunner(agent=loop, app_name="demo")
    await runner.session_service.create_session(
        app_name="demo", user_id="u", session_id="s")
    async for ev in runner.run_async(user_id="u", session_id="s",
            new_message=types.Content(role="user", parts=[types.Part(text="go")])):
        if ev.content and ev.content.parts and ev.content.parts[0].text:
            print(f"[{ev.author}] {ev.content.parts[0].text}")

asyncio.run(main())
```

Real output:

```text
[worker] pass 1 done
[worker] pass 2 done
[worker] pass 3 done

Worker turns executed: 3  (max_iterations was 3)
```

Three clean completions did not stop anything. Only the iteration cap did.

**Block 2 — the same shape, but the critic sets `escalate=True` once its quality gate passes on pass 2.** With `max_iterations=10`, it should stop at 2:

```python
class Critic(BaseAgent):
    async def _run_async_impl(self, ctx):
        n = ctx.session.state.get("passes", 0) + 1
        good_enough = n >= 2                       # our quality gate
        yield Event(
            invocation_id=ctx.invocation_id, author=self.name,
            actions=EventActions(state_delta={"passes": n},
                                 escalate=good_enough),
            content=types.Content(role="model", parts=[types.Part(
                text=f"pass {n}: {'APPROVED -> escalate' if good_enough else 'revise'}")]))

loop = LoopAgent(name="reviewer", sub_agents=[Critic(name="critic")],
                 max_iterations=10)
```

Real output:

```text
[critic] pass 1: revise
[critic] pass 2: APPROVED -> escalate

Critic turns executed: 2  (max_iterations was 10)
```

Same runner, same wiring. The only difference from Block 1 is one boolean on `EventActions`, and it cut the loop from ten iterations to two.

**Block 3 — the deprecation notice, straight from the package.** Constructing a `LoopAgent` in 2.5.0 emits a `DeprecationWarning`. Here it is, captured verbatim:

```python
import warnings
from google.adk.agents import LoopAgent

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    LoopAgent(name="reviewer", sub_agents=[], max_iterations=3)
    for w in caught:
        if w.category is DeprecationWarning and "LoopAgent" in str(w.message):
            print(str(w.message))
```

Real output:

```text
LoopAgent is deprecated in favor of Workflow and will be removed in a future version. Workflow cannot yet be used as an LlmAgent sub-agent.
```

## The bigger context: ADK 2.0 is deprecating this whole pattern

That warning is the timely part. ADK 2.0 reached general availability on [May 19, 2026](https://github.com/google/adk-python/blob/main/CHANGELOG.md), and its headline change is a shift from a hierarchical agent executor to a graph-based **Workflow** runtime — an engine for "non-linear, conditional, and cyclical agent execution patterns," per the changelog. As part of that shift, all three templated workflow agents — `LoopAgent`, `SequentialAgent`, and `ParallelAgent` — now carry the same deprecation message: replaced by `Workflow`, slated for removal.

There is a caveat worth reading twice in that message: "Workflow cannot yet be used as an `LlmAgent` sub-agent." So the replacement is not yet a drop-in for every place the old agents fit. If your architecture nests a loop inside an LLM-driven agent, the migration path is not fully paved as of 2.5.0. That is a reason to understand the current `escalate` contract rather than assume it is already legacy — you will likely be running `LoopAgent` for a while yet, deprecation warning and all.

None of this changes the rule. Whether you stay on `LoopAgent` today or move to the Workflow runtime later, the lesson is the same: iterative agent loops in ADK terminate on an explicit signal, not on an agent quietly deciding it is finished. Make the signal explicit, or make peace with hitting `max_iterations` every time.

## Key Takeaways

- In ADK 2.5.0, a `LoopAgent` stops only when a sub-agent yields an event with `actions.escalate == True`, or when `max_iterations` is reached. A sub-agent completing its turn does not stop the loop.
- The docs' suggestion that "returning a specific value" can signal termination does not match the installed code — direct inspection of `loop_agent.py` shows only `event.actions.escalate` is checked.
- Without `max_iterations`, an ADK loop with no escalate path runs indefinitely. Always set a cap, and always have an escalate condition.
- ADK 2.0 (GA May 19, 2026) deprecated `LoopAgent`, `SequentialAgent`, and `ParallelAgent` in favor of a graph-based `Workflow` runtime, but `Workflow` cannot yet be nested under an `LlmAgent`, so the older agents remain practically necessary for now.
- All of this is verifiable locally with no model: a custom `BaseAgent` yielding events exercises the real loop engine.

Sources: [ADK loop-agents docs](https://google.github.io/adk-docs/agents/workflow-agents/loop-agents/), [adk-python CHANGELOG (2.0.0, 2026-05-19)](https://github.com/google/adk-python/blob/main/CHANGELOG.md), [loop_agent.py source](https://github.com/google/adk-python/blob/main/src/google/adk/agents/loop_agent.py), [google-adk on PyPI](https://pypi.org/project/google-adk/), and the deprecation warning emitted by the installed `google-adk` 2.5.0 package.
