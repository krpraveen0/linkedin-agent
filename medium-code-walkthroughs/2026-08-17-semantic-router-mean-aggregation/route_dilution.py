"""
Demonstrates semantic-router's default "mean" score aggregation, and how
adding more example utterances to a route can LOWER its aggregated score and
flip the winning route.

Runs fully offline: a tiny deterministic hashing bag-of-words encoder is
plugged into the real semantic-router. The aggregation logic being shown is
the library's own and is identical regardless of which encoder you use.
"""
import hashlib
import re
from typing import Any, List

import numpy as np
from semantic_router import Route, SemanticRouter
from semantic_router.encoders.base import DenseEncoder

DIM = 512


class HashingBoWEncoder(DenseEncoder):
    """Deterministic offline encoder: L2-normalized hashed bag-of-words."""

    def __init__(self, **kwargs):
        super().__init__(name="hashing-bow", **kwargs)

    def _embed_one(self, text: str) -> List[float]:
        vec = np.zeros(DIM, dtype=np.float64)
        for tok in re.findall(r"[a-z]+", text.lower()):
            bucket = int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM
            vec[bucket] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def __call__(self, docs: List[Any]) -> List[List[float]]:
        return [self._embed_one(d) for d in docs]

    async def acall(self, docs: List[Any]) -> List[List[float]]:
        return self(docs)


encoder = HashingBoWEncoder()
QUERY = "how do i get a refund for my order"


def winner(router: SemanticRouter, query: str):
    choice = router(query)
    return choice.name, choice.similarity_score


def aggregated_scores(router: SemanticRouter, query: str):
    """Reproduce the per-route scores using the router's OWN methods."""
    qv = encoder([query])[0]
    raw = router.index.query(np.array(qv), top_k=50)  # (scores, route_names)
    query_results = [{"route": r, "score": float(s)} for s, r in zip(raw[0], raw[1])]
    by_class = router.group_scores_by_class(query_results)
    return {
        route: (float(router.aggregation_method(scores)), [round(s, 3) for s in scores])
        for route, scores in by_class.items()
    }


THRESHOLD = 0.4  # a 'refunds' route only fires when its aggregated score clears this
print("aggregation default:", SemanticRouter.__init__.__defaults__)

# 'shipping' has no threshold, so it always passes and acts as the fallthrough.
shipping = Route(name="shipping", utterances=["where is my order right now"])


def report(tag, refunds_route, aggregation="mean"):
    router = SemanticRouter(
        encoder=encoder,
        routes=[refunds_route, shipping],
        aggregation=aggregation,
        auto_sync="local",
    )
    print(f"\n=== {tag} ===")
    scored = aggregated_scores(router, QUERY)
    for route, (agg, scores) in scored.items():
        clears = "clears 0.4" if route == "refunds" and agg >= THRESHOLD else ""
        if route == "refunds" and agg < THRESHOLD:
            clears = "BELOW 0.4 -> skipped"
        print(f"  {route:9s} {aggregation:>4s}={agg:.3f}  scores={scores}  {clears}")
    print("  ROUTER PICKS:", winner(router, QUERY))


# --- Scenario A: one tight example on 'refunds' ----------------------------
report(
    "Scenario A: 1 example on 'refunds'",
    Route(name="refunds", utterances=["how do i get a refund"], score_threshold=THRESHOLD),
)

# --- Scenario B: add 3 more real-but-distant refund-ish examples -----------
report(
    "Scenario B: 4 examples on 'refunds' (same query, same threshold)",
    Route(
        name="refunds",
        utterances=[
            "how do i get a refund",
            "please cancel my subscription",
            "the charge on my card looks wrong",
            "i want to close my account",
        ],
        score_threshold=THRESHOLD,
    ),
)

# --- Scenario C: same data as B, but aggregation='max' ---------------------
report(
    "Scenario C: same 4 examples, aggregation='max'",
    Route(
        name="refunds",
        utterances=[
            "how do i get a refund",
            "please cancel my subscription",
            "the charge on my card looks wrong",
            "i want to close my account",
        ],
        score_threshold=THRESHOLD,
    ),
    aggregation="max",
)
