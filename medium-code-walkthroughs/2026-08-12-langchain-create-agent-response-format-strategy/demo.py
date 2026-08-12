"""
What LangChain 1.0's create_agent does with a raw response_format schema.

No API key, no network: a scripted BaseChatModel stands in for the LLM so we
can watch which tools create_agent actually offers the model.

Tested with: langchain 1.3.15, langchain-core 1.5.4, langgraph 1.2.11
Run:  python demo.py
"""
from typing import Optional

from pydantic import BaseModel
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy, OutputToolBinding

RECORD = {}  # model_name -> list of tool names it was offered


class Weather(BaseModel):
    """Structured weather answer."""
    city: str
    temp_c: float
    summary: str


@tool
def get_weather(city: str) -> str:
    """Look up the weather for a city."""
    return f"{city}: 19C, clear"


class ScriptedModel(BaseChatModel):
    """Replays scripted turns and records every tool list it is bound to."""
    model_name: str = "my-local-llm"
    profile: Optional[dict] = None  # no provider-native structured output
    answer_with_tool: bool = True   # call the injected schema-tool to answer

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        RECORD[self.model_name] = [getattr(t, "name", None) or t.get("name") for t in tools]
        return super().bind(tools=tools, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        already_ran_tool = any(m.type == "tool" for m in messages)
        if not already_ran_tool:
            msg = AIMessage(content="", tool_calls=[
                {"name": "get_weather", "args": {"city": "Paris"}, "id": "c1"}])
        elif self.answer_with_tool:
            msg = AIMessage(content="", tool_calls=[
                {"name": "Weather",
                 "args": {"city": "Paris", "temp_c": 19.0, "summary": "clear"},
                 "id": "c2"}])
        else:
            msg = AIMessage(content='{"city":"Paris","temp_c":19.0,"summary":"clear"}')
        return ChatResult(generations=[ChatGeneration(message=msg)])


# --- Demo 1: the synthetic tool ToolStrategy builds from your schema ----------
print("== Demo 1: ToolStrategy turns your schema into a tool ==")
for spec in ToolStrategy(schema=Weather).schema_specs:
    binding = OutputToolBinding.from_schema_spec(spec)
    print("  injected tool name:", binding.tool.name)
    print("  injected tool args:", list(binding.tool.args.keys()))


# --- Demo 2: a local model gets the schema-tool injected next to real tools ----
print("\n== Demo 2: local model (no native structured output) ==")
local = ScriptedModel(model_name="my-local-llm")
agent = create_agent(local, tools=[get_weather], response_format=Weather)
result = agent.invoke({"messages": [{"role": "user", "content": "weather in Paris?"}]})
print("  tools the model was offered:", RECORD["my-local-llm"])
print("  structured_response:", result.get("structured_response"))


# --- Demo 3: a model that advertises native structured output -----------------
print("\n== Demo 3: model whose profile advertises structured_output ==")
capable = ScriptedModel(model_name="capable-model",
                        profile={"structured_output": True},
                        answer_with_tool=False)
agent2 = create_agent(capable, tools=[get_weather], response_format=Weather)
result2 = agent2.invoke({"messages": [{"role": "user", "content": "weather in Paris?"}]})
print("  tools the model was offered:", RECORD["capable-model"])
print("  structured_response:", result2.get("structured_response"))
