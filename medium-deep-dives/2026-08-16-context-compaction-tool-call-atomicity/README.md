# Context compaction: tool-call atomicity and token-accounting drift

Runnable code for the deep-dive article [`article.md`](./article.md).

Three experiments that measure what LangChain's `SummarizationMiddleware`,
Microsoft Agent Framework's `CompactionProvider` strategies, and
Anthropic-style context editing actually do to a tool-calling conversation
when they make it smaller.

Everything runs on CPU. No API keys, no network calls at runtime, no paid
services.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install langchain langgraph agent-framework-core openai-agents blingfire numpy
```

Exact versions used to produce every number below and in the article:

```
agent-framework-core      1.14.0
blingfire                 0.1.8
langchain                 1.3.15
langchain-core            1.5.5
langgraph                 1.2.11
numpy                     2.4.6
openai-agents             0.21.0
```

`blingfire` is used as the ground-truth tokenizer because it ships GPT-2 BPE
and XLM-RoBERTa SentencePiece models *inside the wheel*. `tiktoken` downloads
its vocabulary at runtime, which does not work in a sealed environment.

## Files

| File | What it does |
|---|---|
| `common.py` | Builds one tool-heavy conversation in both message dialects, plus the orphan/dangling validity checks |
| `exp1_pair_integrity.py` | Sweeps every `keep` value through both frameworks; measures overshoot and pair splitting |
| `exp2_token_accounting.py` | Compares the default estimators against two real tokenizers; measures trigger drift |
| `exp3_edge_cases.py` | Three failure paths: the forward-fallback, an impossible token budget, and in-place tool-result clearing |
| `figure-1-architectures.svg` | Diagram: three compaction designs on the same history |
| `figure-2-token-drift.svg` | Chart: estimator error by content type |

## Running

```bash
./venv/bin/python exp1_pair_integrity.py
./venv/bin/python exp2_token_accounting.py
./venv/bin/python exp3_edge_cases.py
```

All three exit 0 and write nothing to stderr.

## Captured output

### `exp1_pair_integrity.py`

```
========================================================================
1. LangChain SummarizationMiddleware._find_safe_cutoff
========================================================================
history length: 19 messages

  [ 0] System
  [ 1] Human
  [ 2] AI[tool_calls=['call-0-0']]
  [ 3] Tool[for=call-0-0]
  [ 4] AI
  [ 5] Human
  [ 6] AI[tool_calls=['call-1-0']]
  [ 7] Tool[for=call-1-0]
  [ 8] AI
  [ 9] Human
  [10] AI[tool_calls=['call-2-0', 'call-2-1', 'call-2-2']]
  [11] Tool[for=call-2-0]
  [12] Tool[for=call-2-1]
  [13] Tool[for=call-2-2]
  [14] AI
  [15] Human
  [16] AI[tool_calls=['call-3-0']]
  [17] Tool[for=call-3-0]
  [18] AI

  keep=N   cutoff   summarized   kept   overshoot   split-pair?
  --------------------------------------------------------------
      1       18           18      1          +0            no
      2       16           16      3          +1            no
      3       16           16      3          +0            no
      4       15           15      4          +0            no
      5       14           14      5          +0            no
      6       10           10      9          +3            no
      7       10           10      9          +2            no
      8       10           10      9          +1            no
      9       10           10      9          +0            no
     10        9            9     10          +0            no
     11        8            8     11          +0            no
     12        6            6     13          +1            no
     13        6            6     13          +0            no
     14        5            5     14          +0            no
     15        4            4     15          +0            no
     16        2            2     17          +1            no
     17        2            2     17          +0            no
     18        1            1     18          +0            no
     19        0            0     19          +0            no

