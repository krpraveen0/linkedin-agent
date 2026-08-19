from burr.core import action, State, ApplicationBuilder

@action(reads=["turn"], writes=["turn"])     # only "turn" is declared
def take_turn(state: State) -> State:
    return state.update(turn=state["turn"] + 1, log="tick")   # also writes "log"

app = (ApplicationBuilder().with_actions(take_turn=take_turn)
       .with_transitions().with_state(turn=0).with_entrypoint("take_turn").build())
_, _, s = app.step()
print("declared writes: ['turn']")
print("keys after step:", [k for k in sorted(s.keys()) if not k.startswith('__')])
print("undeclared 'log' persisted:", "log" in s.keys(), "->", s["log"])
