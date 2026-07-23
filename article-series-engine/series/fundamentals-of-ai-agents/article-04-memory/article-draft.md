# Two things people call "memory," and why conflating them breaks agents

*Every guide to AI agents lists "memory" as one capability. It isn't one thing - it's two genuinely different engineering problems with two different failure modes, and this article shows both of them actually failing, not just describes the difference.*

## Step 0: What you'll need

Python 3.9+. No API key, same as every article so far in this series.

## Step 1: The two things, named precisely

**Context-window state** is what's in the current conversation - the messages exchanged so far, held in memory only for as long as that conversation is active. **Persistent memory** is what's meant to survive after the conversation ends - a fact stored somewhere that a future, entirely separate session can retrieve. Anthropic's own agent tooling names this distinction directly: their memory tool exists specifically to "store and retrieve information across conversations in files you control" - a deliberate, separate mechanism from whatever's already sitting in the current context.

These are not two flavors of the same thing. They're two different engineering problems. Context-window state is free - it's already there, no extra infrastructure needed, and it disappears on its own when the session ends. Persistent memory costs something to build - a file, a database, a key-value store - and it has to be deliberately written to and deliberately read from, because nothing about a fresh session knows anything happened before it.

Worth naming why this gets conflated so often: many frameworks now auto-manage context windows for you - trimming old messages, summarizing what's been said, keeping the conversation coherent as it grows. That's genuinely useful, and it's easy to mistake for "the framework handles memory now." It doesn't. It handles the free thing well. It says nothing about whether a fact from this conversation will be available in the next one, which is a completely separate question the framework was never answering.

## Step 2: Watch context-only memory actually fail

Save this as `context_only_agent.py`:

```python
@dataclass
class ConversationState:
    messages: list[str] = field(default_factory=list)

def run_context_only_agent(sessions: list[list[str]]) -> list[str]:
    responses = []
    for session_messages in sessions:
        state = ConversationState()  # fresh every session - the bug
        for msg in session_messages:
            state.messages.append(msg)
            if "what is my name" in msg.lower():
                found = None
                for m in state.messages:
                    if "my name is" in m.lower():
                        idx = m.lower().index("my name is") + len("my name is")
                        found = m[idx:].strip()
                responses.append(f"Your name is {found}" if found else "I don't know your name")
    return responses
```

Run two sessions - a real conversation, then a brand new one:

```python
session_1 = ["my name is Alex", "thanks for the help"]
session_2 = ["what is my name?"]
run_context_only_agent([session_1, session_2])
```

```
Session 1: user says 'my name is Alex'
Session 2 (a NEW conversation): user asks 'what is my name?'
  response: "I don't know your name"
```

Nothing's actually broken here, in the sense that the code works exactly as written. `ConversationState` is scoped to one session, on purpose, and Session 2 gets a fresh one. The bug is conceptual, not a crash: treating "the conversation so far" as if it were the same thing as "what the agent remembers," when it never was.

## Step 3: Fix it with a real persistent store

Save this as `persistent_memory_agent.py`. The whole fix is one new piece of state that lives *outside* any single session:

```python
@dataclass
class PersistentMemory:
    facts: dict[str, str] = field(default_factory=dict)

def run_agent_with_persistent_memory(sessions, memory: PersistentMemory) -> list[str]:
    responses = []
    for session_messages in sessions:
        state = ConversationState()  # still fresh per session - that's fine
        for msg in session_messages:
            state.messages.append(msg)
            if "my name is" in msg.lower():
                idx = msg.lower().index("my name is") + len("my name is")
                memory.facts["name"] = msg[idx:].strip()  # THIS is what actually persists
            if "what is my name" in msg.lower():
                if "name" in memory.facts:
                    responses.append(f"Your name is {memory.facts['name']}")
                else:
                    responses.append("I don't know your name")
    return responses
```

Run the exact same two sessions through this version:

```
Session 1: user says 'my name is Alex'
Session 2 (a NEW conversation): user asks 'what is my name?'
  response: 'Your name is Alex'
```

Same fresh `ConversationState` every session - that part didn't need to change. What changed is that one specific fact got written to something that actually outlives the session it was learned in.

Worth a brief, honest aside: the first version of this extraction logic lowercased the whole message before pulling the name out, which meant "Alex" came back as "alex" - a real bug, caught by actually running the code and reading the output, not a planted teaching example. Fixed by finding the split point in the lowercased string but slicing the original, case-preserved message. Small, but it's exactly the kind of thing that only shows up when you run what you wrote instead of trusting that it should work.

<image src="file-upload://3a6c633a-e23a-81ce-b77b-00b26e972c03"></image>

