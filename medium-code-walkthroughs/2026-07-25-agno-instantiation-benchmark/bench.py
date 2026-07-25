"""
Measure agent *instantiation* cost (time + memory) for Agno, LangGraph, and
Pydantic AI, following Agno's own published methodology: build the same
one-tool agent 1000x, isolate the per-instance delta, use tracemalloc for
memory. No LLM calls are made - we only construct the agent objects.
"""
import gc
import time
import tracemalloc
import importlib.metadata as md
import os

os.environ["OPENAI_API_KEY"] = "sk-not-used-no-network-calls-happen"

RUNS = 1000

# --- one identical tool per framework -------------------------------------
def _weather(city: str) -> str:
    "Get the weather for a city."
    return f"It is sunny in {city}."

# --- Agno ------------------------------------------------------------------
from agno.agent import Agent as AgnoAgent
from agno.models.openai import OpenAIChat

def make_agno():
    return AgnoAgent(model=OpenAIChat(id="gpt-4o"), tools=[_weather])

# --- LangGraph -------------------------------------------------------------
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

@tool
def _weather_lc(city: str) -> str:
    "Get the weather for a city."
    return f"It is sunny in {city}."

def make_langgraph():
    return create_react_agent(ChatOpenAI(model="gpt-4o"), tools=[_weather_lc])

# --- Pydantic AI -----------------------------------------------------------
from pydantic_ai import Agent as PydAgent

def make_pydantic():
    agent = PydAgent("openai:gpt-4o")
    agent.tool_plain(_weather)
    return agent

# --- measurement -----------------------------------------------------------
def time_us(factory):
    factory()  # warm up imports/caches
    gc.collect()
    best = None
    # take the best of 5 batches of RUNS to reduce noise from GC pauses
    for _ in range(5):
        gc.disable()
        t0 = time.perf_counter()
        for _ in range(RUNS):
            factory()
        t1 = time.perf_counter()
        gc.enable()
        per = (t1 - t0) / RUNS * 1e6  # microseconds
        best = per if best is None else min(best, per)
    return best

def mem_kib(factory):
    gc.collect()
    tracemalloc.start()
    base = tracemalloc.take_snapshot()
    keep = [factory() for _ in range(RUNS)]
    after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    stats = after.compare_to(base, "filename")
    total = sum(s.size_diff for s in stats)
    keep.clear()
    return total / RUNS / 1024  # KiB per instance

frameworks = [
    ("agno", make_agno, "agno"),
    ("langgraph", make_langgraph, "langgraph"),
    ("pydantic-ai", make_pydantic, "pydantic-ai-slim"),
]

print(f"python {os.sys.version.split()[0]}  runs={RUNS}\n")
print(f"{'framework':<14}{'version':<12}{'instantiate (us)':>18}{'memory (KiB)':>16}")
print("-" * 60)
results = {}
for name, factory, dist in frameworks:
    t = time_us(factory)
    m = mem_kib(factory)
    results[name] = (t, m)
    print(f"{name:<14}{md.version(dist):<12}{t:>18.2f}{m:>16.2f}")

at, am = results["agno"]
print("\nRatios (higher = Agno is lighter/faster):")
for name in ("langgraph", "pydantic-ai"):
    t, m = results[name]
    print(f"  vs {name:<12} time: {t/at:6.1f}x   memory: {m/am:6.1f}x")
