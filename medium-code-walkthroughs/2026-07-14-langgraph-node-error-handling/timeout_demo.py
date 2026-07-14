"""Shows a real NodeTimeoutError firing when a node exceeds TimeoutPolicy.run_timeout."""
import asyncio
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.types import TimeoutPolicy
from langgraph.errors import NodeTimeoutError


class State(TypedDict):
    status: str


async def slow_call(state: State) -> State:
    await asyncio.sleep(3)  # simulates a hung downstream call
    return {"status": "done"}


graph = StateGraph(State)
graph.add_node("slow_call", slow_call, timeout=TimeoutPolicy(run_timeout=1.0))
graph.set_entry_point("slow_call")
graph.add_edge("slow_call", END)
app = graph.compile()


async def main():
    try:
        await app.ainvoke({"status": "pending"})
    except NodeTimeoutError as e:
        print(f"[caught] {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
