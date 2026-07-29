"""
Probe LiteLLM Router cooldown behavior empirically.
litellm 1.94.0. No network / no API keys: every deployment raises a mock 429.
"""
import asyncio
import logging
from importlib.metadata import version

logging.getLogger("LiteLLM").setLevel(logging.ERROR)  # mute cost-map warnings

from litellm import Router
from litellm.exceptions import RateLimitError
from litellm.types.router import RouterRateLimitError

print("litellm", version("litellm"))


def two_deployment_router():
    # One model group "chat" with TWO deployments; both always raise a 429.
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
    return router.cooldown_cache.get_active_cooldowns(model_ids=ids, parent_otel_span=None)


async def exp1_first_429_cools_a_deployment():
    print("\n=== EXP 1: multi-deployment group, one 429 per call ===")
    r = two_deployment_router()
    ids = [d["model_info"]["id"] for d in r.model_list]
    for i in range(1, 3):
        try:
            await r.acompletion(model="chat", messages=[{"role": "user", "content": "hi"}])
        except RateLimitError:
            pass
        cd = await active_cooldowns(r, ids)
        print(f"after call {i}: cooled down -> {[c[0] for c in cd]}")


async def exp2_all_cold_raises_router_error():
    print("\n=== EXP 2: keep calling until every deployment is cold ===")
    r = two_deployment_router()
    for i in range(1, 6):
        try:
            await r.acompletion(model="chat", messages=[{"role": "user", "content": "hi"}])
            print(f"call {i}: succeeded (unexpected)")
        except RouterRateLimitError as e:
            print(f"call {i}: RouterRateLimitError -> cooldown_time={e.cooldown_time}s")
            print(f"          type is HTTP error? {hasattr(e, 'status_code')} | isinstance ValueError: {isinstance(e, ValueError)}")
            break
        except RateLimitError:
            print(f"call {i}: RateLimitError (429 from a live deployment)")


async def exp3_single_deployment_never_cools():
    print("\n=== EXP 3: single-deployment group, same 429 ===")
    r = Router(
        model_list=[
            {"model_name": "solo",
             "litellm_params": {"model": "openai/gpt-a",
                                "mock_response": "litellm.RateLimitError"},
             "model_info": {"id": "only-one"}},
        ],
        num_retries=0,
    )
    for i in range(1, 4):
        try:
            await r.acompletion(model="solo", messages=[{"role": "user", "content": "hi"}])
        except RateLimitError:
            pass
    cd = await active_cooldowns(r, ["only-one"])
    print(f"after 3 x 429: cooled down -> {[c[0] for c in cd] or 'NONE — still serving'}")


async def main():
    await exp1_first_429_cools_a_deployment()
    await exp2_all_cold_raises_router_error()
    await exp3_single_deployment_never_cools()


asyncio.run(main())
