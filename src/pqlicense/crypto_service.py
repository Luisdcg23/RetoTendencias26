from .classical_provider import ClassicalSignatureProvider
from .hybrid_provider import HybridSignatureProvider
from .post_quantum_provider import PostQuantumSignatureProvider


class CryptoService:
    def __init__(self, classical_provider=None, post_quantum_provider=None):
        self.classical_provider = classical_provider or ClassicalSignatureProvider()
        self.post_quantum_provider = post_quantum_provider or PostQuantumSignatureProvider()
        self.hybrid_provider = HybridSignatureProvider(self.classical_provider, self.post_quantum_provider)

    def sign_payload(self, payload, keys):
        return self.hybrid_provider.sign(payload, keys)

    def verify_payload(self, payload, signatures, public_keys, mode):
        verification = self.hybrid_provider.verify(payload, signatures, public_keys, mode)
        return verification, self.hybrid_provider.is_valid_for_mode(verification)
