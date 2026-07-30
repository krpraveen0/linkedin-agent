# DSPy Doesn't Send Your LLM a JSON Schema by Default — It Sends Text Markers, Then Silently Retries as JSON

Ask most developers how a modern LLM framework gets structured output, and they'll say "JSON schema" — you hand the model a schema, the provider enforces it, you get back valid JSON. That's how [OpenAI structured outputs](https://platform.openai.com/docs/guides/structured-outputs) and most tool-calling APIs work. So it surprises people to learn that [DSPy](https://github.com/stanfordnlp/dspy), the framework that popularized programming LLMs instead of prompting them, does not do this by default. Out of the box it sends your model a plain-text template full of `[[ ## field ## ]]` markers and parses the reply by splitting on them. Only if that parse fails does it quietly retry the whole call as JSON.

If you have never printed the prompt DSPy actually builds, this is worth two minutes. I installed `dspy==3.2.1` — the current stable release, published [May 5, 2026](https://pypi.org/project/dspy/) — pointed it at a fake local model that records every request, and watched exactly what it sends and how it recovers. No API key, no network. Here is what came back.

## Why this is worth looking at now

DSPy hit 3.0 on [August 12, 2025](https://pypi.org/project/dspy/), and its adapter layer — the part that turns a typed `Signature` into an actual prompt and turns the reply back into typed fields — has been under active rework since. The [3.2.0 release](https://github.com/stanfordnlp/dspy/releases/tag/3.2.0) (April 21, 2026) added an `XMLAdapter`, changed adapters to "raise `AdapterParseError` on empty LM response instead of silent `None`," and removed the `litellm` import from adapters entirely, exposing capability flags like `supports_response_schema` instead. The adapter is no longer a hidden implementation detail; it is a first-class, swappable piece of the stack. That makes it exactly the layer worth understanding before you trust it in production — because the default behavior is not the one most people assume.

## The default nobody configures

DSPy's control flow for picking an adapter is one line, and you can read it in the installed package (`dspy/predict/predict.py`):

```python
adapter = settings.adapter or ChatAdapter()
```

If you never call `dspy.configure(adapter=...)` — and most tutorials don't — `settings.adapter` is `None`, so you get `ChatAdapter`. That is the default for every `dspy.Predict`, `dspy.ChainOfThought`, and every module built on them. So the question "what does DSPy send my model?" is really "what does `ChatAdapter` build?"

## What DSPy actually sends

Here's the setup: a tiny fake language model that satisfies DSPy's `BaseLM` interface, records each request, and returns whatever text you script. Because it's local, the output below is deterministic and reproducible.

```python
import dspy
from dspy.clients.base_lm import BaseLM
from dspy.dsp.utils import dotdict

class RecordingLM(BaseLM):
    """Records every request DSPy sends and replies with scripted text."""
    def __init__(self, chat_reply, json_reply):
        super().__init__(model="recording-lm")
        self.chat_reply, self.json_reply = chat_reply, json_reply
        self.calls = []

    def forward(self, prompt=None, messages=None, **kwargs):
        # ChatAdapter asks for [[ ## markers ## ]]; JSONAdapter asks for a JSON object.
        is_json_mode = "JSON object" in messages[-1]["content"]
        self.calls.append({"json_mode": is_json_mode})
        content = self.json_reply if is_json_mode else self.chat_reply
        msg = dotdict(content=content, tool_calls=None)
        return dotdict(choices=[dotdict(message=msg, finish_reason="stop")],
                       usage=dotdict(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                       model="recording-lm")

class ClassifyTicket(dspy.Signature):
    """Classify a support ticket by urgency."""
    ticket: str = dspy.InputField()
    urgency: str = dspy.OutputField(desc="one of: low, medium, high")
```

Now run a `ChainOfThought` over one ticket and print the exact messages DSPy sent:

```python
lm = RecordingLM(
    chat_reply="[[ ## reasoning ## ]]\nSite is down for all users.\n"
               "[[ ## urgency ## ]]\nhigh\n[[ ## completed ## ]]",
    json_reply='{"reasoning": "Site is down for all users.", "urgency": "high"}')
dspy.configure(lm=lm)

result = dspy.ChainOfThought(ClassifyTicket)(
    ticket="The whole site is down and no one can log in.")

print(dspy.settings.lm.history[-1]["messages"][0]["content"])   # system message
print(dspy.settings.lm.history[-1]["messages"][-1]["content"])  # user message
print("urgency:", repr(result.urgency), "reasoning:", repr(result.reasoning))
```

The real captured system message is a text contract, not a schema:

```
Your input fields are:
1. `ticket` (str):
Your output fields are:
1. `reasoning` (str):
2. `urgency` (str): one of: low, medium, high
All interactions will be structured in the following way, with the appropriate values filled in.

[[ ## ticket ## ]]
{ticket}

[[ ## reasoning ## ]]
{reasoning}

[[ ## urgency ## ]]
{urgency}

[[ ## completed ## ]]
In adhering to this structure, your objective is:
        Classify a support ticket by urgency.
```

Two things jump out. First, there's a `reasoning` output field I never declared — `ChainOfThought` injects it ahead of my signature's fields, which is how "chain of thought" is implemented under the hood: an extra text field, not a special API. Second, the whole thing is a fill-in-the-blanks template keyed on `[[ ## field ## ]]` markers. The user message then repeats the marker for the input and tells the model exactly how to close out:

```
[[ ## ticket ## ]]
The whole site is down and no one can log in.

Respond with the corresponding output fields, starting with the field `[[ ## reasoning ## ]]`, then `[[ ## urgency ## ]]`, and then ending with the marker for `[[ ## completed ## ]]`.
```

DSPy parses the reply back by matching those markers line by line. The compiled regex lives in `dspy/adapters/chat_adapter.py`:

```python
field_header_pattern = re.compile(r"\[\[ ## (\w+) ## \]\]")
```

Every line that matches starts a new field; everything until the next marker is that field's value. My scripted reply parsed cleanly, and `result.urgency` came back as the string `'high'` in a single LM call. No JSON schema was ever sent.

## When the model breaks the format

Markers are brittle in a way schemas are not: a model that ignores the instructions and answers in prose produces zero markers, and there is nothing to parse. DSPy's answer is a fallback that most users never see. Point the fake model at a marker-free reply and run the same program:

```python
broken_lm = RecordingLM(
    chat_reply="The urgency is high because the site is completely down.",  # no markers
    json_reply='{"reasoning": "Site is down for all users.", "urgency": "high"}')
dspy.configure(lm=broken_lm)

result2 = dspy.ChainOfThought(ClassifyTicket)(
    ticket="The whole site is down and no one can log in.")

print("urgency:", repr(result2.urgency))
for i, c in enumerate(broken_lm.calls, 1):
    print(f"call {i}: json_mode={c['json_mode']}")
```

Real output:

```
urgency: 'high'
call 1: json_mode=False
call 2: json_mode=True
```

The program still returned `'high'` — but it took two LM calls to get there. The first used the marker format and failed to parse; the second was reissued by `JSONAdapter`, which asks the model for a JSON object instead. This is not magic. It's an explicit `try/except` in `ChatAdapter.__call__`, quoted from the installed 3.2.1 source:

```python
try:
    return super().__call__(lm, lm_kwargs, signature, demos, inputs)
except Exception as e:
    from dspy.adapters.json_adapter import JSONAdapter
    if (isinstance(e, ContextWindowExceededError)
            or isinstance(self, JSONAdapter)
            or not self.use_json_adapter_fallback):
        raise e
    return JSONAdapter()(lm, lm_kwargs, signature, demos, inputs)
```

Note the breadth of that `except Exception`. It catches *any* error from the marker attempt — a parse failure, but also a transient provider error — and retries the entire request through `JSONAdapter` unless the error was a context-window overflow. The switch is `use_json_adapter_fallback`, and I confirmed its default is `True` by reading the constructor signature in the same file. `JSONAdapter` in turn uses the provider's real structured-output mode when the model advertises `supports_response_schema`, and falls back to plain-text JSON when it doesn't.

## Why this matters in practice

None of this is a bug — it's a sensible design that makes DSPy work against models with no structured-output API at all. But the defaults have consequences worth knowing before you ship:

- **Your latency and token cost can silently double.** A model that reliably breaks the marker format pays for two full calls on every request, and the retry is invisible unless you inspect `lm.history` or your traces. If you see mysterious 2× cost on a DSPy module, a failing marker parse is a prime suspect.
- **"Structured output" doesn't mean schema-enforced.** By default the first attempt is unconstrained text. If you want the provider to actually enforce a JSON schema on the first call, configure `dspy.configure(adapter=dspy.JSONAdapter())` explicitly rather than relying on the fallback.
- **`ChainOfThought` is a prompt change, not a model feature.** It adds a `reasoning` text field to the same marker template. If you're counting output tokens or debugging why a "reasoning" key appears in your parsed result, that's where it comes from.

The broader point: the adapter is the seam between your typed program and a stochastic text generator, and DSPy 3.2 deliberately made it something you can see and swap. Print your prompt once. It takes one call to `dspy.settings.lm.history`, and it will tell you more about what your agent is doing than any diagram.

## Try It Yourself

Everything above was captured on `dspy==3.2.1` and Python 3.11, with no API key.

```bash
python3 -m venv venv && . venv/bin/activate
pip install "dspy==3.2.1"
python3 dspy_chatadapter_demo.py
```

The full `dspy_chatadapter_demo.py` — the `RecordingLM`, the signature, and both runs — is in the [companion repo](https://github.com/krpraveen0/linkedin-agent). Its real output is exactly the two blocks shown above: the marker template on the successful run, and `call 1: json_mode=False` / `call 2: json_mode=True` on the run where the model breaks the format. Swap `use_json_adapter_fallback=False` into a `ChatAdapter` you configure yourself and the second run raises `AdapterParseError` instead of recovering — proof that the retry is a choice, not a guarantee.

## Key Takeaways

- DSPy's default adapter is `ChatAdapter` (`adapter = settings.adapter or ChatAdapter()`), which sends a plain-text template using `[[ ## field ## ]]` markers, not a JSON schema.
- `ChainOfThought` works by injecting an extra `reasoning` output field into that same template — it's a prompt construction, not a special model call.
- On any exception from the marker attempt (except a context-window overflow), `ChatAdapter` silently retries the request through `JSONAdapter`; `use_json_adapter_fallback` defaults to `True`.
- That fallback can double your calls, latency, and cost without any visible error. Inspect `dspy.settings.lm.history` to see it.
- If you want first-call schema enforcement, configure `JSONAdapter` explicitly instead of leaning on the fallback.

*Sources: [DSPy on PyPI](https://pypi.org/project/dspy/), [DSPy 3.2.0 release notes](https://github.com/stanfordnlp/dspy/releases/tag/3.2.0), [ChatAdapter source (`dspy/adapters/chat_adapter.py`)](https://github.com/stanfordnlp/dspy/blob/main/dspy/adapters/chat_adapter.py), [DSPy ChatAdapter docs](https://dspy.ai/api/adapters/ChatAdapter/), and direct inspection of the installed `dspy==3.2.1` package. Code walkthrough PR: see the companion repository.*
