"""Microsoft Agent Framework runs on a Pregel-style superstep (BSP) model.
Fan-out nodes run concurrently inside one superstep; a fan-in node waits for
the barrier and runs in the next superstep with all inputs collected as a list.

Requires: pip install agent-framework-core   (tested on 1.12.0)
Run:      python 02_supersteps.py
"""
import asyncio
from dataclasses import dataclass
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler


@dataclass
class Order:
    id: str


class Dispatch(Executor):
    @handler
    async def go(self, o: Order, ctx: WorkflowContext[Order]) -> None:
        await ctx.send_message(o)  # one message, fanned out to both checkers


class FraudCheck(Executor):
    @handler
    async def run(self, o: Order, ctx: WorkflowContext[str]) -> None:
        await asyncio.sleep(0.05)
        await ctx.send_message(f"fraud=ok({o.id})")


class StockCheck(Executor):
    @handler
    async def run(self, o: Order, ctx: WorkflowContext[str]) -> None:
        await asyncio.sleep(0.05)
        await ctx.send_message(f"stock=ok({o.id})")


class Approve(Executor):
    # fan-in target receives ALL upstream results as a single list
    @handler
    async def collect(self, parts: list[str], ctx: WorkflowContext[None, str]) -> None:
        await ctx.yield_output("APPROVED with " + " & ".join(sorted(parts)))


async def main():
    d = Dispatch(id="dispatch")
    fr, st = FraudCheck(id="fraud"), StockCheck(id="stock")
    ap = Approve(id="approve")
    wf = (
        WorkflowBuilder(start_executor=d, output_from="all")
        .add_fan_out_edges(d, [fr, st])
        .add_fan_in_edges([fr, st], ap)
        .build()
    )

    supersteps: dict[int, list[str]] = {}
    current = 0
    async for ev in wf.run(Order("A1001"), stream=True):
        if ev.type == "superstep_started":
            current = ev.iteration
            supersteps[current] = []
        elif ev.type == "executor_invoked" and current:
            supersteps[current].append(ev.executor_id)
        elif ev.type == "output":
            print("OUTPUT:", ev.data)

    for step, execs in supersteps.items():
        print(f"superstep {step}: ran {execs}")


if __name__ == "__main__":
    asyncio.run(main())
