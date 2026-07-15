"""Pydantic AI v2: composing an agent out of `capability` units.

No API key. We drive the model with FunctionModel so the run is fully
deterministic and we can print exactly what each capability delivered.

Two capabilities are plugged into one agent:
  1. a Toolset capability that bundles BOTH a tool AND its instructions
  2. a Hooks capability that counts model requests, without touching the
     agent body
"""
from pydantic_ai import Agent, FunctionToolset
from pydantic_ai.capabilities import Toolset, Hooks
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)


# ---- A plain Python tool -----------------------------------------------
def word_count(text: str) -> int:
    """Count the words in a piece of text."""
    return len(text.split())


# ---- Capability #1: a Toolset that carries a tool AND instructions ------
tools_cap = Toolset(
    FunctionToolset(
        tools=[word_count],
        instructions="If asked how long some text is, call word_count.",
    ),
    id="word-tools",
)

# ---- Capability #2: lifecycle hooks, counting model requests ------------
request_count = {"n": 0}


def count_requests(ctx, request_context):
    request_count["n"] += 1
    return request_context  # hooks return the (possibly modified) context


audit_cap = Hooks(before_model_request=count_requests, id="audit")


# ---- A deterministic "model": call the tool once, then answer -----------
def fake_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    # First turn: no tool result yet -> ask to call word_count.
    already_called = any(
        part.part_kind == "tool-return"
        for m in messages
        for part in m.parts
    )
    if not already_called:
        # Prove the capability's instructions + tool reached the model.
        print("instructions seen by model :", repr(info.instructions))
        print("tools seen by model        :", [t.name for t in info.function_tools])
        return ModelResponse(parts=[ToolCallPart("word_count", {"text": "one two three"})])
    return ModelResponse(parts=[TextPart("The text has 3 words.")])


# ---- Compose the agent purely from capabilities -------------------------
agent = Agent(
    FunctionModel(fake_model),
    capabilities=[tools_cap, audit_cap],
)

result = agent.run_sync("How long is 'one two three'?")
print("final output               :", result.output)
print("model requests (via hook)  :", request_count["n"])
