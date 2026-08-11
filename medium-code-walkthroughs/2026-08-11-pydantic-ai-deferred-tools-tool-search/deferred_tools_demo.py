"""Demonstrate Pydantic AI's deferred tool loading + Tool Search (v2.26+).

Runs entirely locally against FunctionModel — no API key, no network.
The FunctionModel callback inspects `info.function_tools`, which is exactly
the list of tools the framework would send to a real model on each request.
"""

import dataclasses

import pydantic_ai
from pydantic_ai import Agent
from pydantic_ai.capabilities import ToolSearch
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset


def build_toolset(defer: bool) -> FunctionToolset:
    ts = FunctionToolset(defer_loading=defer)

    @ts.tool_plain
    def get_weather(city: str) -> str:
        "Get the current weather for a city."
        return f"Weather in {city}: sunny, 24C"

    @ts.tool_plain
    def convert_currency(amount: float, source: str, target: str) -> str:
        "Convert an amount of money from one currency to another."
        return f"{amount} {source} = {amount * 1.1:.2f} {target}"

    @ts.tool_plain
    def search_flights(origin: str, destination: str) -> str:
        "Search available flights between two airports."
        return "FL123 08:00, FL456 12:00"

    return ts


def first_request_tools(toolset: FunctionToolset, capabilities=None) -> list[str]:
    """Return the tool names the model sees on its very first request."""
    seen: list[list[str]] = []

    def spy(messages, info: AgentInfo):
        seen.append(sorted(t.name for t in info.function_tools))
        return ModelResponse(parts=[TextPart("done")])

    kwargs = {"capabilities": capabilities} if capabilities else {}
    Agent(FunctionModel(spy), toolsets=[toolset], **kwargs).run_sync("hi")
    return seen[0]


# --- Part 1: what the model sees --------------------------------------------
print("pydantic-ai:", pydantic_ai.__version__)
print("ToolDefinition.defer_loading field exists:",
      any(f.name == "defer_loading" for f in dataclasses.fields(ToolDefinition)))
print()
print("no deferral                 ->", first_request_tools(build_toolset(defer=False)))
print("deferral, no search enabled ->", first_request_tools(build_toolset(defer=True)))
print("deferral + keyword search   ->",
      first_request_tools(build_toolset(defer=True), [ToolSearch(strategy="keywords")]))


# --- Part 2: discover -> reveal -> call -------------------------------------
deferred = build_toolset(defer=True)
step = {"n": 0}


def driver(messages, info: AgentInfo):
    step["n"] += 1
    visible = sorted(t.name for t in info.function_tools)
    print(f"[call {step['n']}] model sees {len(visible)} tool(s): {visible}")
    if step["n"] == 1:  # only search_tools is visible -> go find a weather tool
        return ModelResponse(parts=[ToolCallPart("search_tools", {"queries": ["weather"]})])
    if step["n"] == 2:  # get_weather has been revealed -> call it
        return ModelResponse(parts=[ToolCallPart("get_weather", {"city": "Paris"})])
    return ModelResponse(parts=[TextPart("The weather in Paris is sunny, 24C.")])


agent = Agent(FunctionModel(driver), toolsets=[deferred],
              capabilities=[ToolSearch(strategy="keywords")])
result = agent.run_sync("What's the weather in Paris?")

for msg in result.all_messages():
    for part in getattr(msg, "parts", []):
        if getattr(part, "tool_name", None) == "search_tools" and type(part).__name__.endswith("ReturnPart"):
            print("search_tools returned:", part.content)
print("final output:", result.output)
