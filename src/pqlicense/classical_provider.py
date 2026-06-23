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


@dataclass(frozen=True)
class SignatureKeyPair:
    algorithm: str
    key_id: str
    private_key: str
    public_key: str


class ClassicalSignatureProvider:
    algorithm = "Ed25519"
    default_key_id = "classic-local-demo"

    def generate_key_pair(self, key_id: str = default_key_id) -> SignatureKeyPair:
        private_key = Ed25519PrivateKey.generate()
        return SignatureKeyPair(
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
        return _b64encode(Ed25519PrivateKey.from_private_bytes(_b64decode(private_key)).sign(payload))

    def verify(self, payload: bytes, signature: str, public_key: str) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(_b64decode(public_key)).verify(_b64decode(signature), payload)
            return True
        except (InvalidSignature, ValueError):
            return False

    def signature_dict(self, key_id: str, value: str) -> Dict[str, str]:
        return {"algorithm": self.algorithm, "key_id": key_id, "value": value}
