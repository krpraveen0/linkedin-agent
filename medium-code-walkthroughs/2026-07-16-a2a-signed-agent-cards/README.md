# A2A v1.0 signed Agent Cards — code walkthrough

Companion code for the article *"Before Your Agent Trusts a Stranger: How A2A
v1.0 Signs Agent Cards"* (`article.md` in this folder).

A single, fully offline, deterministic script that builds a real A2A
`AgentCard`, signs it with the official `a2a-sdk` signing helpers, verifies the
signature, then tampers with the agent's endpoint URL and shows verification
fail. No LLM, no network, no API key.

The script uses a **fixed Ed25519 key**. EdDSA signatures are deterministic
(RFC 8032), so the signature bytes — and therefore the printed output — are
identical on every run, which makes the result reproducible for fact-checking.

## Files

- `sign_agent_card.py` — build → sign → verify → tamper, using
  `a2a.utils.signing.create_agent_card_signer` / `create_signature_verifier`.
- `article.md` — the full article.
- `diagram1_signing_flow.svg`, `diagram2_jws_anatomy.svg` — the diagrams.

## Setup & run

```bash
python3 -m venv venv
./venv/bin/pip install "a2a-sdk[signing]" cryptography
./venv/bin/python sign_agent_card.py
```

The `[signing]` extra pulls in PyJWT, which the SDK's signing utilities require.

Verified on **a2a-sdk 1.1.0**, **PyJWT 2.13.0**, **cryptography 49.0.0**,
**Python 3.11.15**.

## Real captured output

```
== AgentCardSignature (the three JWS fields) ==
protected: eyJhbGciOiJFZERTQSIsImtpZCI6IndlYXRoZXIta2V5LTEiLCJ0eXAiOiJKT1NFIn0
signature: ZTUF0Gf7nkFz8jhHnymhPW0a…
protected (decoded): {"alg":"EdDSA","kid":"weather-key-1","typ":"JOSE"}

== Genuine card ==
verify(card): OK, signature valid

== Tampered card (endpoint URL swapped) ==
verify(tampered): rejected -> InvalidSignaturesError: No valid signature found
```

Changing one character of the endpoint URL invalidates the signature, because
that URL is part of the canonicalized payload the signature covers.

## A note on canonicalization

The SDK's `a2a.utils.signing._canonicalize_agent_card` docstring cites RFC 8785
(JCS), but the implementation is `json.dumps(..., separators=(",", ":"),
sort_keys=True)` after removing the `signatures` field and empty values. For
ASCII-only cards this matches JCS; for non-ASCII text it diverges (Python
escapes `é` to `\u00e9` and sorts by code point, while strict JCS keeps the
literal character and sorts by UTF-16 code units). Worth knowing if you verify
cards across SDK implementations.
