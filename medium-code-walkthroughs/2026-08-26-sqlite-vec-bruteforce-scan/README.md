# sqlite-vec: brute-force scan vs the 2026 DiskANN alpha

Code for the Medium article **"I Moved 200,000 Embeddings Into sqlite-vec. Every Query Still Scanned All of Them."** (2026-08-26).

These scripts show, empirically, that the stable `sqlite-vec` you get from `pip install`
(v0.1.9) answers every KNN query with an exact brute-force scan, and that the
v0.1.10 **alpha** finally adds a DiskANN index with real tradeoffs.

No model or API key is required: the vectors are random `float32`, and the query
timing depends only on how many vectors there are, not what they contain.

## Files

- `scan_benchmark.py` — times a KNN query as the table grows from 10k to 200k rows. Flat "microseconds per 1,000 rows" = O(n) full scan.
- `probe_plan_and_filter.py` — `EXPLAIN QUERY PLAN` (shows a `SCAN`) and how much a selective metadata filter actually saves.
- `bench_ann.py` — builds the same vectors into a brute-force table and a v0.1.10-alpha DiskANN table; compares query latency, build time, and recall@10.

## Run the brute-force benchmark (stable, v0.1.9)

```
pip install sqlite-vec numpy
python scan_benchmark.py
```

Real captured output (CPU, August 2026):

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

The last column stays near constant (~670 us / 1k rows) across a 20x range of
table sizes: 20x the rows, 20x the latency. That is a full scan.

`probe_plan_and_filter.py` confirms the plan and the filter behavior:

```
--- EXPLAIN QUERY PLAN (plain KNN) ---
(2, 0, 0, 'SCAN items VIRTUAL TABLE INDEX 0:3{___}___')

plain KNN over 100,000 rows:                 66.61 ms
KNN + metadata filter (category=7, ~1%):  29.69 ms
ratio (filtered / plain): 0.45x
```

A `SCAN`, not a `SEARCH`. A filter keeping ~1% of rows only cut latency to 45%,
not to 1% — the predicate is checked by walking the whole table.

## Run the DiskANN alpha comparison (v0.1.10-alpha.4)

The DiskANN index is pre-release only. Install it into a separate environment:

```
python -m venv .venv-alpha
. .venv-alpha/bin/activate
pip install --pre 'sqlite-vec==0.1.10a4' numpy
python bench_ann.py
```

Real captured output (CPU, August 2026; this run takes ~2 minutes because
building the DiskANN graph is slow):

```
vec_version: v0.1.10-alpha.4
rows=50,000  dim=128  k=10  queries=100

                  insert (s)   ms/query
brute force             0.87      4.031
DiskANN (alpha)       108.74      1.480

speedup (brute/ann): 2.7x faster query
DiskANN recall@10 vs exact: 20.1%
```

The DiskANN query was 2.7x faster, but the index took ~125x longer to build, and
recall@10 was 20% on random Gaussian vectors (a worst case for the binary
quantizer). Real embeddings have structure and the `rescore` index re-ranks
candidates with full-precision vectors; measure recall on your own data before
trusting it.

DiskANN table syntax (found in the project's
[test suite](https://github.com/asg017/sqlite-vec/blob/main/tests/test-diskann.py),
not yet in the docs):

```sql
CREATE VIRTUAL TABLE ann USING vec0(
    emb float[128] INDEXED BY diskann(neighbor_quantizer=binary)
)
```

`neighbor_quantizer` is required (`binary` or `int8`); `binary` needs a dimension
divisible by 8. Optional: `n_neighbors`, `search_list_size`.

## Sources

- sqlite-vec repository: https://github.com/asg017/sqlite-vec
- ANN tracking issue #25 (brute-force only): https://github.com/asg017/sqlite-vec/issues/25
- Releases (v0.1.9 stable, v0.1.10-alpha ANN indexes): https://github.com/asg017/sqlite-vec/releases

Benchmarks run by the author against sqlite-vec v0.1.9 and v0.1.10-alpha.4 on CPU, August 2026.
