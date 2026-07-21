import asyncio, json
from agents import SQLiteSession

async def main():
    session = SQLiteSession("grow", db_path=":memory:")
    print(f"{'turn':>4} {'items_replayed':>15} {'history_chars':>14}")
    for turn in range(1, 11):
        # Each turn appends one user message + one assistant reply.
        await session.add_items([
            {"role": "user", "content": f"Question number {turn} about my order."},
            {"role": "assistant", "content": f"Here is the answer to question {turn}."},
        ])
        # This is exactly what the Runner prepends to the next model call.
        history = await session.get_items()
        chars = len(json.dumps(history))
        print(f"{turn:>4} {len(history):>15} {chars:>14}")

asyncio.run(main())
