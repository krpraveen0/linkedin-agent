# NVIDIA's NOOA Turns Your Agent Into One Python Class — and a `...` Method Body Into an LLM Call

Most agent frameworks make you learn their vocabulary before you write a line of logic: register a tool, hand it a JSON schema, wire a graph, configure a runner, thread state through a checkpointer. NVIDIA's NOOA throws that away and asks you to write a Python class. The fields are the agent's state, the methods are what it can do, the docstrings are the prompts, and the type hints are contracts the runtime enforces. The one genuinely strange part is what happens when you leave a method body empty. Write `...` and that method stops being ordinary Python; the runtime hands it to the model.

NVIDIA published NOOA (NVIDIA Object-Oriented Agents) on PyPI as version 0.0.8 on July 30, 2026, under Apache 2.0, alongside a paper describing the design ([PyPI](https://pypi.org/project/nooa/); [arXiv:2607.20709](https://arxiv.org/abs/2607.20709)). It is early. PyPI classifies 0.0.8 as an alpha, and NVIDIA calls it a research preview. But the programming model is unusual enough to be worth understanding now, and you can verify most of its claims yourself without an API key. That is what this article does.

## The claim, in NVIDIA's own words

The [project README](https://github.com/NVIDIA-NeMo/labs-OO-Agents) states the design in one line:

> "Agents are Python objects. Fields are state, methods are capabilities, docstrings are prompts, type annotations are contracts."

And the mechanism that ties an ordinary class to a language model:

> "A method with `...` becomes an agentic loop; a real body stays deterministic Python."

That second sentence is the whole trick. In a normal Python file, an ellipsis body is a placeholder: a stub you mean to fill in later, or a type-only declaration. NOOA repurposes it as a signal: *this method's implementation is the model's job.* A method with a real body runs as plain, deterministic Python. A method with `...` becomes a call to the LLM, driven by whatever you wrote in its signature and docstring.

The "why now" is not just the release date. NVIDIA's paper reports that a 253-line agent built this way reaches 82.2% on SWE-bench Verified with GPT-5.5, ahead of the roughly 78% it measured for the open harnesses it compared against, at roughly half the tokens ([arXiv:2607.20709](https://arxiv.org/abs/2607.20709), as summarized in [MarkTechPost, Aug 7, 2026](https://www.marktechpost.com/2026/08/07/nvidia-ai-releases-nooa-an-object-oriented-python-framework/)). I could not open the paper from my sandbox to re-derive those numbers, so treat the benchmark as reported-not-reproduced. The programming model below, though, I ran directly.

## What a NOOA agent looks like

Here is a complete agent. Not a snippet with the setup elided, but the whole thing.

```python
import nooa

class TicketTriage(nooa.Agent):
    """You are a customer-support triage agent. You are terse and precise."""

    async def urgent_count(self, tickets: list[dict]) -> int:
        """Count how many tickets have priority == 'high'."""
        ...   # the ellipsis body is the signal: NOOA fills this in with the LLM
```

There is no tool registry, no schema, no prompt template file. The class docstring is the system prompt. The method name and its docstring are the task. The `list[dict]` and `-> int` annotations tell the runtime what goes in and what must come out. The `...` says "ask the model."

One detail matters and is easy to miss: the generation method must be `async def`. NOOA's metaclass only rewrites coroutine functions into LLM-backed methods; a synchronous `def` with a `...` body is left alone and simply returns `None`. I found this the hard way: a sync version of `urgent_count` silently returned nothing until I made it `async`.

## Proving the class *is* the prompt — with no model call

You do not have to take the "docstrings are prompts" claim on faith. NOOA ships `nooa.print_prompt()`, which renders exactly what would be sent to the model for a given method and makes no network call while doing it. Its own docstring says it "Print[s] the prompts that would be sent to the LLM for *method*" using "real agent state and real arguments."

To construct an agent without a provider key, I used the library's built-in `FakeLLMClient`, whose docstring calls it "Fake LLM client that returns scripted responses ... Useful for hermetic testing without network calls." Rendering the prompt for `urgent_count` produced this — the docstring, verbatim, as the system prompt:

```text
=== SYSTEM PROMPT  [TicketTriage] ===

<system_prompt expr="self._resolve_system_prompt()">
You are a customer-support triage agent. You are terse and precise.
</system_prompt>
```

Further down the same output, the class itself is dropped into the context, rendered by calling `doc()` on the type:

```text
<self expr="doc(type(self))">
class TicketTriage:
    """You are a customer-support triage agent. You are terse and precise."""

    async def urgent_count(self, tickets: list[dict]) -> int:
        """Count how many tickets have priority == 'high'."""
</self>
```

The model does not see a synthesized description of your agent. It sees your class. That is a direct, checkable consequence of "docstrings are prompts, type annotations are contracts."

## How the agent actually acts: it writes Python

The README says "the model acts by writing Python in a Jupyter-style REPL with access to `self`, imports, and helpers." Inspecting the installed package confirms what that REPL is called internally: `nooa.get_default_strategy()` returns a `CodeActStrategy` object. In other words, out of the box the agent does not emit tool-call JSON; it writes code and runs it.

The rendered prompt spells out the contract the model works under. It is given exactly two tools:

```text
**Your two tools:**
- `execute_python(code)` — run a code cell
- `return_result(value)` — submit your final answer (also callable from inside `execute_python`)
```

and a list of things the sandbox will refuse:

```text
## Restrictions (will throw)

- `eval`, `exec`, `compile`, `__import__`, `input`, `breakpoint`
- `globals`, `locals`, `vars`, `asyncio.run`, `loop.run_until_complete`
- Attaching callables to the agent: `self.foo = fn`, `setattr(self, 'foo', fn)`, `type(self).foo = fn`
```

This is the CodeAct pattern with guardrails: the agent expresses its action as a Python cell, `execute_python` runs it, and `return_result` ends the turn. Because the final value flows back through a typed method, the `-> int` annotation is not decoration — it is the shape the runtime expects to hand you.

## Running the loop end to end, offline

To watch the loop run without a live model, I scripted a single response for `FakeLLMClient` — one `execute_python` call whose code computes the answer and passes it to `return_result`:

```python
import asyncio, json, nooa
from nooa.unifiedllm import FakeLLMClient, LLMResponse, ToolCall

code = "n = sum(1 for t in tickets if t['priority'] == 'high')\nreturn_result(n)"
scripted = [LLMResponse(
    raw_response={}, content="",
    tool_calls=[ToolCall(id="c1", name="execute_python",
                         arguments=json.dumps({"code": code}))],
    finish_reason="tool_calls",
    assistant_message={"role": "assistant", "content": ""},
)]

async def main():
    agent = TicketTriage(llm=FakeLLMClient(scripted_responses=scripted))
    tickets = [{"id": 1, "priority": "high"},
               {"id": 2, "priority": "low"},
               {"id": 3, "priority": "high"}]
    result = await agent.urgent_count(tickets)
    print("RESULT:", result, "| type:", type(result).__name__)

asyncio.run(main())
```

The scripted "model" wrote a comprehension, the runtime executed it, and the value came back through the typed method:

```text
RESULT: 2 | type: int
```

Two of three tickets are high priority, and the return type is a real `int`, not a string that happens to say `2`. The generated code ran inside NOOA's REPL, `return_result` closed the turn, and the type annotation on `urgent_count` was honored on the way out. (One implementation note for anyone reproducing this: `ToolCall.arguments` must be a JSON string — passing a raw dict raises `TypeError: the JSON object must be str, bytes or bytearray, not dict`, because the strategy calls `json.loads` on it.)

## Where this fits, and where it doesn't

The appeal is that an agent becomes an ordinary Python object, so ordinary Python tooling applies: you can subclass it, unit-test a deterministic method next to an LLM-backed one, trace calls, and keep the whole thing under version control without leaving the language. It is a genuinely different bet from the graph-and-registry frameworks that dominated 2026.

The costs are just as real. It is alpha software pinned to Python 3.12–3.13 (I had to build a 3.12 virtual environment; the default 3.11 could not install it). CodeAct means the model runs generated code, so the sandbox restrictions above are load-bearing, not cosmetic. And the headline benchmark is NVIDIA's own, measured with frontier models — worth noting, not worth building a roadmap on. What you can trust today is the programming model, because you can run it yourself in a few minutes.

## Try It Yourself

Everything above was produced by the code below. It needs no API key.

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install nooa
python triage_agent.py
```

The script prints the installed version and default strategy, then the rendered prompt, then the hermetic run. The real header of that run:

```text
nooa version: 0.0.8
default strategy: CodeActStrategy
```

If you have a provider key (any [LiteLLM](https://docs.litellm.ai/)-supported model — NVIDIA NIM, OpenAI, Anthropic), swap `FakeLLMClient` for a real client via `nooa`'s registry and the same `urgent_count` method will let an actual model write the counting code instead of a scripted stub. The class does not change.

## Key Takeaways

- **The class is the agent.** In NOOA, fields are state, methods are capabilities, docstrings are prompts, and type annotations are contracts — verified by `print_prompt()`, which shows the class docstring becoming the system prompt verbatim.
- **`...` is the switch.** An `async` method with an ellipsis body becomes an LLM-driven agentic loop; a method with a real body stays deterministic Python. A *synchronous* ellipsis method is not wired up and returns `None`.
- **CodeAct by default.** The installed package's default strategy is `CodeActStrategy`: the agent acts by writing Python in a sandboxed REPL with two tools, `execute_python` and `return_result`, and a concrete list of banned builtins.
- **Typed returns are enforced.** A `-> int` method returns a real `int`; the annotation shapes what `return_result` hands back.
- **It is early.** Version 0.0.8, Python 3.12–3.13 only, Apache 2.0. The 82.2% SWE-bench Verified claim is NVIDIA's, from the paper, and not independently reproduced here.

*Sources:* [NOOA on PyPI (v0.0.8, July 30, 2026)](https://pypi.org/project/nooa/) · [NVIDIA-NeMo/labs-OO-Agents README](https://github.com/NVIDIA-NeMo/labs-OO-Agents) · [NVIDIA OO Agents paper, arXiv:2607.20709](https://arxiv.org/abs/2607.20709) · [MarkTechPost coverage, Aug 7, 2026](https://www.marktechpost.com/2026/08/07/nvidia-ai-releases-nooa-an-object-oriented-python-framework/) · [LiteLLM docs](https://docs.litellm.ai/) · Runtime facts (version 0.0.8, `CodeActStrategy` default, rendered prompt, and `RESULT: 2` output) captured directly from the installed package.
