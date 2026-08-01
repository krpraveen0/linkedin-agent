"""Where does a deepagents `write_file` actually write? (no LLM/API key needed)."""
import os
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from deepagents import create_deep_agent

class FakeToolModel(GenericFakeChatModel):
    """A scripted model that also answers bind_tools (the agent binds tools)."""
    def bind_tools(self, tools, **kwargs):
        return self  # ignore the tool schemas; we already scripted the calls


TARGET = "/reports/summary.md"          # an absolute path the agent will "write"
CONTENT = "quarterly numbers look fine\n"

# A fake model: first turn emits a write_file tool call, second turn ends the run.
scripted = iter([
    AIMessage(content="", tool_calls=[
        {"name": "write_file", "id": "call_1",
         "args": {"file_path": TARGET, "content": CONTENT}},
    ]),
    AIMessage(content="Done. I wrote the summary."),
])
model = FakeToolModel(messages=scripted)

agent = create_deep_agent(model=model)   # backend=None -> default StateBackend
result = agent.invoke({"messages": [{"role": "user", "content": "write the summary"}]})

print("files key in returned state:", list(result.get("files", {}).keys()))
print("content stored in state    :", repr(result["files"][TARGET]))
print("exists on real disk?       :", os.path.exists(TARGET))
