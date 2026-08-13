"""
Block 1 — Prove, from the *installed* mem0 package, which prompt the default
add() path actually uses, and whether the classic ADD/UPDATE/DELETE reconciler
is still wired in. No LLM calls, no network — pure source inspection.
"""
import inspect
import mem0
from mem0.memory import main as memory_main
from mem0.configs import prompts

print("mem0 version:", mem0.__version__)

# What the default add() pipeline imports for extraction:
src = inspect.getsource(memory_main)
print("main.py imports ADDITIVE_EXTRACTION_PROMPT:",
      "ADDITIVE_EXTRACTION_PROMPT" in src)
print("main.py references DEFAULT_UPDATE_MEMORY_PROMPT:",
      "DEFAULT_UPDATE_MEMORY_PROMPT" in src)
print("main.py references get_update_memory_messages:",
      "get_update_memory_messages" in src)

# The classic reconciler prompt still ships in the package...
print("DEFAULT_UPDATE_MEMORY_PROMPT still defined in prompts.py:",
      hasattr(prompts, "DEFAULT_UPDATE_MEMORY_PROMPT"))

# ...but what does the prompt the pipeline DOES use tell the model to do?
role_line = prompts.ADDITIVE_EXTRACTION_PROMPT.split("Your sole operation is")[1]
print("Additive prompt mandate: Your sole operation is" + role_line.split(".")[0] + ".")
