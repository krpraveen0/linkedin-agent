import asyncio, json
from agents import SQLiteSession
from agents.memory.session_settings import SessionSettings

async def main():
    # Cap retrieval at the 6 most recent items, set once at construction.
    session = SQLiteSession(
        "capped", db_path=":memory:",
        session_settings=SessionSettings(limit=6),
    )
    for turn in range(1, 11):
        await session.add_items([
            {"role": "user", "content": f"Question number {turn} about my order."},
            {"role": "assistant", "content": f"Here is the answer to question {turn}."},
        ])

    replayed = await session.get_items()               # uses the default limit=6
    stored = await session.get_items(limit=10_000)     # a big explicit cap sees all rows

    print("total items still stored on disk :", len(stored))
    print("items replayed to the model      :", len(replayed),
          "->", len(json.dumps(replayed)), "chars")
    print("oldest replayed                  :", replayed[0]["content"])
    print("newest replayed                  :", replayed[-1]["content"])
    # Gotcha: None does NOT mean "unlimited" once a default limit is set.
    print("get_items(limit=None) returns    :", len(await session.get_items(limit=None)),
          "items (falls back to the default, not all)")

asyncio.run(main())
