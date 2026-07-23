"""
Article 04, part 1: an agent that only has context-window state - the
current conversation's messages - and nothing that survives once that
conversation ends. This is the common mistake: treating "the
conversation so far" as if it were memory.
"""

from dataclasses import dataclass, field


@dataclass
class ConversationState:
    """Context-window state: exists only for the current session.
    A fresh instance of this gets created every time a session starts."""
    messages: list[str] = field(default_factory=list)


def run_context_only_agent(sessions: list[list[str]]) -> list[str]:
    """Each session gets a FRESH ConversationState. Nothing persists
    between them - simulating separate conversations, the way a new
    chat session or a new API call with no shared state actually works."""
    responses = []
    for session_messages in sessions:
        state = ConversationState()  # fresh every session - the bug
        for msg in session_messages:
            state.messages.append(msg)
            if "my name is" in msg.lower():
                pass  # noted in this session's messages, nowhere else
            if "what is my name" in msg.lower():
                found = None
                for m in state.messages:
                    if "my name is" in m.lower():
                        idx = m.lower().index("my name is") + len("my name is")
                        found = m[idx:].strip()
                if found:
                    responses.append(f"Your name is {found}")
                else:
                    responses.append("I don't know your name")
    return responses


if __name__ == "__main__":
    session_1 = ["my name is Alex", "thanks for the help"]
    session_2 = ["what is my name?"]

    responses = run_context_only_agent([session_1, session_2])
    print("Session 1: user says 'my name is Alex'")
    print("Session 2 (a NEW conversation): user asks 'what is my name?'")
    print(f"  response: {responses[0]!r}")
