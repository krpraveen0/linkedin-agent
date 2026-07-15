# Pydantic AI v2 Turned Every Agent Extension Point Into One Object. Here's What a "Capability" Actually Does.

In Pydantic AI v1, the pieces you bolted onto an agent all looked different. A tool was a decorated function. An instruction was a string. A lifecycle hook barely had a home. Model settings were a keyword argument. Each extension point had its own shape, and wiring several of them together meant threading four unrelated concepts through your agent definition.

[Pydantic AI v2](https://pydantic.dev/articles/pydantic-ai-v2), released June 23, 2026, collapses all of that into a single primitive: the **capability**. Tools, instructions, hooks, and model settings are now the same kind of object, and you compose an agent by dropping capabilities into one list. That is the headline change, and it is the kind of claim that is easy to nod along to and hard to actually picture. So I installed v2 and built a small agent entirely out of capabilities — no API key, fully deterministic — to see what the abstraction buys you when you run it.

## What the docs claim

The [official v2 announcement](https://pydantic.dev/articles/pydantic-ai-v2) describes a capability as a single composable unit that bundles an agent's tools, hooks, instructions, and model settings, reaching every layer of the agent through one concept. Some capabilities ship inside Pydantic AI; more come from a first-party **Pydantic AI Harness** that packages things like memory, guardrails, context management, filesystem access, and a code-execution mode as capabilities you opt into ([AlphaSignal's writeup](https://alphasignal.ai/news/pydantic-ai-v2-ships-a-single-primitive-that-rebuilds-how-agents-work) frames it as "a single primitive that rebuilds how agents work").

That is the pitch. Before trusting it, I checked what the installed package actually exposes rather than what the blog posts say. On `pydantic-ai` 2.9.1, the top-level package exports `AgentCapability`, `CapabilityFunc`, and a `capabilities` submodule, and `Agent.__init__` has a real `capabilities` keyword argument. The submodule ships concrete capability types with names that map straight onto the marketing: `Toolset`, `Hooks`, `Instrumentation`, `WebSearch`, `MCP`, `ToolSearch`, and more. This is not a rename of v1's toolsets — it is a genuinely wider abstraction, and it is really there in the shipped code.

## The one thing worth internalizing

The mechanically interesting part is that a single capability can carry more than one kind of extension at once. A `Toolset` capability, for example, takes both the tools *and* the instructions that explain when to use them. That means the guidance and the callable that guidance refers to travel together as one unit, instead of living in two different arguments that you have to keep in sync by hand.

Here are the two capabilities I built. The first bundles a tool with its own instructions; the second is a pure lifecycle hook that counts model requests without touching the agent body at all.

```python
from pydantic_ai import FunctionToolset
from pydantic_ai.capabilities import Toolset, Hooks

def word_count(text: str) -> int:
    """Count the words in a piece of text."""
    return len(text.split())

# Capability #1: a Toolset carrying a tool AND its instructions together.
tools_cap = Toolset(
    FunctionToolset(
        tools=[word_count],
        instructions="If asked how long some text is, call word_count.",
    ),
    id="word-tools",
)

# Capability #2: lifecycle hooks. Counts model requests, no agent code needed.
request_count = {"n": 0}

def count_requests(ctx, request_context):
    request_count["n"] += 1
    return request_context  # hooks return the (possibly modified) context

audit_cap = Hooks(before_model_request=count_requests, id="audit")
```

Note the shape of both objects: they are values, not decorators glued to your agent class. `tools_cap` and `audit_cap` are plain variables you can pass around, store in a list, or reuse. That portability is the whole point, and I will come back to it.

## Composing and running the agent

To keep the run deterministic and free of any API dependency, I drove the model with Pydantic AI's `FunctionModel`, which lets you supply an ordinary Python function in place of a real LLM. My fake model does two things on its first turn: it prints what instructions and tools it was handed (so we can confirm the capability actually delivered them), then it emits a tool call. On the second turn it returns a final answer.

```python
from pydantic_ai import Agent
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart

def fake_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    already_called = any(
        p.part_kind == "tool-return" for m in messages for p in m.parts
    )
    if not already_called:
        print("instructions seen by model :", repr(info.instructions))
        print("tools seen by model        :", [t.name for t in info.function_tools])
        return ModelResponse(parts=[ToolCallPart("word_count", {"text": "one two three"})])
    return ModelResponse(parts=[TextPart("The text has 3 words.")])

# The agent is composed purely from capabilities.
agent = Agent(FunctionModel(fake_model), capabilities=[tools_cap, audit_cap])
result = agent.run_sync("How long is 'one two three'?")
print("final output               :", result.output)
print("model requests (via hook)  :", request_count["n"])
```

The agent definition is one line, and it contains no tools, no instructions, and no hooks directly. Everything comes from the `capabilities` list. Running it produces:

```
instructions seen by model : 'If asked how long some text is, call word_count.'
tools seen by model        : ['word_count']
final output               : The text has 3 words.
model requests (via hook)  : 2
```

Three things are confirmed in that output. The instruction string reached the model, and it came from inside the `Toolset` capability, not from an `instructions=` argument on the agent. The `word_count` tool reached the model from the same capability. And the `audit_cap` hook fired twice — once for the tool-calling turn and once for the final answer — proving the lifecycle hook was wired in purely by being an item in the list. Tools, instructions, and hooks all entered through one door.

## Why "one object" is more than tidiness

The unification would be a cosmetic win if capabilities were stuck to the agent that declared them. They are not. A capability is a free-standing value, so the same object plugs into unrelated agents. I defined one `Hooks` capability and shared it across two agents with different jobs, backed by `TestModel` (Pydantic AI's canned-response test model) so nothing hits a network:

```python
from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai.models.test import TestModel

calls = {"n": 0}
def count_requests(ctx, request_context):
    calls["n"] += 1
    return request_context

audit_cap = Hooks(before_model_request=count_requests, id="audit")

translator = Agent(TestModel(custom_output_text="bonjour"), capabilities=[audit_cap])
summarizer = Agent(TestModel(custom_output_text="tl;dr"), capabilities=[audit_cap])

print("translator output:", translator.run_sync("Translate hello to French").output)
print("summarizer output:", summarizer.run_sync("Summarize this document").output)
print("total model requests counted by the one shared capability:", calls["n"])
```

Output:

```
translator output: bonjour
summarizer output: tl;dr
total model requests counted by the one shared capability: 2
```

One capability object, two agents, one shared counter that ends at 2. This is the payoff of making every extension point the same type. An audit hook, a guardrail, a memory backend — each becomes a reusable component you write once and hand to any agent, which is exactly the model the Pydantic AI Harness leans on to ship batteries like memory and guardrails as drop-in units.

## The sharp edge I hit

The abstraction has one rule worth knowing before it bites you: capability `id`s must be unique within a single run. When I accidentally supplied the same `audit_cap` both at construction time and again as a per-run argument, v2 refused to run and raised a clear error:

```
pydantic_ai.exceptions.UserError: Capability id 'audit' is used by
multiple capabilities. Capability ids must be unique within a run.
```

That is a reasonable guard — duplicate ids would make it ambiguous which capability a later override targets — but it does mean you cannot lazily double-register the same object. Give each capability a stable, distinct `id`, and decide whether it belongs on the agent or on the individual run, not both.

## Is this actually new, or a repackage?

It is fair to be skeptical of "one primitive to rule them all" framing. What convinced me it is more than marketing is that the release history shows the concept being actively load-bearing, not bolted on. The v2 line has shipped fast — the public [GitHub releases](https://github.com/pydantic/pydantic-ai/releases) run from v2.3.0 on July 2, 2026 through v2.9.1 on July 14, 2026 — and the changelogs reference capability internals directly (v2.6.0, for instance, notes resolving a capability "once per run"). The abstraction is threaded through the runtime, not painted on top of it.

Whether you should adopt it depends on how much extension machinery your agents carry. If you have one tool and a system prompt, capabilities are overkill and the old ergonomics are fine. If you are assembling agents from reusable middleware — audit hooks, guardrails, memory, context trimming — then having all of it be one composable type, portable across agents, is a real structural simplification rather than a cosmetic one.

## Try It Yourself

You need only the base package and no API key. The `FunctionModel` and `TestModel` used above are built into Pydantic AI for exactly this kind of deterministic, offline run.

```bash
python3 -m venv venv && ./venv/bin/pip install pydantic-ai
./venv/bin/python capability_agent.py
./venv/bin/python capability_reuse.py
```

The full `capability_agent.py` and `capability_reuse.py` scripts are in the companion repository folder, and their real output — captured from the runs above on `pydantic-ai` 2.9.1, Python 3.11 — is reproduced verbatim in this article. If you swap `FunctionModel`/`TestModel` for a real model, the capability wiring does not change; only the thing behind the request does.

## Key Takeaways

- **Pydantic AI v2 (June 23, 2026) makes tools, instructions, hooks, and model settings one type: the capability.** You compose an agent by passing a list of capabilities, not by threading four different arguments.
- **A single capability can carry several extension points at once.** A `Toolset` capability bundles a tool and its instructions so the guidance and the callable travel together — verified by inspecting what the model actually received.
- **Capabilities are portable values, not decorators.** The same object plugs into multiple agents, which is what makes reusable middleware (audit, guardrails, memory) practical.
- **Mind the constraints.** Capability `id`s must be unique within a run; duplicate registration raises a `UserError`.
- **The concept is load-bearing, not cosmetic.** The fast v2.x release cadence and changelog references to capability internals show it is threaded through the runtime.

*Sources: [Pydantic AI v2 announcement (2026-06-23)](https://pydantic.dev/articles/pydantic-ai-v2), [AlphaSignal: a single primitive that rebuilds how agents work](https://alphasignal.ai/news/pydantic-ai-v2-ships-a-single-primitive-that-rebuilds-how-agents-work), [MindStudio: the capability primitive](https://www.mindstudio.ai/blog/what-is-pydantic-ai-2-0-capability-primitive), [pydantic-ai on PyPI](https://pypi.org/project/pydantic-ai/), [pydantic-ai GitHub releases](https://github.com/pydantic/pydantic-ai/releases). All code output captured on pydantic-ai 2.9.1, Python 3.11.15.*
