# I Told Chroma to Use Cosine. `get_or_create_collection` Kept My Old L2 Index and Never Said a Word.

My retrieval quality dropped the day I "improved" it. I had a [Chroma](https://www.trychroma.com/) collection full of text embeddings, decided cosine distance was the right metric for them, added `configuration={"hnsw": {"space": "cosine"}}` to my `get_or_create_collection` call, redeployed, and watched the top results get slightly worse. No error. No warning. The collection was still running squared L2, because it already existed and Chroma quietly kept the index it had.

This is not a bug report. Every behavior below is documented and reproducible on the current release. It is a set of defaults and rules that bite in a specific order, and the order is what makes them expensive: by the time you notice, the index is already built the wrong way and you cannot change it in place.

## Why this is worth your attention now

Chroma shipped its Rust-rewritten 1.0 core in [April 2025](https://github.com/chroma-core/chroma/releases) and has moved fast since: `1.5.0` landed on February 9, 2026 and `1.5.9`, the version used for every result in this article, on May 5, 2026 (dates from [PyPI](https://pypi.org/project/chromadb/)). The 1.x line also standardized on a typed `configuration` argument for index settings, replacing the older habit of stuffing `hnsw:space` into `metadata`. That is a good change. But two things did not change with it: the default distance is still squared L2, and the distance is still fixed for the life of the collection. If you are standing up a new RAG store on Chroma in 2026, those two facts decide whether your retrieval is correct on day one.

## The default is squared L2, and for text that flips your rankings

Chroma's [collection configuration docs](https://docs.trychroma.com/docs/collections/configure) are explicit: the `space` parameter "defines the distance function of the embedding space," and "the default is `l2` which is the squared L2 norm." The three options carry these formulas:

- `l2` (default): `d = Σ(Aᵢ - Bᵢ)²`
- `ip`: `d = 1.0 - Σ(Aᵢ × Bᵢ)`
- `cosine`: `d = 1.0 - (Σ Aᵢ·Bᵢ) / (√ΣAᵢ² · √ΣBᵢ²)`

Squared L2 measures raw coordinate distance. Cosine measures the angle between vectors and ignores their magnitude. That difference matters for text because embedding magnitude often tracks things you do not care about, like chunk length, rather than topic. A long, on-topic passage can land far from your query in raw L2 terms while pointing in almost exactly the same direction.

Here is that exact situation with hand-set vectors so the arithmetic is checkable. The query sits at `[1, 0]`. Document A points the same direction but is "longer" (larger magnitude) at `[5, 0]`. Document B sits numerically near the query but points elsewhere, at `[1, 1]`.

```python
import chromadb

client = chromadb.Client()
QUERY = [1.0, 0.0]
DOCS = {"A_on_topic_long": [5.0, 0.0], "B_off_topic_short": [1.0, 1.0]}

col = client.create_collection("default_store")   # no space specified
col.add(ids=list(DOCS), embeddings=list(DOCS.values()))

print("space  :", col.configuration_json["hnsw"]["space"])
r = col.query(query_embeddings=[QUERY], n_results=2)
print("ranking:", list(zip(r["ids"][0], [round(d, 4) for d in r["distances"][0]])))
```

Real output:

```
space  : l2
ranking: [('B_off_topic_short', 1.0), ('A_on_topic_long', 16.0)]
```

The off-topic document wins. Under squared L2, B is at distance `(1-1)² + (1-0)² = 1`, while the same-direction document A is at `(5-1)² + 0² = 16`. Chroma ranked the semantically closer document last, and it did so silently, because you never told it which distance you wanted.

Switch the metric to cosine using the modern `configuration` argument and the order corrects itself:

```python
col = client.create_collection(
    "cosine_store", configuration={"hnsw": {"space": "cosine"}}
)
col.add(ids=list(DOCS), embeddings=list(DOCS.values()))

print("space  :", col.configuration_json["hnsw"]["space"])
r = col.query(query_embeddings=[QUERY], n_results=2)
print("ranking:", list(zip(r["ids"][0], [round(d, 4) for d in r["distances"][0]])))
```

Real output:

```
space  : cosine
ranking: [('A_on_topic_long', 0.0), ('B_off_topic_short', 0.2929)]
```

Now the same-direction document sits at cosine distance `0.0` and the off-topic one at `0.2929`. One detail to internalize: `0.0` is *closest*. Chroma's `query` returns distances, not similarities. For cosine, identical direction gives `0`, orthogonal gives `1`, and opposite gives `2`. If you sort these expecting a "score" that goes up with relevance, you have the ranking backwards.

## The trap: `get_or_create_collection` ignores your configuration if the collection exists

The default is only half the story. The reason my "fix" did nothing is that `get_or_create_collection` is a get-or-create, and on the "get" path it hands back the stored collection as-is. Whatever `configuration` you pass is discarded, and nothing tells you.

```python
again = client.get_or_create_collection(   # "default_store" already exists as l2
    "default_store", configuration={"hnsw": {"space": "cosine"}}
)
print("asked for   : cosine")
print("actually got:", again.configuration_json["hnsw"]["space"])
```

Real output:

```
asked for   : cosine
actually got: l2
```

No exception, no log line, no deprecation notice. This is the failure that reaches production, because `get_or_create_collection` is exactly the call you reach for in service code that must be safe to run repeatedly. It is idempotent, which is convenient, but it makes configuration changes invisible: the first process to create the collection wins the metric forever, and every later call that "sets" a different space is a no-op.

## And you cannot fix it in place

The obvious next move is to change the metric on the existing collection. Chroma will not let you.

```python
try:
    col.modify(configuration={"hnsw": {"space": "cosine"}})
    print("modify: succeeded")
except Exception as e:
    print("modify:", type(e).__name__)
    print(" ", str(e).splitlines()[0])
```

Real output:

```
modify: InvalidArgumentError
  unknown field `space`, expected one of `ef_search`, `max_neighbors`, `num_threads`, `resize_factor`, `sync_threshold`, `batch_size` at line 1 column 17
```

The error names precisely what `modify` will accept, and `space` is not on the list. You can tune search-time and construction knobs like `ef_search` and `max_neighbors`, but the distance function is baked into the HNSW index at creation. The docs say the same thing plainly: the space "cannot be changed after index creation," and the recommended path is to recreate the collection (the community [Chroma Cookbook](https://cookbook.chromadb.dev/core/configuration/) documents the same immutability). In practice that means deleting the collection and re-adding every embedding, which for a real corpus is a re-index, not a config edit.

Note the shape of the error, too. It is a Rust-side validation message referring to `line 1 column 17`, an artifact of how the 1.x core parses configuration. It tells you the field is rejected, not the higher-level reason (the distance function is immutable). Worth knowing before you spend time assuming your JSON was malformed.

## Try It Yourself

One file reproduces all four behaviors. It uses fixed vectors, so it needs no model, no API key, and no network.

```bash
python -m venv env && . env/bin/activate
pip install chromadb        # tested on chromadb 1.5.9, Python 3.11
python demo.py
```

The script (`demo.py`) creates a default collection, a cosine collection, calls `get_or_create_collection` with a mismatched config, and tries to `modify` the space. Full captured output from a clean run:

```
space         : l2
ranking       : [('B_off_topic_short', 1.0), ('A_on_topic_long', 16.0)]

space         : cosine
ranking       : [('A_on_topic_long', 0.0), ('B_off_topic_short', 0.2929)]

asked for     : cosine
actually got  : l2
ranking       : [('B_off_topic_short', 1.0), ('A_on_topic_long', 16.0)]

modify        : InvalidArgumentError
                unknown field `space`, expected one of `ef_search`, `max_neighbors`, `num_threads`, `resize_fact
```

Two small things you may hit while experimenting. Collection names must be 3 to 512 characters of `[a-zA-Z0-9._-]`, so a throwaway name like `"kb"` raises a validation error before anything interesting happens. And `chromadb.Client()` is in-memory, so each run starts clean; if you switch to `PersistentClient`, the very first run's metric is the one you are stuck with on disk.

## What to do instead

- Set `space` explicitly at creation, every time, using `configuration={"hnsw": {"space": "cosine"}}`. Never rely on the default for text embeddings.
- Do not trust `get_or_create_collection` to apply configuration. Treat it as "get the existing one, or create with these settings," never "reconcile to these settings." If the metric matters, assert it after the call: read `collection.configuration_json["hnsw"]["space"]` and fail loudly if it is not what you expect.
- Decide the metric before you index. Changing it later is a full recreate-and-re-add, so bake the choice into your collection-creation code path and cover it with a test.
- Read `query` results as distances. Smaller is closer. For cosine, `0` is a perfect direction match.

None of this requires a new tool or a patched version. It requires setting one argument on purpose and verifying it stuck, because the two moments where Chroma stays silent, an unspecified default and an ignored configuration, are the two moments that decide your retrieval quality.

## Key Takeaways

- Chroma's default distance is **squared L2**, and for magnitude-varying text embeddings that can rank an off-topic chunk above an on-topic one. Verified on `chromadb 1.5.9`: default ranks `B` (distance 1.0) above `A` (16.0); cosine reverses it (0.0 vs 0.2929).
- `get_or_create_collection` **silently ignores** the `configuration` you pass when the collection already exists. It returned `l2` after being asked for `cosine`, with no error or warning.
- The distance function is **immutable after creation**. `modify` rejects `space` outright; switching metrics means deleting and re-indexing the collection.
- `query` returns **distances, not similarities** (`0` is closest for cosine). Set the space explicitly and assert it after creation rather than trusting the default.

## Sources

- Chroma, "Configure Collections" (default `l2`, distance formulas, immutability): https://docs.trychroma.com/docs/collections/configure
- Chroma Cookbook, "Configuration" (space cannot be changed after creation): https://cookbook.chromadb.dev/core/configuration/
- chromadb on PyPI (version and release dates; 1.5.9 on 2026-05-05): https://pypi.org/project/chromadb/
- Chroma releases (1.0 Rust core, April 2025): https://github.com/chroma-core/chroma/releases
- Chroma issue #2668, cosine metadata returning L2 distances (reported 2024-08-15): https://github.com/chroma-core/chroma/issues/2668
- All code output captured from a live run on `chromadb 1.5.9`, Python 3.11.15.
