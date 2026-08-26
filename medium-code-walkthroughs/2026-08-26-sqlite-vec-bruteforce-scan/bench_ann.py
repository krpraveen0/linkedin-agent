"""
Compare the stable brute-force vec0 table against the v0.1.10-alpha DiskANN
index on the SAME vectors: query latency and recall@10.
DiskANN is approximate, so we measure how often it agrees with the exact scan.
"""
import sqlite3, struct, time, sqlite_vec
import numpy as np

DIM = 128           # divisible by 8 (binary quantizer requirement)
N = 50_000
K = 10
QN = 100
rng = np.random.default_rng(0)

def ser(v): return struct.pack("%sf" % len(v), *v)

def connect():
    db = sqlite3.connect(":memory:")
    db.enable_load_extension(True); sqlite_vec.load(db); db.enable_load_extension(False)
    return db

vecs = rng.standard_normal((N, DIM), dtype=np.float32)
queries = rng.standard_normal((QN, DIM), dtype=np.float32)

db = connect()
print("vec_version:", db.execute("select vec_version()").fetchone()[0])

# ---- brute-force table ----
db.execute(f"CREATE VIRTUAL TABLE flat USING vec0(emb float[{DIM}])")
t = time.perf_counter()
db.executemany("INSERT INTO flat(rowid, emb) VALUES (?,?)", ((i, ser(vecs[i])) for i in range(N)))
db.commit()
flat_insert = time.perf_counter() - t

# ---- DiskANN table (alpha) ----
db.execute(f"CREATE VIRTUAL TABLE ann USING vec0(emb float[{DIM}] INDEXED BY diskann(neighbor_quantizer=binary))")
t = time.perf_counter()
db.executemany("INSERT INTO ann(rowid, emb) VALUES (?,?)", ((i, ser(vecs[i])) for i in range(N)))
db.commit()
ann_insert = time.perf_counter() - t

def run(table):
    sql = f"SELECT rowid FROM {table} WHERE emb MATCH ? AND k=? ORDER BY distance"
    db.execute(sql, (ser(queries[0]), K)).fetchall()  # warm
    t = time.perf_counter()
    results = []
    for q in queries:
        results.append([r[0] for r in db.execute(sql, (ser(q), K)).fetchall()])
    ms = (time.perf_counter() - t) / len(queries) * 1000
    return ms, results

flat_ms, flat_res = run("flat")
ann_ms,  ann_res  = run("ann")

# recall@10: fraction of exact neighbors the ANN index also returned
recalls = [len(set(a) & set(f)) / K for a, f in zip(ann_res, flat_res)]
recall = sum(recalls) / len(recalls)

print(f"rows={N:,}  dim={DIM}  k={K}  queries={QN}\n")
print(f"{'':16} {'insert (s)':>11} {'ms/query':>10}")
print(f"{'brute force':16} {flat_insert:>11.2f} {flat_ms:>10.3f}")
print(f"{'DiskANN (alpha)':16} {ann_insert:>11.2f} {ann_ms:>10.3f}")
print(f"\nspeedup (brute/ann): {flat_ms/ann_ms:.1f}x faster query")
print(f"DiskANN recall@10 vs exact: {recall*100:.1f}%")
