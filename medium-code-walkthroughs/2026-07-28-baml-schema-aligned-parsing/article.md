# BAML's Schema-Aligned Parser Reads LLM Output That json.loads() Can't — Here's Exactly What It Coerces

A model handed me this back when I asked it to triage a support ticket:

````text
I looked at the report. This is clearly urgent, here you go:

```json
{
  "summary": "Checkout page returns 500 on payment submit",
  "priority": "high",
  "effort_days": "2 days",
  "tags": "billing",
}
```
````

`json.loads()` on that string fails at character 0. Not on the trailing comma, not on the `"2 days"` — at the very first character, because the response opens with the word "I", not a `{`. Every downstream `try/except` I write is a bet that the model will stop doing this. It won't.

There are two ways out of this, and 2026's structured-output tooling has split cleanly down the middle. One camp stops the model from ever producing the bad string. The other lets the model say whatever it wants and fixes the string afterward. [BAML](https://docs.boundaryml.com/), whose Python runtime `baml-py` shipped version 0.223.0 on [June 23, 2026](https://pypi.org/project/baml-py/), is the sharpest expression of the second camp. Its parser is called Schema-Aligned Parsing, and this post is about exactly what it does to a string like the one above — verified against the installed package, not the marketing page.

## Two schools: constrain the tokens, or parse the mess

A quick map of the field, because BAML only makes sense in contrast.

