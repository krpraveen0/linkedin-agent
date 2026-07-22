# Shared-resource contention: when your agents fight over the same database row

*Connection-pool exhaustion and double-booking get mentioned in passing by a couple of articles, and then nobody walks through the actual concurrency-control fix with runnable code. This one does - a real race condition, reproduced with real threads against a real database file, not narrated.*

## A problem sixty years older than multi-agent systems

A recent paper on concurrency control for multi-agent LLM systems makes a point worth sitting with: running multiple agents concurrently against shared state - a file, a git tree, a database row - revives a classical problem, not a new one. The same paper traces the failure rate directly back to Article 05's own source: a large-scale audit of multi-agent traces attributes more than a third of all observed failures to inter-agent misalignment, which explicitly includes agents acting on the same resource unaware of each other.

The classical version of this problem is old enough to have a name from 1965. Dijkstra's Dining Philosophers formalized the setting where independent actors claim shared resources and can end up in states nobody designed for - though it is worth being precise about which specific anomaly this article demonstrates, since the two get conflated constantly. Dining Philosophers is fundamentally about deadlock: a circular wait where every actor holds one resource and waits forever for another, with classical fixes like resource ordering (every actor claims resources in the same fixed order) and symmetry breaking (one actor reverses its order to break the cycle). This article's scenario is a different, more common anomaly: a lost update, where no one waits forever, but two actors both proceed on stale information and one's work silently vanishes without either agent, or the system, ever noticing. Multi-agent LLM systems did not invent either failure mode. They just gave both a new place to hide, because the read-then-write pattern that causes a lost update looks completely reasonable in code that has never been run under real concurrency.

<image src="file-upload://3a5c633a-e23a-811f-acb7-00b28ccc818d"></image>

*The exact anomaly this article reproduces: two threads, one SQLite file, a genuine lost update - not narrated, run.*

## The scenario: two tickets, one port

DevPulse's workspace provisioner needs a local port for each project's Postgres container. Say four ports are available, tracked in a `port_leases` table - one row per port, `leased_by` either null or a ticket ID. Two tickets, PAY-402 and PAY-404, arrive close enough together that their provisioning runs concurrently.

The naive allocation looks like ordinary, unremarkable code: check which port is free, then claim it.

```python
def naive_allocate_port(ticket_id, results):
    row = conn.execute("SELECT port FROM port_leases WHERE leased_by IS NULL LIMIT 1").fetchone()
    port = row[0]
    # ...the agent does other work here - reading a config file, calling another
    # tool, anything that takes any time at all...
    conn.execute("UPDATE port_leases SET leased_by = ? WHERE port = ?", (ticket_id, port))
    conn.commit()
    results[ticket_id] = port
```

Run this from two threads against the same real SQLite file and the result is not hypothetical:

```
PAY-402 believes it holds port: 5432
PAY-404 believes it holds port: 5432
DOUBLE-BOOKED: both tickets believe they hold port 5432
No exception was raised. No SQL error occurred. This is silent.
```

Both threads read "5432 is free" before either one wrote its claim. Both proceeded as if they legitimately owned it. The database itself never complained - the second UPDATE statement is perfectly valid SQL, it just silently overwrites what the first one believed was settled. This is the lost-update anomaly, and it reproduces every time this code runs under real concurrency, not occasionally under unlucky timing, because the artificial delay between the read and the write reliably forces the interleaving rather than leaving it to chance. The two agents will find out they collided only later, when two Postgres containers both try to bind port 5432 and one of them fails - far from the point where the actual mistake happened.

## Why "just add a database" does not fix this

This is the trap the gap this article closes is built around: teams hear "shared state needs a database" and stop there, as if the presence of a database were itself the fix. It is not. `port_leases` in the example above is a real, perfectly normal SQLite table. The bug is not the absence of a database. It is that the code talks to the database with two separate statements - a read, then a write - leaving a gap in between where another agent can act on the same stale information.

The fix is not a bigger database, or a different one. It is doing the check and the claim as one atomic operation, so there is no gap for another agent to land in.

```python
def safe_allocate_port(ticket_id, results):
    for port in PORTS:
        cur = conn.execute(
            "UPDATE port_leases SET leased_by = ? WHERE port = ? AND leased_by IS NULL",
            (ticket_id, port),
        )
        conn.commit()
        if cur.rowcount == 1:
            results[ticket_id] = port
            return
    results[ticket_id] = None
```

One statement. The `WHERE leased_by IS NULL` clause is checked and enforced by the database engine at the exact moment of the write, not by application code a moment earlier. Run the same race against this version:

