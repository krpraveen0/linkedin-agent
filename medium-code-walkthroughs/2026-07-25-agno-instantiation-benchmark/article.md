# Agno Says It Builds Agents 529× Faster Than LangGraph. I Measured What That Actually Buys You.

Open the [Agno performance page](https://docs.agno.com/performance) and the first thing you see is a number designed to end the argument: an Agno agent instantiates in about **3 microseconds**, which the docs report as **529× faster than LangGraph** and using 24× less memory. Agno shipped [version 2.8.2 to PyPI on July 24, 2026](https://pypi.org/project/agno/), and that benchmark is still the headline of the pitch.

A 529× speed difference is the kind of claim that makes you switch frameworks. So I installed the current releases of Agno, LangGraph, and Pydantic AI on one Linux box and ran the comparison myself. The gap is real and it is enormous. It is also measuring something much narrower than "which framework is faster," and once you see what's actually on the clock, the number stops being a reason to choose anything.

## What the benchmark actually times

Agno's methodology is public and simple: build the same one-tool agent 1,000 times, and use Python's `tracemalloc` to isolate the per-instance memory delta against an empty-function baseline. Nothing in it calls a language model. It is a pure measurement of **how expensive it is to construct the agent object in Python**, before a single token is generated.

That matters because the three frameworks do very different amounts of work in their constructor:

- **Agno** builds a lightweight agent object and defers almost everything else until you actually run it.
- **LangGraph** compiles a `StateGraph` — it wires nodes and edges into an executable graph every time you call `create_react_agent`. (LangGraph 1.2 even prints a deprecation warning here: `create_react_agent` has moved to `langchain.agents.create_agent`, a reminder that this "agent" is really a pre-built graph.)
- **Pydantic AI** eagerly constructs the model provider and its HTTP client inside `Agent(...)`.

Same word, "instantiate," three very different bills. Keep that in mind, because it's the whole story.

## My numbers

I ran 1,000 constructions per framework, took the best of five timed batches to suppress garbage-collection noise, and measured memory the way Agno does. Here is the real output:

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

My hardware isn't Agno's, so my absolute microseconds differ from their docs, but the direction is identical: Agno constructs its agent hundreds of times faster than LangGraph. I got **305×** on time where the docs report 529×; the exact multiplier is softer than a single hero number suggests. It moves with your CPU, your framework versions, and precisely what you count, but "hundreds of times faster to construct" holds up.

The memory ratio is where the reproduction diverges most. Agno's docs claim LangGraph uses 161 KiB per agent against Agno's 6.6 KiB (24×). I measured 30 KiB versus 5.3 KiB — a real gap, but 5.8×, not 24×. Memory deltas from `tracemalloc` are sensitive to how you group and count allocations, so treat the *ratio* as directional and distrust any exact "24×."

## The Pydantic AI number is a trap worth understanding

Look again at Pydantic AI: **49 milliseconds** to instantiate one agent. That's not 57× slower than Agno, as Agno's docs report — on my box it's over 5,000× slower. A number that far outside everyone else's range is a signal to stop and profile, not to publish. So I ran `cProfile` over 50 constructions and sorted by cumulative time:

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

Read the chain top to bottom: the Pydantic AI `Agent.__init__` calls `infer_model` → `infer_provider` → the OpenAI provider's constructor (`openai.py:53`) → `create_async_http_client`, which builds an `httpx` client, builds an SSL context, and calls `load_verify_locations`. That last line — OpenSSL reading the system CA certificate bundle off disk — accounts for **2.159 of the 2.482 seconds**. Passing `Agent("openai:gpt-4o")` a model *string* makes Pydantic AI eagerly construct an OpenAI provider and its TLS trust store. Every single time.

That is a legitimate design difference (Pydantic AI front-loads the network client; Agno defers it), but the benchmark is now measuring **OpenSSL reading a file**, not agent-framework overhead. It says nothing about how fast either framework runs an agent. It's the clearest possible illustration that "instantiation time" is not a proxy for "framework speed."

## Put the winning number in context

Here's the arithmetic that the 529× headline leaves out. A single real LLM call takes somewhere between a few hundred milliseconds and a few seconds. Against an 800 ms call:

- LangGraph's 2.79 ms construction is **0.35%** of one request.
- Agno's 0.009 ms construction is **0.001%** of one request.

You build an agent object once and then make many model calls through it. The construction cost is paid at import/startup, amortized to nothing across a process's lifetime, and dwarfed by the first network round-trip. Winning the instantiation race by 305× turns a rounding error into a smaller rounding error. It does not make your agent answer faster, cost less per token, or hallucinate less.

None of this means Agno is slow or the benchmark is dishonest. Agno genuinely is a lean, fast-to-construct framework, and if you spin up thousands of short-lived agents per second (think per-request fan-out at scale) that construction cost can actually start to matter. The point is narrower: **a microbenchmark of object construction is the wrong number to pick a framework on**, and the one framework that looks catastrophically slow here is really just loading a certificate file.

## Try It Yourself

Install the three frameworks and run the benchmark. No API keys are used — nothing here makes a network call; we only construct the objects.

```bash
python -m venv venv && source venv/bin/activate
pip install agno langgraph langchain-openai pydantic-ai-slim openai
```

The core of the measurement — identical one-tool agent, 1,000 constructions each, best-of-five timing, `tracemalloc` memory delta:

```python
import gc, time, tracemalloc, os
os.environ["OPENAI_API_KEY"] = "sk-not-used-no-network-calls-happen"

def time_us(factory, runs=1000):
    factory(); gc.collect(); best = None
    for _ in range(5):
        gc.disable(); t0 = time.perf_counter()
        for _ in range(runs): factory()
        best = min(best or 9e9, (time.perf_counter()-t0)/runs*1e6); gc.enable()
    return best

def mem_kib(factory, runs=1000):
    gc.collect(); tracemalloc.start()
    base = tracemalloc.take_snapshot()
    keep = [factory() for _ in range(runs)]
    diff = tracemalloc.take_snapshot().compare_to(base, "filename")
    tracemalloc.stop(); keep.clear()
    return sum(s.size_diff for s in diff)/runs/1024
```

Each `factory` is just the framework's own constructor — for Agno, `Agent(model=OpenAIChat(id="gpt-4o"), tools=[weather])`; for LangGraph, `create_react_agent(ChatOpenAI(model="gpt-4o"), tools=[weather])`; for Pydantic AI, `Agent("openai:gpt-4o")` plus one `tool_plain`. Run it and you'll see the same shape I did: Agno in single-digit microseconds, LangGraph in milliseconds, and Pydantic AI paying a one-time SSL-context tax on every build. If you want to confirm the last one, wrap the Pydantic AI constructor in `cProfile`: sorted by cumulative time the call chain runs through the OpenAI provider into the HTTP client, and `load_verify_locations` carries the largest self-time of anything in the run.

## Key Takeaways

- Agno's "**529× faster than LangGraph**" is a real, reproducible construction-time gap; I measured 305× on different hardware. The exact multiplier is fragile; treat it as "hundreds of times," not a precise constant.
- The benchmark times **Python object construction only**, with no LLM calls. LangGraph compiles a graph in its constructor; Pydantic AI eagerly builds an HTTP client and loads your CA bundle. "Instantiate" means something different in each.
- Pydantic AI's apparent slowness is almost entirely `ssl.load_verify_locations`, not agent logic. Always profile an outlier before you trust it.
- Construction cost is amortized to near-zero in any real workload: LangGraph's 2.79 ms is ~0.35% of one 800 ms model call. Pick a framework on ergonomics, reliability, and features, not on this number.
- Memory ratios from `tracemalloc` are directional; the "24×" claim came out as 5.8× for me. Reproduce before you quote.

**Sources:** [Agno performance benchmarks (docs.agno.com/performance)](https://docs.agno.com/performance); [Agno 2.8.2 on PyPI, released 2026-07-24](https://pypi.org/project/agno/); [Agno on GitHub](https://github.com/agno-agi/agno); plus direct measurements and `cProfile` output captured on Agno 2.8.2, LangGraph 1.2.9, and Pydantic AI 2.17.0 (Python 3.11.15), reproduced from the code above.
