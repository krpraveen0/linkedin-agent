"""
Sign and verify an A2A Agent Card with the official a2a-sdk (>=1.0) helpers.

Everything here is offline and deterministic: no LLM, no network, no API key.
We use a fixed Ed25519 key so the signature bytes are identical on every run
(EdDSA signatures are deterministic by RFC 8032), which makes the output
reproducible for fact-checking.
"""

import base64
import json

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from a2a.types import AgentCard, AgentCapabilities, AgentInterface, AgentSkill
from a2a.utils.signing import (
    create_agent_card_signer,
    create_signature_verifier,
    InvalidSignaturesError,
)

# ---- 1. A fixed issuer key (pinned; in production this lives behind a JWKS URL)
SEED = bytes(range(32))  # fixed 32-byte seed -> deterministic key & signature
priv = Ed25519PrivateKey.from_private_bytes(SEED)
pub = priv.public_key()


def build_card() -> AgentCard:
    return AgentCard(
        name="weather-agent",
        description="Answers weather questions for other agents.",
        version="1.4.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        supported_interfaces=[
            AgentInterface(
                url="https://weather.example.com/a2a",
                protocol_binding="JSONRPC",
            )
        ],
        skills=[
            AgentSkill(
                id="forecast",
                name="forecast",
                description="Return a forecast for a city.",
                tags=["weather"],
            )
        ],
    )


# ---- 2. Sign the card (the signer appends an AgentCardSignature)
signer = create_agent_card_signer(
    signing_key=priv,
    protected_header={"kid": "weather-key-1", "alg": "EdDSA", "typ": "JOSE"},
)
card = signer(build_card())
sig = card.signatures[0]

print("== AgentCardSignature (the three JWS fields) ==")
print("protected:", sig.protected)
print("signature:", sig.signature[:24] + "…")
decoded = base64.urlsafe_b64decode(sig.protected + "==").decode()
print("protected (decoded):", decoded)

# ---- 3. Verify with the issuer's public key (trusted key store)
verify = create_signature_verifier(
    key_provider=lambda kid, jku: pub,  # real clients fetch this from `jku`
    algorithms=["EdDSA"],               # pinned alg -> blocks alg-confusion
)
verify(card)
print("\n== Genuine card ==")
print("verify(card): OK, signature valid")

# ---- 4. Tamper: an attacker redirects the endpoint to their own host
card.supported_interfaces[0].url = "https://evil.example.net/a2a"
try:
    verify(card)
    print("verify(tampered): OK  <-- should not happen")
except InvalidSignaturesError as e:
    print("\n== Tampered card (endpoint URL swapped) ==")
    print(f"verify(tampered): rejected -> {type(e).__name__}: {e}")
