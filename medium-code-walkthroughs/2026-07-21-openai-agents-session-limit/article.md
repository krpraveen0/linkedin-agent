# OpenAI Agents SDK Sessions Replay Your Whole Conversation on Every Turn. One Setting Stops It.

You add a `Session` to your agent, the follow-up questions suddenly work, and you move on. That is the whole pitch for [Sessions in the OpenAI Agents SDK](https://openai.github.io/openai-agents-python/sessions/): pass a session object to `Runner.run`, and conversation history is stored and retrieved automatically so you never thread `previous_messages` through your own code.

What the pitch leaves out is the retrieval half. Before every model call, the SDK reads the session back and prepends it to the new input. By default it reads *everything*. Turn 40 of a support chat resends turns 1 through 39 to the model, every single time. Your agent still works, but your token bill is now quadratic in the length of the conversation, and nothing in the happy-path code tells you that.

This is not a bug, and it is not hidden in a way you can't check. The `openai-agents` package on PyPI shipped `0.18.3` on [July 17, 2026](https://pypi.org/project/openai-agents/), and the behavior is right there in the installed source. Let me show you exactly what a session stores, watch the replay grow, and then set the one knob that caps it.

## What a session actually stores

`SQLiteSession` is the default in-process store. Point it at a file and it keeps two tables: `agent_sessions` for metadata and `agent_messages` for the history. Every item you add becomes one row, serialized with `json.dumps`. There is no trimming on write.

Here is that store after four items:

```python
import asyncio, sqlite3
from agents import SQLiteSession

async def main():
    session = SQLiteSession("demo-user", db_path="chat.db")
    await session.add_items([
        {"role": "user", "content": "My name is Ada."},
        {"role": "assistant", "content": "Nice to meet you, Ada."},
        {"role": "user", "content": "What's the weather?"},
        {"role": "assistant", "content": "I can't check live weather."},
    ])
    history = await session.get_items()   # what the Runner fetches next turn
    print("get_items() returned", len(history), "items (default limit=None)")

    rows = sqlite3.connect("chat.db").execute(
        "SELECT id, length(message_data) FROM agent_messages ORDER BY id").fetchall()
    for rid, nbytes in rows:
        print(f"  row id={rid}  {nbytes} bytes of JSON")

asyncio.run(main())
```

Running it:

```
get_items() returned 4 items (default limit=None)
  row id=1  46 bytes of JSON
  row id=2  58 bytes of JSON
  row id=3  50 bytes of JSON
  row id=4  63 bytes of JSON
```

Four items in, four rows out. The number that matters is the argument to `get_items()`. The method signature is `get_items(limit: int | None = None)`, and the docstring says it plainly: "If None, uses `session_settings.limit`." The default `SessionSettings` sets `limit = None`, and when the limit resolves to `None` the query is `SELECT message_data ... ORDER BY id ASC` with no `LIMIT` clause. Every row, every turn.

## Watch the replay grow

The single-turn view undersells the problem, because the cost compounds. Each turn appends new items *and* re-reads the full history that now includes all the previous turns. This loop counts what `get_items()` hands back after each of ten turns:

```python
import asyncio, json
from agents import SQLiteSession

async def main():
    session = SQLiteSession("grow", db_path=":memory:")
    print(f"{'turn':>4} {'items_replayed':>15} {'history_chars':>14}")
    for turn in range(1, 11):
        await session.add_items([
            {"role": "user", "content": f"Question number {turn} about my order."},
            {"role": "assistant", "content": f"Here is the answer to question {turn}."},
        ])
        history = await session.get_items()   # prepended to the next model call
        print(f"{turn:>4} {len(history):>15} {len(json.dumps(history)):>14}")

asyncio.run(main())
```

The output is a straight line up and to the right:

```
turn  items_replayed  history_chars
   1               2            137
   2               4            274
   3               6            411
   4               8            548
   5              10            685
   6              12            822
   7              14            959
   8              16           1096
   9              18           1233
  10              20           1372
```

By turn ten, the model call carries all twenty items. Tokens track those characters closely, and providers bill input tokens per call, so the total tokens you pay across a conversation grow with the square of its length. In a short demo that is 1,372 characters. In a real support session with tool calls, function outputs, and long assistant messages, the same curve runs into tens of thousands of tokens resent on every turn — for context the model already saw.

## The one knob that caps it

The fix is `SessionSettings`, passed once when you build the session. `SessionSettings(limit=N)` tells `get_items()` to return only the most recent `N` items. Under the hood the query flips to `ORDER BY id DESC LIMIT N` and reverses the rows back into chronological order, so the model still reads them oldest-to-newest — it just reads a sliding window instead of the whole tape.

```python
import asyncio, json
from agents import SQLiteSession
from agents.memory.session_settings import SessionSettings

async def main():
    session = SQLiteSession(
        "capped", db_path=":memory:",
        session_settings=SessionSettings(limit=6),
    )
    for turn in range(1, 11):
        await session.add_items([
            {"role": "user", "content": f"Question number {turn} about my order."},
            {"role": "assistant", "content": f"Here is the answer to question {turn}."},
        ])

    replayed = await session.get_items()             # uses the default limit=6
    stored = await session.get_items(limit=10_000)   # a big explicit cap sees all rows

    print("total items still stored on disk :", len(stored))
    print("items replayed to the model      :", len(replayed),
          "->", len(json.dumps(replayed)), "chars")
    print("oldest replayed                  :", replayed[0]["content"])
    print("get_items(limit=None) returns    :", len(await session.get_items(limit=None)),
          "items (falls back to the default, not all)")

asyncio.run(main())
```

Output:

```
total items still stored on disk : 20
items replayed to the model      : 6 -> 413 chars
oldest replayed                  : Question number 8 about my order.
get_items(limit=None) returns    : 6 items (falls back to the default, not all)
```

Twenty items are still on disk — the cap is on retrieval, not storage, so you keep the full record for audit or export. But only the six most recent are replayed to the model, holding the per-turn payload flat no matter how long the conversation runs.

## The `None` trap

Look at that last line again. I called `get_items(limit=None)` expecting it to mean "give me everything," and it returned six, not twenty. That surprised me, so I checked the resolver directly instead of trusting the intuition:

```python
from agents.memory.session_settings import SessionSettings, resolve_session_limit
print(resolve_session_limit(None, SessionSettings(limit=6)))   # -> 6
```

`resolve_session_limit` returns the explicit argument only when it is not `None`; otherwise it falls back to the session's configured limit. Once you set a default limit, `None` means "use the default," never "no limit." To deliberately read the entire history from a capped session you pass a large explicit number, as `limit=10_000` does above. The docstring is technically accurate — "If None, uses `session_settings.limit`" — but the word "limit" reads like "no limit" until you watch it return six rows. Direct inspection beats the assumption here.

## When a window isn't enough

A fixed window is the blunt tool: cheap, predictable, and it forgets the user's name from turn 1 once turn 1 falls off the edge. When you need to keep the full thread coherent without resending all of it, the SDK also ships `OpenAIResponsesCompactionSession`, a wrapper that calls the Responses compaction API to summarize older history once enough new items accumulate — its default trigger fires when the candidate item count reaches 10 (`DEFAULT_COMPACTION_THRESHOLD` in the installed source), not a token threshold (see the [memory reference](https://openai.github.io/openai-agents-python/ref/memory/)). That trades a hard cutoff for periodic summarization calls. The point is that neither behavior is the default — the default is "replay all," and you opt into anything smarter.

## Try It Yourself

Everything above runs with no API key, because sessions are a storage layer — no model is called.

```bash
python3 -m venv venv && source venv/bin/activate
pip install openai-agents          # installs 0.18.3
python3 02_growth.py               # watch history_chars climb each turn
python3 03_capped.py               # cap it with SessionSettings(limit=6)
```

`02_growth.py` prints the linear climb in items replayed per turn. `03_capped.py` prints `total items still stored on disk : 20` alongside `items replayed to the model : 6`, and the `get_items(limit=None) returns 6` line that catches the `None` trap. If your numbers differ, check your installed version with `pip show openai-agents` — the row-per-item storage and `SessionSettings.limit` resolution described here are from `0.18.3`.

## Key Takeaways

- **The default replays everything.** `SQLiteSession` stores one row per item and never trims on write; `get_items()` with the default `limit=None` returns the full history and prepends it to every model call, so input tokens grow with the square of conversation length.
- **`SessionSettings(limit=N)` is the cap.** Set it once at construction to replay only the `N` most recent items. Storage is untouched — you keep the full record while bounding what the model sees.
- **`None` is not "unlimited."** Once a default limit is set, `get_items(limit=None)` resolves back to that limit. Pass a large explicit number to read the entire history on purpose.
- **A window forgets.** For long threads that must stay coherent, look at `OpenAIResponsesCompactionSession` instead of a hard cutoff — but know that summarization is opt-in too.

## Sources

- OpenAI Agents SDK — [Sessions](https://openai.github.io/openai-agents-python/sessions/) and [Memory API reference](https://openai.github.io/openai-agents-python/ref/memory/), accessed July 21, 2026, cross-checked against the installed `agents/memory/sqlite_session.py` and `session_settings.py` in `openai-agents 0.18.3`
- [openai-agents on PyPI](https://pypi.org/project/openai-agents/) — release history (0.18.3 published July 17, 2026)
- OpenAI — [New tools for building agents](https://openai.com/index/new-tools-for-building-agents/) (Agents SDK overview)
