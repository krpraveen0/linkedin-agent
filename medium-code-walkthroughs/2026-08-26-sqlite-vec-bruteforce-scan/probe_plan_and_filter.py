import sqlite3, struct, time, sqlite_vec
import numpy as np

DIM = 384
N = 100_000
rng = np.random.default_rng(7)

def ser(v): return struct.pack("%sf" % len(v), *v)

db = sqlite3.connect(":memory:")
db.enable_load_extension(True); sqlite_vec.load(db); db.enable_load_extension(False)
print("vec_version:", db.execute("select vec_version()").fetchone()[0])

# vec0 table with a metadata column (category 0..99)
db.execute(f"CREATE VIRTUAL TABLE items USING vec0(embedding float[{DIM}], category integer)")
vecs = rng.standard_normal((N, DIM), dtype=np.float32)
cats = rng.integers(0, 100, size=N)
db.executemany("INSERT INTO items(rowid, embedding, category) VALUES (?,?,?)",
               ((i, ser(vecs[i]), int(cats[i])) for i in range(N)))
db.commit()

q = ser(rng.standard_normal(DIM, dtype=np.float32))

print("\n--- EXPLAIN QUERY PLAN (plain KNN) ---")
for row in db.execute("EXPLAIN QUERY PLAN SELECT rowid FROM items WHERE embedding MATCH ? AND k = 10", (q,)):
    print(row)

def timeit(sql, params, reps=100):
    db.execute(sql, params).fetchall()  # warm
    t = time.perf_counter()
    for _ in range(reps):
        db.execute(sql, params).fetchall()
    return (time.perf_counter()-t)/reps*1000

plain = timeit("SELECT rowid FROM items WHERE embedding MATCH ? AND k=10 ORDER BY distance", (q,))
# metadata filter that keeps ~1% of rows
filt  = timeit("SELECT rowid FROM items WHERE embedding MATCH ? AND k=10 AND category = 7 ORDER BY distance", (q,))
print(f"\nplain KNN over {N:,} rows:                 {plain:.2f} ms")
print(f"KNN + metadata filter (category=7, ~1%):  {filt:.2f} ms")
print(f"ratio (filtered / plain): {filt/plain:.2f}x")
