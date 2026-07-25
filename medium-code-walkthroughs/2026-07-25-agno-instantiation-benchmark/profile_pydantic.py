"""
Why is Pydantic AI's Agent(...) construction so slow in the instantiation
benchmark? Profile it. Spoiler: it's not agent logic - it's the TLS trust
store being loaded for an eagerly-built HTTP client, on every construction.
No network call is made.
"""
import os, cProfile, pstats, io

os.environ["OPENAI_API_KEY"] = "sk-not-used-no-network-calls-happen"

from pydantic_ai import Agent


def _weather(city: str) -> str:
    "Get the weather for a city."
    return f"It is sunny in {city}."


def make():
    agent = Agent("openai:gpt-4o")
    agent.tool_plain(_weather)
    return agent


make()  # warm up imports
pr = cProfile.Profile()
pr.enable()
for _ in range(50):
    make()
pr.disable()

s = io.StringIO()
# strip_dirs() drops absolute path prefixes so output is portable
pstats.Stats(pr, stream=s).strip_dirs().sort_stats("cumulative").print_stats(12)
print(s.getvalue())
