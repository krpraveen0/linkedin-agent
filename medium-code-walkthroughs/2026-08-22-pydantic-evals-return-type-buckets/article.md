# My pydantic-evals Evaluator Returned `1` for Pass and `0` for Fail. The Pass Rate Never Moved.

I was writing a test suite for an agent with [pydantic-evals](https://pypi.org/project/pydantic-evals/), Pydantic's evaluation framework. My evaluator compared the agent's answer to the expected answer and returned `1` when they matched and `0` when they didn't. Half my cases failed. I expected the summary table to show a 50% pass rate.

It showed a 50% *score*. The pass rate column was empty.

The difference is not cosmetic. In pydantic-evals, an assertion pass rate and an average score are two different things, tracked in two different columns, and my `0`s never touched the pass rate at all. The reason comes down to a single line in the library, and it is worth understanding before you trust a green eval run.

## The one line that decides everything

pydantic-evals lets an evaluator return a scalar, and that scalar can be a `bool`, an `int`, a `float`, or a `str`. What it does with the value depends entirely on the value's Python type. Here is the type definition, quoted verbatim from `evaluator.py` at the [v2.33.0 tag](https://raw.githubusercontent.com/pydantic/pydantic-ai/v2.33.0/pydantic_evals/pydantic_evals/evaluators/evaluator.py):

```python
EvaluationScalar = bool | int | Annotated[float, Field(allow_inf_nan=False)] | str
"""The most primitive output allowed as an output from an Evaluator.

`int` and finite `float` are treated as scores, `str` as labels, and `bool` as assertions.
"""
```

Read that docstring again. The category is not something you configure. It is inferred from the return type:

- a `bool` becomes an **assertion** (a pass/fail check),
- an `int` or finite `float` becomes a **score** (a number to average),
- a `str` becomes a **label** (a category to tally).

So `return True` and `return 1` are not interchangeable, even though Python itself says `1 == True`. One registers a passing test; the other records the number one. That is the whole bug in my suite: I reached for `0` and `1` out of habit, and pydantic-evals filed them under scores.

## Where the sorting actually happens

The classification is not a comment that the library ignores. When a report is assembled, each result is routed by type. This is `dataset.py`, lines 1254–1259 in the installed 2.33.0 package:

```python
if assertion := er.downcast(bool):
    assertions[name] = assertion
elif score := er.downcast(int, float):
    scores[name] = score
elif label := er.downcast(str):
    labels[name] = label
```

`downcast(bool)` is tried first. If your value is a real `bool`, it lands in `assertions`. Otherwise `downcast(int, float)` catches numbers and drops them in `scores`.

You might expect `downcast(int, float)` to also catch a `bool`, because in Python `bool` is a subclass of `int` — `isinstance(True, int)` is `True`. The library specifically prevents that. Here is the guard inside `downcast`:

```python
for value_type in value_types:
    if isinstance(self.value, value_type):
        # Only match bool with explicit bool type
        if isinstance(self.value, bool) and value_type is not bool:
            continue
        return cast(EvaluationResult[T], self)
return None
```

A `True` will match `downcast(bool)` but is skipped by `downcast(int, float)`. A plain `1` matches `downcast(int, float)` and never reaches the bool branch, because `1` is not a `bool`. The two values take entirely different paths through the same six lines of code.

## Why the pass rate stayed flat

The assertion pass rate is computed from the assertions bucket only. From `reporting/__init__.py`, lines 242–245:

```python
n_assertions = sum(len(case.assertions) for case in cases)
if n_assertions > 0:
    n_passing = sum(1 for case in cases for assertion in case.assertions.values() if assertion.value)
    average_assertions = n_passing / n_assertions
```

`n_assertions` counts only the results that landed in `case.assertions` — the `bool` returns. My evaluator returned `int`, so its results went to `case.scores`. As far as the pass-rate math was concerned, I had zero assertions. A failing `0` cannot lower a pass rate it was never counted in. The number I saw was `average_scores`: `(1 + 0) / 2 = 0.500`, displayed in the Scores column, which is a coincidence that made the mistake easy to miss.

## Try It Yourself

You do not need an API key or a model to see this. The "system under test" here is a plain Python function, so the whole thing runs offline and deterministically. Install the framework:

```bash
pip install pydantic-ai   # pulls in pydantic-evals 2.33.0
```

Now define two evaluators with identical logic — one returns a `bool`, one returns an `int` — and run them over the same two cases:

```python
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext


def classify(text: str) -> str:
    return "positive" if "love" in text.lower() else "negative"


class MatchesBool(Evaluator[str, str, str]):
    def evaluate(self, ctx: EvaluatorContext[str, str, str]) -> bool:
        return ctx.output == ctx.expected_output


class MatchesInt(Evaluator[str, str, str]):
    def evaluate(self, ctx: EvaluatorContext[str, str, str]) -> int:
        return 1 if ctx.output == ctx.expected_output else 0


dataset = Dataset[str, str, str](
    name="sentiment-check",
    cases=[
        Case(name="clear_positive", inputs="I love this",  expected_output="positive"),
        Case(name="wrong_guess",    inputs="This is fine", expected_output="positive"),
    ],
    evaluators=[MatchesBool(), MatchesInt()],
)

if __name__ == "__main__":
    report = dataset.evaluate_sync(classify)
    report.print(include_input=True, include_output=True, include_expected_output=True)
```

(Two small notes. As of 2.33.0, `Dataset` requires a `name` keyword argument — leave it out and you get a `TypeError` before anything runs. And the `if __name__ == "__main__"` guard matters: the second script imports this module, and without the guard the import would re-run the table print.)

Here is the real, unedited output:

```
Evaluating classify ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
                                       Evaluation Summary: classify
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Case ID        ┃ Inputs       ┃ Expected Output ┃ Outputs  ┃ Scores            ┃ Assertions ┃ Duration ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ clear_positive │ I love this  │ positive        │ positive │ MatchesInt: 1     │ ✔          │    1.8ms │
├────────────────┼──────────────┼─────────────────┼──────────┼───────────────────┼────────────┼──────────┤
│ wrong_guess    │ This is fine │ positive        │ negative │ MatchesInt: 0     │ ✗          │    2.4ms │
├────────────────┼──────────────┼─────────────────┼──────────┼───────────────────┼────────────┼──────────┤
│ Averages       │              │                 │          │ MatchesInt: 0.500 │ 50.0% ✔    │    2.1ms │
└────────────────┴──────────────┴─────────────────┴──────────┴───────────────────┴────────────┴──────────┘
```

(The `Duration` column is wall-clock timing and will differ on your machine; every other value is deterministic.)

`MatchesBool` produced the `✔`/`✗` marks and the `50.0% ✔` pass rate under **Assertions**. `MatchesInt` — the same comparison — produced `MatchesInt: 1`, `MatchesInt: 0`, and the `0.500` average under **Scores**. Two evaluators, one difference: the annotated return type.

To confirm the two values really are filed separately, inspect the buckets directly. This second script imports the same dataset and reads the per-case result dictionaries:

```python
from eval_types import dataset, classify

report = dataset.evaluate_sync(classify, progress=False)
case = report.cases[0]  # "clear_positive": both evaluators pass

print("Python thinks 1 == True:", 1 == True)
print("assertions bucket:", list(case.assertions))
print("scores bucket:    ", list(case.scores))

b = case.assertions["MatchesBool"].value
i = case.scores["MatchesInt"].value
print(f"MatchesBool -> {b!r} ({type(b).__name__}) counted toward pass rate")
print(f"MatchesInt  -> {i!r} ({type(i).__name__}) counted as a score, not a pass/fail")
```

Real output:

```
Python thinks 1 == True: True
assertions bucket: ['MatchesBool']
scores bucket:     ['MatchesInt']
MatchesBool -> True (bool) counted toward pass rate
MatchesInt  -> 1 (int) counted as a score, not a pass/fail
```

Python agrees that `1 == True`, and pydantic-evals still puts them in different buckets. The value's equality is irrelevant; only its type is consulted.

## What this means for your eval suite

The practical failure mode is a suite that looks stricter than it is. If you write correctness checks that return `0` and `1`, your CI gate that keys off the assertion pass rate sees no assertions and nothing to fail on. Every regression shows up as a slightly lower average score instead of a red pass/fail, and a score threshold is easier to fudge past than a hard assertion.

The fix is to decide, per evaluator, which category you actually want and return the matching type:

- Return a **`bool`** for anything you want to gate on. `assert`-style checks — did the output equal the expected value, did it contain the required phrase, did it stay under the token budget — belong here.
- Return an **`int`** or **`float`** only for genuine magnitudes you plan to average — a similarity score, a latency, a rubric grade from 1 to 5.
- Return a **`str`** when you want a labelled tally, like `"refusal"` / `"answer"` / `"tool_error"`, which the report groups into a distribution rather than averaging.

This also explains why the built-in `EqualsExpected` evaluator returns a `bool`: correctness is meant to be an assertion. If you write a custom correctness check, mirror that — return the comparison itself (`ctx.output == ctx.expected_output`), which is already a `bool`, rather than converting it to `0`/`1` on the way out.

## Key Takeaways

- In pydantic-evals, an evaluator's return **type** decides its report category: `bool` → assertion, `int`/`float` → score, `str` → label. This is stated in the `EvaluationScalar` docstring and enforced in `dataset.py`.
- `bool` and `int` are not interchangeable here even though `1 == True` in Python. `downcast` specifically refuses to treat a `bool` as an `int` and vice versa.
- The assertion pass rate is computed only from `bool` results. Returning `0`/`1` produces a score average, so failures expressed as `0` never lower a pass rate.
- Return a `bool` for anything you want a CI gate to fail on; reserve `int`/`float` for numbers you actually intend to average.
- Verified against pydantic-evals 2.33.0 (released 2026-08-21) by running the code above and reading the installed package source.

**Sources:** [pydantic-evals on PyPI (2.33.0, released 2026-08-21)](https://pypi.org/project/pydantic-evals/) · [`EvaluationScalar` definition and docstring, `evaluator.py` @ v2.33.0](https://raw.githubusercontent.com/pydantic/pydantic-ai/v2.33.0/pydantic_evals/pydantic_evals/evaluators/evaluator.py) · type-routing in `dataset.py` (lines 1254–1259) and pass-rate math in `reporting/__init__.py` (lines 242–245), both verified in the installed 2.33.0 package.
