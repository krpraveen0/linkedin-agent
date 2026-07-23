# Putting it together: designing a production multi-agent system end to end

*No new concepts in this one - seven articles' worth of decisions, applied to one real relationship in one real system, in the order those decisions actually get made. If you have only read this article, the other seven are where each individual claim gets earned. If you have read all seven, this is where you watch them compose.*

## The system, one more time, briefly

DevPulse: a developer-productivity daemon with five pieces - a supervisor, an inbox-triage agent, a file-classifier agent, a calendar and focus-planning agent, and a workspace provisioner. Across this series, one relationship inside that system did more teaching than any other: the file classifier writes a spec to a shared folder, and the workspace provisioner reads it later and acts on it - cloning a repository, spinning up containers.

That one relationship touched every article in this series. Article 01 asked whether it justified being multi-agent at all. Article 02 named it a blackboard. Article 03 named it the one genuinely sequential link in an otherwise hybrid system. Article 04 found a confused-deputy risk in it. Article 05 found spec, handoff, and verification gaps in it. Article 06 found a trace-propagation gap in it. Article 07 found a resource-contention risk one step downstream of it. Seven articles, one relationship, seven different questions - which is itself the point this capstone exists to make concrete: a single real relationship in a real system is where every one of these concerns actually lives at once, not in seven separate systems built to illustrate seven separate ideas.

<image src="file-upload://3a6c633a-e23a-816f-864a-00b2dc4f1443"></image>

*One ticket, seven gates, in the order the decisions actually get made - executed end to end in this article's src/, not narrated.*

## Walking PAY-402 through all seven gates

`capstone_pipeline.py`, in this folder's `src/`, runs a real ticket - PAY-402 - through every gate, back to back, and prints the result of each one as it happens.

**Gate 1 (Article 01):** is this relationship multi-agent for a real reason? Run it through the three-question framework and the honest answer is not the reassuring one. It fails the parallel test - the provisioner genuinely depends on the classifier's completed output, which is not what "independent, parallelizable subtasks" means. Article 01's actual finding here was a caution, not a green light: multi-agent variants tested on genuinely sequential tasks degraded performance 39 to 70% in Article 03's own research, and the n(n−1)/2 coordination-cost model from Article 01 was never an argument that more links are automatically bad - it was an argument for knowing exactly which links exist before adding one. This relationship proceeds anyway, because classification and provisioning are genuinely different tool surfaces that one agent cannot cheaply hold at once - but it proceeds having actually asked the question, not by default.

**Gate 2 (Article 02):** control, state, and communication, named separately rather than inherited from a framework's tutorial defaults. Centralized control - the supervisor is still the thing dispatching work. Shared, blackboard-style state - the spec file, not a message. Filesystem communication, not a direct call. Naming these three independently is what let Article 02 discover the blackboard was there at all, instead of calling the whole thing "a handoff" and moving on - and it is worth remembering that pattern traces back five decades, to HEARSAY-II's own blackboard architecture, not to anything specific to LLM agents.

**Gate 3 (Article 03):** which of the four canonical patterns, honestly. Sequential, specifically, nested inside DevPulse's overall hierarchical structure - Article 03's own conclusion that DevPulse as a whole is a hybrid, not one pure pattern, and that forcing a single label onto it would have hidden exactly the trade-off this capstone is walking through.

**Gate 4 (Article 04):** does the provisioner's authority to run Docker come from its own grant, or from trusting a file the classifier wrote? `capstone_pipeline.py` checks this directly - the provisioner's capability is verified against its own independently-issued grant, never inherited from the classifier's. This is the confused-deputy prevention from Article 04 running as code rather than asserted as a principle, and the underlying failure it prevents is not novel to this series or to AI - Norm Hardy named it in 1988, watching a compiler at a real company overwrite a real billing file because nobody checked whether the requester actually had authority over the path it asked for.

**Gate 5 (Article 05):** does the spec actually name a completion criterion, and does the handoff actually carry the context the provisioner needs - ticket ID, urgency, requesting party, and (this is where Article 06 connects back into Article 05) a trace ID? Both checks pass for PAY-402. They do not always. See below.

**Gate 6 (Article 06):** does the trace stay connected across the one hop in this system that was never a direct call? Because the handoff context carried a trace ID - the exact mechanism Article 06 built its entire argument around - the classifier's span and the provisioner's span share one trace, reconstructable from a single ID instead of two disconnected stories correlated by guessing at timestamps.

