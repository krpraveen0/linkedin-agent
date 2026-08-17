# I Added Examples to My semantic-router Route. It Sent My Refund Question to Shipping.

I had a `refunds` route working. The query "how do i get a refund for my order" matched it every time, with a confidence around 0.82. Then I did the thing every tutorial tells you to do: I added more example phrases to make the route more robust. Three more refund-adjacent utterances: cancel a subscription, dispute a charge, close an account.

The exact same query stopped matching `refunds`. It went to `shipping` instead. My perfect example phrase, "how do i get a refund," was still sitting right there in the route. I hadn't touched the query, the threshold, or the encoder. I had only added good examples, and that alone rerouted a refund question to the wrong handler.

The cause is one default in [semantic-router](https://github.com/aurelio-labs/semantic-router) that its README example never sets, and it changes how every route in your app scores.

## What semantic-router is actually doing

semantic-router is, in its own words, "a superfast decision-making layer for your LLMs and agents" that routes requests using [semantic vector space](https://github.com/aurelio-labs/semantic-router/blob/main/README.md) instead of an LLM call. You define routes, each with a handful of example utterances:

```python
from semantic_router import Route
politics = Route(name="politics", utterances=["isn't politics the best thing ever", "why don't you tell me about your political opinions"])
chitchat = Route(name="chitchat", utterances=["how's the weather today?", "how are things going?"])
```

At build time it embeds every utterance. At query time it embeds your incoming text and finds the nearest utterance vectors by cosine similarity. So far this is ordinary nearest-neighbor search: each *utterance* gets a similarity score against the query.

But routes have more than one utterance. To pick a winning *route*, semantic-router has to collapse each route's set of utterance scores into a single number. That collapsing step is where the surprise lives.

## The default nobody sets: `mean`

Look at how the router groups and reduces scores. In the installed source of version 0.1.16, `group_scores_by_class` builds a list of every utterance score per route, and the constructor picks the function that reduces each list:

```python
# semantic_router/routers/base.py (v0.1.16)
def _set_aggregation_method(self, aggregation: str = "sum"):
    if aggregation == "sum":
        return lambda x: sum(x)
    elif aggregation == "mean":
        return lambda x: np.mean(x)
    elif aggregation == "max":
        return lambda x: max(x)
```

The three choices are `sum`, `mean`, and `max`. The constructor default, the one you get when you copy the README example and never pass `aggregation`, is `mean`:

```python
def __init__(self, ..., aggregation: str = "mean", ...):
```

`mean` is a trap for the most natural way people improve a route. A route's score is the *average* similarity across all its example utterances. Add an utterance that is genuinely on-topic but not close to *this particular query*, and it pulls the average down. The single perfect match that used to carry the route is now one term in a longer average. Your route gets less confident precisely because you gave it more knowledge.

`max` would have taken the single best-matching utterance and ignored the rest, which is what most people assume "does this route have a phrase like my query?" means. `sum` rewards routes with more matches. `mean` punishes breadth. And `mean` is the default.

That default interacts with one more thing: the threshold. A route only fires if its aggregated score clears a `score_threshold`; otherwise the router skips it and moves to the next best route. Here is the exact gate from the same file:

```python
# _pass_routes: a route is skipped when its aggregated score is below threshold
if current_threshold := (route.score_threshold if route.score_threshold is not None else self.score_threshold):
    passed = total_score >= current_threshold
else:
    passed = True
```

So dropping the mean is not just a smaller number. Cross the threshold on the way down and the route disappears from the running entirely, and a different route answers.

## Try It Yourself

This runs fully offline with no API key and no model download. semantic-router's default encoder calls OpenAI, and Hugging Face models need a download, so I plugged in a tiny deterministic hashing bag-of-words encoder instead. The point being demonstrated, how the router aggregates a route's utterance scores, is the library's own logic and is identical no matter which encoder produces the vectors. The encoder only decides the raw numbers; `mean` decides what happens to them.

```python
import hashlib, re
import numpy as np
from semantic_router import Route, SemanticRouter
from semantic_router.encoders.base import DenseEncoder

DIM = 512
class HashingBoWEncoder(DenseEncoder):
    def __init__(self, **kw): super().__init__(name="hashing-bow", **kw)
    def _embed_one(self, text):
        v = np.zeros(DIM)
        for tok in re.findall(r"[a-z]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        n = np.linalg.norm(v)
        return (v / n if n else v).tolist()
    def __call__(self, docs): return [self._embed_one(d) for d in docs]
    async def acall(self, docs): return self(docs)
```

Now the same query against a `refunds` route with a `0.4` threshold, and a thresholdless `shipping` route as the fallthrough. First with one example, then with four:

```python
encoder = HashingBoWEncoder()
QUERY = "how do i get a refund for my order"
shipping = Route(name="shipping", utterances=["where is my order right now"])

# A: one tight example
refunds_1 = Route(name="refunds", utterances=["how do i get a refund"], score_threshold=0.4)
# B: three more real-but-distant refund-ish examples added
refunds_4 = Route(name="refunds", score_threshold=0.4, utterances=[
    "how do i get a refund",
    "please cancel my subscription",
    "the charge on my card looks wrong",
    "i want to close my account",
])

for tag, r in [("A: 1 example", refunds_1), ("B: 4 examples", refunds_4)]:
    router = SemanticRouter(encoder=encoder, routes=[r, shipping], auto_sync="local")
    print(tag, "->", router(QUERY).name)
```

The real output (warning lines from the local index trimmed):

```
=== Scenario A: 1 example on 'refunds' ===
  shipping  mean=0.272  scores=[0.272]
  refunds   mean=0.816  scores=[0.816]  clears 0.4
  ROUTER PICKS: ('refunds', np.float64(0.816496580927726))

=== Scenario B: 4 examples on 'refunds' (same query, same threshold) ===
  refunds   mean=0.345  scores=[0.126, 0.167, 0.272, 0.816]  BELOW 0.4 -> skipped
  shipping  mean=0.272  scores=[0.272]
  ROUTER PICKS: ('shipping', np.float64(0.2721655269759087))
```

Read the `refunds` line in scenario B. The best utterance still scores **0.816**, identical to scenario A. "how do i get a refund" is still the closest phrase to the query. But the mean of `[0.126, 0.167, 0.272, 0.816]` is **0.345**, which is below the 0.4 threshold, so the router drops `refunds` and hands the refund question to `shipping`. Adding three correct examples silently misrouted the query.

Switching one argument fixes it. `aggregation="max"` reduces each route to its single best utterance:

```python
router = SemanticRouter(encoder=encoder, routes=[refunds_4, shipping],
                        aggregation="max", auto_sync="local")
print(router(QUERY).name)
```

```
=== Scenario C: same 4 examples, aggregation='max' ===
  refunds    max=0.816  scores=[0.126, 0.167, 0.272, 0.816]  clears 0.4
  shipping   max=0.272  scores=[0.272]
  ROUTER PICKS: ('refunds', 0.816496580927726)
```

Same four utterances, same query, same threshold. With `max`, the 0.816 match carries the route and `refunds` wins again.

## So which aggregation should you use?

None of the three is "correct" for every case, which is exactly why leaving it on an unexamined default is risky.

- **`max`** answers "does this route contain a phrase close to the query?" It is immune to dilution and usually what people expect. Its weakness is the mirror image: one accidentally over-broad utterance can make a route match things it shouldn't, because only the single best score counts.
- **`sum`** rewards routes that match on *several* utterances, which can help when a query legitimately overlaps a whole cluster. But it scales with how many utterances a route has, so routes with long example lists win by sheer volume, and any fixed threshold becomes meaningless across routes of different sizes.
- **`mean`** is stable against route size, which is a real virtue. Its cost is the one above: representative-but-distant examples drag the score down, and thresholds you tuned with a few examples silently stop holding as the route grows.

If you use `mean`, your example utterances need to be *tight*: every phrase should be close to the kinds of queries you want to match, not merely in the same topic. And re-check thresholds whenever you edit a route's utterance list, because the number that gates it just moved.

One more reason to pin down your scoring now: semantic-router is actively changing this machinery. Version [0.1.16, released July 26, 2026](https://github.com/aurelio-labs/semantic-router/releases/tag/v0.1.16), fixed a bug where the internal `top_scores` results were not returned sorted by score, and [v0.1.15](https://github.com/aurelio-labs/semantic-router/releases/tag/v0.1.15) addressed CVE-2026-42208 with an explicit recommendation to upgrade. The scoring path is not frozen, so verify the behavior against the version you actually install. That is what I did here, reading the aggregation code straight out of the installed 0.1.16 package rather than the docs.

## Key Takeaways

- semantic-router reduces each route's per-utterance similarity scores to one number, and the constructor default is `aggregation="mean"`, verified in the installed v0.1.16 source, not stated in the README's quickstart.
- With `mean`, adding on-topic-but-distant example utterances *lowers* a route's score. A route's single best match no longer determines whether it wins.
- Combined with a `score_threshold`, a diluted mean can drop a route below its gate, and the router silently falls through to a different route, as shown, sending a refund query to `shipping`.
- `aggregation="max"` scores a route by its closest utterance and is immune to this dilution; `sum` rewards match count but scales with route size. Pick deliberately.
- Re-tune thresholds whenever you change a route's utterances, and pin the semantic-router version, because the scoring code is still being changed release to release.

**Sources:** [semantic-router GitHub repo & README](https://github.com/aurelio-labs/semantic-router) · [v0.1.16 release notes (July 26, 2026)](https://github.com/aurelio-labs/semantic-router/releases/tag/v0.1.16) · [releases list](https://github.com/aurelio-labs/semantic-router/releases) · aggregation and threshold behavior verified directly against the installed `semantic-router==0.1.16` source (`semantic_router/routers/base.py`).
