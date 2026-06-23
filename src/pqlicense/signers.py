import base64
from dataclasses import dataclass
from typing import Any, Dict

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

try:
    from pqcrypto.sign import ml_dsa_65
except ImportError:  # pragma: no cover - optional dependency fallback.
    ml_dsa_65 = None


CLASSIC_ALGORITHM = "Ed25519"
PQ_DEMO_ALGORITHM = "ML-DSA-65-DEMO"
PQ_REAL_ALGORITHM = "ML-DSA-65"
PQ_DOMAIN = b"pqlicense-demo-ml-dsa-slot:"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(frozen=True)
class PublicKeyBundle:
    classic_algorithm: str
    classic_public_key: str
    pq_algorithm: str
    pq_public_key: str

    @property
    def classic_key_id(self) -> str:
        return "classic-local-demo"

    @property
    def pq_key_id(self) -> str:
        return "pq-local-demo"

    def to_dict(self) -> Dict[str, str]:
        return {
            "classic_algorithm": self.classic_algorithm,
            "classic_public_key": self.classic_public_key,
            "pq_algorithm": self.pq_algorithm,
            "pq_public_key": self.pq_public_key,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "PublicKeyBundle":
        return cls(
            classic_algorithm=value["classic_algorithm"],
            classic_public_key=value["classic_public_key"],
            pq_algorithm=value["pq_algorithm"],
            pq_public_key=value["pq_public_key"],
        )


@dataclass(frozen=True)
class KeyBundle:
    classic_algorithm: str
    classic_private_key: str
    classic_public_key: str
    pq_algorithm: str
    pq_private_key: str
    pq_public_key: str

    @property
    def classic_key_id(self) -> str:
        return "classic-local-demo"

    @property
    def pq_key_id(self) -> str:
        return "pq-local-demo"

    def public_bundle(self) -> PublicKeyBundle:
        return PublicKeyBundle(
            classic_algorithm=self.classic_algorithm,
            classic_public_key=self.classic_public_key,
            pq_algorithm=self.pq_algorithm,
            pq_public_key=self.pq_public_key,
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "classic_algorithm": self.classic_algorithm,
            "classic_private_key": self.classic_private_key,
            "classic_public_key": self.classic_public_key,
            "pq_algorithm": self.pq_algorithm,
            "pq_private_key": self.pq_private_key,
            "pq_public_key": self.pq_public_key,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "KeyBundle":
        return cls(
            classic_algorithm=value["classic_algorithm"],
            classic_private_key=value["classic_private_key"],
            classic_public_key=value["classic_public_key"],
            pq_algorithm=value["pq_algorithm"],
            pq_private_key=value["pq_private_key"],
            pq_public_key=value["pq_public_key"],
        )


def _new_ed25519_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _private_key_to_b64(key: Ed25519PrivateKey) -> str:
    return _b64encode(
        key.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )
    )


def _public_key_to_b64(key: Ed25519PublicKey) -> str:
    return _b64encode(
        key.public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )
    )


def _private_key_from_b64(value: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_b64decode(value))


def _public_key_from_b64(value: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_b64decode(value))


def create_key_bundle() -> KeyBundle:
    classic = _new_ed25519_private_key()
    if ml_dsa_65 is not None:
        pq_public_key, pq_private_key = ml_dsa_65.generate_keypair()
        pq_algorithm = PQ_REAL_ALGORITHM
        pq_private = _b64encode(pq_private_key)
        pq_public = _b64encode(pq_public_key)
    else:
        pq_demo = _new_ed25519_private_key()
        pq_algorithm = PQ_DEMO_ALGORITHM
        pq_private = _private_key_to_b64(pq_demo)
        pq_public = _public_key_to_b64(pq_demo.public_key())
    return KeyBundle(
        classic_algorithm=CLASSIC_ALGORITHM,
        classic_private_key=_private_key_to_b64(classic),
        classic_public_key=_public_key_to_b64(classic.public_key()),
        pq_algorithm=pq_algorithm,
        pq_private_key=pq_private,
        pq_public_key=pq_public,
    )


def sign_classic(keys: KeyBundle, message: bytes) -> str:
    if keys.classic_algorithm != CLASSIC_ALGORITHM:
        raise ValueError(f"unsupported classical algorithm: {keys.classic_algorithm}")
    return _b64encode(_private_key_from_b64(keys.classic_private_key).sign(message))


def sign_pq_demo(keys: KeyBundle, message: bytes) -> str:
    if keys.pq_algorithm == PQ_REAL_ALGORITHM and ml_dsa_65 is not None:
        return _b64encode(ml_dsa_65.sign(_b64decode(keys.pq_private_key), message))
    if keys.pq_algorithm != PQ_DEMO_ALGORITHM:
        raise ValueError(f"unsupported PQ demo algorithm: {keys.pq_algorithm}")
    return _b64encode(_private_key_from_b64(keys.pq_private_key).sign(PQ_DOMAIN + message))


def verify_classic(public_keys: PublicKeyBundle, message: bytes, signature: str) -> bool:
    if public_keys.classic_algorithm != CLASSIC_ALGORITHM:
        return False
    try:
        _public_key_from_b64(public_keys.classic_public_key).verify(_b64decode(signature), message)
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_pq_demo(public_keys: PublicKeyBundle, message: bytes, signature: str) -> bool:
    if public_keys.pq_algorithm == PQ_REAL_ALGORITHM and ml_dsa_65 is not None:
        try:
            return bool(ml_dsa_65.verify(_b64decode(public_keys.pq_public_key), message, _b64decode(signature)))
        except (ValueError, TypeError):
            return False
    if public_keys.pq_algorithm != PQ_DEMO_ALGORITHM:
        return False
    try:
        _public_key_from_b64(public_keys.pq_public_key).verify(
            _b64decode(signature),
            PQ_DOMAIN + message,
        )
        return True
    except (InvalidSignature, ValueError):
        return False
