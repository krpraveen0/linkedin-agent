# The coordination primitives: control, state, and communication — a vendor-neutral model

*Every multi-agent orchestration guide reaches for a specific framework within the first paragraph. This one does not, on purpose — because the underlying model is the same whether you build it in Google's ADK, LangGraph, or a Python daemon with no framework at all.*

## Three questions, not one framework

Article 01 established when a second agent earns its coordination cost, using a five-agent developer-productivity system as the running example: a supervisor, an inbox-triage agent, a file-classifier agent, a calendar and focus-planning agent, and a workspace provisioner. This article assumes that decision is already made, and asks the next one: once you have decided on multi-agent, how do the agents actually coordinate?

Strip away any specific vendor SDK and the answer reduces to three independent questions.

**Control**: who decides sequencing? A supervisor that plans and dispatches, or agents that negotiate directly with no single owner of the plan?

**State**: where does information live between steps? Local to each agent, exchanged only through messages, or in a shared store every relevant agent can read and write?

**Communication**: how does information actually move? Structured, addressed messages between named agents. A shared workspace agents read and write without addressing each other. Or, if everything runs in one process, a direct function call.

[DIAGRAM: coordination-primitives-three-axes-model — see this folder's README for the source link]

Most pattern guides collapse these three into one vendor's default answer and call it "the" architecture. A recent orchestration survey makes the actual structure explicit: an orchestration layer's execution and control component decides sequencing, a separate state and knowledge management component tracks checkpoints and context, and communication protocols operationalize the exchange between them. Three separable concerns, not one monolithic choice.

## Why this needs to be vendor-neutral before it needs to be anything else

Here is the trap: pick a framework first, and the framework's defaults quietly become "the" model in your head. Google's Agent Development Kit ships strong opinions about supervisor-worker control. LangGraph ships strong opinions about state as a shared graph. Neither opinion is wrong, but neither is the only option, and a design built by inheriting a framework's defaults is a design nobody actually chose.

The three axes are independent of each other and independent of any framework. You can have centralized control with local state (a supervisor dispatching to workers that never share data). You can have decentralized control with shared state (peer agents that plan for themselves but coordinate through a common store). Naming the axes separately is what lets you actually choose, instead of inheriting a bundle of defaults from whichever SDK's tutorial you read first.

Here is what that inheritance looks like in practice. A team follows a framework's quick-start guide, gets a working supervisor-worker system in an afternoon, and ships it. Six months later someone asks why a specific agent cannot negotiate directly with another instead of routing every exchange back through the supervisor. The honest answer is usually that nobody chose centralized control on purpose — the tutorial's default became the architecture, and the actual task never got evaluated against the other two options on that axis.

## Applying the three axes to Article 01's case study

Back to the developer-productivity system from Article 01: a supervisor, an inbox-triage agent, a file-classifier agent, a calendar and focus-planning agent, and a workspace provisioner.

**Control, first.** Article 01 already established this is hub-and-spoke: a supervisor dispatches to each functional agent. That answers the control axis outright. Centralized.

**State, next — and here is where it gets more interesting than Article 01 showed.** Three of the four agents (inbox, classifier, calendar) keep entirely local state. Nothing they track needs to be visible to the others. But the fourth relationship — the classifier-to-provisioner handoff — is not just a sequential dependency, as Article 01 described it. Look again at what actually happens: the classifier writes a file to a specific project folder, and the provisioner reads from that folder later. Neither agent addresses the other directly. There is no message. There is a shared point — the filesystem — that one agent writes and another reads.

That is not a handoff. That is a blackboard.

The term is not a metaphor invented for this article. Blackboard systems are one of the older coordination patterns in AI, tracing back to HEARSAY-II, a speech-understanding system developed at Carnegie Mellon between 1971 and 1976. Its architecture had three parts: independent modules with specific knowledge, a shared data structure they read and wrote without addressing each other directly, and a control mechanism deciding whose turn it was to act. That is close to exactly what the classifier-provisioner relationship is doing, five decades and a very different problem domain later. The pattern survives because the underlying coordination problem — several specialists that need to see each other's partial results without a rigid message protocol between every pair — has not gone away.

**Communication, last.** Since the whole system runs as a single local daemon, three of the four relationships are direct function calls: the supervisor calls each agent in-process, no network involved. The fourth relationship, the classifier-provisioner pair, communicates through the filesystem rather than a call or a message — a small, single-purpose blackboard rather than the classic multi-agent version where many agents read and write a shared workspace with no supervisor at all.

Run the actual classification through code, not description. `coordination_model_classifier.py`, in this folder's `src/`, implements exactly this:

```python
inbox_pattern = classify(CoordinationChoice(
    control=Control.CENTRALIZED,
    state=State.LOCAL,
    communication=Communication.DIRECT_CALL,
))
# -> "Supervisor-dispatched local agents"

handoff_pattern = classify(CoordinationChoice(
    control=Control.CENTRALIZED,
    state=State.SHARED,
    communication=Communication.BLACKBOARD,
))
# -> "Supervisor-mediated blackboard"
```

Same supervisor. Same overall control model. Two different coordination patterns living inside the same system, because state and communication are separate axes from control, not derived from it.

None of the combinations above is the correct one in general. A blackboard costs almost nothing to read and write when everyone shares a filesystem, and becomes a real consistency problem the moment two agents might write at the same time. Direct calls are free until you need one of the agents to survive a restart independently of the others. There is no combination that wins every case, which is exactly why naming the three axes separately matters more than memorizing a single "best practice" architecture.

## What changes when agents are not on one machine

DevPulse runs as a single local daemon, so direct function calls are free. Distributed deployments do not have that luxury — a lead agent and its workers might run as separate services, possibly on different machines entirely, and cannot share memory or call each other's functions directly.

This is where structured protocols earn their place. The Model Context Protocol standardizes how an agent reaches external tools and data. The Agent-to-Agent protocol standardizes how agents negotiate, delegate, and exchange results with each other, whether that exchange goes directly between two agents or gets mediated through an orchestrator. Neither protocol changes which of the three axes you need to decide — control, state, and communication are still three separate questions. What changes is which concrete mechanism answers the communication question once direct function calls are no longer an option.

You do not need A2A to build DevPulse. You very likely do need it, or something equivalent, the moment your agents stop sharing a process.

Shared state gets more expensive at exactly the same moment. On one machine, a shared filesystem or an in-memory store is nearly free to read and write — the blackboard pattern costs almost nothing when everyone shares physical memory. Across a network, that same shared store becomes a real system to build and keep consistent: what happens when two agents write at the same time, what happens when the store is briefly unreachable, whether a stale read is acceptable or a correctness problem. None of that changes which axis you are choosing on. It changes how much the choice costs once you have made it.

## The mistake this framework is built to catch

Run a design through the classifier and an inconsistent-looking combination shows up: decentralized control paired with direct function calls.

```python
unusual = classify(CoordinationChoice(
    control=Control.DECENTRALIZED,
    state=State.LOCAL,
    communication=Communication.DIRECT_CALL,
))
# -> flagged: "Decentralized control with direct function calls is unusual -
#    direct calls usually imply one process deciding the order."
```

This combination is not impossible, but it usually signals a design that has not actually decided who owns the plan. Direct function calls are the communication mechanism of a single process making its own decisions in order — which is, in practice, centralized control wearing decentralized language. If you catch your own design landing here, the honest fix is not a code change. It is going back and answering the control question you skipped.

## DevPulse's blackboard is not the classic blackboard

Worth being precise about one more distinction, since the term gets used loosely. DevPulse's classifier-provisioner relationship is a supervisor-mediated blackboard: a shared store, but a supervisor still decides when the provisioner runs relative to the classifier. The classic blackboard architecture that HEARSAY-II introduced has no supervisor at all — independent knowledge sources watch the shared store and act opportunistically whenever their trigger condition appears, with a separate control mechanism arbitrating turns rather than a central planner dispatching work.

`coordination_model_classifier.py` distinguishes these as two different patterns, not one:

```python
supervised = classify(CoordinationChoice(
    control=Control.CENTRALIZED,
    state=State.SHARED,
    communication=Communication.BLACKBOARD,
))
# -> "Supervisor-mediated blackboard" (DevPulse's case)

classic = classify(CoordinationChoice(
    control=Control.DECENTRALIZED,
    state=State.SHARED,
    communication=Communication.BLACKBOARD,
))
# -> "Classic blackboard architecture" (coordination emerges from
#    the shared state itself, not from a supervisor's plan)
```

Same shared-state, same blackboard-style communication. Different control axis, and a genuinely different system to build and debug. Collapsing both into "we use a blackboard pattern" hides the one decision — who is actually in charge of sequencing — that determines whether you need a supervisor process at all.

## What this looks like Monday morning

Before you draw the next architecture diagram, answer the three questions separately, in this order: who decides sequencing, where does state live, how does information actually move. Do not let a framework's tutorial answer any of them for you by default.

If two parts of the same system land on different answers, like DevPulse's direct calls for three agents and a blackboard for the fourth, that is not a design flaw. It is what an honestly-examined system usually looks like. The flaw is not noticing it, and building as if the whole system had one uniform coordination style when it does not.

The next time you sketch an architecture diagram, do not label it with a framework's name and call the design decided. Answer control, state, and communication separately, out loud, for every relationship in the diagram — not just the ones that look interesting. The relationship you skip is usually the one that breaks first.

The next article in this series picks up from here: the four canonical orchestration patterns, and a decision procedure for choosing between them once control, state, and communication are already answered.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

*Part 2 of "Design Multi-Agent Systems." Previous: Multi-agent or overkill? Next: The four canonical orchestration patterns, and how to actually choose one.*

## References

1. When to use multi-agent systems (and when not to), Anthropic
   https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them
2. The Orchestration of Multi-Agent Systems: Architectures, Protocols, and Enterprise Adoption
   https://arxiv.org/abs/2601.13671
3. Model Context Protocol documentation
   https://modelcontextprotocol.io/docs/getting-started/intro
4. Agent2Agent (A2A) Protocol, The Linux Foundation
   https://a2a-protocol.org/latest/
