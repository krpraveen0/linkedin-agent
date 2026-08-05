# Haystack 3.0 Gives You Two Ways to Loop an Agent. One Crashes When It Runs Away; the Other Just Stops and Hands You a Half-Finished Answer.

You wire up an agent loop, a bug in your exit condition means it never terminates, and you expect a stack trace. In Haystack 3.0 you might get one, or you might get a perfectly normal-looking return value that is quietly incomplete. Which of the two you get depends entirely on which of Haystack's two looping constructs you reached for, and the choice is easy to make without noticing.

Haystack 3.0 shipped its stable release to PyPI on [July 20, 2026](https://pypi.org/project/haystack-ai/), and the [3.0 Launch Week](https://haystack.deepset.ai/launch-week/haystack-3) put the `Agent` component at the center of the framework. That makes this a good moment to look at the safety net under an agent that misbehaves, because Haystack actually has two nets, they default to the same number, and they catch you in opposite ways.

## Two loops, two guards

There are two ways to build an iterative, tool-calling loop in Haystack 3.0.

The first is a **`Pipeline` with a cycle**: you connect a component's output back into the graph so it runs again, which is how looping RAG and self-correction pipelines are built. The scheduler protects you with a per-component run limit, `max_runs_per_component`.

The second is the **`Agent` component**: a self-contained loop that calls a chat model, runs whatever tools the model asked for, and repeats until an exit condition is met. It protects you with a step limit, `max_agent_steps`.

Both limits default to 100. That is the only thing they have in common. When a `Pipeline` hits its limit it raises an exception and the run dies. When an `Agent` hits its limit it writes a log line and returns normally. Everything below is that difference, verified against the installed `haystack-ai==3.0.0` package with no model, no API key, and no network at runtime.

## The pipeline loop crashes loudly

Here is a two-node cycle with no way out. A `BranchJoiner` merges the initial input with the value fed back around the loop, which is what lets Haystack form a cycle at all, and the `Worker` always hands its output straight back in. To make the boundary easy to read, the limit is set to 3 instead of the default 100.

```python
from haystack import component, Pipeline
from haystack.components.joiners import BranchJoiner
from haystack.core.errors import PipelineMaxComponentRuns

worker_runs = []

@component
class Worker:
    @component.output_types(value=int)
    def run(self, value: int):
        worker_runs.append(value)
        return {"value": value + 1}

pipe = Pipeline(max_runs_per_component=3)
pipe.add_component("loop", BranchJoiner(int))
pipe.add_component("worker", Worker())
pipe.connect("loop.value", "worker.value")
pipe.connect("worker.value", "loop.value")   # feed the result back in forever

try:
    pipe.run({"loop": {"value": 0}})
except PipelineMaxComponentRuns as e:
    print(f"RAISED {type(e).__name__}: {e}")

print(f"Worker.run executed {len(worker_runs)} times; values seen: {worker_runs}")
```

Running it prints:

```
RAISED PipelineMaxComponentRuns: Maximum run count 3 reached for component 'loop'
Worker.run executed 3 times; values seen: [0, 1, 2]
```

The `Worker` ran exactly three times and then the loop died. The count is not off by one by accident. Inside `haystack/core/pipeline/base.py`, the scheduler checks the limit *before* it lets a component run again:

```python
if item[0] < ComponentPriority.BLOCKED and comp["visits"] >= self._max_runs_per_component:
    msg = f"Maximum run count {self._max_runs_per_component} reached for component '{component_name}'"
    raise PipelineMaxComponentRuns(msg)
```

So a component with a limit of 3 completes runs on visits 0, 1, and 2, and the fourth time it comes up for scheduling its `visits` count is already 3, the check trips, and `PipelineMaxComponentRuns` is raised. The error names the joiner, `loop`, because in this cycle it is the component that reaches the cap first. The important part is that the whole `pipe.run(...)` call raises. You cannot miss it, and nothing downstream of the pipeline runs on a broken loop.

## The agent loop stops quietly

Now the same runaway condition, built with the `Agent` component. The `Agent` needs a chat generator, so this uses a stub that always asks to call a tool and never returns a plain-text reply. The `Agent`'s default exit condition is `"text"`, meaning it stops when the model returns a message with no tool calls. This stub never does that, so the exit condition is never met and the loop has no natural end. `max_agent_steps` is set to 5 to keep the output short.

```python
from haystack import component
from haystack.dataclasses import ChatMessage, ToolCall
from haystack.tools import Tool
from haystack.components.agents import Agent

@component
class NeverStopsGenerator:
    @component.output_types(replies=list[ChatMessage])
    def run(self, messages, tools=None, **kwargs):
        call = ToolCall(tool_name="noop", arguments={}, id="call-1")
        return {"replies": [ChatMessage.from_assistant(tool_calls=[call])]}

def noop() -> str:
    return "ok"

tool = Tool(name="noop", description="does nothing",
            parameters={"type": "object", "properties": {}}, function=noop)

agent = Agent(chat_generator=NeverStopsGenerator(), tools=[tool], max_agent_steps=5)
agent.warm_up()

result = agent.run(messages=[ChatMessage.from_user("go")])
print("RETURNED NORMALLY (no exception raised)")
print(f"step_count:       {result.get('step_count')}")
print(f"messages collected: {len(result.get('messages', []))}")
print(f"tool_call_counts: {result.get('tool_call_counts')}")
```

Running it prints:

```
WARNING haystack.components.agents.agent: Agent reached maximum agent steps of 5, stopping.
RETURNED NORMALLY (no exception raised)
step_count:       5
messages collected: 11
tool_call_counts: {'noop': 5}
```

There is no exception. The `Agent` ran its five steps, called the `noop` tool five times, wrote one `WARNING` line to the logger, and returned a normal result dictionary. The only signal that anything went wrong is that log line and a `step_count` that happens to equal `max_agent_steps`. This is exactly what the loop in `haystack/components/agents/agent.py` does:

```python
while exe_context.counter < self.max_agent_steps:
    if not self._run_step(exe_context, span):
        break
if exe_context.counter >= self.max_agent_steps:
    logger.warning(
        "Agent reached maximum agent steps of {max_agent_steps}, stopping.",
        max_agent_steps=self.max_agent_steps,
    )
```

After the `while` ends, whether it ended because an exit condition fired or because the step budget ran out, the method builds and returns the result either way. A "step," per the constructor's own docstring, is one chat-generator call plus the execution of every tool call the model requested in that call. Eleven messages here is the one user message plus five assistant tool-call messages plus five tool-result messages.

The reason this is worth calling out is that a partial agent result reads like a successful one. Your caller gets a well-formed dictionary with messages in it. If you are not checking `step_count` against `max_agent_steps`, or watching for that warning in your logs, a truncated run looks the same as a completed one to the code that consumes it. The pipeline's crash is annoying; the agent's silent truncation is the one that ships to production and returns a confident, incomplete answer.

## Same number, opposite behavior

You do not have to take the demos' word for the defaults. Read them straight out of the installed package:

```python
import inspect
import haystack
from haystack import Pipeline
from haystack.components.agents import Agent

print(f"haystack-ai version: {haystack.__version__}")

pipe_default = inspect.signature(Pipeline.__init__).parameters["max_runs_per_component"].default
agent_default = inspect.signature(Agent.__init__).parameters["max_agent_steps"].default

print(f"Pipeline.max_runs_per_component default: {pipe_default}")
print(f"Agent.max_agent_steps default:           {agent_default}")
print(f"same default value? {pipe_default == agent_default}")
```

```
haystack-ai version: 3.0.0
Pipeline.max_runs_per_component default: 100
Agent.max_agent_steps default:           100
same default value? True
```

Both are 100. The number is identical; the consequence of reaching it is not. And the two can stack: an `Agent` is itself a component, so if you drop one inside a `Pipeline`, the `Agent`'s internal steps are bounded by `max_agent_steps` while the pipeline separately bounds how many times the whole `Agent` component is scheduled, each with its own failure mode.

The practical takeaway is to treat `max_agent_steps` as a real branch in your code, not a safety default you can ignore. Check whether the run actually finished:

```python
result = agent.run(messages=[ChatMessage.from_user(question)])
if result["step_count"] >= agent.max_agent_steps:
    raise RuntimeError("agent hit its step budget without reaching an exit condition")
```

## Try It Yourself

Everything above runs offline. One install, three scripts, no keys.

```bash
python3 -m venv .venv
./.venv/bin/pip install "haystack-ai==3.0.0"

./.venv/bin/python demo1_pipeline_crashes.py       # raises PipelineMaxComponentRuns
./.venv/bin/python demo2_agent_stops_quietly.py    # returns normally, step_count == 5
./.venv/bin/python demo3_defaults_from_package.py   # both defaults are 100
```

The pipeline demo will print a raised `PipelineMaxComponentRuns` and confirm the worker ran exactly three times. The agent demo will print a single `WARNING` line and a normal result with `step_count: 5`. The behavior is not a claim from a blog post; it comes straight out of the package you just installed, and you can re-read the guard in `haystack/core/pipeline/base.py` and the agent loop in `haystack/components/agents/agent.py` to confirm it.

## Key Takeaways

- Haystack 3.0 (stable on PyPI July 20, 2026) has two independent runaway-loop guards: `Pipeline`'s `max_runs_per_component` and `Agent`'s `max_agent_steps`. Both default to 100.
- A `Pipeline` cycle that never exits **raises `PipelineMaxComponentRuns`** and the whole run dies. A component with a limit of N runs exactly N times, and the next scheduling attempt raises.
- An `Agent` whose exit condition is never met **does not raise**. It runs up to `max_agent_steps`, logs one warning, and returns a normal-looking partial result with `step_count` equal to the limit.
- Because a truncated agent result is shaped like a complete one, check `result["step_count"]` against `max_agent_steps` (or watch for the warning) instead of assuming a returned value means the agent finished.
- If you nest an `Agent` inside a `Pipeline`, both limits apply at different granularities, with different failure modes.

## Sources

- [haystack-ai on PyPI](https://pypi.org/project/haystack-ai/) — version 3.0.0 uploaded 2026-07-20 (release date confirmed via PyPI's JSON API, `upload_time_iso_8601`)
- [Haystack 3.0 Launch Week](https://haystack.deepset.ai/launch-week/haystack-3) — the release that moves agents to the center of the framework
- [Haystack Pipeline Loops documentation](https://docs.haystack.deepset.ai/docs/pipeline-loops) — `max_runs_per_component` and `PipelineMaxComponentRuns`
- [Haystack Agent documentation](https://docs.haystack.deepset.ai/docs/agent) — `max_agent_steps` and `exit_conditions`
- Direct inspection of the installed `haystack-ai==3.0.0` package (verified 2026-08-05): the guard in `haystack/core/pipeline/base.py`, the `PipelineMaxComponentRuns` class in `haystack/core/errors.py`, and the step loop plus warning in `haystack/components/agents/agent.py`