**Gate 7 (Article 07):** does allocating a port for this ticket's container survive a second ticket racing for the same resource at the same moment? The atomic conditional UPDATE from Article 07 claims port 5432 in one statement, with no gap for another ticket to land in.

Run the whole thing, and the output is not seven separate demos stitched together after the fact. It is one ticket, resolved:

```
DECISION 1 (Article 01) - sequential dependency, not parallel - proceed with caution
DECISION 2 (Article 02) - centralized control, shared-blackboard state, filesystem communication
DECISION 3 (Article 03) - sequential (nested inside DevPulse's overall hierarchical/hybrid design)
DECISION 4 (Article 04) - provisioner's own capability permits exec:docker: True
DECISION 5 (Article 05) - spec: valid / handoff: complete
DECISION 6 (Article 06) - trace connected: True
DECISION 7 (Article 07) - allocated port: 5432
VERIFICATION - passed=True, evidence='docker ps confirms container is running on port 5432'
```

## Proving the gates matter, not just that they pass

A pipeline that only ever shows green checkmarks proves nothing except that the happy path was tested. `capstone_pipeline.py` runs a second ticket, PAY-403, through the identical pipeline with exactly one thing removed: the handoff context is missing its trace ID.

```
--- Same ticket, one deliberate omission: no trace_id in the handoff ---
  spec: valid
  handoff: BLOCKED - handoff missing: {'trace_id'}
  pipeline stops here - Decisions 6 and 7 never run for this ticket,
  because the gate that should have caught this actually did.
```

This is the entire argument of this series compressed into one output. The gate at Decision 5 exists specifically to prevent Decision 6 from ever running on broken input. A system without that gate would have proceeded straight into Decision 6 with an incomplete handoff, and the trace-connectivity check would have quietly reported the exact failure Article 06 described - a split trace, discovered later, correlated by guessing.

## The compressed version, for a system that is not DevPulse

Strip away this series' one running example and the sequence of questions generalizes to any two agents with a real relationship between them:

1. Does this relationship justify being multi-agent at all, by one of three specific reasons - context limits, worthwhile parallelism, or genuine failure isolation - not by default? A relationship that fails all three is not a design decision yet.
2. Named separately: who controls sequencing, where does state live, how does information actually move? Answering these together, as one bundled "architecture," is how a framework's tutorial defaults quietly become a design nobody actually chose.
3. Which of the four patterns does this specific relationship actually match, and does forcing one label onto the whole system hide a relationship that does not fit it? Most real systems are hybrids; insisting on one clean label is usually where the hiding happens.
4. When the downstream agent acts, is its authority its own, independently granted, or inherited from whoever handed it a file? If the honest answer is "whatever the upstream agent's output implies," that is a confused-deputy candidate whether or not it has caused a problem yet.
5. Would an ambiguous spec, an incomplete handoff, or an unverified completion pass silently, or does something actually reject it? A gate that has never rejected anything has never actually been tested against the failure it exists to catch.
6. If this relationship crosses anything other than a direct call, does trace context survive the crossing, or does the observability tooling quietly show two disconnected stories? The crossing itself is the tell - a shared file, a queue, a webhook, anything asynchronous.
7. If two instances of this same relationship can run concurrently, does the shared resource get claimed atomically, or does a read-then-write gap exist for a second instance to land in? The absence of a reported collision is not evidence the gap is not there.

Seven questions, not seven separate systems to build. Most relationships in a real system will answer several of them the same way - DevPulse's three parallel agents needed Article 04's capability discipline just as much as the classifier-provisioner pair did, even though their control/state/communication answers from Article 02 were completely different. The questions do not change. The answers do, per relationship, and that is the actual design work.

## What made this series different, said plainly

Worth naming the pattern this series followed eight times in a row, since it was a deliberate choice repeated deliberately, not an accident of style. Every article in this series fetched a primary source directly rather than trusting a secondary summary - Anthropic's own numbers, Google Research's own study, the actual 1988 paper behind the confused deputy, HEARSAY-II's real history, OpenTelemetry's actual span names, the actual papers on multi-agent concurrency control. Every mechanism this series claimed worked was executed before the claim was written down, not described from a place of confidence that it probably would. Every diagram was built to pay off a specific claim in the surrounding text, not decorate a section that would have read fine without one. And every gap this series claimed to close against existing content was checked against what existing content actually says, not assumed.

