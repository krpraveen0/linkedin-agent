# I Gave My Pydantic AI Agent Three Tools. The Model Saw One Until It Went Looking.

Every tool you register on an agent is a bill you pay before the model does any work. The tool's name, description, and full JSON schema are serialized into the request and sent on every single turn. Ten tools is fine. Fifty tools, spread across a few MCP servers, is thousands of tokens of schema sitting in context before the user's question even lands, and a measurably harder selection problem for the model on top of it.

Pydantic AI's answer shipped on August 7, 2026 in [v2.26.0](https://github.com/pydantic/pydantic-ai/releases/tag/v2.26.0). The changelog line is terse: "Support hiding function tools until revealed — via tool search, `load_capability`, or `ToolReturn.tools` — using each provider's native deferral/addition channel." Translated: you can now mark a tool so the model never sees it until it searches for it by keyword. I installed the current release and pushed on it to find out exactly what the model sees, and when.

## The one flag that hides a tool

The mechanism is a single keyword argument, `defer_loading`, that lives in three places. You can set it on a whole toolset, on an individual tool, or wrap an existing toolset with `.defer_loading()`:

```python
from pydantic_ai.toolsets import FunctionToolset

# Option A: hide every tool in this toolset
ts = FunctionToolset(defer_loading=True)

@ts.tool_plain
def get_weather(city: str) -> str:
    "Get the current weather for a city."
    return f"Weather in {city}: sunny, 24C"
```

Under the hood, deferral is not a special tool type. Looking at the installed package, `DeferredLoadingToolset` is a thin wrapper whose only job is to flip a boolean on each tool's definition:

```python
# pydantic_ai/toolsets/deferred_loading.py (v2.27.0)
async def _mark_deferred(_ctx, tool_defs):
    return [
        replace(td, defer_loading=True)
        if (tool_names is None or td.name in tool_names) else td
        for td in tool_defs
    ]
```

That `defer_loading=True` on the `ToolDefinition` is the whole story. Everything downstream — what the model sees, how the tool reaches the wire — keys off that flag.

## What the model actually sees

To see the effect without paying for a real model, I used Pydantic AI's built-in `FunctionModel`. It hands your callback an `AgentInfo` object whose `function_tools` field is exactly the list of tools the framework would send to a real provider on that request. Inspecting it is like reading the wire.

I registered three tools — `get_weather`, `convert_currency`, `search_flights` — and asked what the model sees on its first request under three configurations:

```python
print("no deferral                 ->", first_request_tools(build_toolset(defer=False)))
print("deferral, no search enabled ->", first_request_tools(build_toolset(defer=True)))
print("deferral + keyword search   ->",
      first_request_tools(build_toolset(defer=True), [ToolSearch(strategy="keywords")]))
```

The real captured output:

```
no deferral                 -> ['convert_currency', 'get_weather', 'search_flights']
deferral, no search enabled -> []
deferral + keyword search   -> ['search_tools']
```

Three findings, in three lines. Without deferral, the model sees all three tools, as always. With deferral turned on, it sees a single meta-tool, `search_tools`, and none of the three real ones. And the middle line is the gotcha I'll come back to.

## Discover, reveal, call

