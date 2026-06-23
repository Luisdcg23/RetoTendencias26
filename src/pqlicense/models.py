from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


SignatureMode = Literal["classical_only", "post_quantum_only", "hybrid"]

CLASSICAL_ONLY: SignatureMode = "classical_only"
POST_QUANTUM_ONLY: SignatureMode = "post_quantum_only"
HYBRID: SignatureMode = "hybrid"
SUPPORTED_SIGNATURE_MODES = {CLASSICAL_ONLY, POST_QUANTUM_ONLY, HYBRID}


@dataclass(frozen=True)
class SignatureVerification:
    classical_signature: bool
    post_quantum_signature: bool
    required_mode: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classical_signature": self.classical_signature,
            "post_quantum_signature": self.post_quantum_signature,
            "required_mode": self.required_mode,
        }


@dataclass(frozen=True)
class ValidationResult:
    status: str
    redirect_url: str
    details: str = ""
    valid: bool = False
    reason: str = ""
    error_redirect_url: str = ""
    verification: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "status": self.status,
            "reason": self.reason or self.status,
            "redirect_url": self.redirect_url,
            "error_redirect_url": self.error_redirect_url,
            "details": self.details,
            "verification": self.verification,
        }


def normalize_signature_mode(value: Optional[str]) -> Optional[str]:
    if value is None:
        return HYBRID
    normalized = str(value).strip()
    if normalized in SUPPORTED_SIGNATURE_MODES:
        return normalized
    return None
