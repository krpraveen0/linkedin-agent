# OpenAI Agents SDK Sessions: unbounded history replay and the `SessionSettings` cap

Code for the 2026-07-21 Medium article *"OpenAI Agents SDK Sessions Replay Your Whole
Conversation on Every Turn. One Setting Stops It."*

These scripts demonstrate, with no API key, that `SQLiteSession` stores every item and
`get_items()` replays the entire history by default, and that `SessionSettings(limit=N)`
caps what is replayed to the model.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install openai-agents        # verified against 0.18.3 (released 2026-07-17)
```

## Run

```bash
python3 01_full_replay.py        # one row per item; get_items() returns all 4
python3 02_growth.py             # history replayed per turn climbs linearly
python3 03_capped.py             # SessionSettings(limit=6) caps retrieval
```

`01_full_replay.py` writes a local `chat.db`; delete it (`rm -f chat.db*`) for a clean run.

## Real captured output

### `01_full_replay.py`

```
get_items() returned 4 items (default limit=None)
  user -> My name is Ada.
  assistant -> Nice to meet you, Ada.
  user -> What's the weather?
  assistant -> I can't check live weather.

agent_messages table: one row per item, nothing trimmed
  row id=1  46 bytes of JSON
  row id=2  58 bytes of JSON
  row id=3  50 bytes of JSON
  row id=4  63 bytes of JSON
```

### `02_growth.py`

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

### `03_capped.py`

```
total items still stored on disk : 20
items replayed to the model      : 6 -> 413 chars
oldest replayed                  : Question number 8 about my order.
newest replayed                  : Here is the answer to question 10.
get_items(limit=None) returns    : 6 items (falls back to the default, not all)
```

## Notes

- Sessions are a storage layer, so none of these scripts call a model or need an API key.
- `get_items(limit=None)` resolves to the session's configured limit, not "unlimited";
  pass a large explicit number to read the full history from a capped session.
- Environment used: Python 3.11.15, `openai-agents 0.18.3` on Linux.

## Files

- `01_full_replay.py`, `02_growth.py`, `03_capped.py` — the runnable demos
- `article.md` — the full article
- `figure1_replay_loop.svg`, `figure2_limit_window.svg` — diagrams
