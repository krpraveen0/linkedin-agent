"""
NOOA: the whole agent is one Python class.

Run:
    uv venv --python 3.12 .venv && source .venv/bin/activate
    uv pip install nooa
    python triage_agent.py

No API key needed. print_prompt() renders what NOOA *would* send the model
(it makes no network call), and FakeLLMClient replays a scripted response so
the CodeAct loop runs fully offline.
"""
import asyncio, json
import nooa
from nooa.unifiedllm import FakeLLMClient, LLMResponse, ToolCall


class TicketTriage(nooa.Agent):
    """You are a customer-support triage agent. You are terse and precise."""

    async def urgent_count(self, tickets: list[dict]) -> int:
        """Count how many tickets have priority == 'high'."""
        ...   # the ellipsis body is the signal: NOOA fills this in with the LLM


async def show_prompt():
    # No LLM call happens here — this just renders the prompt NOOA builds.
    agent = TicketTriage(llm=FakeLLMClient())
    tickets = [{"id": 1, "priority": "high"}]
    await nooa.print_prompt(agent.urgent_count, tickets)


async def run_hermetic():
    # Script the model's turn: one execute_python cell that computes and returns.
    code = "n = sum(1 for t in tickets if t['priority'] == 'high')\nreturn_result(n)"
    scripted = [
        LLMResponse(
            raw_response={}, content="",
            tool_calls=[ToolCall(id="c1", name="execute_python",
                                 arguments=json.dumps({"code": code}))],
            finish_reason="tool_calls",
            assistant_message={"role": "assistant", "content": ""},
        )
    ]
    agent = TicketTriage(llm=FakeLLMClient(scripted_responses=scripted))
    tickets = [{"id": 1, "priority": "high"},
               {"id": 2, "priority": "low"},
               {"id": 3, "priority": "high"}]
    result = await agent.urgent_count(tickets)
    print("RESULT:", result, "| type:", type(result).__name__)


async def main():
    print("nooa version:", nooa.__version__)
    print("default strategy:", type(nooa.get_default_strategy()).__name__)
    print("\n========== print_prompt(urgent_count) ==========")
    await show_prompt()
    print("\n========== hermetic CodeAct run ==========")
    await run_hermetic()


asyncio.run(main())
