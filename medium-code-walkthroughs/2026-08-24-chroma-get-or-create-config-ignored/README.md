# Chroma distance-metric footguns (default L2, get_or_create, immutability)

Runnable code for the article **"I Told Chroma to Use Cosine. `get_or_create_collection` Kept My Old L2 Index and Never Said a Word."** (2026-08-24).

`demo.py` reproduces four documented behaviors of [Chroma](https://www.trychroma.com/) using fixed, hand-set embeddings, so it needs no model, no API key, and no network:

1. A new collection defaults to **squared L2** distance, which can rank an off-topic chunk above an on-topic one for text embeddings.
2. Setting `configuration={"hnsw": {"space": "cosine"}}` at creation fixes the ranking.
3. `get_or_create_collection` **silently ignores** the `configuration` you pass when the collection already exists.
4. The distance function is **immutable**: `modify` rejects `space`.

## Setup and run

```bash
python -m venv env && . env/bin/activate
pip install chromadb        # tested on chromadb 1.5.9, Python 3.11.15
python demo.py
```

## Real captured output

Captured from a live run on `chromadb 1.5.9`, Python 3.11.15:

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

The full `modify` error (before truncation in the demo) is:

```
unknown field `space`, expected one of `ef_search`, `max_neighbors`, `num_threads`, `resize_factor`, `sync_threshold`, `batch_size` at line 1 column 17
```

## Files

- `demo.py` — the runnable demonstration.
- `article.md` — the article.
- `fig1-ranking-flip.svg` — vector plot of the squared-L2-vs-cosine ranking flip.
- `fig2-metric-lifecycle.svg` — where Chroma stays silent about the metric across a collection's lifecycle.

## Notes

- Distances, not similarities: `query` returns distances, so smaller is closer. For cosine, `0` is a perfect direction match.
- Collection names must be 3–512 characters of `[a-zA-Z0-9._-]`.
- `chromadb.Client()` is in-memory; with `PersistentClient` the first run's metric is what you are stuck with on disk.
