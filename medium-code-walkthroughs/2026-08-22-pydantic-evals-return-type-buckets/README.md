# pydantic-evals: the return type of your evaluator decides its report category

Code for the 2026-08-22 Medium article **"My pydantic-evals Evaluator Returned `1` for Pass and `0` for Fail. The Pass Rate Never Moved."**

In [pydantic-evals](https://pypi.org/project/pydantic-evals/), an evaluator's **return type** decides where its result lands in the report:

- `bool` → **assertion** (feeds the pass rate)
- `int` / finite `float` → **score** (averaged)
- `str` → **label** (tallied)

Because `bool` is a subclass of `int` in Python (`1 == True`), returning `0`/`1` for pass/fail is a trap: those results become *scores*, not *assertions*, and never touch the assertion pass rate. This is stated in the `EvaluationScalar` docstring and enforced in `dataset.py` (the `downcast(bool)` / `downcast(int, float)` / `downcast(str)` chain, lines 1254–1259) and `reporting/__init__.py` (pass-rate math, lines 242–245) of the installed 2.33.0 package.

Both scripts run fully offline — the "system under test" is a plain Python function, so **no API key, no model, no network**.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install pydantic-ai        # pulls in pydantic-evals 2.33.0
```

Verified with `pydantic-evals==2.33.0` (released 2026-08-21), `pydantic-ai==2.33.0`, `pydantic==2.13.4`, on CPython 3.11.15.

## Run

```bash
# Block 1: two evaluators, identical logic, bool vs int return type
COLUMNS=110 python eval_types.py

# Block 2: prove the two values land in different buckets even though 1 == True
COLUMNS=110 python inspect_buckets.py
```

`COLUMNS=110` just widens the Rich table so the columns are legible; it does not change any value.

## Real captured output

### `eval_types.py`

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

`MatchesBool` (bool) drives the **Assertions** column and the `50.0% ✔` pass rate. `MatchesInt` (int), same comparison, lands in **Scores** as `0.500`.

> The `Duration` column is wall-clock timing and varies run to run; every other value is deterministic.

### `inspect_buckets.py`

```
Python thinks 1 == True: True
assertions bucket: ['MatchesBool']
scores bucket:     ['MatchesInt']
MatchesBool -> True (bool) counted toward pass rate
MatchesInt  -> 1 (int) counted as a score, not a pass/fail
```

## Takeaway

Return a `bool` for any check you want a CI gate to fail on; reserve `int`/`float` for numbers you actually intend to average, and `str` for labels you want tallied. Converting a comparison to `0`/`1` on the way out silently demotes it from a pass/fail to a score.
