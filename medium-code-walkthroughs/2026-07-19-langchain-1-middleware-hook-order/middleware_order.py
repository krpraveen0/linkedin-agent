"""
LangChain 1.0 agent middleware: which hooks fire, in what order.

Runs fully offline against a scripted fake chat model (no API key). It logs
every middleware hook as create_agent drives one tool-calling turn, so the
printed sequence is the real execution order of the installed langchain build.

    pip install "langchain>=1.3,<2"
    python middleware_order.py
"""
import langchain
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import tool

STEP = [0]


def log(hook: str, mw: str) -> None:
    STEP[0] += 1
    print(f"{STEP[0]:>2}. {hook:<16} [{mw}]")


class FakeToolCallingModel(GenericFakeChatModel):
    """Scripted model that accepts .bind_tools() so create_agent can run it."""

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002 - tools ignored on purpose
        return self


class TraceMiddleware(AgentMiddleware):
    """Logs every hook it is given, tagged with its own name."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self._tag = name

    @property
    def name(self) -> str:
        return f"Trace-{self._tag}"

    def before_agent(self, state, runtime):
        log("before_agent", self._tag)

    def before_model(self, state, runtime):
        log("before_model", self._tag)

    def wrap_model_call(self, request, handler):
        log("wrap_model_call>", self._tag)   # before handing off to the model
        response = handler(request)
        log("wrap_model_call<", self._tag)   # after the model returns
        return response

    def wrap_tool_call(self, request, handler):
        log("wrap_tool_call", self._tag)
        return handler(request)

    def after_model(self, state, runtime):
        log("after_model", self._tag)

    def after_agent(self, state, runtime):
        log("after_agent", self._tag)


@tool
def get_weather(city: str) -> str:
    """Return the weather for a city."""
    return f"It is 21C and clear in {city}."


scripted = iter([
    AIMessage(content="", tool_calls=[
        {"name": "get_weather", "args": {"city": "Paris"}, "id": "call_1"}]),
    AIMessage(content="It is 21C and clear in Paris."),
])
model = FakeToolCallingModel(messages=scripted)

agent = create_agent(
    model=model,
    tools=[get_weather],
    middleware=[TraceMiddleware("OUTER"), TraceMiddleware("INNER")],
)

print(f"langchain {langchain.__version__}\n")
agent.invoke({"messages": [{"role": "user", "content": "Weather in Paris?"}]})