========================================================================
2. Agent Framework SlidingWindowStrategy (group-based)
========================================================================
  keep_groups   kept msgs   dropped msgs   split-pair?   kept ids
  ----------------------------------------------------------------------------
            1           2             17            no   sys-0,final-3
            2           4             15            no   sys-0,ai-3,tm-3-0,final-3
            3           5             14            no   sys-0,h-3,ai-3,tm-3-0,final-3
            4           6             13            no   sys-0,final-2,h-3,ai-3,tm-3-0,final-3
            5          10              9            no   sys-0,ai-2,tm-2-0,tm-2-1,tm-2-2,final-2,h-3,ai-3,tm-3-0,final-3
            6          11              8            no   sys-0,h-2,ai-2,tm-2-0,tm-2-1,tm-2-2,final-2,h-3,ai-3,tm-3-0,final-3
            7          12              7            no   sys-0,final-1,h-2,ai-2,tm-2-0,tm-2-1,tm-2-2,final-2,h-3,ai-3,tm-3-0,final-3
            8          14              5            no   sys-0,ai-1,tm-1-0,final-1,h-2,ai-2,tm-2-0,tm-2-1,tm-2-2,final-2,h-3,ai-3,tm-3-0,final-3
            9          15              4            no   sys-0,h-1,ai-1,tm-1-0,final-1,h-2,ai-2,tm-2-0,tm-2-1,tm-2-2,final-2,h-3,ai-3,tm-3-0,final-3

========================================================================
3. How Agent Framework groups the same history
========================================================================
  group  0  kind=system         members=[sys-0]
  group  1  kind=user           members=[h-0]
  group  2  kind=tool_call      members=[ai-0, tm-0-0]
  group  3  kind=assistant_text members=[final-0]
  group  4  kind=user           members=[h-1]
  group  5  kind=tool_call      members=[ai-1, tm-1-0]
  group  6  kind=assistant_text members=[final-1]
  group  7  kind=user           members=[h-2]
  group  8  kind=tool_call      members=[ai-2, tm-2-0, tm-2-1, tm-2-2]
  group  9  kind=assistant_text members=[final-2]
  group 10  kind=user           members=[h-3]
  group 11  kind=tool_call      members=[ai-3, tm-3-0]
  group 12  kind=assistant_text members=[final-3]

  19 messages collapse into 13 atomic groups.
```

Key result: the invariant holds on every row (`split-pair? = no`), but asking
LangChain to keep 6 messages returns 9, because the cutoff snaps backward past
the three-way parallel tool call at index 10.

### `exp2_token_accounting.py`

```
==============================================================================
1. Estimator error against two real tokenizers
==============================================================================
  sample             chars   gpt2   xlmr  lc_approx  vs gpt2  maf //4  vs gpt2
  ----------------------------------------------------------------------------
  english prose        133     24     30         38     +58%       33     +38%
  japanese prose        52     79     31         17     -78%       13     -84%
  hindi prose          120    186     27         34     -82%       30     -84%
  json tool result     283    126    159         75     -40%       70     -44%

  chars-per-token actually observed:
    english prose      gpt2  5.54    xlm-r  4.43    (both estimators assume ~4.00)
    japanese prose     gpt2  0.66    xlm-r  1.68    (both estimators assume ~4.00)
    hindi prose        gpt2  0.65    xlm-r  4.44    (both estimators assume ~4.00)
    json tool result   gpt2  2.25    xlm-r  1.78    (both estimators assume ~4.00)

