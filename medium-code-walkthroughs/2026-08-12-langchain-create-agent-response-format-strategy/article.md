# I Gave create_agent a Response Schema. For My Local Model, LangChain Turned It Into a Tool.

You pass a Pydantic class to LangChain's `create_agent` as `response_format`, expecting the agent to return a typed object. That much works. What you probably do not expect is that, for some models, LangChain quietly adds a tool to the list your model gets to choose from — a tool named after your schema — and leaves it sitting there next to the real tools you registered. For other models, it adds nothing. The deciding factor is a hardcoded list of model-name patterns baked into the framework.

I found this while poking at `langchain==1.3.15`, released on [2026-08-11](https://pypi.org/project/langchain/1.3.15/), one day before I wrote this. The behavior traces back to the 1.0 line ([1.0.0 shipped 2025-10-17](https://pypi.org/project/langchain/1.0.0/)), and it is the mechanical root of several open bug reports. Here is exactly what happens, verified against the installed package rather than the docs.

## Two ways to get structured output, picked for you

LangChain 1.0's `create_agent` folds structured output into the main agent loop instead of making a separate call at the end. It does this through one of two strategies, and the [structured-output design](https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/factory.py) names both:

- **`ProviderStrategy`** uses the model provider's native structured-output feature (the `json_schema` response format that OpenAI, Anthropic, and others expose). No extra tool is involved.
- **`ToolStrategy`** wraps your schema as a tool. The model "answers" by calling that synthetic tool with arguments that match your fields, and the framework parses those arguments back into your object.

When you hand `response_format` a raw schema instead of an explicit strategy, `create_agent` decides for you. The source comment in `factory.py` is blunt about the sequence:

> Raw schemas are wrapped in AutoStrategy to preserve auto-detection intent. AutoStrategy is converted to ToolStrategy upfront to calculate tools during agent creation, but may be replaced with ProviderStrategy later based on model capabilities.

Read that carefully. Your raw schema is turned into a `ToolStrategy` at construction time so the framework can build the tool. Only later, once it inspects the model, might it switch to `ProviderStrategy`. If that switch does not happen, the synthetic tool ships to the model.

## The fork is a hardcoded capability check

The switch is decided by a function called `_supports_provider_strategy`. It looks at the model in two steps. First it checks the model object's `profile` — capability metadata that real provider integrations carry — for a `structured_output` flag. If there is no profile (a local model, a custom `BaseChatModel`, or a bare model-name string), it falls back to matching the model name against a fixed list of regexes named `FALLBACK_MODELS_WITH_STRUCTURED_OUTPUT`.

That list covers specific families: OpenAI `gpt-4o` / `gpt-4.1` / `gpt-5.x`, several Claude models, and Grok. It has no entry for Gemini, Llama, Mistral, or anything you run yourself. The list even carries its own honest caveat in the source:

> If model profile data are not available, model names matching these patterns are assumed to support provider-native structured output.

So the rule is: recognized name or a profile that advertises the feature, and you get `ProviderStrategy` with no extra tool. Anything else, and you get `ToolStrategy` with a tool grafted onto your model's options. There is a special case worth knowing: for Gemini models with a profile, the check excludes pre-3-series versions from combining tools with structured output, while [Gemini 3 is allowed](https://github.com/langchain-ai/langchain/issues/34463). That carve-out exists because an agent was falling back to `ToolStrategy` for Gemini 3 even though the model supports both together.

## Try It Yourself

You do not need an API key to watch this happen. A scripted `BaseChatModel` stands in for a real LLM, records the tools it is offered whenever `create_agent` binds them, and replays canned turns. Everything below ran on `langchain==1.3.15`, `langchain-core==1.5.4`, `langgraph==1.2.11`.

First, confirm that `ToolStrategy` really does build a tool out of a plain schema:

```python
from pydantic import BaseModel
from langchain.agents.structured_output import ToolStrategy, OutputToolBinding

class Weather(BaseModel):
    """Structured weather answer."""
    city: str
    temp_c: float
    summary: str

for spec in ToolStrategy(schema=Weather).schema_specs:
    binding = OutputToolBinding.from_schema_spec(spec)
    print("injected tool name:", binding.tool.name)
    print("injected tool args:", list(binding.tool.args.keys()))
```

```text
== Demo 1: ToolStrategy turns your schema into a tool ==
  injected tool name: Weather
  injected tool args: ['city', 'temp_c', 'summary']
```

Your `Weather` model is now a tool called `Weather`. Next, build an agent with a real tool and a local-style model whose `profile` is `None`, and record what the model is offered:

```python
class ScriptedModel(BaseChatModel):
    model_name: str = "my-local-llm"
    profile: Optional[dict] = None  # no provider-native structured output

    def bind_tools(self, tools, **kwargs):
        RECORD[self.model_name] = [getattr(t, "name", None) or t.get("name") for t in tools]
        return super().bind(tools=tools, **kwargs)
    # _generate() replays: first a get_weather call, then a Weather call to answer

agent = create_agent(local, tools=[get_weather], response_format=Weather)
result = agent.invoke({"messages": [{"role": "user", "content": "weather in Paris?"}]})
print("tools the model was offered:", RECORD["my-local-llm"])
print("structured_response:", result.get("structured_response"))
```

```text
== Demo 2: local model (no native structured output) ==
  tools the model was offered: ['get_weather', 'Weather']
  structured_response: city='Paris' temp_c=19.0 summary='clear'
```

There it is. The model was handed `['get_weather', 'Weather']`. Your real tool and a tool minted from your response schema sit side by side, and the model has to decide which one to call on every turn. Now flip a single field — give the model a `profile` that advertises structured output — and rerun the same agent:

```python
capable = ScriptedModel(model_name="capable-model",
                        profile={"structured_output": True})
agent2 = create_agent(capable, tools=[get_weather], response_format=Weather)
result2 = agent2.invoke({"messages": [{"role": "user", "content": "weather in Paris?"}]})
print("tools the model was offered:", RECORD["capable-model"])
```

```text
== Demo 3: model whose profile advertises structured_output ==
  tools the model was offered: ['get_weather']
  structured_response: city='Paris' temp_c=19.0 summary='clear'
```

Same schema, same tool, same final `structured_response`. But the capable model was offered only `['get_weather']` — no synthetic tool, because the framework routed it through `ProviderStrategy` and asked for native structured output instead. The only thing that changed the tool list was the model's advertised capability.

## Why this bites in production

On its own, an extra tool is not a catastrophe. The trouble starts when the synthetic response tool has to share the model's attention with your real tools, and the model is weaker or less predictable than the ones on the hardcoded list — which describes most local and self-hosted setups.

Two open issues show the shape of the failures. The Gemini 3 report ([#34463](https://github.com/langchain-ai/langchain/issues/34463), opened 2025-12-23) is the case where a capable model was wrongly forced into `ToolStrategy` because the capability check returned false whenever tools were present. A separate report ([#36568](https://github.com/langchain-ai/langchain/issues/36568), opened 2026-04-06) documents that when middleware tries to narrow which structured-output tools a model sees, the narrowing is "validated but never enforced" — the model is still bound with all of them, because the tool set is built once at initialization and reused in several places. Both are downstream of the same design: structured output is a tool, and tools are decided early.

The practical lesson is that `response_format` is not a passive type annotation. It changes the model's action space, and it does so conditionally. If you run a model that is not on the list and does not carry a profile, assume `ToolStrategy` is in play and design for a model that may reach for your response tool when you wanted a real one, or reach for a real tool when you wanted the answer. If your model genuinely supports native structured output, you can skip the guessing by passing `ProviderStrategy(schema=YourModel)` explicitly instead of a raw schema — that is the same workaround the Gemini 3 reporter used.

## Key Takeaways

- `create_agent(response_format=Schema)` does not always use native structured output. It wraps a raw schema in `AutoStrategy`, builds a `ToolStrategy` tool upfront, and only swaps to `ProviderStrategy` if the model is judged capable.
- Capability is judged by `_supports_provider_strategy`: the model's `profile` first, then a hardcoded `FALLBACK_MODELS_WITH_STRUCTURED_OUTPUT` regex list covering specific OpenAI, Anthropic, and Grok names. Gemini, Llama, Mistral, and local models are not on it.
- Under `ToolStrategy`, a tool named after your schema is added to the same list as your real tools. I observed a local model offered `['get_weather', 'Weather']` versus `['get_weather']` for a model with a structured-output profile.
- This design is the root of real bug reports (#34463, #36568). If your model supports native structured output, pass `ProviderStrategy(schema=...)` explicitly to avoid the fallback.

**Sources:** [langchain factory.py source](https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/factory.py) · [Issue #34463 — Gemini 3 falls back to ToolStrategy](https://github.com/langchain-ai/langchain/issues/34463) · [Issue #36568 — middleware narrowing not enforced](https://github.com/langchain-ai/langchain/issues/36568) · [langchain 1.3.15 on PyPI](https://pypi.org/project/langchain/1.3.15/) · [langchain 1.0.0 on PyPI](https://pypi.org/project/langchain/1.0.0/) · verified locally against `langchain==1.3.15`, `langchain-core==1.5.4`, `langgraph==1.2.11`.
