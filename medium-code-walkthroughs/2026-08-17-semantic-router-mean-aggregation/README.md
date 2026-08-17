# semantic-router: `mean` aggregation dilutes a route as you add examples

Code for the 2026-08-17 Medium article *"I Added Examples to My semantic-router Route. It Sent My Refund Question to Shipping."*

`SemanticRouter` collapses each route's per-utterance similarity scores into one
number before comparing routes. The constructor default is `aggregation="mean"`
(verified in the installed `semantic-router==0.1.16` source, `semantic_router/routers/base.py`).
With `mean`, adding on-topic-but-distant example utterances *lowers* a route's
score. Combined with a `score_threshold`, the diluted mean can drop the route
below its gate, and the router silently falls through to a different route.

`route_dilution.py` demonstrates this end-to-end against the real library. It
runs fully offline: the default encoder calls OpenAI and Hugging Face models
require a download, so a tiny deterministic hashing bag-of-words encoder is
plugged in instead. The aggregation logic being shown is the library's own and
is identical regardless of encoder.

## Setup

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt   # semantic-router==0.1.16, numpy
```

## Run

```bash
python3 route_dilution.py 2>&1 | grep -v "WARNING semantic_router"
```

## Real captured output

```
aggregation default: (None, None, None, None, 5, 'mean', None, False)

=== Scenario A: 1 example on 'refunds' ===
  shipping  mean=0.272  scores=[0.272]
  refunds   mean=0.816  scores=[0.816]  clears 0.4
  ROUTER PICKS: ('refunds', np.float64(0.816496580927726))

=== Scenario B: 4 examples on 'refunds' (same query, same threshold) ===
  refunds   mean=0.345  scores=[0.126, 0.167, 0.272, 0.816]  BELOW 0.4 -> skipped
  shipping  mean=0.272  scores=[0.272]
  ROUTER PICKS: ('shipping', np.float64(0.2721655269759087))

=== Scenario C: same 4 examples, aggregation='max' ===
  refunds    max=0.816  scores=[0.126, 0.167, 0.272, 0.816]  clears 0.4
  shipping   max=0.272  scores=[0.272]
  ROUTER PICKS: ('refunds', 0.816496580927726)
```

Without the `grep` filter you will also see two `WARNING semantic_router No
index provided. Using default LocalIndex.` lines per router build; they are
harmless (the demo uses the in-memory `LocalIndex`).

## What to read in the output

- **Scenario A:** one tight example. `refunds` scores 0.816, clears its 0.4
  threshold, wins.
- **Scenario B:** three more real-but-distant refund-ish examples added. The
  best utterance still scores **0.816**, but the `mean` of all four is
  **0.345**, below 0.4. `refunds` is skipped and the refund query is answered
  by `shipping`.
- **Scenario C:** same four utterances, `aggregation="max"`. The route is scored
  by its single best utterance (0.816), clears the threshold, and `refunds`
  wins again.

## Files

- `route_dilution.py` — the runnable demonstration.
- `requirements.txt` — pinned dependencies.
- `article.md` — the full article.
- `fig1-pipeline.svg`, `fig2-flip.svg` — diagrams.

Verified on Python 3.11, `semantic-router==0.1.16`.
