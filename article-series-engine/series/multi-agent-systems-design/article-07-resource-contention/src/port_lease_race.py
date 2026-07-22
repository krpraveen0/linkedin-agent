"""
port_lease_race.py

A small, runnable tool for Article 07 ("Shared-resource contention: when
your agents fight over the same database row").

This is a REAL race condition, reproduced with real threads against a
real SQLite file - not a simulated or narrated one. Two provisioner
"agents" try to claim a local port for a Postgres container from a
shared leases table at the same time.

1. naive_allocate_port: SELECT a free port, then UPDATE it - two
   separate statements, with a deliberate small delay between them to
   reliably trigger the interleaving (the same technique used to make
   a real, otherwise-intermittent race condition reproducible for
   demonstration, rather than hoping it happens to occur).
2. safe_allocate_port: one atomic conditional UPDATE - claims a port
   only if it is still unclaimed, checking the affected row count to
   know whether the claim actually succeeded.

Usage:
    python port_lease_race.py
"""

import sqlite3
import threading
import time
import os

DB_PATH = "/tmp/port_leases_demo.db"
PORTS = [5432, 5433, 5434, 5435]


def reset_db() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE port_leases (port INTEGER PRIMARY KEY, leased_by TEXT)")
    conn.executemany("INSERT INTO port_leases (port, leased_by) VALUES (?, NULL)", [(p,) for p in PORTS])
    conn.commit()
    conn.close()


def naive_allocate_port(ticket_id: str, results: dict) -> None:
    """The naive pattern: read the free port, then write the claim as a
    separate statement. The sleep between them is what makes the race
    happen reliably instead of only sometimes."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT port FROM port_leases WHERE leased_by IS NULL LIMIT 1").fetchone()
    port = row[0]
    time.sleep(0.05)  # simulate the other work a real agent does between check and act
    conn.execute("UPDATE port_leases SET leased_by = ? WHERE port = ?", (ticket_id, port))
    conn.commit()
    conn.close()
    results[ticket_id] = port


def safe_allocate_port(ticket_id: str, results: dict) -> None:
    """The fix: one atomic conditional UPDATE. The WHERE clause requires
    the port to still be unclaimed at the moment of the write itself -
    there is no separate read step for another thread to race against."""
    conn = sqlite3.connect(DB_PATH)
    for port in PORTS:
        cur = conn.execute(
            "UPDATE port_leases SET leased_by = ? WHERE port = ? AND leased_by IS NULL",
            (ticket_id, port),
        )
        conn.commit()
        if cur.rowcount == 1:
            results[ticket_id] = port
            conn.close()
            return
    conn.close()
    results[ticket_id] = None  # no port available


if __name__ == "__main__":
    print("--- Naive allocation: two threads, real SQLite file, real race ---")
    reset_db()
    naive_results: dict = {}
    t1 = threading.Thread(target=naive_allocate_port, args=("PAY-402", naive_results))
    t2 = threading.Thread(target=naive_allocate_port, args=("PAY-404", naive_results))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print(f"  PAY-402 believes it holds port: {naive_results['PAY-402']}")
    print(f"  PAY-404 believes it holds port: {naive_results['PAY-404']}")
    if naive_results["PAY-402"] == naive_results["PAY-404"]:
        print(f"  DOUBLE-BOOKED: both tickets believe they hold port {naive_results['PAY-402']}")
        print("  No exception was raised. No SQL error occurred. This is silent.\n")

    print("--- Safe allocation: same race, atomic conditional UPDATE ---")
    reset_db()
    safe_results: dict = {}
    t3 = threading.Thread(target=safe_allocate_port, args=("PAY-402", safe_results))
    t4 = threading.Thread(target=safe_allocate_port, args=("PAY-404", safe_results))
    t3.start()
    t4.start()
    t3.join()
    t4.join()
    print(f"  PAY-402 was allocated port: {safe_results['PAY-402']}")
    print(f"  PAY-404 was allocated port: {safe_results['PAY-404']}")
    if safe_results["PAY-402"] != safe_results["PAY-404"]:
        print("  Correctly allocated to two different ports - no double-booking.")
