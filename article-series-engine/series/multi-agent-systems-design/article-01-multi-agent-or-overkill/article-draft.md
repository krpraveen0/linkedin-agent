# Multi-agent or overkill? A decision framework before you add a second agent

*A framework for deciding whether a second agent actually earns its cost — walked through against ClaimGuard, an insurance claims and fraud-detection system, where getting the answer wrong has real financial and regulatory consequences.*

New to AI agents? Quick grounding before this gets specific: an AI agent is software built around a model that decides what to do next based on what it observes, and can take real actions — call an API, update a record, move money — not just answer questions. This series' companion, *Fundamentals of AI Agents*, builds that idea up from a testable definition if you want the full foundation first. This article picks up from there and asks the next question: once you have one agent, when does a second one actually make sense?

## What ClaimGuard does

ClaimGuard processes insurance claims. A claim router receives each new submission and dispatches it to three checks that can run at the same time: an intake agent that parses the claim into a structured record, a fraud-risk agent that scores it against historical fraud patterns, and a policy-verification agent that checks it against actual coverage terms. Once those three finish, a payment-processing agent decides whether to pay out — and this is where the design gets interesting, because payment processing moves real money, and it cannot simply trust whatever the fraud-risk agent handed it.

This isn't a hypothetical stakes-raiser. Insurance carriers operate under real regulatory obligations most software never has to think about: a claims decision has to be explainable to a regulator on request, a payout has to be traceable to a specific authorization, and a false denial or a false payout both carry consequences that a dropped API call in a developer-productivity tool never will. That regulatory weight is exactly why the design questions in this series get sharper against ClaimGuard than they would against a lower-stakes system — not because the underlying framework changes, but because a wrong answer here is a wrong answer that matters.

Five agents. Ask the same question a coordination-theory result gives a precise answer to: how many potential links exist between five things? The formula is n(n−1)/2, which for five agents is ten. Ten possible relationships this system *could* have. Most systems never need most of them.

## The question nobody asks before drawing the diagram

Architecture diagrams for multi-agent systems tend to start from "here are the boxes" and work backward to justification, if they justify anything at all. The better order is the reverse: before a box exists, what earns it a place in the diagram?

Anthropic's engineering team has shipped enough production multi-agent systems to put a real number on what skipping that question costs: multi-agent implementations typically use three to ten times more tokens than a single agent handling the same task. Every additional agent is another prompt to maintain, another boundary where context can get lost, another thing that fails in a way a single agent never could. None of that is an argument against multi-agent design. It's the reason the "why" has to come before the box.

## Three reasons, and only three, that hold up

Reason one: the task exceeds what a single agent can hold in context. Not "it would be tidier split up" — genuinely too much for one pass. A claims system reviewing a backlog of thousands of historical cases while also parsing today's incoming claim is a real example of this; most individual claim processing is not.

Reason two: independent, parallelizable work exists, and the speedup is worth what coordinating it costs. This is ClaimGuard's intake, fraud-risk, and policy-verification agents exactly. None needs the others' output to do its own job. Running all three at once instead of in sequence buys real thoroughness — a claim gets checked from three angles simultaneously rather than waiting on each check in turn.

Reason three: failure isolation. One agent's mistake must not be able to reach into another's territory. This is why fraud-risk scoring and payment execution are different agents in the first place, and it's the reason this design gets interesting rather than obvious. Picture what happens if they aren't separated: a fraud-risk agent that misclassifies a batch of claims during a model update, or simply returns a malformed score under load, now sits in the same execution path as the code that actually authorizes a payout. Splitting them into separate agents doesn't prevent the fraud-risk agent from making a mistake — nothing can guarantee that — but it creates a real boundary where payment-processing has to independently confirm what it's about to do, rather than inheriting a scoring error as if it were a settled fact.

If a proposed agent doesn't clear one of these three, it isn't solving anything. It's decoration.

## Running ClaimGuard's numbers

`agent_decision_calculator.py`, in this folder's `src/`, checks all of this directly rather than asking you to take the argument's word for it.

```python
parallel_case = DecisionInputs(
    exceeds_single_context_window=False,
    has_independent_parallelizable_subtasks=True,
    speedup_worth_coordination_cost=True,
    needs_failure_isolation=False,
)
should_use_multi_agent(parallel_case)
# -> (True, "parallel workers: subtasks are independent and the speedup earns the cost")
```

