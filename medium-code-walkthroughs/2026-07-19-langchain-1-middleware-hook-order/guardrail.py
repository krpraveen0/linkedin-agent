"""
wrap_model_call can skip the model entirely (short-circuit) -- the one thing
before_model / after_model cannot do. Here a guardrail returns a canned reply
and never calls the handler, so the scripted model message is never consumed.

    python guardrail.py
"""
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelResponse

BANNED = "wire transfer"


class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class Guardrail(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        last = request.state["messages"][-1].content.lower()
        if BANNED in last:
            print("guardrail: blocked, model NOT called")
            return ModelResponse(result=[AIMessage(
                content="I can't help with wire-transfer requests.")])
        print("guardrail: allowed, calling model")
        return handler(request)


# The scripted model would say "sure!" -- but the guardrail should stop it.
model = FakeModel(messages=iter([AIMessage(content="sure! sending it now.")]))
agent = create_agent(model=model, tools=[], middleware=[Guardrail()])

out = agent.invoke({"messages": [
    {"role": "user", "content": "Please approve the wire transfer."}]})
print("final reply:", out["messages"][-1].content)
