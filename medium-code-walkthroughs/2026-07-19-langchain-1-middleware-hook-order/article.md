# LangChain 1.0's Agent Middleware: Which Hooks Fire, and In What Order

If you read the LangChain 1.0 launch material and then opened a fresh install, you already hit the first surprise: the middleware hook every blog post calls `modify_model_request` is not there. The current package ships `wrap_model_call` instead. That is not a documentation typo. It is a rename that happened between the 1.0 alpha and the stable line, and it changes what the hook can do.

Middleware is the headline of the [LangChain 1.0](https://pypi.org/pypi/langchain/json) agent API. `create_agent` is a thin loop; middleware is where you customize it. But "composable hooks" is a vague promise until you know exactly which hook runs, how many times, and in what order when two pieces of middleware stack. This article answers that precisely, by running the installed build and logging every hook as it fires. Everything below was checked against `langchain==1.3.14`, published to PyPI on 2026-07-16 — three days before this was written.

## Why middleware, and why now

The 1.0 line reached PyPI as `1.0.0` on 2025-10-17, after a first alpha (`1.0.0a1`) on 2025-08-27 (dates from the [PyPI release metadata](https://pypi.org/pypi/langchain/json)). The API kept moving after GA: `1.3.0` landed on 2026-05-12 and `1.3.14` on 2026-07-16. If you pinned an early 1.0 release and are migrating now, the middleware surface you wrote against has shifted underneath you. That is the "why now."

The idea is simple. Instead of forking the agent loop to add retries, guardrails, PII redaction, or a dynamic system prompt, you attach middleware objects and each one gets called at fixed points in the loop. LangChain ships a set of them already — inspecting the installed module shows `HumanInTheLoopMiddleware`, `SummarizationMiddleware`, `PIIMiddleware`, `ModelFallbackMiddleware`, `ModelCallLimitMiddleware`, and more. The interesting part is writing your own, and for that you need the execution model.

## The six hooks

Subclass `AgentMiddleware` and override any of these (each also has an `a`-prefixed async twin like `awrap_model_call`). Inspecting the class in `langchain==1.3.14` gives the exact signatures:

- `before_agent(self, state, runtime)` — runs once, when the agent starts.
- `before_model(self, state, runtime)` — runs before every model call. In a tool-calling loop that is once per turn.
- `wrap_model_call(self, request, handler)` — wraps each model call. It receives a `handler` callback and decides whether, when, and how many times to call it.
- `wrap_tool_call(self, request, handler)` — wraps each tool call the model requests.
- `after_model(self, state, runtime)` — runs after every model call.
- `after_agent(self, state, runtime)` — runs once, when the agent finishes.

The `before_*` and `after_*` hooks return `dict | None` — a state update, or nothing. The `wrap_*` hooks are different in kind: they own the call. That distinction is the whole point of the next section.

## The rename nobody mentions: `modify_model_request` became `wrap_model_call`

In the 1.0 alpha, the hook for touching a model request was `modify_model_request`: you got the request, mutated it, returned it. Community guides written during the alpha still describe it that way. In the shipped package it is gone. Grepping the installed `langchain` and `langchain_core` trees for `modify_model_request` returns zero files; `wrap_model_call` is what exists.

The rename is not cosmetic. `modify_model_request` could only edit the request on the way in. `wrap_model_call` receives a `handler` and sits around the actual call, so the installed docstring describes three powers a pure "modify" hook never had:

> Middleware can call the handler multiple times for retry logic, skip calling it to short-circuit, or modify the request/response.

Retry, short-circuit, and response rewriting are only possible because the hook wraps the call instead of preceding it. If you are following a tutorial that binds prompt-caching tags or a fallback model to `modify_model_request`, that method no longer exists — the same logic now lives inside `wrap_model_call`, and you get the handler as an argument. (You can still shape the outgoing request: `ModelRequest` exposes a `system_prompt` field and an `override(...)` method.)

## Try It Yourself

You do not need an API key to see the order. A scripted fake chat model is enough to drive one full tool-calling turn, and a tracing middleware logs every hook as it fires. Install the dependency:

```bash
pip install "langchain>=1.3,<2"
```

The tracing middleware just records each hook, tagged with an instance name so we can watch two of them stack. `wrap_model_call` logs twice — once before it hands off to the model (`>`) and once after the model returns (`<`):

```python
from langchain.agents.middleware import AgentMiddleware

class TraceMiddleware(AgentMiddleware):
    def __init__(self, name):
        super().__init__()
        self._tag = name

    @property
    def name(self):            # distinct name; duplicates are rejected
        return f"Trace-{self._tag}"

    def before_agent(self, state, runtime):  log("before_agent", self._tag)
    def before_model(self, state, runtime):  log("before_model", self._tag)
    def after_model(self, state, runtime):   log("after_model", self._tag)
    def after_agent(self, state, runtime):   log("after_agent", self._tag)

    def wrap_model_call(self, request, handler):
        log("wrap_model_call>", self._tag)   # before the model
        response = handler(request)
        log("wrap_model_call<", self._tag)   # after the model
        return response

    def wrap_tool_call(self, request, handler):
        log("wrap_tool_call", self._tag)
        return handler(request)
```

We attach two instances, `OUTER` first and `INNER` second, to a `create_agent` running a scripted model that asks for one tool call and then answers. The stock `GenericFakeChatModel` does not implement `bind_tools`, so we add a one-line no-op override — a standard test double:

```python
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain.agents import create_agent
from langchain.tools import tool

class FakeToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

@tool
def get_weather(city: str) -> str:
    """Return the weather for a city."""
    return f"It is 21C and clear in {city}."

model = FakeToolCallingModel(messages=iter([
    AIMessage(content="", tool_calls=[
        {"name": "get_weather", "args": {"city": "Paris"}, "id": "call_1"}]),
    AIMessage(content="It is 21C and clear in Paris."),
]))

agent = create_agent(model=model, tools=[get_weather],
    middleware=[TraceMiddleware("OUTER"), TraceMiddleware("INNER")])
agent.invoke({"messages": [{"role": "user", "content": "Weather in Paris?"}]})
```

Running it prints the real, deterministic order:

```text
langchain 1.3.14

 1. before_agent     [OUTER]
 2. before_agent     [INNER]
 3. before_model     [OUTER]
 4. before_model     [INNER]
 5. wrap_model_call> [OUTER]
 6. wrap_model_call> [INNER]
 7. wrap_model_call< [INNER]
 8. wrap_model_call< [OUTER]
 9. after_model      [INNER]
10. after_model      [OUTER]
11. wrap_tool_call   [OUTER]
12. wrap_tool_call   [INNER]
13. before_model     [OUTER]
14. before_model     [INNER]
15. wrap_model_call> [OUTER]
16. wrap_model_call> [INNER]
17. wrap_model_call< [INNER]
18. wrap_model_call< [OUTER]
19. after_model      [INNER]
20. after_model      [OUTER]
21. after_agent      [INNER]
22. after_agent      [OUTER]
```

## Reading the order

Four rules fall straight out of that trace, and they match the docstring's one-line promise that "multiple middleware compose with first in list as outermost layer."

1. **`before_*` runs outer to inner; `after_*` runs inner to outer.** The list order sets an onion. `OUTER` is listed first, so it wraps everything: it enters first (steps 1, 3) and leaves last (steps 10, 22). This is the classic middleware nesting, and it means an outer guardrail sees state before an inner transform and again after it.

2. **`wrap_model_call` nests symmetrically.** Steps 5–8 read `OUTER>`, `INNER>`, `INNER<`, `OUTER<` — outer opens the call, inner opens inside it, and they close in reverse. The model runs exactly once at the center of that stack.

3. **The agent-level hooks fire once; the model-level hooks fire per turn.** `before_agent` and `after_agent` appear a single time (steps 1–2, 21–22). The whole `before_model → wrap → after_model` block repeats: steps 3–10 are the turn that requests the tool, steps 13–20 are the turn that produces the final answer.

4. **`wrap_tool_call` sits between turns.** Steps 11–12 fire after the first model turn asks for `get_weather` and before the second model turn sees the result. It follows the same outer-to-inner order on the way in.

## The short-circuit that `before`/`after` can't do

The reason `wrap_model_call` exists as its own hook — rather than a `before_model` that edits the request — is that it can decline to call the model at all. A guardrail can inspect the request and return a canned response, and the model is never invoked:

```python
from langchain.agents.middleware import AgentMiddleware, ModelResponse
from langchain_core.messages import AIMessage

class Guardrail(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        last = request.state["messages"][-1].content.lower()
        if "wire transfer" in last:
            print("guardrail: blocked, model NOT called")
            return ModelResponse(result=[AIMessage(
                content="I can't help with wire-transfer requests.")])
        return handler(request)
```

Point it at a model scripted to say "sure! sending it now." and the guardrail wins, because it returns without ever calling `handler`:

```text
guardrail: blocked, model NOT called
final reply: I can't help with wire-transfer requests.
```

A `before_model` hook could log the risky input or edit it, but it cannot stop the turn — control always returns to the loop, which then calls the model. Only a hook that owns the `handler` can decide not to pull the trigger. That is also how the built-in `ModelFallbackMiddleware` and retry middleware work: they call `handler` again on failure.

## When to reach for which hook

- Read or update state around the whole run: `before_agent` / `after_agent`.
- Read or update state around each model turn: `before_model` / `after_model`.
- Change the outgoing request, retry, cache, fall back, or block the call: `wrap_model_call`.
- Intercept a specific tool invocation (sandbox it, mock it, add approval): `wrap_tool_call`.
- Stacking several: remember that list position decides nesting — the first middleware is the outermost layer on the way in and the last to finish on the way out.

## Key Takeaways

- LangChain 1.0 middleware exposes six override points: `before_agent`, `before_model`, `wrap_model_call`, `wrap_tool_call`, `after_model`, `after_agent` (each with an async twin).
- `before_*` hooks fire outer-to-inner; `after_*` hooks fire inner-to-outer; `wrap_*` hooks nest symmetrically around the call. Agent-level hooks fire once; model-level hooks fire once per turn.
- The alpha's `modify_model_request` is gone in `langchain==1.3.14`. Its replacement, `wrap_model_call`, wraps the call and can retry it, short-circuit it, or rewrite the response — none of which a plain "modify request" hook could do.
- You can verify all of this offline: a scripted fake model plus a tracing middleware reproduces the exact order with no API key.
- Pin your version. The middleware API moved between the 1.0 alpha, `1.0.0` (2025-10-17), and `1.3.14` (2026-07-16); tutorials written against one may not match another.

## Sources

- LangChain PyPI release metadata (versions and upload dates), retrieved 2026-07-19: https://pypi.org/pypi/langchain/json
- LangChain middleware documentation: https://docs.langchain.com/oss/python/langchain/middleware/custom
- LangChain API reference, `middleware`: https://reference.langchain.com/python/langchain/middleware
- "Middleware in LangChain 1.0 alpha" changelog: https://changelog.langchain.com/announcements/middleware-in-langchain-1-0-alpha
- Primary source of truth for hook names, signatures, and order: direct inspection and execution of the installed `langchain==1.3.14` / `langchain-core==1.4.9` packages (code and captured output included above).
