"""
Does a sqlite-vec vec0 KNN query use an index, or read every row?
Time the same query as the table grows. If latency scales linearly with the
row count, every query is a full brute-force scan.

No model needed: vectors are random float32 (the timing does not depend on
their values, only on how many there are).

    pip install sqlite-vec numpy
    python scan_benchmark.py
"""
import sqlite3
import struct
import time
import sqlite_vec
import numpy as np

DIM = 384
SIZES = [10_000, 25_000, 50_000, 100_000, 200_000]
QUERIES = 200  # queries averaged per size
rng = np.random.default_rng(42)


def serialize(vec):
    # sqlite-vec reads a float32 vector as raw little-endian bytes.
    return struct.pack("%sf" % len(vec), *vec)


def build(n):
    db = sqlite3.connect(":memory:")
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.execute(f"CREATE VIRTUAL TABLE items USING vec0(embedding float[{DIM}])")
    vecs = rng.standard_normal((n, DIM), dtype=np.float32)
    db.executemany(
        "INSERT INTO items(rowid, embedding) VALUES (?, ?)",
        ((i, serialize(vecs[i])) for i in range(n)),
    )
    db.commit()
    return db


def time_knn(db, queries, k=10):
    sql = "SELECT rowid FROM items WHERE embedding MATCH ? AND k = ? ORDER BY distance"
    db.execute(sql, (serialize(queries[0]), k)).fetchall()  # warm up
    start = time.perf_counter()
    for q in queries:
        db.execute(sql, (serialize(q), k)).fetchall()
    return (time.perf_counter() - start) / len(queries) * 1000.0  # ms/query


probe = sqlite3.connect(":memory:")
probe.enable_load_extension(True)
sqlite_vec.load(probe)
print("sqlite-vec version:", probe.execute("select vec_version()").fetchone()[0])
print(f"dim={DIM}, queries averaged per size={QUERIES}\n")
print(f"{'rows':>10} | {'ms/query':>10} | {'us per 1k rows':>15}")
print("-" * 43)

query_vecs = rng.standard_normal((QUERIES, DIM), dtype=np.float32)
for n in SIZES:
    db = build(n)
    ms = time_knn(db, query_vecs)
    per_1k = (ms * 1000.0) / (n / 1000.0)
    print(f"{n:>10,} | {ms:>10.3f} | {per_1k:>15.2f}")
    db.close()
