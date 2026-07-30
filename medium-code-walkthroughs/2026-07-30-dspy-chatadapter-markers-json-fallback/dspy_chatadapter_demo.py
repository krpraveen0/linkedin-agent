"""
Demonstrate what DSPy's default ChatAdapter actually sends to an LLM,
how it parses the reply, and how it silently falls back to JSONAdapter
when the reply breaks the [[ ## field ## ]] format.

No network and no API key: a fake LM records every request DSPy makes
and replies with scripted text.

Tested on dspy==3.2.1, Python 3.11.
"""
import dspy
from dspy.clients.base_lm import BaseLM
from dspy.dsp.utils import dotdict


class RecordingLM(BaseLM):
    """A fake LM that records every request DSPy sends and replies
    with scripted text. DSPy's JSONAdapter sets `response_format` on the
    call; ChatAdapter does not, so we can tell the two apart."""

    def __init__(self, chat_reply, json_reply):
        super().__init__(model="recording-lm")
        self.chat_reply = chat_reply
        self.json_reply = json_reply
        self.calls = []

    def forward(self, prompt=None, messages=None, **kwargs):
        # ChatAdapter asks for [[ ## markers ## ]]; JSONAdapter asks for a JSON object.
        is_json_mode = "JSON object" in messages[-1]["content"]
        self.calls.append({"json_mode": is_json_mode})
        content = self.json_reply if is_json_mode else self.chat_reply
        msg = dotdict(content=content, tool_calls=None)
        return dotdict(
            choices=[dotdict(message=msg, finish_reason="stop")],
            usage=dotdict(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            model="recording-lm",
        )


class ClassifyTicket(dspy.Signature):
    """Classify a support ticket by urgency."""
    ticket: str = dspy.InputField()
    urgency: str = dspy.OutputField(desc="one of: low, medium, high")


# ============ Block 1: the prompt DSPy actually builds ============
lm = RecordingLM(
    chat_reply="[[ ## reasoning ## ]]\nSite is down for all users.\n"
               "[[ ## urgency ## ]]\nhigh\n[[ ## completed ## ]]",
    json_reply='{"reasoning": "Site is down for all users.", "urgency": "high"}',
)
dspy.configure(lm=lm)

predict = dspy.ChainOfThought(ClassifyTicket)
result = predict(ticket="The whole site is down and no one can log in.")

print("=== SYSTEM MESSAGE DSPy BUILT ===")
print(dspy.settings.lm.history[-1]["messages"][0]["content"])
print("\n=== USER MESSAGE DSPy BUILT ===")
print(dspy.settings.lm.history[-1]["messages"][-1]["content"])
print("\n=== PARSED RESULT (structured) ===")
print("urgency:", repr(result.urgency), "| reasoning:", repr(result.reasoning))
print("LM calls:", len(lm.calls))


# ============ Block 2: break the format, watch the fallback ============
broken_lm = RecordingLM(
    chat_reply="The urgency is high because the site is completely down.",  # no markers
    json_reply='{"reasoning": "Site is down for all users.", "urgency": "high"}',
)
dspy.configure(lm=broken_lm)

result2 = dspy.ChainOfThought(ClassifyTicket)(
    ticket="The whole site is down and no one can log in."
)
print("\n=== FALLBACK BEHAVIOR ===")
print("urgency:", repr(result2.urgency))
for i, c in enumerate(broken_lm.calls, 1):
    print(f"call {i}: json_mode={c['json_mode']}")
