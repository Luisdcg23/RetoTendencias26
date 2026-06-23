from dataclasses import dataclass
from typing import Dict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from .signers import _b64decode, _b64encode

try:
    from pqcrypto.sign import ml_dsa_65
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent.
    ml_dsa_65 = None


PQ_DOMAIN = b"pqlicense-demo-ml-dsa-slot:"


@dataclass(frozen=True)
class PostQuantumKeyPair:
    algorithm: str
    key_id: str
    private_key: str
    public_key: str


class PostQuantumSignatureProvider:
    """Safe adapter boundary for future ML-DSA/Falcon/SPHINCS+ replacement.

    The demo implementation uses Ed25519 with a separate key and domain
    separation only so the full licensing flow is testable without an optional
    PQC dependency. Replace this class with a real ML-DSA provider in production.
    """

    default_key_id = "pq-local-demo"

    def __init__(self):
        self.uses_real_pqc = ml_dsa_65 is not None
        self.algorithm = "ML-DSA-65" if self.uses_real_pqc else "ML-DSA-65-DEMO"

    def generate_key_pair(self, key_id: str = default_key_id) -> PostQuantumKeyPair:
        if self.uses_real_pqc:
            public_key, private_key = ml_dsa_65.generate_keypair()
            return PostQuantumKeyPair(
                algorithm=self.algorithm,
                key_id=key_id,
                private_key=_b64encode(private_key),
                public_key=_b64encode(public_key),
            )

        private_key = Ed25519PrivateKey.generate()
        return PostQuantumKeyPair(
            algorithm=self.algorithm,
            key_id=key_id,
            private_key=_b64encode(
                private_key.private_bytes(
                    encoding=Encoding.Raw,
                    format=PrivateFormat.Raw,
                    encryption_algorithm=NoEncryption(),
                )
            ),
            public_key=_b64encode(
                private_key.public_key().public_bytes(
                    encoding=Encoding.Raw,
                    format=PublicFormat.Raw,
                )
            ),
        )

    def sign(self, payload: bytes, private_key: str) -> str:
        if self.uses_real_pqc:
            return _b64encode(ml_dsa_65.sign(_b64decode(private_key), payload))
        return _b64encode(Ed25519PrivateKey.from_private_bytes(_b64decode(private_key)).sign(PQ_DOMAIN + payload))

    def verify(self, payload: bytes, signature: str, public_key: str) -> bool:
        if self.uses_real_pqc:
            try:
                return bool(ml_dsa_65.verify(_b64decode(public_key), payload, _b64decode(signature)))
            except (ValueError, TypeError):
                return False
        try:
            Ed25519PublicKey.from_public_bytes(_b64decode(public_key)).verify(
                _b64decode(signature),
                PQ_DOMAIN + payload,
            )
            return True
        except (InvalidSignature, ValueError):
            return False

    def signature_dict(self, key_id: str, value: str) -> Dict[str, str]:
        return {"algorithm": self.algorithm, "key_id": key_id, "value": value}
