# Agno vs LangGraph vs Pydantic AI — agent *instantiation* benchmark

Companion code for the Medium article "Agno Says It Builds Agents 529× Faster Than
LangGraph. I Measured What That Actually Buys You." (2026-07-25).

This reproduces [Agno's published instantiation benchmark](https://docs.agno.com/performance)
and then explains what the number does — and does not — measure. Every output block below is
copied verbatim from a real run; nothing was invented or cleaned up. No LLM calls are made —
the scripts only construct agent objects, so no API key or network access is required.

Measured against `agno==2.8.2` (released 2026-07-24), `langgraph==1.2.9`,
`pydantic-ai-slim==2.17.0`, `langchain-openai==1.4.1`, `openai==2.48.0` on Python 3.11.15.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install agno langgraph langchain-openai pydantic-ai-slim openai
```

## 1. The benchmark — `bench.py`

Builds the same one-tool agent 1,000× per framework, takes the best of five timed batches
(to suppress GC noise), and isolates per-instance memory with `tracemalloc` against an
empty-function baseline — the same methodology Agno documents.

```bash
python bench.py 2>/dev/null
```

Real output:

```
python 3.11.15  runs=1000

framework     version       instantiate (us)    memory (KiB)
------------------------------------------------------------
agno          2.8.2                     9.13            5.28
langgraph     1.2.9                  2792.25           30.46
pydantic-ai   2.17.0                49122.48           18.96

Ratios (higher = Agno is lighter/faster):
  vs langgraph    time:  305.7x   memory:    5.8x
  vs pydantic-ai  time: 5377.9x   memory:    3.6x
```

Absolute microseconds vary with hardware and load; the direction is stable: Agno constructs
its agent in single-digit microseconds, LangGraph in low-thousands (it compiles a `StateGraph`),
Pydantic AI in tens-of-thousands.

## 2. Why Pydantic AI's construction is so slow — `profile_pydantic.py`

An outlier that far outside the pack is a signal to profile, not publish. `Agent("openai:gpt-4o")`
eagerly builds the model provider and an `httpx` client, which loads the system CA bundle.

```bash
python profile_pydantic.py 2>/dev/null
```

Real output (cumulative-time profile, absolute paths stripped by `strip_dirs()`):

```
         584751 function calls (583151 primitive calls) in 2.482 seconds

   Ordered by: cumulative time
   List reduced from 488 to 12 due to restriction <12>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
       50    0.001    0.000    2.483    0.050 profile_pydantic.py:19(make)
       50    0.024    0.000    2.402    0.048 __init__.py:339(__init__)
       50    0.000    0.000    2.365    0.047 __init__.py:1280(infer_model)
       50    0.000    0.000    2.364    0.047 __init__.py:258(infer_provider)
       50    0.000    0.000    2.363    0.047 openai.py:53(__init__)
       50    0.000    0.000    2.353    0.047 __init__.py:1372(create_async_http_client)
       50    0.001    0.000    2.353    0.047 _client.py:1353(__init__)
      100    0.001    0.000    2.190    0.022 default.py:280(__init__)
      100    0.001    0.000    2.187    0.022 _config.py:23(create_ssl_context)
      100    0.001    0.000    2.186    0.022 ssl.py:745(create_default_context)
      100    2.159    0.022    2.159    0.022 {method 'load_verify_locations' of '_ssl._SSLContext' objects}
       50    0.002    0.000    1.169    0.023 _client.py:1412(<dictcomp>)
```

Almost the entire cost — 2.159 of 2.482 s — is `load_verify_locations`, OpenSSL reading the trust store off disk.
That's a design difference (eager vs lazy client construction), not agent-framework overhead.

## Takeaway

The 529× / 305× gap is a real object-construction difference, but it's amortized to near-zero in
any real workload (LangGraph's ~2.8 ms is ~0.35% of one 800 ms model call), and the framework that
looks catastrophic here is really just loading a certificate file. Pick a framework on ergonomics
and reliability — not on this microbenchmark.