==============================================================================
2. Why ensure_ascii matters (agent-framework #7124, python-1.12.0)
==============================================================================
  Agent Framework token-counts a JSON serialization of the message.
  With ensure_ascii=True each non-ASCII char becomes a 6-char \uXXXX escape.

  sample              gpt2 true  ensure_ascii=False  ensure_ascii=True  inflation
  ------------------------------------------------------------------------------
  english prose              24                  60                 60        +0%
  japanese prose             79                  40                105      +162%
  hindi prose               186                  57                181      +218%
  json tool result          126                 110                110        +0%

==============================================================================
3. What the error does to a 100,000-token trigger
==============================================================================
  A message is repeated until each counter first reports >= 100,000
  tokens. 'real' is what the tokenizer says the model would see then.

  [english prose]  gpt2=24  lc_approx=38  maf=60 per copy
    LangChain fires at  2632 copies -> real   63,168 tok ( 0.63x the configured trigger)
    AgentFwk  fires at  1667 copies -> real   40,008 tok ( 0.40x the configured trigger)

  [japanese prose]  gpt2=79  lc_approx=17  maf=40 per copy
    LangChain fires at  5883 copies -> real  464,757 tok ( 4.65x the configured trigger)
    AgentFwk  fires at  2500 copies -> real  197,500 tok ( 1.98x the configured trigger)

  [hindi prose]  gpt2=186  lc_approx=34  maf=57 per copy
    LangChain fires at  2942 copies -> real  547,212 tok ( 5.47x the configured trigger)
    AgentFwk  fires at  1755 copies -> real  326,430 tok ( 3.26x the configured trigger)

```

Key result: both default estimators overcount English and undercount
non-Latin scripts. The two reference tokenizers disagree with each other by
6.9x on the Hindi sample, which is why a single correction factor cannot fix
this: the estimator does not know which tokenizer is downstream.

### `exp3_edge_cases.py`

```
==========================================================================
1. LangChain: what happens when the AIMessage is already gone
==========================================================================
  input history (an already-compacted conversation):
    [0] sys-0     System
    [1] sum-0     Human
    [2] tm-x-0    Tool[for=call-x-0]
    [3] tm-x-1    Tool[for=call-x-1]
    [4] final-x   AI
    [5] h-y       Human
    [6] ai-y      AI[tool_calls=['call-y-0']]
    [7] tm-y-0    Tool[for=call-y-0]
    [8] final-y   AI

  before compaction: dangling=[] orphaned=['call-x-0', 'call-x-1']
  -> the input is ALREADY invalid: two tool results with no tool call.

  keep=6: target=3 -> cutoff=4 ( forward), kept=5, dangling=[], orphaned=[]
  keep=7: target=2 -> cutoff=4 ( forward), kept=5, dangling=[], orphaned=[]
  keep=8: target=1 -> cutoff=1 (   exact), kept=8, dangling=[], orphaned=['call-x-0', 'call-x-1']

  keep=7 targets index 2 (a ToolMessage with no matching AIMessage).
  The backward scan finds nothing, so the fallback advances FORWARD
  past both tool results - dropping them rather than orphaning them.

==========================================================================
2. Agent Framework: an impossible token budget is not an error
==========================================================================
  budget= 10000  start= 916 tok  end= 916 tok  kept=19 msgs  within budget    [system,user,assistant,tool,assistant,user,assistant,tool,assistant,user,assistant,tool,tool,tool,assistant,user,assistant,tool,assistant]
  budget=   200  start= 916 tok  end= 177 tok  kept= 4 msgs  within budget    [system,assistant,tool,assistant]
  budget=    50  start= 916 tok  end=  34 tok  kept= 1 msgs  within budget    [assistant]
  budget=     5  start= 916 tok  end=  34 tok  kept= 1 msgs  OVER by 29       [assistant]
  budget=     1  start= 916 tok  end=  34 tok  kept= 1 msgs  OVER by 33       [assistant]

  _minimum_retained_group_ids() guarantees a non-empty projection,
  so the budget is best-effort: below a floor it is silently exceeded.

==========================================================================
3. Clearing tool results instead of dropping messages
==========================================================================
  messages : 19 -> 19  (structure untouched)
  tokens   : 444 -> 356 (20% reclaimed)
  dangling=[] orphaned=[]

    tm-0-0   cleared=True  content='[cleared]'
    tm-1-0   cleared=True  content='[cleared]'
    tm-2-0   cleared=True  content='[cleared]'
    tm-2-1   cleared=True  content='[cleared]'
    tm-2-2   cleared=False content="{'tool': 'get_weather', 'turn': 2, 'rows': 
    tm-3-0   cleared=False content="{'tool': 'search_flights', 'turn': 3, 'rows

  Every tool_call still has a matching result, so the request stays
  valid - but the model can no longer read what those tools returned.
```

Key results: LangChain's pair repair runs only at the seam, so an
already-orphaned tool result elsewhere in the retained window passes through
untouched (`keep=8`). Agent Framework's token budget is best-effort, because
`_minimum_retained_group_ids()` always keeps one group. Context editing
reclaims tokens with zero structural risk but tells the model nothing about
what it lost.

## Caveats

- Ground truth is GPT-2 BPE and XLM-R SentencePiece, not the exact tokenizer
  of any production model. The direction and mechanism of the error are the
  point; the exact magnitudes will differ per vocabulary.
- The fixtures use short synthetic tool payloads, so the 20% reclaim figure in
  experiment 3 is a floor. Real tool results are far larger relative to the
  surrounding messages.
- `SummarizationMiddleware` is exercised through `_find_safe_cutoff`, a private
  method, so the cutoff arithmetic can be measured without a live model. The
  summarization LLM call itself is not made.
