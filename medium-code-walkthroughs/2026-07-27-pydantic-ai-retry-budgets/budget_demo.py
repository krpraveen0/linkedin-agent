"""The retry budget is finite, and since 2.x it splits into separate 'tools' and 'output'
pools. Here we exhaust the output budget and read the exact exception."""
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart

def always_uppercase(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("STILL-UPPER")])   # never complies

# retries={'output': 2}: two output-validation retries allowed before giving up.
agent = Agent(FunctionModel(always_uppercase), output_type=str, retries={"output": 2})

@agent.output_validator
def must_be_lowercase(text: str) -> str:
    if text != text.lower():
        raise ModelRetry("must be lowercase")
    return text

# Confirm the split budget the agent stored, straight off the object.
print("stored output budget:", agent._max_output_retries)
print("stored tool budget:  ", agent._max_tool_retries)

try:
    agent.run_sync("go")
except UnexpectedModelBehavior as e:
    print("RAISED:", type(e).__name__, "->", e)
