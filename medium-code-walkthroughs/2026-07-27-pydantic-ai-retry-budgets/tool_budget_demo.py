"""The 'tools' pool is separate from 'output'. A tool that keeps raising ModelRetry
draws down only the tools budget. We set tools=3 and count how many times the model
is asked to try the tool again before the run gives up."""
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart

tool_calls = {"n": 0}

def keep_calling_tool(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    # Every turn, the fake model calls the tool again (never emits final text).
    return ModelResponse(parts=[ToolCallPart(tool_name="lookup", args={})])

agent = Agent(FunctionModel(keep_calling_tool), output_type=str, retries={"tools": 3})

@agent.tool_plain
def lookup() -> str:
    tool_calls["n"] += 1
    raise ModelRetry("not found, try again")   # always fails

print("stored tool budget:", agent._max_tool_retries, "| output budget:", agent._max_output_retries)
try:
    agent.run_sync("look it up")
except UnexpectedModelBehavior as e:
    print("RAISED:", type(e).__name__, "->", e)
print("tool actually executed:", tool_calls["n"], "times (1 initial + 3 retries)")
