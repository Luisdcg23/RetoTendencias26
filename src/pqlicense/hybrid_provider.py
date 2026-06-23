from typing import Any, Dict

from .canonical import canonical_json_bytes
from .models import CLASSICAL_ONLY, HYBRID, POST_QUANTUM_ONLY, SignatureVerification, normalize_signature_mode


class HybridSignatureProvider:
    def __init__(self, classical_provider, post_quantum_provider):
        self.classical_provider = classical_provider
        self.post_quantum_provider = post_quantum_provider

    def sign(self, payload: Dict[str, Any], keys) -> Dict[str, Dict[str, str]]:
        message = canonical_json_bytes(payload)
        return {
            "classical": self.classical_provider.signature_dict(
                keys.classic_key_id,
                self.classical_provider.sign(message, keys.classic_private_key),
            ),
            "post_quantum": self.post_quantum_provider.signature_dict(
                keys.pq_key_id,
                self.post_quantum_provider.sign(message, keys.pq_private_key),
            ),
        }

    def verify(self, payload: Dict[str, Any], signatures: Dict[str, Any], public_keys, mode: str) -> SignatureVerification:
        required_mode = normalize_signature_mode(mode)
        if required_mode is None:
            return SignatureVerification(False, False, str(mode))

        message = canonical_json_bytes(payload)
        classical_signature = signatures.get("classical") or signatures.get("classic") or {}
        pq_signature = signatures.get("post_quantum") or {}
        classical_ok = self.classical_provider.verify(
            message,
            str(classical_signature.get("value", "")),
            public_keys.classic_public_key,
        )
        pq_ok = self.post_quantum_provider.verify(
            message,
            str(pq_signature.get("value", "")),
            public_keys.pq_public_key,
        )
        return SignatureVerification(classical_ok, pq_ok, required_mode)

    def is_valid_for_mode(self, verification: SignatureVerification) -> bool:
        if verification.required_mode == CLASSICAL_ONLY:
            return verification.classical_signature
        if verification.required_mode == POST_QUANTUM_ONLY:
            return verification.post_quantum_signature
        if verification.required_mode == HYBRID:
            return verification.classical_signature and verification.post_quantum_signature
        return False
