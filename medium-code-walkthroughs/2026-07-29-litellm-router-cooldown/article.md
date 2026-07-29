# LiteLLM Cools Down a Failing Model on the First 429 — Unless It's Your Only One

If you run more than one LLM behind [LiteLLM](https://docs.litellm.ai/docs/routing)'s Router, you have probably repeated the same sentence in a design review: "it retries a few times, and after three failures it takes the bad model out of rotation for a while." That sentence is wrong in two ways that matter in production. In the current Router (litellm `1.94.0`), a single `429` pulls a deployment out of rotation immediately — and if that deployment is the only one in its model group, the Router will never cool it down at all and keeps sending traffic straight into the failure.

I installed the package, read the cooldown code, and ran it against mock deployments that do nothing but raise a rate-limit error. Here is exactly when LiteLLM cools a model down, when it refuses to, and what your caller actually receives when every deployment is cold.

## The knob everyone quotes

The number in everyone's head is three. It comes from a real constant. Open the installed package and it is right there in `litellm/constants.py`:

```python
DEFAULT_ALLOWED_FAILS = 3
DEFAULT_COOLDOWN_TIME_SECONDS = 5
```

So the folklore has a source. The problem is that `allowed_fails` is a legacy path. Inspecting `Router.__init__` shows `allowed_fails`, `cooldown_time`, and `num_retries` all default to `None`, not to those constants. The three-strikes counter only governs cooldowns when you *explicitly* set `allowed_fails` (or an `allowed_fails_policy`). Leave it at its default — as almost every deployment does — and the Router runs a different decision entirely.

That decision lives in [`router_utils/cooldown_handlers.py`](https://github.com/BerriAI/litellm/blob/main/litellm/router_utils/cooldown_handlers.py), in a function called `_should_cooldown_deployment`. The relevant branch is short:

```python
exception_status_int = cast_exception_status_to_int(exception_status)
if exception_status_int == 429 and not is_single_deployment_model_group:
    return True
```

One `429`, and the deployment is cooled. No counter, no minute-long window, no third strike.

## What actually earns a cooldown

Before that branch runs, a separate gate — `_is_cooldown_required` — decides whether the exception is even a cooldown candidate. Reading it changes how you think about failures, because not every error counts:

- `429` (rate limit), `401` (auth), `408` (timeout), and `404` (not found) trigger a cooldown.
- Every other `4xx` — a malformed request, a content-policy `400` — does **not** cool the deployment down.
- All `5xx` and other non-4xx errors do.
- `APIConnectionError` is explicitly ignored. The function keeps a small `ignored_strings = ["APIConnectionError"]` list and returns `False` on a match.

That last one surprised me, so I want to underline it. If your upstream endpoint is unreachable — wrong host, DNS failure, connection refused — LiteLLM treats it as *not worth cooling down* and will happily route the next request to the same dead address. Cooldowns are tuned for "this provider is throttling or rejecting me," not "this provider is gone." My first instinct for a reproducible test was to point a deployment at a closed localhost port; the code told me that would never cool anything, so I switched to a mock `429` instead. When the package contradicts your plan, believe the package.

## The single-deployment trap

Look again at the cooldown condition: `429 and not is_single_deployment_model_group`. LiteLLM computes `is_single_deployment_model_group` by counting the deployments that share a `model_name`. If a model group has exactly one deployment, that flag is `True`, and the whole `429` branch is skipped. An inline comment on that same `is_single_deployment_model_group` guard in the source says the quiet part out loud: *"by default we should avoid cooldowns on single deployment model groups."*

The reasoning is defensible. Cooling down your only deployment would leave you with nothing to route to, so the Router keeps trying rather than fail closed. But the consequence catches people off guard. If your config lists `gpt-4o` once, no amount of throttling will ever park it. Every request marches into the same rate limit, and the cooldown machinery you configured for exactly this situation stays dormant. Cooldowns are a load-balancing feature first and a circuit breaker second — and load balancing needs at least two things to balance.

## What your caller sees when everything is cold

Give the Router two deployments and fail both, and eventually every member of the group is in cooldown. At that point the Router has nowhere to send the request, and it raises `RouterRateLimitError`. Two details about that error matter operationally.

First, the cooldown window is right in the message. The class is defined in `litellm/types/router.py` and builds a string like `No deployments available for selected model, Try again in 5 seconds`. Five seconds, because that is `DEFAULT_COOLDOWN_TIME_SECONDS`.

Second — and this is the sharp edge — `RouterRateLimitError` subclasses `ValueError`, not an HTTP error. It has a `cooldown_time` attribute, but it does not carry a `Retry-After` header. That is not a nitpick; it is [open issue #27823](https://github.com/BerriAI/litellm/issues/27823), filed on May 13, 2026, asking LiteLLM to promote `cooldown_time` into a real `retry-after` header so downstream clients can back off without string-parsing an error message. Today, a client that wants to honor the cooldown has to read the number out of the exception text.

There is a matching blind spot on the operator side. [Issue #25504](https://github.com/BerriAI/litellm/issues/25504), opened April 10, 2026, asked for an API endpoint to expose which deployments are currently cooled down and why. It was closed as not planned and went stale. So the cooldown state that decides whether your requests get served lives in a cache with no first-class way to observe it. You can reach it in code — I do below — but there is no supported `/router/cooldowns` view.

## Try It Yourself

No API keys, no network. Every deployment uses LiteLLM's built-in `mock_response: "litellm.RateLimitError"`, which raises a real `429` through the same code path a live provider would. Install and set up:

```bash
pip install litellm            # tested on litellm 1.94.0
python cooldown_probe.py
```

The probe builds a two-deployment group where both deployments always return `429`, reads the active cooldown list after each call, then repeats the setup with a single-deployment group:

```python
def two_deployment_router():
    return Router(
        model_list=[
            {"model_name": "chat",
             "litellm_params": {"model": "openai/gpt-a",
                                "mock_response": "litellm.RateLimitError"},
             "model_info": {"id": "deploy-a"}},
            {"model_name": "chat",
             "litellm_params": {"model": "openai/gpt-b",
                                "mock_response": "litellm.RateLimitError"},
             "model_info": {"id": "deploy-b"}},
        ],
        num_retries=0,   # one attempt per call, so we can count cleanly
    )

async def active_cooldowns(router, ids):
    return router.cooldown_cache.get_active_cooldowns(
        model_ids=ids, parent_otel_span=None)
```

The full script (three experiments) is in the [code walkthrough repo](https://github.com/krpraveen0/linkedin-agent). Running it prints exactly this:

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

Read that output against the claims. Experiment 1: the first `429` cools one deployment; the second cools the other. No third strike. Experiment 2: with `num_retries=0`, the caller sees the raw `429` on the first two calls (cooldown does not shield the caller from a failure it just observed), and only once both deployments are cold does the Router substitute its own `RouterRateLimitError` — a `ValueError` with `cooldown_time=5` and no HTTP status. Experiment 3: three `429`s against a lone deployment leave the cooldown list empty. It is still serving, still failing.

One honest caveat about reproducibility: which deployment gets picked first in Experiment 1 depends on the Router's routing strategy, so the specific id in `after call 1` can be `deploy-a` or `deploy-b` between runs. The counts — one cold after one call, both cold after two — are stable.

## Key Takeaways

- In litellm `1.94.0`, the default cooldown path does not count to three. A single `429` cools a deployment for `5` seconds, as long as its model group has more than one deployment. The `allowed_fails = 3` constant only applies if you opt into it.
- Not all failures cool a deployment. `429`, `401`, `408`, `404`, and `5xx` do; other `4xx` do not; and `APIConnectionError` is explicitly ignored, so an unreachable endpoint keeps receiving traffic.
- A model group with exactly one deployment is never cooled down by default. If you rely on cooldowns as a circuit breaker, give every model group at least two deployments.
- When every deployment is cold, callers get `RouterRateLimitError` — a `ValueError` with the retry window buried in the message text and no `Retry-After` header. Parse `cooldown_time`, and do not expect a supported endpoint to observe which models are cold.

## Sources

- LiteLLM source inspected directly at version `1.94.0` (`litellm/constants.py`, [`router_utils/cooldown_handlers.py`](https://github.com/BerriAI/litellm/blob/main/litellm/router_utils/cooldown_handlers.py), `litellm/types/router.py`), 2026-07-29.
- [LiteLLM Routing & Load Balancing docs](https://docs.litellm.ai/docs/routing).
- [Issue #25504 — expose router cooldown state via API endpoint](https://github.com/BerriAI/litellm/issues/25504) (opened April 10, 2026).
- [Issue #27823 — no Retry-After header on RouterRateLimitError](https://github.com/BerriAI/litellm/issues/27823) (opened May 13, 2026).
