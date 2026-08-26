# I Moved 200,000 Embeddings Into sqlite-vec. Every Query Still Scanned All of Them.

If you are building agent memory or a small RAG store, `sqlite-vec` is a tempting default. One `pip install`, no server, no Docker, and your embeddings live in the same SQLite file as everything else. You create a `vec0` virtual table, insert your vectors, and run a `MATCH` query that returns nearest neighbors. It reads like a database index.

It is not one. The version `pip install sqlite-vec` gives you today compares your query against every stored vector, one at a time. I measured it: doubling the row count doubles the query latency, exactly, all the way up. This spring the project finally shipped a real approximate-nearest-neighbor index, but only in a pre-release you have to opt into by name, and it comes with tradeoffs worth knowing before you reach for it.

## What `vec0` does when you query it

sqlite-vec describes itself as ["An extremely small, 'fast enough' vector search SQLite extension that runs anywhere"](https://github.com/asg017/sqlite-vec). You store vectors in a `vec0` virtual table and query the nearest ones with a `MATCH` constraint and a `k`:

```python
import sqlite3, struct, sqlite_vec

db = sqlite3.connect(":memory:")
db.enable_load_extension(True)
sqlite_vec.load(db)
db.execute("CREATE VIRTUAL TABLE items USING vec0(embedding float[384])")

def serialize(vec):
    return struct.pack("%sf" % len(vec), *vec)  # raw little-endian float32

db.execute("INSERT INTO items(rowid, embedding) VALUES (?, ?)", (1, serialize([0.1] * 384)))
rows = db.execute(
    "SELECT rowid FROM items WHERE embedding MATCH ? AND k = 3 ORDER BY distance",
    (serialize([0.1] * 384),),
).fetchall()
```

The word "index" never appears, but the mental model most people bring is a b-tree: the engine narrows the search using some structure and touches a small slice of the rows. That is not what happens here. The [ANN tracking issue](https://github.com/asg017/sqlite-vec/issues/25), open since June 2024, states it plainly: "sqlite-vec as of v0.1.0 will be brute-force search only, which slows down on large datasets (>1M w/ large dimensions)." Every `MATCH` query computes the distance from your query to every row, sorts, and returns the top `k`.

That is a reasonable design choice for a "fast enough" extension. It is only a problem when you assume otherwise and size your data accordingly.

## Measuring the scan

The clean way to prove a query is O(n) is to grow n and watch the clock. If latency per query rises in lockstep with the row count, the cost per row is constant, which is the signature of touching every row.

I inserted random 384-dimensional float32 vectors (the timing depends only on how many vectors there are, not their values), then timed 200 KNN queries at each size:

```python
def build(n):
    db = sqlite3.connect(":memory:")
    db.enable_load_extension(True); sqlite_vec.load(db)
    db.execute("CREATE VIRTUAL TABLE items USING vec0(embedding float[384])")
    vecs = rng.standard_normal((n, 384), dtype=np.float32)
    db.executemany("INSERT INTO items(rowid, embedding) VALUES (?, ?)",
                   ((i, serialize(vecs[i])) for i in range(n)))
    db.commit()
    return db

def time_knn(db, queries, k=10):
    sql = "SELECT rowid FROM items WHERE embedding MATCH ? AND k = ? ORDER BY distance"
    start = time.perf_counter()
    for q in queries:
        db.execute(sql, (serialize(q), k)).fetchall()
    return (time.perf_counter() - start) / len(queries) * 1000.0  # ms/query
```

The result is about as linear as real-world timing gets:

```
sqlite-vec version: v0.1.9
dim=384, queries averaged per size=200

      rows |   ms/query |  us per 1k rows
-------------------------------------------
    10,000 |      6.568 |          656.77
    25,000 |     17.324 |          692.94
    50,000 |     34.060 |          681.21
   100,000 |     67.250 |          672.50
   200,000 |    131.746 |          658.73
```

The last column is the tell. Cost per thousand rows sits between 656 and 693 microseconds across a 20x range of table sizes. Twenty times the rows, twenty times the latency: 6.6 ms at 10,000 rows, 131.7 ms at 200,000. There is no index doing any pruning. `EXPLAIN QUERY PLAN` says the same thing in one line:

```
(2, 0, 0, 'SCAN items VIRTUAL TABLE INDEX 0:3{___}___')
```

A `SCAN`, not a `SEARCH`. For an agent that recalls memories on every turn, 130 ms per lookup against a few hundred thousand vectors is the difference between snappy and sluggish, and it only gets worse as the store grows.

## The metadata filter doesn't rescue you

sqlite-vec lets you attach metadata columns to a `vec0` table and filter on them inside a KNN query, which sounds like a way to shrink the search. I added a `category` column with 100 distinct values and queried with a filter that keeps roughly 1% of rows:

```sql
SELECT rowid FROM items
WHERE embedding MATCH ? AND k = 10 AND category = 7
ORDER BY distance
```

Over 100,000 rows, the unfiltered query took 66.6 ms and the 1%-selective filtered query took 29.7 ms. Faster, but only by about 2.2x, not the 100x you would get if the filter pruned the work down to the matching rows. The filter lets sqlite-vec skip the distance math on rows that fail the predicate, but it still walks the whole table to check the predicate. The scan is still a scan.

## The 2026 alpha adds a real index, with a catch

Here is the genuinely new part. Between March and May 2026, the alpha line finally grew ANN indexes. The [v0.1.10-alpha.1 release notes](https://github.com/asg017/sqlite-vec/releases) read: "new ANN indexes: rescore, ivf (experimental, not enabled), and DiskANN." The latest at the time of writing, v0.1.10-alpha.4, landed on May 18, 2026.

The catch is right there in the version string. `pip install sqlite-vec` resolves to the stable **v0.1.9** (released March 31, 2026), which has none of this. You have to ask for the pre-release explicitly:

```
pip install --pre 'sqlite-vec==0.1.10a4'
```

The DiskANN syntax is not in the published docs yet; I found it by reading the [test suite](https://github.com/asg017/sqlite-vec/blob/main/tests/test-diskann.py). You attach the index to the vector column with `INDEXED BY`:

```sql
CREATE VIRTUAL TABLE ann USING vec0(
    emb float[128] INDEXED BY diskann(neighbor_quantizer=binary)
)
```

The quantizer is required (`binary` or `int8`), and `binary` needs a dimension divisible by 8. I built the same 50,000 vectors into a brute-force table and a DiskANN table and compared:

```
vec_version: v0.1.10-alpha.4
rows=50,000  dim=128  k=10  queries=100

                  insert (s)   ms/query
brute force             0.87      4.031
DiskANN (alpha)       108.74      1.480

speedup (brute/ann): 2.7x faster query
DiskANN recall@10 vs exact: 20.1%
```

Three things stand out, and none of them is "free speedup." The query got 2.7x faster. But building the index took 108.7 seconds against 0.87 for a plain insert, roughly 125x slower, because every insert updates a graph. And recall@10 was 20.1%: on this data the DiskANN table agreed with the exact top-10 only one time in five.

That last number deserves an honest caveat. Random Gaussian vectors are close to a worst case for a binary quantizer, which throws away everything except the sign of each dimension. Real embeddings have structure, and the `rescore` index exists precisely to re-rank approximate candidates with full-precision vectors and claw recall back. The point is not that DiskANN is bad; it is that swapping in an ANN index is a tuning problem with a real accuracy budget, not a flag you flip. And today it only exists in an alpha you have to name explicitly.

## Try it yourself

Everything here reproduces on a laptop with no model and no API key, because the vectors are random and the timing does not care what they contain.

```
pip install sqlite-vec numpy
python scan_benchmark.py
```

You should see the same flat "microseconds per 1,000 rows" column, confirming the query cost scales linearly with the table size. If you want to see the alpha index, install `sqlite-vec==0.1.10a4` with `--pre` and create a table with `INDEXED BY diskann(neighbor_quantizer=binary)`. Watch both the query speedup and the insert time, and measure recall against a plain `vec0` table before you trust it. The full benchmark scripts, including the DiskANN comparison, are in the repository linked below.

## Key Takeaways

- The stable `sqlite-vec` you get from `pip install` (v0.1.9) does exact brute-force KNN. Query latency scales linearly with row count: I measured a constant ~670 microseconds per 1,000 rows from 10k to 200k vectors.
- `EXPLAIN QUERY PLAN` reports a `SCAN`, not a `SEARCH`. There is no index pruning the rows.
- Metadata filters skip distance math but still scan the whole table. A 1%-selective filter was only ~2.2x faster, not 100x.
- The 2026 alpha (v0.1.10) adds DiskANN, IVF, and rescore indexes, but they are pre-release only and undocumented; you opt in with `pip install --pre` and `INDEXED BY diskann(...)`.
- The alpha DiskANN index traded a 2.7x query speedup for a ~125x slower build and, on random vectors, 20% recall. ANN is a tuning problem with an accuracy budget, so measure recall on your own embeddings before shipping it.

*Sources: [sqlite-vec repository and README](https://github.com/asg017/sqlite-vec), [ANN tracking issue #25](https://github.com/asg017/sqlite-vec/issues/25), [sqlite-vec releases](https://github.com/asg017/sqlite-vec/releases), [DiskANN test suite](https://github.com/asg017/sqlite-vec/blob/main/tests/test-diskann.py). All benchmarks run by the author against sqlite-vec v0.1.9 (stable) and v0.1.10-alpha.4 on CPU, August 2026.*