**Constrained generation** compiles your schema into a finite state machine and, at every token step, sets the logits of any token that would break the grammar to negative infinity. The model *physically cannot* emit invalid JSON. [XGrammar](https://arxiv.org/abs/2411.15100) is the best-known implementation and the default constrained-decoding backend for vLLM, SGLang, and TensorRT-LLM ([TECHSY's 2026 library survey](https://techsy.io/en/blog/best-llm-structured-output-libraries)). It's fast and it's airtight — but it needs logit access, so it only works with models you host or providers that expose a strict mode.

**Schema-Aligned Parsing (SAP)**, BAML's approach, runs *after* generation. The model reasons freely, produces whatever it produces, and then a parser reads that output using your declared schema as a guide for what to look for ([BAML's SAP write-up](https://boundaryml.com/blog/schema-aligned-parsing)). Because it touches the string and not the sampler, it works with any model — including ones with no function-calling API at all — and it runs in microseconds without a network call ([The Data Quarry](https://thedataquarry.com/blog/baml-and-future-agentic-workflows/)).

The trade-off is obvious once you name it: constrained generation guarantees valid JSON but needs logit access; SAP needs no special access but has to be good enough at cleaning up whatever arrives. So the question that matters is empirical: how good is it, actually? Let me run it.

## The schema is the whole program

BAML uses its own small schema language. You describe the shape once in a `.baml` file, run a code generator, and get a typed Python client. Here is the entire schema for the ticket above:

```
enum Priority {
  Low
  Medium
  High
}

class Ticket {
  summary   string
  priority  Priority
  effort_days int
  tags      string[]
}

function TriageTicket(report: string) -> Ticket {
  client "openai-responses/gpt-5-mini"
  prompt #"
    Triage this report into a ticket.
    {{ report }}
    {{ ctx.output_format }}
  "#
}
```

The `client` line names a model, but I never call it in this article. BAML's [modular API](https://docs.boundaryml.com/guide/baml-advanced/modular-api) splits a function into its two halves — the HTTP request and the response parser — and exposes the parser on its own as `b.parse.TriageTicket(...)`. That method takes a raw string and returns a typed `Ticket`. No API key, no tokens, no network. It's the parser, isolated, and it's what makes SAP testable on your laptop.

## Try It Yourself

Setup is three commands. `baml-cli` ships inside the `baml-py` wheel.

```bash
pip install baml-py pydantic typing_extensions
baml-cli init            # writes baml_src/ (replace the sample with the schema above)
baml-cli generate        # writes baml_client/
```

Now the confrontation. Same messy string from the top of this article, run through `json.loads()` and then through `b.parse`:

````python
import json
from baml_client import b

raw = '''I looked at the report. This is clearly urgent, here you go:

```json
{
  "summary": "Checkout page returns 500 on payment submit",
  "priority": "high",
  "effort_days": "2 days",
  "tags": "billing",
}
```'''

print("=== json.loads() ===")
try:
    json.loads(raw)
except json.JSONDecodeError as e:
    print(f"JSONDecodeError -> {e}")

print("\n=== b.parse.TriageTicket() ===")
t = b.parse.TriageTicket(raw)
print("returned:", type(t).__name__)
print("priority   ->", repr(t.priority), "  (", type(t.priority).__name__, ")")
print("effort_days->", repr(t.effort_days), "        (", type(t.effort_days).__name__, ")")
print("tags       ->", repr(t.tags), "     (", type(t.tags).__name__, ")")
print("summary    ->", t.summary)
````

The captured output, on `baml-py` 0.223.0 with Python 3.11.15:

```
=== json.loads() ===
JSONDecodeError -> Expecting value: line 1 column 1 (char 0)

=== b.parse.TriageTicket() ===
returned: Ticket
priority   -> <Priority.High: 'High'>   ( Priority )
effort_days-> 2         ( int )
tags       -> ['billing']      ( list )
summary    -> Checkout page returns 500 on payment submit
```

Look at what happened beyond stripping the prose and the fence. SAP did three coercions that a lenient JSON parser would not:

- `"priority": "high"` became the enum member `Priority.High`. The schema declares three variants; SAP matched the lowercase string to the right one, case-insensitively.
- `"effort_days": "2 days"` became the integer `2`. The field is typed `int`, so SAP pulled a number out of a string that was never a valid JSON number.
- `"tags": "billing"` — a single string — became the list `['billing']`. The field is `string[]`, so a scalar was lifted into a one-element array.

None of that is "parse the JSON leniently." It's parsing *toward a type*. The schema told the parser what each field was supposed to be, and the parser reshaped the raw values to fit. That is the "schema-aligned" in Schema-Aligned Parsing, and it's the part that a `json.loads()` plus a pile of `if isinstance(...)` checks doesn't give you for free.

## Where SAP stops

A coercion engine that never says no is just a hallucination with extra steps, so the useful question is what SAP *refuses* to do. Two cases, same parser:

```python
from baml_client import b
from baml_py import errors

cases = [
    ("enum value not in schema ('urgent')",
     '{"summary":"x","priority":"urgent","effort_days":1,"tags":["a"]}'),
    ("required field 'summary' absent",
     '{"priority":"Low","effort_days":1,"tags":["a"]}'),
]
for label, raw in cases:
    print(f"=== {label} ===")
    try:
        b.parse.TriageTicket(raw)
    except errors.BamlError as e:
        print(f"{type(e).__name__} -> {str(e).splitlines()[0]}")
    print()
```

Captured output:

```
=== enum value not in schema ('urgent') ===
BamlError -> Failed to coerce value: ParsingError { scope: [], reason: "Failed while parsing required fields: missing=0, unparsed=1", causes: [ParsingError { scope: [], reason: "Failed to parse field priority: priority: Expected Priority enum value, got String(\"urgent\", Complete).", causes: [ParsingError { scope: ["priority"], reason: "Expected Priority enum value, got String(\"urgent\", Complete).", causes: [] }] }] }

=== required field 'summary' absent ===
BamlError -> Failed to coerce value: ParsingError { scope: [], reason: "Failed while parsing required fields: missing=1, unparsed=0", causes: [ParsingError { scope: [], reason: "Missing required field: summary", causes: [] }] }
```

This is the line SAP draws. It matched `"high"` to `Priority.High` a moment ago, but it will not invent a mapping for `"urgent"` — there's no schema variant close enough, so it raises `BamlError` rather than guess. And a missing required field is a hard failure, not a silently-null result. SAP bends the *format* and the *type*; it does not bend the *meaning* of your schema. The error is structured, too — it tells you the field (`priority`), what it wanted (a `Priority` enum value), and what it got (`String("urgent")`), which is exactly what you'd feed back into a retry.

## When to reach for this

The decision is about access, not preference. If you serve your own weights or your provider exposes a strict JSON mode, constrained generation gives you a hard guarantee and you should take it. The moment you're calling a model that doesn't offer logit access — or you want the model to emit reasoning before its answer, which strict JSON mode forbids — parsing-after becomes the only option that works, and SAP is a well-built version of it. BAML claims state-of-the-art results on the Berkeley Function Calling Leaderboard for this approach ([SAP write-up](https://boundaryml.com/blog/schema-aligned-parsing)); I haven't reproduced that benchmark, so treat the number as their claim, not mine. What I did reproduce is the behavior above, and the behavior is the part you actually depend on in production.

## Key Takeaways

- `json.loads()` fails at character 0 on a real LLM response because the response starts with prose, not `{`. Constrained generation and Schema-Aligned Parsing are the two ways past that, and they split on one axis: constrain the tokens during generation, or parse the string after.
- BAML's `b.parse.FunctionName()` runs only the parser — no model call, no API key — so SAP's behavior is fully testable offline on `baml-py` 0.223.0.
- SAP coerces *toward the declared type*: a case-wrong enum string became an enum member, `"2 days"` became `int 2`, and a lone string became a one-element list — none of which lenient JSON parsing does.
- SAP has a hard floor: an enum value with no schema match and a missing required field both raise a structured `BamlError`. It fixes format and type, not meaning.
- Choose by access. Own the logits → constrained generation's guarantee. Calling a black-box model, or want free-form reasoning first → parse-after with SAP.

## Sources

- BAML Python package, version 0.223.0 (released 2026-06-23), [PyPI](https://pypi.org/project/baml-py/) — and direct inspection of the installed `baml-py==0.223.0` on Python 3.11.15.
- BAML, "Prompting vs JSON Mode vs Function Calling vs Constrained Generation vs SAP" — [Schema-Aligned Parsing write-up](https://boundaryml.com/blog/schema-aligned-parsing).
- BAML docs, [Modular API](https://docs.boundaryml.com/guide/baml-advanced/modular-api) (the `b.parse` / `b.request` split).
- TECHSY, "[8 LLM Structured Output Libraries Ranked (2026)](https://techsy.io/en/blog/best-llm-structured-output-libraries)."
- The Data Quarry, "[Why I'm excited about BAML and the future of agentic workflows](https://thedataquarry.com/blog/baml-and-future-agentic-workflows/)."
- XGrammar (constrained decoding), [arXiv:2411.15100](https://arxiv.org/abs/2411.15100).