Hiding tools is only useful if the model can get them back. The [Tool Search capability](https://github.com/pydantic/pydantic-ai/blob/main/docs/capabilities/tool-search.md) gives the model a `search_tools` function whose schema takes a list of keyword queries. When the model calls it, matching tools are revealed for the rest of the run.

I drove the full loop with `FunctionModel`, logging what the model sees at each step. Step one, it searches for "weather"; step two, it calls whatever got revealed:

```python
def driver(messages, info):
    step["n"] += 1
    visible = sorted(t.name for t in info.function_tools)
    print(f"[call {step['n']}] model sees {len(visible)} tool(s): {visible}")
    if step["n"] == 1:
        return ModelResponse(parts=[ToolCallPart("search_tools", {"queries": ["weather"]})])
    if step["n"] == 2:
        return ModelResponse(parts=[ToolCallPart("get_weather", {"city": "Paris"})])
    return ModelResponse(parts=[TextPart("The weather in Paris is sunny, 24C.")])
```

The captured output:

```
[call 1] model sees 1 tool(s): ['search_tools']
[call 2] model sees 2 tool(s): ['get_weather', 'search_tools']
[call 3] model sees 2 tool(s): ['get_weather', 'search_tools']
search_tools returned: {'discovered_tools': [{'name': 'get_weather'}]}
final output: The weather in Paris is sunny, 24C.
```

Read call 2 closely. After searching for "weather", the model can now see `get_weather` — and still cannot see `convert_currency` or `search_flights`. The search revealed exactly the tool that matched the query and left the other two hidden. The return payload confirms it: `{'discovered_tools': [{'name': 'get_weather'}]}`. A revealed tool stays available for the rest of the run, which is why it is still visible on call 3.

That is the behavior that makes deferral pay off. A model with fifty tools behind `search_tools` never carries fifty schemas. It carries one meta-tool, plus whatever it deliberately pulls in.

## The gotcha: "auto-injected" is not "always on"

The docs say tool search is auto-injected once any deferred tool exists. That is true, but it hides a sharp edge that my middle output line exposed: `deferral, no search enabled -> []`. With tools deferred and no explicit `ToolSearch` strategy, the model saw nothing at all. No real tools, and no `search_tools` either. A dead end.

The reason is in how the capability picks a path. Per the tool-search docs, it uses "native server-executed search for Anthropic and OpenAI, or falling back to a local `search_tools` function elsewhere." The default strategy is tuned for models that support native tool search on the provider side. `FunctionModel` does not, and neither do most non-frontier models, so no local discovery tool is emitted unless you ask for one. Passing an explicit local strategy fixes it:

```python
from pydantic_ai.capabilities import ToolSearch
agent = Agent(model, toolsets=[ts], capabilities=[ToolSearch(strategy="keywords")])
```

That single change is what turned `[]` into `['search_tools']`. The lesson: if you defer tools for a model that lacks native tool search, set `ToolSearch(strategy="keywords")` (or `"bm25"` / `"regex"`) yourself, or your agent will have tools it can never reach.

## How it reaches the wire

The split between native and local is not marketing. It is visible in the installed package's model profiles. The OpenAI profile gates native tool search by model name:

```python
# pydantic_ai/profiles/openai.py
supports_tool_search = model_name.startswith(('gpt-5.4', 'gpt-5.5', 'gpt-5.6'))
```

The Anthropic profile lists the models where `ToolSearchTool` is supported, starting at `claude-sonnet-4-5`. On those providers, deferred tools ride the provider's own deferral channel and a reveal unlocks them in place. Everywhere else, Pydantic AI runs the keyword search locally against the tool names and descriptions and injects `search_tools` as an ordinary function tool. Same API for you; different plumbing underneath. This mirrors the direction the frontier providers already took, where on-demand tool discovery replaced loading every tool definition up front.

## Try It Yourself

You need only `pydantic-ai` and no API key. The whole demo runs against `FunctionModel`.

```bash
python -m venv venv && . venv/bin/activate
pip install "pydantic-ai-slim[openai]"   # installs 2.26.0 or newer
python deferred_tools_demo.py
```

The script (in the companion repo) builds one toolset three ways and then drives a discover-reveal-call loop. Its real output, top to bottom:

```
pydantic-ai: 2.27.0
ToolDefinition.defer_loading field exists: True

no deferral                 -> ['convert_currency', 'get_weather', 'search_flights']
deferral, no search enabled -> []
deferral + keyword search   -> ['search_tools']
[call 1] model sees 1 tool(s): ['search_tools']
[call 2] model sees 2 tool(s): ['get_weather', 'search_tools']
[call 3] model sees 2 tool(s): ['get_weather', 'search_tools']
search_tools returned: {'discovered_tools': [{'name': 'get_weather'}]}
final output: The weather in Paris is sunny, 24C.
```

Change the query on call 1 from `["weather"]` to `["currency"]` and watch a different tool surface while `get_weather` stays hidden. That one experiment tells you everything about how the reveal is scoped.

## Key Takeaways

- **`defer_loading=True` hides a tool from the model until it is discovered by search.** It is available on `FunctionToolset(...)`, on `@toolset.tool_plain(...)`, and via `.defer_loading()` on any toolset, and it works by setting `defer_loading=True` on the tool's `ToolDefinition`.
- **A deferred toolset collapses the model's tool list to one meta-tool.** In my run, three real tools became a single `search_tools` on the first request.
- **Search reveals only what matches.** Searching `["weather"]` surfaced `get_weather` and left `convert_currency` and `search_flights` hidden; a revealed tool then stays available for the rest of the run.
- **On models without native tool search, set the strategy explicitly.** Deferral with no `ToolSearch` strategy left `FunctionModel` with zero reachable tools. `ToolSearch(strategy="keywords")` fixed it.
- **Native versus local is decided by the model profile.** OpenAI `gpt-5.4+` and Claude Sonnet 4.5+ get provider-native search; everything else gets a local keyword `search_tools`.

This article was produced by an automated daily pipeline. The code and its output were executed and captured directly; the process validates traceability, freshness, and that the code runs, not deep domain correctness. A human accuracy pass is still recommended before relying on it.

**Sources:** [Pydantic AI v2.26.0 release](https://github.com/pydantic/pydantic-ai/releases/tag/v2.26.0) (Aug 7, 2026) · [Pydantic AI releases](https://github.com/pydantic/pydantic-ai/releases) · [Tool Search docs](https://github.com/pydantic/pydantic-ai/blob/main/docs/capabilities/tool-search.md) · [Deferred Tools docs](https://github.com/pydantic/pydantic-ai/blob/main/docs/tools-toolsets/deferred-tools.md) · direct inspection of the installed `pydantic-ai` 2.27.0 package (`toolsets/deferred_loading.py`, `profiles/openai.py`, `profiles/anthropic.py`).
