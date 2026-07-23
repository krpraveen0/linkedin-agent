"""
Article 04, part 2: the fix for Part 1's failure - a persistent
memory store that survives across sessions. Anthropic's own agent
tooling calls this exactly what it is: a way to "store and retrieve
information across conversations in files you control."

Part 3, further down: the OTHER conflation - relying on persistent
memory for something that was always just current-conversation
context, and having that fail too.
"""

import sys
sys.path.insert(0, ".")
from context_only_agent import ConversationState
from dataclasses import dataclass, field


@dataclass
class PersistentMemory:
    """Survives across sessions - a real key-value store, a file, a
    database row. Here, a plain dict standing in for any of those."""
    facts: dict[str, str] = field(default_factory=dict)


def run_agent_with_persistent_memory(sessions: list[list[str]], memory: PersistentMemory) -> list[str]:
    responses = []
    for session_messages in sessions:
        state = ConversationState()  # still fresh per session - that's fine
        for msg in session_messages:
            state.messages.append(msg)
            if "my name is" in msg.lower():
                idx = msg.lower().index("my name is") + len("my name is")
                name = msg[idx:].strip()
                memory.facts["name"] = name  # THIS is what actually persists
            if "what is my name" in msg.lower():
                if "name" in memory.facts:
                    responses.append(f"Your name is {memory.facts['name']}")
                else:
                    responses.append("I don't know your name")
    return responses


# --- Part 3: the OTHER conflation - over-relying on persistent memory ---

def run_memory_only_agent(messages: list[str], memory: PersistentMemory) -> list[str]:
    """A DIFFERENT mistake: checking ONLY persistent memory, never the
    current conversation, even for something said moments ago in the
    same session."""
    responses = []
    for msg in messages:
        if "i like" in msg.lower():
            pass  # not the kind of fact this system persists - and it
                  # shouldn't have to be, it was JUST said
        if "what did i just say i like" in msg.lower():
            if "liked_thing" in memory.facts:
                responses.append(f"You said you like {memory.facts['liked_thing']}")
            else:
                responses.append("I don't know - nothing about that is in memory")
    return responses


if __name__ == "__main__":
    print("--- Part 2: persistent memory fixes the cross-session failure ---")
    memory = PersistentMemory()
    session_1 = ["my name is Alex", "thanks for the help"]
    session_2 = ["what is my name?"]
    responses = run_agent_with_persistent_memory([session_1, session_2], memory)
    print("Session 1: user says 'my name is Alex'")
    print("Session 2 (a NEW conversation): user asks 'what is my name?'")
    print(f"  response: {responses[0]!r}\n")

    print("--- Part 3: the OTHER conflation - memory-only, no context check ---")
    memory_2 = PersistentMemory()
    same_session = ["I like pizza", "what did I just say I like?"]
    responses = run_memory_only_agent(same_session, memory_2)
    print("Same conversation, same session: 'I like pizza' then immediately")
    print("'what did I just say I like?'")
    print(f"  response: {responses[0]!r}")
    print("  -> failed on something said ONE message ago, because this agent")
    print("     only ever checks persistent memory and never looks at the")
    print("     actual conversation it's already holding in context.")
