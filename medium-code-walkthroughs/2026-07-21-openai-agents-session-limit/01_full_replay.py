import asyncio, sqlite3
from agents import SQLiteSession

async def main():
    session = SQLiteSession("demo-user", db_path="chat.db")
    # Simulate two prior turns already saved to the session.
    await session.add_items([
        {"role": "user", "content": "My name is Ada."},
        {"role": "assistant", "content": "Nice to meet you, Ada."},
        {"role": "user", "content": "What's the weather?"},
        {"role": "assistant", "content": "I can't check live weather."},
    ])
    # What the Runner fetches before the NEXT model call:
    history = await session.get_items()
    print("get_items() returned", len(history), "items (default limit=None)")
    for h in history:
        print(" ", h["role"], "->", h["content"][:32])

    # Look at how it's actually stored on disk.
    rows = sqlite3.connect("chat.db").execute(
        "SELECT id, length(message_data) FROM agent_messages ORDER BY id").fetchall()
    print("\nagent_messages table: one row per item, nothing trimmed")
    for rid, nbytes in rows:
        print(f"  row id={rid}  {nbytes} bytes of JSON")

asyncio.run(main())