## Step 4: The mistake in the other direction

This is the part almost nobody shows, because it looks less obviously wrong: over-relying on persistent memory, and never checking the conversation that's already sitting right there. It's also worth naming the cost angle, since it's the reason this direction of the mistake matters beyond correctness: a persistent-memory lookup is a real operation - a file read, a database round trip, sometimes a network call - while checking the current conversation costs nothing, because it's already loaded. An agent that reaches for the expensive path by default, even for things the free path already answers, is paying a real, avoidable tax on every single turn.

```python
def run_memory_only_agent(messages: list[str], memory: PersistentMemory) -> list[str]:
    responses = []
    for msg in messages:
        if "what did i just say i like" in msg.lower():
            if "liked_thing" in memory.facts:
                responses.append(f"You said you like {memory.facts['liked_thing']}")
            else:
                responses.append("I don't know - nothing about that is in memory")
    return responses
```

Run it on one conversation, one session, with the relevant fact said just one message earlier:

```
Same conversation, same session: 'I like pizza' then immediately
'what did I just say I like?'
  response: "I don't know - nothing about that is in memory"
  -> failed on something said ONE message ago, because this agent
     only ever checks persistent memory and never looks at the
     actual conversation it's already holding in context.
```

This agent has a real, working persistent-memory system. It just never checks the free thing sitting right next to it - the current conversation - before reaching for the expensive thing. The fix is the opposite instinct from Step 3: check context first, for anything the current conversation can already answer, and reach for persistent memory only for what genuinely needs to survive past this session.

## Step 5: The actual rule

One sentence covers both failures: **check context for anything within the current conversation, check persistent memory for anything that needs to survive past it, and never assume one of them covers what the other is for.** Step 2's agent assumed context-window state would survive - it doesn't. Step 4's agent assumed persistent memory was the only place worth checking - it isn't, for things said moments ago.

If you're deciding whether a given fact needs persistent storage at all, one honest question does most of the work: will this specific piece of information ever be needed in a session that hasn't started yet? If yes, it needs to be written somewhere that outlives the current conversation. If no, the conversation itself already has it, for free, and building a persistence layer for it is solving a problem that doesn't exist yet.

A few concrete examples, since the line is easier to see with real cases than with the abstract question alone. A user's name, their stated preferences, a decision they made last week that a support agent needs to honor today - these need persistence, because by definition the session where they'll matter again hasn't started yet. What the user just asked two messages ago, a number they mentioned earlier in the same request, the specific wording of the question they're currently asking - none of that needs persistence, because the conversation holding it hasn't ended. Writing it to a database anyway isn't wrong exactly, but it is a real cost paid for information the agent already had for free, and it's the same mistake Step 4 demonstrated, just committed proactively instead of discovered as a failure.

## What this looks like today

Look at whatever agent you're building or already have running, and ask two separate questions, not one: what does it actually remember across sessions, versus what does it merely have access to for the length of one conversation? If you can't answer that cleanly - if "memory" is one undifferentiated concept in your own head about your own system - that's exactly the gap this article closes, and it's worth drawing the line explicitly before it causes the kind of silent failure Step 2 showed.

Test both directions on purpose, the way this article did. Start a genuinely new session and ask your agent something it should only know if a fact actually persisted - if the answer comes back wrong or blank, that's Step 2's failure, live in your own system. Then, within one live conversation, ask about something said moments earlier and watch whether your agent answers from context immediately or goes looking somewhere else first - if it hesitates or fails, that's Step 4's failure, and it's usually a one-line fix once you've actually seen it happen.

The next article in this series moves from what an agent remembers to how it decides what to do next: reactive, one step at a time, versus planning the whole sequence upfront - and a real decision procedure for which one actually fits a given task.

---

*This article was researched and drafted with AI assistance, then reviewed and edited by Praveen Kumar.*

## Series: Fundamentals of AI Agents

1. What actually makes something an agent? A testable definition, not an analogy — not yet published
2. The agent loop, built from scratch: observe, decide, act, and actually stop — not yet published
3. Tool use, for real: the mechanism behind "agents can take actions" — not yet published
4. **Two things people call "memory," and why conflating them breaks agents** *(this article)*
5. Reactive vs. planning agents, and how to actually choose — not yet published
6. Stopping conditions: why "cap max_steps" is the least of it — not yet published
7. Evaluating a single agent: what to actually measure before you add a second one — not yet published
8. Building one real agent end to end, and what comes after it: multi-agent systems — not yet published

## References

1. Tool use with Claude (memory tool), Claude Platform Docs
   https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
