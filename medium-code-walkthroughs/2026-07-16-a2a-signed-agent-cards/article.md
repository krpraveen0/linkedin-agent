# Before Your Agent Trusts a Stranger: How A2A v1.0 Signs Agent Cards

Two agents that have never met need a way to find each other. In the [Agent2Agent (A2A) protocol](https://a2a-protocol.org/latest/specification/), that handshake starts with an **Agent Card**: a small JSON document, usually served at `/.well-known/agent-card.json`, that advertises an agent's name, version, skills, and the URL where it actually listens. Your agent fetches that card and, from then on, sends work to whatever endpoint it lists.

That is a nice discovery story with an obvious hole. If anything between you and the card can rewrite one field, it can point the `url` at a host it controls, and your agent will happily send its tasks (and whatever data rides along) to a stranger. A plain JSON file carries no proof of who wrote it.

A2A version 1.0, which reached stable in [April 2026](https://a2a-protocol.org/latest/whats-new-v1/), addresses this with **signed Agent Cards**. This article looks at exactly what that signature is, verifies its shape against the installed SDK rather than the marketing, and runs a signing-and-tampering demo end to end with real output.

## The trust gap in agent discovery

An Agent Card is deliberately public and easy to fetch. That is what makes discovery work, and it is also what makes the card a tempting thing to tamper with. The fields that matter most for an attacker are the ones that route traffic: the interface `url`, the security scheme, the provider identity. Change the endpoint and you have a redirection attack that the calling agent has no built-in way to notice.

Transport security (HTTPS) protects the card in flight from the host that serves it, but it says nothing about whether that host is the legitimate author of the agent, whether the card was assembled correctly upstream, or whether a registry that re-serves cards altered one. A2A's answer is to move trust from the transport to the document: sign the card itself, so any consumer can check the content independently of how it arrived.

## What v1.0 actually added

The v1.0 release bundled several trust-oriented features, including signed Agent Cards, an [agent directory, and the Agent Payments Protocol](https://a2a-protocol.org/latest/whats-new-v1/). Signing is the relevant piece here. The [specification](https://github.com/a2aproject/A2A/blob/main/docs/specification.md) states plainly that "signatures use the JSON Web Signature (JWS) format as defined in RFC 7515," and that "the `signatures` field itself MUST be excluded from the content being signed to avoid circular dependencies."

So an Agent Card gains an optional `signatures` array. Each entry is a detached JWS over the rest of the card. The word "detached" matters: the signed payload is not embedded in the signature blob. It *is* the card you already downloaded, minus its own `signatures` field. A verifier reconstructs the payload from the card in front of it, so any edit to any signed field breaks the check.

## The signature is just JWS, and you can prove it

It is easy to take "it's JWS" on faith. Instead, look at the type the SDK actually ships. Installing the official Python SDK (`pip install a2a-sdk`, version 1.1.0 at the time of writing) and inspecting the generated `AgentCardSignature` type shows three fields and nothing more:

```python
from a2a.types import AgentCardSignature
print([f.name for f in AgentCardSignature.DESCRIPTOR.fields])
# ['protected', 'signature', 'header']
```

Those are precisely the members of a [RFC 7515 JWS in JSON serialization](https://datatracker.ietf.org/doc/html/rfc7515): a base64url-encoded `protected` header, a base64url-encoded `signature`, and an optional unprotected `header`. One detail worth noting from this inspection: in the 1.0 line the SDK's types are **protobuf-generated**, not Pydantic models. The SDK migrated to a proto-first design with ProtoJSON as the canonical serialization, per the [v1.0 migration guide](https://github.com/a2aproject/a2a-python/blob/main/docs/migrations/v1_0/README.md), which is why `AgentCardSignature` reports a protobuf `DESCRIPTOR` instead of Pydantic fields.

The protected header follows JOSE conventions: an `alg` (the signing algorithm), a `kid` (which key signed this), `typ` set to `"JOSE"`, and optionally a `jku` pointing at the JSON Web Key Set where the public key lives. That `kid`/`jku` pair is how a verifier finds the right key without you hardcoding it.

## Try it yourself

The SDK ships the signing logic in `a2a.utils.signing`, gated behind an optional extra (`pip install "a2a-sdk[signing]"`, which pulls in PyJWT). The demo below builds a real `AgentCard`, signs it, verifies it, then tampers with the endpoint URL and watches verification fail. Everything runs offline with no LLM and no API key.

To keep the output reproducible, it uses a fixed Ed25519 key. EdDSA signatures are deterministic by [RFC 8032](https://datatracker.ietf.org/doc/html/rfc8032), so the signature bytes are identical on every run, and `EdDSA` is a valid JWS algorithm under [RFC 8037](https://datatracker.ietf.org/doc/html/rfc8037). Most production cards use `ES256`, whose ECDSA signatures are randomized (a fresh value per signing), so their output would differ every run.

Building and signing the card:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from a2a.types import AgentCard, AgentCapabilities, AgentInterface, AgentSkill
from a2a.utils.signing import create_agent_card_signer

priv = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))  # fixed seed
card = AgentCard(
    name="weather-agent", version="1.4.0",
    description="Answers weather questions for other agents.",
    capabilities=AgentCapabilities(streaming=True),
    supported_interfaces=[AgentInterface(
        url="https://weather.example.com/a2a", protocol_binding="JSONRPC")],
    skills=[AgentSkill(id="forecast", name="forecast",
                       description="Return a forecast for a city.", tags=["weather"])],
)
sign = create_agent_card_signer(
    signing_key=priv,
    protected_header={"kid": "weather-key-1", "alg": "EdDSA", "typ": "JOSE"})
card = sign(card)             # appends an AgentCardSignature
sig = card.signatures[0]
```

Verifying the genuine card, then a tampered copy:

```python
from a2a.utils.signing import create_signature_verifier, InvalidSignaturesError

verify = create_signature_verifier(
    key_provider=lambda kid, jku: priv.public_key(),  # real clients fetch via jku
    algorithms=["EdDSA"],                             # pinned alg blocks confusion
)
verify(card)                                          # genuine card: passes

card.supported_interfaces[0].url = "https://evil.example.net/a2a"  # redirect attack
try:
    verify(card)
except InvalidSignaturesError as e:
    print("rejected:", e)
```

The real captured output:

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

Changing a single character of the endpoint URL is enough to invalidate the signature, because that URL is part of the canonicalized payload the signature covers. The verifier never has to know what a "good" URL looks like; it only has to know the issuer's public key.

Two design choices in the SDK are worth copying. The verifier takes a `key_provider(kid, jku)` callback rather than a raw key, so key lookup (fetching a JWKS over HTTPS, checking a trust store) is your decision, not the library's. And it takes an explicit `algorithms` allow-list, which is the standard defense against JWS algorithm-confusion attacks where an attacker swaps the `alg` header to something weaker or to `none`.

## A wrinkle: the payload canonicalization

Signing over a JSON document only works if the signer and every verifier serialize that document to the exact same bytes. The A2A spec calls for [RFC 8785 JSON Canonicalization Scheme (JCS)](https://datatracker.ietf.org/doc/html/rfc8785) with default-valued protobuf fields removed.

Reading the installed SDK's `_canonicalize_agent_card`, its docstring says RFC 8785, but the implementation is `json.dumps(cleaned_dict, separators=(",", ":"), sort_keys=True)` after stripping the `signatures` field and empty values. For an all-ASCII agent card with no floating-point numbers, that produces the same bytes as JCS. For a card containing non-ASCII text the two diverge: Python's `json.dumps` escapes `é` to the ASCII sequence `\u00e9` and sorts keys by Unicode code point, while strict JCS emits the literal character and sorts by UTF-16 code units. That gap is invisible for typical English-language cards, and it can bite a card with localized descriptions verified by a stricter implementation in another language. If your agents exchange non-ASCII cards across SDKs, canonicalization is the first place to look when a valid signature is rejected.

## What signing does and does not buy you

A verified signature tells you the card's content has not changed since the holder of `weather-key-1` signed it. It does not, by itself, tell you that key belongs to the agent you think it does. That trust still comes from somewhere out of band: a key published at a domain you already trust, an entry in the A2A agent directory, or a certificate chain. Signing closes the tampering gap; it moves the hard question from "was this card modified?" to "do I trust this key?", which is a question you can answer once per issuer instead of once per fetch.

It also does nothing about the agent's runtime behavior. A correctly signed card can still front an agent that misbehaves after you connect. Card signing is an integrity control for discovery, and it pairs with, rather than replaces, the authentication and authorization on the agent's actual endpoints.

## Key Takeaways

- An A2A Agent Card is public JSON that routes your traffic; unsigned, any field (especially the endpoint `url`) can be silently rewritten in transit or by a registry.
- A2A v1.0 (April 2026) adds signed Agent Cards. Each `AgentCardSignature` is a detached JWS (RFC 7515) with exactly three fields: `protected`, `signature`, `header` — confirmed against the installed SDK type.
- The signed payload is the card minus its own `signatures` field, canonicalized; editing any covered field breaks verification, as the tampering demo shows.
- Verify with an explicit algorithm allow-list and a `kid`/`jku`-driven key lookup to avoid algorithm-confusion attacks and to keep key trust in your hands.
- The 1.1.0 SDK canonicalizes with `json.dumps(sort_keys=True)`, which matches RFC 8785 for ASCII cards but diverges on non-ASCII text — a real cross-implementation gotcha.
- Signing proves integrity, not identity: you still need an out-of-band reason to trust the signing key.

*Sources: [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/), [What's New in A2A v1.0](https://a2a-protocol.org/latest/whats-new-v1/) (April 2026), [A2A spec on GitHub](https://github.com/a2aproject/A2A/blob/main/docs/specification.md), [a2a-python v1.0 migration guide](https://github.com/a2aproject/a2a-python/blob/main/docs/migrations/v1_0/README.md), [a2a-sdk on PyPI](https://pypi.org/project/a2a-sdk/), [RFC 7515 (JWS)](https://datatracker.ietf.org/doc/html/rfc7515), [RFC 8785 (JCS)](https://datatracker.ietf.org/doc/html/rfc8785), [RFC 8037 (EdDSA in JOSE)](https://datatracker.ietf.org/doc/html/rfc8037). Verified against a2a-sdk 1.1.0, PyJWT 2.13.0, cryptography 49.0.0, Python 3.11.15.*