```
PAY-402 was allocated port: 5432
PAY-404 was allocated port: 5433
Correctly allocated to two different ports - no double-booking.
```

`cur.rowcount` is what makes this trustworthy rather than hopeful: if the conditional UPDATE actually changed a row, exactly one row was updated, meaning the claim genuinely succeeded. If another agent claimed the port first, the WHERE clause matches nothing, `rowcount` is zero, and the code knows to try the next port - rather than believing a write succeeded that never actually happened.

## Why this beats a Python lock, specifically

The obvious-looking alternative fix is wrapping the naive version in a `threading.Lock`. It would even work, in this exact demo, because both threads are running in the same process. It would stop working the moment DevPulse's provisioner runs as more than one process - a common and likely deployment shape once a system handles enough concurrent tickets to need more than one worker. A Python-level lock only coordinates threads inside the process holding it. It says nothing to a second process, a second container, or a second machine also trying to claim a port from the same table.

The atomic conditional UPDATE has no such limitation, because the coordination point is the database itself, not application memory. Any number of separate provisioner processes, on any number of machines, hit the same `WHERE leased_by IS NULL` check enforced by the same database engine. This is also why "add a database" sounded like a fix in the first place and was not: a database was already present in the naive version. What was missing was making the database do the actual coordination work, instead of just storing the result of coordination application code assumed it had already done correctly.

Worth naming which of the two standard approaches this is, since both are legitimate and the choice matters. Pessimistic locking reserves a resource before reading it - the equivalent of `SELECT ... FOR UPDATE`, which blocks any other transaction from touching that row until the first one finishes. Optimistic locking, what the conditional UPDATE above actually does, proceeds without reserving anything up front and instead checks at the moment of writing whether the assumption still holds, retrying if it does not. Optimistic locking is the better fit here specifically because two tickets landing at literally the same instant is the exception, not the norm - reserving a lock for every single allocation would pay a coordination cost on every request to guard against a collision that happens rarely. Pessimistic locking earns its cost when collisions are frequent enough that most attempts would need a retry anyway; forcing every request to wait up front is cheaper than the alternative at that point, which is not the situation DevPulse's provisioner is actually in.

One more honest limit worth stating: the fix above solves correctness, not capacity. If every port is genuinely leased when a fifth ticket arrives, the safe version correctly returns "no port available" rather than corrupting a row - which is the right behavior, but it is a different problem from the one this article solves, and solving it means adding capacity or a queue, not tightening the concurrency control further. A correct allocator that is honestly out of ports is not a bug.

## What this looks like Monday morning

Find the shared-resource writes in your own system that look like the naive version above: a read, some amount of other work, then a write based on what was read. That gap is where this article's failure lives, whether or not two agents have collided there yet. The absence of a reported incident does not mean the gap is not there - it means nobody has been unlucky with timing yet, and MAST's own numbers suggest waiting for that is not a strategy.

Replace the read-then-write pattern with one atomic statement wherever the underlying store supports it - a conditional UPDATE, a compare-and-swap, an INSERT with a uniqueness constraint that fails cleanly on conflict. Check the actual result of that statement, not just whether it ran without an exception, the same discipline Article 05 argued for completion verification generally.

Run your own allocator against two real concurrent callers before trusting it, the same way this article's demo did - not a single-threaded test that never exercises the actual gap. A read-then-write pattern that has only ever been tested one call at a time has not actually been tested for the failure this article describes.

The next article in this series is the last one: pulling every design decision from Articles 01 through 07 into one worked system, end to end.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Design Multi-Agent Systems

1. Multi-agent or overkill? A decision framework before you add a second agent — not yet published
2. The coordination primitives: control, state, and communication — a vendor-neutral model — not yet published
3. The four canonical orchestration patterns, and how to actually choose one — not yet published
4. Designing the trust boundary: authorization between agents that isn't an afterthought — not yet published
5. Preventing the MAST failure modes by design, not by autopsy — not yet published
6. Observability and evaluation for multi-agent systems: what to actually measure — not yet published
7. **Shared-resource contention: when your agents fight over the same database row** *(this article)*
8. Putting it together: designing a production multi-agent system end to end — not yet published

## References

1. CoAgent: Concurrency Control for Multi-Agent Systems (2026)
   https://arxiv.org/abs/2606.15376
2. DPBench: Structural Determinants of Multi-Agent LLM Coordination Under Simultaneous Resource Contention (2026)
   https://arxiv.org/abs/2602.13255
3. Cemri, M. et al. Why Do Multi-Agent LLM Systems Fail?, 2025
   https://arxiv.org/abs/2503.13657
