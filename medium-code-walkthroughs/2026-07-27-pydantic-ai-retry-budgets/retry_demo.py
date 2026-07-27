"""What Pydantic AI actually sends the model when your agent's output fails validation.
No API key: we drive the agent with FunctionModel, a fake model that returns whatever
Python we tell it to, so every message the framework builds is fully observable."""
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, RetryPromptPart

# The fake model. It ignores the prompt and replies from a fixed script, one line per
# model request. On call 1 it returns an ALL-CAPS ticket id; on call 2, a lowercase one.
replies = iter(["ORD-77", "ord-77"])
seen_requests = []

def scripted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    seen_requests.append(messages)          # record exactly what the framework sent us
    return ModelResponse(parts=[TextPart(next(replies))])

agent = Agent(FunctionModel(scripted_model), output_type=str)

@agent.output_validator
def must_be_lowercase(text: str) -> str:
    if text != text.lower():
        # This message is what Pydantic AI relays back to the model.
        raise ModelRetry(f"'{text}' is not lowercase; return the id in lowercase.")
    return text

result = agent.run_sync("Give me the order id.")
print("FINAL OUTPUT:", repr(result.output))
print("MODEL WAS CALLED:", len(seen_requests), "times")

# Pull the retry message the framework injected before the 2nd model call.
second_call = seen_requests[1]
for part in second_call[-1].parts:
    if isinstance(part, RetryPromptPart):
        print("RETRY PART SENT BACK ->", repr(part.content))
        print("part_kind:", part.part_kind, "| tool_name:", part.tool_name)