That's intake, fraud-risk, and policy-verification. Now the relationship that actually matters:

```python
sequential_case = DecisionInputs(
    exceeds_single_context_window=False,
    has_independent_parallelizable_subtasks=False,
    speedup_worth_coordination_cost=False,
    needs_failure_isolation=True,
)
should_use_multi_agent(sequential_case)
# -> (True, "isolated agents: one agent's failure must not cascade into another's work")
```

Fraud-risk feeding payment-processing clears the bar for a completely different reason than the first three agents did. It isn't about speed. It's about making sure a fraud-scoring bug can never directly authorize a payout — which is a real, describable financial-services failure mode, not an abstraction. Two agents, same yes/no verdict, opposite justification. Collapsing that distinction into one generic "multi-agent good" answer would erase the actual design decision.

<image src="file-upload://3a7c633a-e23a-81ee-b47b-00b237128858"></image>

One more test worth running: a proposed sixth agent, a "claim summarizer" that just reformats what intake already produced.

```python
unnecessary_case = DecisionInputs(
    exceeds_single_context_window=False,
    has_independent_parallelizable_subtasks=True,
    speedup_worth_coordination_cost=False,
    needs_failure_isolation=False,
)
should_use_multi_agent(unnecessary_case)
# -> (False, "stay single-agent - add tools, not agents")
```

Looks parallelizable on a whiteboard. Isn't, once the actual question — is the speedup worth the coordination cost — gets asked honestly. Most agents that never should have been built pass the first test and fail the second, quietly, because nobody asked it.

## Five agents, ten possible links, five real ones

ClaimGuard uses five of its ten mathematically possible links: the claim router's dispatch to each of the three parallel agents, and the fraud-risk-to-payment-processing relationship. The other five pairs — intake talking directly to policy-verification, fraud-risk talking directly to intake, and so on — were never going to exist, because nothing in this design needs them to. That's not a limitation. Building all ten links because the math allows them would be adding coordination cost for connections nobody asked for.

The fraud-risk-to-payment-processing link deserves more attention than the other four for a specific reason: it's the one point in the system where a design mistake has financial and regulatory consequences, not just an inconvenient bug. The next four articles in this series stay anchored to exactly this relationship — control and communication design, pattern choice, authorization, and failure prevention — because a system with real financial stakes is where these questions stop being academic.

## What this means for the design in front of you

Name each relationship in your own system separately before naming the system as a whole. A system that's mostly parallel with one sequential, isolation-driven exception is not the same design as five agents talking freely to each other, even if both diagrams have five boxes. The label you'd put on an architecture diagram is not the design decision. The answers to these three questions, asked per relationship, are.

If your own system has a relationship where a mistake carries real cost — money, a legal obligation, a customer's data — that relationship is the one to interrogate first, before the ones that are merely convenient to diagram. ClaimGuard's fraud-risk-to-payment link earns that scrutiny for a specific reason: everything downstream of it is harder to undo than everything upstream. Your own system almost certainly has an equivalent, even if it isn't moving money.

The next article in this series stays with ClaimGuard and asks what happens once a relationship has cleared this bar: who controls sequencing, where does state actually live, and how does information move between the fraud-risk agent and the one downstream of it that has the authority to act on real financial consequences.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Design Multi-Agent Systems

1. **Multi-agent or overkill? A decision framework before you add a second agent** *(this article)*
2. The coordination primitives: control, state, and communication — a vendor-neutral model — not yet published
3. The four canonical orchestration patterns, and how to actually choose one — not yet published
4. Designing the trust boundary: authorization between agents that isn't an afterthought — not yet published
5. Preventing the MAST failure modes by design, not by autopsy — not yet published
6. Observability and evaluation for multi-agent systems: what to actually measure — not yet published
7. Shared-resource contention: when your agents fight over the same database row — not yet published
8. Putting it together: designing a production multi-agent system end to end — not yet published

## References

1. When to use multi-agent systems (and when not to), Anthropic
   https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them
2. Fundamentals of AI Agents (companion series) — Article 01: What actually makes something an agent?
