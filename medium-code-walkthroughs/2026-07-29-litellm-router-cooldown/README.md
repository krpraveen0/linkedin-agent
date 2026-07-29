# LiteLLM Router cooldown — code walkthrough

Companion code for the 2026-07-29 article *"LiteLLM Cools Down a Failing Model on the First 429 — Unless It's Your Only One."*

`cooldown_probe.py` demonstrates, with no API keys and no network, exactly when the
LiteLLM Router puts a deployment into cooldown. Every deployment uses LiteLLM's
built-in `mock_response: "litellm.RateLimitError"`, which raises a real `429`
through the same code path a live provider would.

Three experiments:

1. **Multi-deployment group, one 429 per call** — shows a single `429` cools one
   deployment immediately (no three-strike counter in the default path).
2. **Keep calling until every deployment is cold** — shows the caller gets the raw
   `RateLimitError` until all deployments are cold, then a `RouterRateLimitError`
   (a `ValueError` carrying `cooldown_time=5` in its message, with no `Retry-After`
   header).
3. **Single-deployment group** — shows a lone deployment is never cooled down.

## Setup and run

```bash
pip install litellm            # tested on litellm 1.94.0
python cooldown_probe.py
```

If `import litellm` fails with a `cryptography` / `_cffi_backend` error on your
machine (a pre-existing broken system install), reinstall the wheels:

```bash
pip install --force-reinstall --no-cache-dir --ignore-installed cffi cryptography
```

## Real captured output

The `logging.getLogger("LiteLLM").setLevel(logging.ERROR)` line in the script mutes
LiteLLM's cost-map warnings, so the output below is what the script genuinely prints
(not hand-edited):

```text
litellm 1.94.0

=== EXP 1: multi-deployment group, one 429 per call ===
after call 1: cooled down -> ['deploy-a']
after call 2: cooled down -> ['deploy-a', 'deploy-b']

=== EXP 2: keep calling until every deployment is cold ===
call 1: RateLimitError (429 from a live deployment)
call 2: RateLimitError (429 from a live deployment)
call 3: RouterRateLimitError -> cooldown_time=5s
          type is HTTP error? False | isinstance ValueError: True

=== EXP 3: single-deployment group, same 429 ===
after 3 x 429: cooled down -> NONE — still serving
```

**Note on reproducibility:** which deployment id appears first in EXP 1
(`deploy-a` vs `deploy-b`) depends on the Router's routing order and can vary
between runs. The counts — one cold after one call, both cold after two — are stable.

## Files

- `cooldown_probe.py` — the runnable probe (three experiments).
- `article.md` — the full article.
- `figure1-cooldown-decision.svg` — the cooldown decision path.
- `figure2-all-cold-timeline.svg` — the two-deployment failure timeline.
