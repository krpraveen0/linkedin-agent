# Pydantic AI's Retry Budget Is Now Two Budgets — and Here's the Exact Message It Sends Your Model When Output Fails

Your agent asks the model for an order id. The model returns `ORD-77`. Your validator wanted lowercase. In most frameworks that is a raised exception and a dead run. In [Pydantic AI](https://ai.pydantic.dev/), it is a conversation: the framework quietly turns your validation error into a message, sends it back to the model, and lets the model try again. What surprised me when I looked closely is *what* it sends back, and the fact that as of the current release the retry allowance is no longer one number — it is two independent budgets, one for tools and one for output.

Pydantic AI `2.18.0` landed on [PyPI](https://pypi.org/project/pydantic-ai/) on 2026-07-25, two days before this was written; the project has shipped a release almost every day this week (`2.14.0` on 2026-07-21 through `2.18.0` on 2026-07-25). The retry model described here is the one in that release, verified by running it rather than by trusting the docs.

## The retry is a real message, not a silent loop

When a tool's arguments fail validation, or a tool or output validator raises `ModelRetry`, Pydantic AI builds a [`RetryPromptPart`](https://ai.pydantic.dev/tools-advanced/#tool-retries) "containing the validation details" and, in the docs' words, "sent back to the LLM, informing it of the error and allowing it to correct." That is the whole self-correction mechanism: the exception message you write *is* the instruction the model reads.

That has a practical consequence people miss. The string you pass to `ModelRetry(...)` is not a log line for you — it is a prompt for the model. Write `raise ModelRetry("bad")` and the model gets "bad." Write a specific correction and the model gets a specific correction. I wanted to see the exact object, so I drove an agent with `FunctionModel` — Pydantic AI's built-in fake model that returns whatever Python you script, with no API key and no network — and read the message the framework injected between the model's two turns. The captured `RetryPromptPart` carried my exact validator text, a `part_kind` of `retry-prompt`, and `tool_name=None` because it came from an output validator rather than a named tool. The full run is in the "Try It Yourself" section below.

## Two budgets, not one

Here is the part worth updating your mental model for. Retrying forever would be a great way to burn tokens on a model that will never comply, so there is a budget. Until you look, it is natural to assume that budget is a single "number of retries" for the whole run. It is not.

Pydantic AI tracks a **tools** budget and an **output** budget separately. Both [default to 1](https://ai.pydantic.dev/api/agent/). You set them with the `retries` argument: pass a bare `int` and it sets both, or pass an `AgentRetries` dict such as `retries={'tools': 3, 'output': 1}` to set them individually. From the `Agent.__init__` docstring in the installed package:

> `retries`: Per-category retry budgets for tools and output validation. Pass an `int` to set the same budget for both, or an `AgentRetries` dict to set them individually (e.g. `retries={'tools': 3, 'output': 1}`). Defaults to 1 for both.

The two pools also behave differently when they run dry. The tool path is tracked **per tool** — "every function tool has its own counter, with no global 'tool call' budget shared across the run," per the [tool docs](https://ai.pydantic.dev/tools-advanced/#tool-retries). When one tool exhausts its counter, the run raises `UnexpectedModelBehavior` naming that tool. The output path has a single global budget for the run's output validation; exhaust it and you get a different `UnexpectedModelBehavior` message. Both are shown, captured, below.

There is also a per-run override — `agent.run(retries={'tools': N})` and its `run_sync`/`run_stream`/`iter` siblings — layered above the agent-wide default but below any explicit per-tool `Tool(max_retries=N)` or `ToolOutput(max_retries=N)`. The docs publish the [full precedence table](https://ai.pydantic.dev/tools-advanced/#tool-retries); the short version is that the more specific setting wins, and a bare `int` at any layer touches both budgets while a dict touches only the keys it names.

One more distinction that pairs with this: `ModelRetry` consumes budget, but its sibling [`ToolFailed`](https://ai.pydantic.dev/tools-advanced/#tool-retries) does **not**. `ToolFailed` reports a tool result to the model as a failure without drawing down the retry counter — you reach for it when the call is genuinely done and failed, versus `ModelRetry` when you want another attempt. Bounding repeated `ToolFailed`s is then the job of `UsageLimits`, not the retry budget.

## Try It Yourself

Everything below runs on `pydantic-ai==2.18.0` with **no API key** — `FunctionModel` stands in for a real model and returns scripted responses, so every message the framework constructs is fully observable.

```bash
python -m venv venv && . venv/bin/activate
pip install "pydantic-ai==2.18.0"
```

**1. Capture the exact message sent back on an output failure.** The fake model returns `ORD-77` first, then `ord-77`; the output validator rejects anything not lowercase.

```python
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, RetryPromptPart

replies = iter(["ORD-77", "ord-77"])
seen_requests = []

def scripted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    seen_requests.append(messages)          # record what the framework sent us
    return ModelResponse(parts=[TextPart(next(replies))])

agent = Agent(FunctionModel(scripted_model), output_type=str)

@agent.output_validator
def must_be_lowercase(text: str) -> str:
    if text != text.lower():
        raise ModelRetry(f"'{text}' is not lowercase; return the id in lowercase.")
    return text

result = agent.run_sync("Give me the order id.")
print("FINAL OUTPUT:", repr(result.output))
print("MODEL WAS CALLED:", len(seen_requests), "times")
for part in seen_requests[1][-1].parts:
    if isinstance(part, RetryPromptPart):
        print("RETRY PART SENT BACK ->", repr(part.content))
        print("part_kind:", part.part_kind, "| tool_name:", part.tool_name)
```

Real output:

```
FINAL OUTPUT: 'ord-77'
MODEL WAS CALLED: 2 times
RETRY PART SENT BACK -> "'ORD-77' is not lowercase; return the id in lowercase."
part_kind: retry-prompt | tool_name: None
```

The validator string reached the model verbatim. That is the entire self-correction loop.

**2. Exhaust the output budget and read the exception.** Same idea, but the model never complies and we allow only two output retries.

```python
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart

def always_uppercase(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("STILL-UPPER")])   # never complies

agent = Agent(FunctionModel(always_uppercase), output_type=str, retries={"output": 2})

@agent.output_validator
def must_be_lowercase(text: str) -> str:
    if text != text.lower():
        raise ModelRetry("must be lowercase")
    return text

print("stored output budget:", agent._max_output_retries)
print("stored tool budget:  ", agent._max_tool_retries)
try:
    agent.run_sync("go")
except UnexpectedModelBehavior as e:
    print("RAISED:", type(e).__name__, "->", e)
```

Real output:

```
stored output budget: 2
stored tool budget:   1
RAISED: UnexpectedModelBehavior -> Exceeded maximum output retries (2)
```

Note the tool budget stayed at its default `1` while the output budget was `2` — the two are stored independently.

**3. Prove the tool budget is a separate pool.** Now a tool keeps raising `ModelRetry`; we set `tools=3` and count how many times it actually runs.

```python
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart

tool_calls = {"n": 0}

def keep_calling_tool(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name="lookup", args={})])

agent = Agent(FunctionModel(keep_calling_tool), output_type=str, retries={"tools": 3})

@agent.tool_plain
def lookup() -> str:
    tool_calls["n"] += 1
    raise ModelRetry("not found, try again")   # always fails

print("stored tool budget:", agent._max_tool_retries, "| output budget:", agent._max_output_retries)
try:
    agent.run_sync("look it up")
except UnexpectedModelBehavior as e:
    print("RAISED:", type(e).__name__, "->", e)
print("tool actually executed:", tool_calls["n"], "times (1 initial + 3 retries)")
```

Real output:

```
stored tool budget: 3 | output budget: 1
RAISED: UnexpectedModelBehavior -> Tool 'lookup' exceeded max retries count of 3. Consider raising the retry limit, or see the docs on tool retries: https://ai.pydantic.dev/tools-advanced/#tool-retries
tool actually executed: 4 times (1 initial + 3 retries)
```

The tool ran four times — the initial call plus three retries — and the exception names the tool, not a generic "run" limit. The output budget stayed at `1` the entire time.

## Why this matters when you tune it

The split is not cosmetic. Tool retries and output retries protect against different failures. A tool that raises `ModelRetry` is often talking to the outside world — a lookup that might legitimately need the model to reformulate its query a few times. Output validation, by contrast, is you enforcing a shape on the final answer; if the model can't produce lowercase after two tries, a third rarely helps and just costs tokens. Because the budgets are independent, you can be generous with one and strict with the other: `retries={'tools': 4, 'output': 1}` says "let the tools negotiate, but I trust the output rules to be quickly satisfiable or not at all."

If you had assumed a single shared counter, you would have tuned the wrong dial. Setting `retries=4` to give a flaky tool room also quietly hands your output validators four attempts each, multiplying token spend on outputs that were never going to converge. The two-budget model exists precisely so you don't have to make that trade.

## Key Takeaways

- Pydantic AI turns a raised `ModelRetry` (or a validation failure) into a `RetryPromptPart` and sends it back to the model — the string you raise is a prompt the model reads, so write it for the model.
- As of `2.18.0` (released 2026-07-25) the retry allowance is two independent budgets: `tools` and `output`, both defaulting to `1`. Pass `retries={'tools': N, 'output': M}` to set them separately; a bare `int` sets both.
- Tool retries are tracked per tool and raise `UnexpectedModelBehavior` naming the tool; output retries share one global budget and raise `Exceeded maximum output retries (N)`. Both messages here were captured from real runs, not the docs.
- `ModelRetry` spends budget; `ToolFailed` does not — use `ToolFailed` when a call is genuinely done and failed.
- `FunctionModel` lets you verify all of this deterministically with no API key, which is how these outputs were produced.

*Caveat: this walkthrough validates the retry mechanics and message shapes against a real run of `pydantic-ai==2.18.0`; API details can change between the near-daily releases, so re-check the version you install.*

**Sources:** [Pydantic AI — Advanced Tool Features / tool retries](https://ai.pydantic.dev/tools-advanced/#tool-retries), [Pydantic AI — Output docs](https://ai.pydantic.dev/output/), [Pydantic AI — Agents docs](https://ai.pydantic.dev/agents/), [pydantic-ai on PyPI (2.18.0, 2026-07-25)](https://pypi.org/project/pydantic-ai/), and direct inspection of the installed `pydantic-ai==2.18.0` package.