None of that is a novel research methodology. It is closer to just refusing the shortcuts that produce most of what currently exists on this topic - the taxonomy restated without a decision procedure, the guardrail described without a check that fails on a real bad input, the pattern named without the code that would prove it works. The gap most competing content leaves is not a lack of awareness that these things matter. It is a lack of anything a reader could run themselves and watch either pass or fail.

## What this series did not cover, said plainly

A synthesis is a good place for an honest accounting of scope, not just a victory lap. This series ran one illustrative case study - disclosed as such from Article 01 onward - through a specific, narrow slice of what a production multi-agent system actually has to handle. Left out, on purpose:

Decentralized, peer-negotiation architectures never got a worked example, because DevPulse never needed one - every relationship in this system had a clear owner. A real decentralized system, with genuine debate rounds and no fixed hierarchy, would need its own capstone; the seven questions above still apply to it, but the answers to Gate 2 and Gate 3 would look nothing like DevPulse's.

Heterogeneous agent teams built from different model providers, with different context windows and different tool-calling conventions, never came up. The coordination principles do not change based on which model sits behind an agent, but the practical friction of Gate 5's spec validation absolutely does when one agent's idea of a complete spec does not match another's.

Human-in-the-loop escalation - when a gate should stop and hand a decision to a person rather than retry or fail automatically - was implicit throughout this series (every "not auto-approved" moment in the actual production of these articles was exactly this pattern) but never got its own worked example. A real system needs an explicit answer for which of these seven gates, on failure, pages a human instead of just logging an error.

Cost and reliability at real production scale - hundreds of concurrent tickets rather than two, geographic distribution, actual on-call incidents - is a different kind of article than this series set out to write. Article 06 and Article 07 gave you the primitives. Operating them at scale, for months, under real load, is where the primitives get tested for real, and no illustrative case study can substitute for that.

## What this looks like Monday morning, for the last time

Pick one real relationship in your own system - not the whole system, one relationship, the way this entire series stayed anchored to one. Run it through the seven questions above, honestly, including the ones with uncomfortable answers. Most real systems will fail at least one gate on the first honest pass, the same way a large share of MAST's observed failures trace back to exactly these categories going unchecked.

Then build the check, not just the fix. A fix without a gate that would have caught the next occurrence of the same problem is a patch. A gate is what turns "we fixed it" into "it cannot happen the same way again" - which has been the actual thesis of this series since Article 01's first framework: not whether multi-agent systems are good or bad, but whether each specific decision inside one was made on purpose, and checked.

That distinction - made on purpose, and checked, versus inherited by default and never examined - is the one idea underneath all seven articles' different vocabulary. Article 01 called it earning a coordination cost. Article 04 called it independently granted authority. Article 07 called it an atomic check instead of a hopeful read. Different words, in every case, for the same underlying discipline: a system where every relationship can answer, specifically, why it exists and what would catch it failing.

DevPulse was never the point. It was the vehicle for making seven abstract questions concrete enough to run. The system worth building is whichever one is sitting in front of you right now, with its own five agents or fifty, its own one blackboard or several, its own single relationship most likely to fail next because nobody has looked at it closely yet. Go look at it.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Design Multi-Agent Systems

1. Multi-agent or overkill? A decision framework before you add a second agent — not yet published
2. The coordination primitives: control, state, and communication — a vendor-neutral model — not yet published
3. The four canonical orchestration patterns, and how to actually choose one — not yet published
4. Designing the trust boundary: authorization between agents that isn't an afterthought — not yet published
5. Preventing the MAST failure modes by design, not by autopsy — not yet published
6. Observability and evaluation for multi-agent systems: what to actually measure — not yet published
7. Shared-resource contention: when your agents fight over the same database row — not yet published
8. **Putting it together: designing a production multi-agent system end to end** *(this article)*

## Further reading (the primary sources behind this series, in one place)

1. When to use multi-agent systems (and when not to), Anthropic
   https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them
2. Kim, Y. and Liu, X. Towards a Science of Scaling Agent Systems, Google Research, 2026
   https://arxiv.org/abs/2512.08296
3. Hardy, N. The Confused Deputy, ACM SIGOPS, 1988
4. Cemri, M. et al. Why Do Multi-Agent LLM Systems Fail?, 2025
   https://arxiv.org/abs/2503.13657
5. Semantic Conventions for Generative AI Systems, OpenTelemetry
   https://opentelemetry.io/docs/specs/semconv/gen-ai/
6. CoAgent: Concurrency Control for Multi-Agent Systems, 2026
   https://arxiv.org/abs/2606.15376
