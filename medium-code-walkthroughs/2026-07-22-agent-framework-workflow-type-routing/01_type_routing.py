"""Microsoft Agent Framework: an edge delivers a message only to a handler
whose parameter type matches. Same wiring, different destinations by type.

Requires: pip install agent-framework-core   (tested on 1.12.0)
Run:      python 01_type_routing.py
"""
import asyncio
from dataclasses import dataclass
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


@dataclass
class Ticket:
    text: str

@dataclass
class Refund:
    amount: int

@dataclass
class Question:
    text: str


class Classifier(Executor):
    @handler
    async def classify(self, t: Ticket, ctx: WorkflowContext[Refund | Question]) -> None:
        if "refund" in t.text.lower():
            await ctx.send_message(Refund(amount=42))
        else:
            await ctx.send_message(Question(text=t.text))


class RefundDesk(Executor):
    # handles BOTH types
    @handler
    async def on_refund(self, r: Refund, ctx: WorkflowContext[None, str]) -> None:
        print("  RefundDesk.on_refund invoked")
        await ctx.yield_output(f"RefundDesk paid ${r.amount}")

    @handler
    async def on_question(self, q: Question, ctx: WorkflowContext[None, str]) -> None:
        print("  RefundDesk.on_question invoked")
        await ctx.yield_output(f"RefundDesk relayed: {q.text}")


class FAQ(Executor):
    # handles ONLY Question
    @handler
    async def on_question(self, q: Question, ctx: WorkflowContext[None, str]) -> None:
        print("  FAQ.on_question invoked")
        await ctx.yield_output(f"FAQ answered: {q.text}")


async def main():
    c, r, f = Classifier(id="classifier"), RefundDesk(id="refund_desk"), FAQ(id="faq")
    wf = (
        WorkflowBuilder(start_executor=c, output_from="all")
        .add_edge(c, r)   # identical wiring
        .add_edge(c, f)   # identical wiring
        .build()
    )
    print("refund_desk handles:", sorted(t.__name__ for t in r.input_types))
    print("faq         handles:", sorted(t.__name__ for t in f.input_types))

    print("\n[Refund ticket] -> Refund is a type only RefundDesk handles")
    res = await wf.run(Ticket("I want a refund please"))
    print("outputs:", res.get_outputs())

    print("\n[Plain question] -> Question is a type BOTH downstream nodes handle")
    res2 = await wf.run(Ticket("What are your opening hours?"))
    print("outputs:", res2.get_outputs())


if __name__ == "__main__":
    asyncio.run(main())
