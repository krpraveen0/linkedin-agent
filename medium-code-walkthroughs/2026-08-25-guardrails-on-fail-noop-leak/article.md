# My Guardrails Validator Caught the Leaked API Key. With `on_fail="noop"`, It Handed the Key Right Back.

I wired a validator into my agent's output path to stop it from ever echoing an API key back to a user. I fed it a string with a live-looking `sk-` token. The validator fired. `validation_passed` came back `False`. And the value my code read next — the one it forwarded to the user — was the original string, key intact.

The guardrail worked exactly as documented. I had just read the wrong field.

This is a small, specific trap in [Guardrails AI](https://github.com/guardrails-ai/guardrails), and it is worth understanding right now because the library shipped [version 0.11.0 on August 14, 2026](https://pypi.org/pypi/guardrails-ai/json). That release [deprecated the old `guardrails hub` CLI and private registry, moving validators to plain `pip install` packages on PyPI](https://github.com/guardrails-ai/guardrails/releases). Installing a validator is now a one-line pip command with no separate registry step, which means more people are about to reach for it. The trap below is the first thing that bites them.

## A guard returns two answers, not one

The mental model most people bring to an output guard is a filter: pass text in, get safe text out. Guardrails does not work that way. When you call `guard.validate(...)`, it returns a `ValidationOutcome` object with two independent signals:

- `validation_passed` — a boolean verdict: did every validator pass?
- `validated_output` — the value the guard decided to give back.

These two fields do not always agree, and that is by design. What `validated_output` contains when a validator fails depends entirely on the `on_fail` action you chose for that validator. The verdict tells you *whether* something failed. The action decides *what you get anyway*.

If you treat `validated_output` as "the safe version" and never check `validation_passed`, you have built a guard that inspects your output, records a failure, and then hands the failure through untouched.

## What each `on_fail` action actually returns

Guardrails ships a fixed set of failure actions. The [documented options](https://www.guardrailsai.com/docs/concepts/validator_on_fail_actions) are `reask`, `fix`, `filter`, `refrain`, `noop`, `exception`, and `fix_reask`. The two that involve re-prompting a model (`reask`, `fix_reask`) need an LLM. The rest are pure, deterministic transforms on the value, so you can see exactly what each one does with no API key and no model at all.

Here is a validator that fails any string containing an `sk-` token, run through every non-LLM action against the same input:

```python
from guardrails import Guard, OnFailAction
from guardrails.validator_base import Validator, register_validator, PassResult, FailResult


@register_validator(name="no-api-key", data_type="string")
class NoApiKey(Validator):
    """Fails any text that looks like it leaked an API key."""
    def validate(self, value, metadata):
        if "sk-" in value:
            return FailResult(error_message="Output contains an API-key-like token.",
                              fix_value="[REDACTED]")
        return PassResult()


BAD = "sure, your key is sk-abc123"

# None == "let the validator use its default action"
actions = [None, OnFailAction.NOOP, OnFailAction.FIX,
           OnFailAction.FILTER, OnFailAction.REFRAIN, OnFailAction.EXCEPTION]

print(f"input: {BAD!r}\n")
print(f"{'on_fail':<22}{'passed':<8}{'validated_output'}")
print("-" * 60)
for action in actions:
    validator = NoApiKey() if action is None else NoApiKey(on_fail=action)
    label = "(default)" if action is None else str(action).split(".")[-1].lower()
    guard = Guard().use(validator)
    try:
        outcome = guard.validate(BAD)
        print(f"{label:<22}{str(outcome.validation_passed):<8}{outcome.validated_output!r}")
    except Exception as exc:
        print(f"{label:<22}{'—':<8}RAISES {type(exc).__name__}")
```

Running that script against Guardrails 0.11.0 prints exactly this:

```
input: 'sure, your key is sk-abc123'

on_fail               passed  validated_output
------------------------------------------------------------
(default)             —       RAISES ValidationError
noop                  False   'sure, your key is sk-abc123'
fix                   True    '[REDACTED]'
filter                False   None
refrain               False   None
exception             —       RAISES ValidationError
```

Read that table as a spectrum of trust in `validated_output`:

- **`exception`** and the **default** stop execution cold. Nothing downstream runs. The unsafe value never reaches your next line of code.
- **`filter`** and **`refrain`** replace the output with `None`. Your value is gone, and `validation_passed` is `False`. You will notice, because your next line probably chokes on `None`.
- **`fix`** returns the `fix_value` your validator supplied (`[REDACTED]`), and reports `passed=True`. This is the one case where a failed check produces a genuinely safe, usable string.
- **`noop`** returns the original, unmodified, unsafe value, and sets `passed=False`.

`noop` is the outlier. It is the only action that gives you back the exact bytes you were trying to block while looking, at a glance, like it did something.

## Why `noop` is the one that leaks

The name reads like "log it and move on," and that is precisely how people use it: a soft mode that flags problems without breaking the app. It does flag the problem. The failure reason is recorded and available. But the value it returns is the raw input, and the failure lives in a field you have to go read on purpose.

Here is the realistic version of the bug — not a contrived test, but the shape of code people actually write:

```python
from guardrails import Guard
from guardrails.validator_base import Validator, register_validator, PassResult, FailResult


@register_validator(name="no-api-key", data_type="string")
class NoApiKey(Validator):
    def validate(self, value, metadata):
        if "sk-" in value:
            return FailResult(error_message="Output contains an API-key-like token.")
        return PassResult()


model_output = "sure, your key is sk-abc123"

# "noop" sounds harmless: just note the problem, don't blow up.
guard = Guard().use(NoApiKey(on_fail="noop"))
outcome = guard.validate(model_output)

# The natural thing to write, and the bug.
print("shipping to user:", outcome.validated_output)

# The verdict lived in a different field the whole time.
print("validation_passed:", outcome.validation_passed)
for s in outcome.validation_summaries:
    print("summary:", s.failure_reason)
```

The output:

```
shipping to user: sure, your key is sk-abc123
validation_passed: False
summary: Output contains an API-key-like token.
```

The verdict was `False` the entire time, and the failure reason sat in `validation_summaries` waiting to be read. But the one line a developer naturally writes — take `validated_output`, send it on — sails straight past both and ships the token.

## The default is not `noop` — and that matters

There is a reassuring half of this story. If you never pass `on_fail` at all, Guardrails does not fall back to `noop`. It defaults to `exception`. You can confirm this in the source: in `validator_base.py`, the base `Validator` constructor runs `if on_fail is None: on_fail = OnFailAction.EXCEPTION`. A bare validator raises on failure, which is the fail-closed behavior you want for a safety check.

So the danger is not the out-of-the-box default. The danger is the moment you reach for what looks like the gentle option. `noop` is a common choice in tutorials and staging setups because nobody wants a validator to crash production on a false positive. That instinct is reasonable. The mistake is assuming `noop` also cleans the output. It does not clean anything. It hands the value back and asks you to check the verdict yourself.

If you want fail-open behavior that is actually safe, `noop` is the wrong tool. Reach for `filter` (drops the value to `None`) or `fix` (returns a scrubbed replacement), or keep the `exception` default and catch it where you can substitute a safe fallback. Use `noop` only when you have already wired `validation_passed` into your control flow and are treating the guard as a signal, not a filter.

## Try It Yourself

Everything above runs on CPU with no API key. Setup:

```bash
python -m venv gr-venv && . gr-venv/bin/activate
pip install "guardrails-ai==0.11.0"
```

Save the first script as `on_fail_actions.py` and the second as `noop_leak.py` (both are in the linked walkthrough repo), then run them. This is the exact, unedited output captured on Python 3.11.15 with `guardrails-ai==0.11.0`:

```
$ python on_fail_actions.py
input: 'sure, your key is sk-abc123'

on_fail               passed  validated_output
------------------------------------------------------------
(default)             —       RAISES ValidationError
noop                  False   'sure, your key is sk-abc123'
fix                   True    '[REDACTED]'
filter                False   None
refrain               False   None
exception             —       RAISES ValidationError
```

```
$ python noop_leak.py
shipping to user: sure, your key is sk-abc123
validation_passed: False
summary: Output contains an API-key-like token.
```

That third line — `summary` — is the failure reason, pulled from `outcome.validation_summaries`. It was there all along. The `noop` path just never put it in your way.

## Key Takeaways

- A Guardrails `ValidationOutcome` carries two separate signals: `validation_passed` (the verdict) and `validated_output` (the value). They can disagree, and which one you trust is a decision you make in code.
- The `on_fail` action decides what `validated_output` contains on failure. `fix` returns a safe replacement; `filter` and `refrain` return `None`; `exception` and the default raise; `noop` returns the original unsafe value.
- With `on_fail="noop"`, reading only `validated_output` ships exactly the content you were validating against. Always check `validation_passed` when you use `noop`.
- The default action in Guardrails 0.11.0 is `exception`, verified in the `Validator` base constructor, not `noop`. The risk appears when you deliberately choose the "soft" option.
- For fail-open safety, prefer `filter` or `fix` over `noop`, or catch the default exception and substitute a fallback.

*This walkthrough validates traceability, freshness, and code execution against Guardrails 0.11.0. It is not a substitute for a security review of your own validation logic.*

**Sources:** [Guardrails AI 0.11.0 on PyPI (released 2026-08-14)](https://pypi.org/pypi/guardrails-ai/json) · [Guardrails GitHub releases](https://github.com/guardrails-ai/guardrails/releases) · [Validator OnFail Actions documentation](https://www.guardrailsai.com/docs/concepts/validator_on_fail_actions) · [Guardrails source repository](https://github.com/guardrails-ai/guardrails)
