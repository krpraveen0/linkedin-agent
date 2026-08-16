"""Experiment 2: the trigger you configure is not the trigger you get.

Both frameworks decide *when* to compact using an estimator, not a tokenizer.
LangChain defaults to `count_tokens_approximately`; Agent Framework defaults
to `CharacterEstimatorTokenizer` (len // 4). This measures the error against
two real subword tokenizers, and shows why "count non-ASCII text correctly
during compaction" (agent-framework #7124) was a bug worth fixing.

Ground truth note: tiktoken downloads its vocabulary at runtime, which is not
available in a sealed environment. We use the two BPE/SentencePiece models
that ship *inside* the `blingfire` wheel instead:

  * gpt2.bin              - GPT-2 byte-level BPE, 50k vocab (small, older)
  * xlm_roberta_base.bin  - XLM-R SentencePiece, 250k multilingual vocab

They bracket the behaviour of a production tokenizer: a modern large vocab
handles non-Latin scripts better than GPT-2 but still far worse than English.
"""

import json
import os

import blingfire as bf
from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately

from agent_framework import Content, Message
from agent_framework._compaction import CharacterEstimatorTokenizer, _serialize_message

_BF_DIR = os.path.dirname(bf.__file__)
GPT2 = bf.load_model(os.path.join(_BF_DIR, "gpt2.bin"))
XLMR = bf.load_model(os.path.join(_BF_DIR, "xlm_roberta_base.bin"))


def ntok(handle, text: str) -> int:
    """Count real subword tokens (ids array is zero-padded)."""
    ids = bf.text_to_ids(handle, text, max(64, len(text) * 4), 0)
    return int((ids != 0).sum())


SAMPLES = {
    "english prose": (
        "The agent retrieved the flight options and compared them against the "
        "user's stated budget before proposing an itinerary for the trip."
    ),
    "japanese prose": (
        "エージェントはフライトの選択肢を取得し、ユーザーが指定した予算と比較して"
        "から、旅行の日程を提案しました。"
    ),
    "hindi prose": (
        "एजेंट ने उड़ान विकल्प प्राप्त किए और उपयोगकर्ता के बताए गए बजट से तुलना "
        "करने के बाद यात्रा का कार्यक्रम प्रस्तावित किया।"
    ),
    "json tool result": json.dumps(
        {"flights": [{"id": "AI101", "price": 421.5, "stops": 0} for _ in range(6)]}
    ),
}


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def raw_text_estimates() -> None:
    rule("1. Estimator error against two real tokenizers")
    print(f"  {'sample':<18}{'chars':>6}{'gpt2':>7}{'xlmr':>7}"
          f"{'lc_approx':>11}{'vs gpt2':>9}{'maf //4':>9}{'vs gpt2':>9}")
    print("  " + "-" * 76)
    for name, text in SAMPLES.items():
        g, x = ntok(GPT2, text), ntok(XLMR, text)
        lc = count_tokens_approximately([HumanMessage(content=text)])
        maf = CharacterEstimatorTokenizer().count_tokens(text)
        print(f"  {name:<18}{len(text):>6}{g:>7}{x:>7}{lc:>11}"
              f"{(lc - g) / g * 100:>+8.0f}%{maf:>9}{(maf - g) / g * 100:>+8.0f}%")

    print("\n  chars-per-token actually observed:")
    for name, text in SAMPLES.items():
        print(f"    {name:<18} gpt2 {len(text) / ntok(GPT2, text):>5.2f}"
              f"    xlm-r {len(text) / ntok(XLMR, text):>5.2f}"
              f"    (both estimators assume ~4.00)")


def ensure_ascii_effect() -> None:
    rule("2. Why ensure_ascii matters (agent-framework #7124, python-1.12.0)")
    print("  Agent Framework token-counts a JSON serialization of the message.")
    print("  With ensure_ascii=True each non-ASCII char becomes a 6-char \\uXXXX escape.\n")
    print(f"  {'sample':<18}{'gpt2 true':>11}{'ensure_ascii=False':>20}"
          f"{'ensure_ascii=True':>19}{'inflation':>11}")
    print("  " + "-" * 78)
    for name, text in SAMPLES.items():
        msg = Message(role="user", contents=[Content.from_text(text)], message_id="m1")
        shipped = _serialize_message(msg)  # ensure_ascii=False, as shipped in 1.14.0

        payload = {
            "role": msg.role,
            "message_id": msg.message_id,
            "contents": [c.to_dict(exclude_none=True) for c in msg.contents],
        }
        for c in payload["contents"]:
            c.pop("raw_representation", None)
            c.pop("items", None)
        legacy = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)

        tk = CharacterEstimatorTokenizer()
        n_new, n_old = tk.count_tokens(shipped), tk.count_tokens(legacy)
        print(f"  {name:<18}{ntok(GPT2, text):>11}{n_new:>20}{n_old:>19}"
              f"{(n_old - n_new) / n_new * 100:>+10.0f}%")


def trigger_drift() -> None:
    rule("3. What the error does to a 100,000-token trigger")
    print("  A message is repeated until each counter first reports >= 100,000")
    print("  tokens. 'real' is what the tokenizer says the model would see then.\n")

    for name in ("english prose", "japanese prose", "hindi prose"):
        text = SAMPLES[name]
        true_per = ntok(GPT2, text)
        lc_per = count_tokens_approximately([HumanMessage(content=text)])
        maf_per = CharacterEstimatorTokenizer().count_tokens(
            _serialize_message(
                Message(role="user", contents=[Content.from_text(text)], message_id="m")
            )
        )
        lc_n = -(-100_000 // lc_per)
        maf_n = -(-100_000 // maf_per)
        print(f"  [{name}]  gpt2={true_per}  lc_approx={lc_per}  maf={maf_per} per copy")
        print(f"    LangChain fires at {lc_n:>5} copies -> real {lc_n * true_per:>8,} tok "
              f"({lc_n * true_per / 100_000:>5.2f}x the configured trigger)")
        print(f"    AgentFwk  fires at {maf_n:>5} copies -> real {maf_n * true_per:>8,} tok "
              f"({maf_n * true_per / 100_000:>5.2f}x the configured trigger)")
        print()


def main() -> None:
    raw_text_estimates()
    ensure_ascii_effect()
    trigger_drift()
    bf.free_model(GPT2)
    bf.free_model(XLMR)


if __name__ == "__main__":
    main()
