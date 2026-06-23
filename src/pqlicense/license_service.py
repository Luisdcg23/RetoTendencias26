from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from .crypto_service import CryptoService
from .models import HYBRID, normalize_signature_mode
from .time_utils import utc_iso


class LicenseService:
    def __init__(self, keys, crypto_service: Optional[CryptoService] = None):
        self.keys = keys
        self.crypto_service = crypto_service or CryptoService()

    def generate_license(
        self,
        *,
        license_id: str,
        customer_id: str,
        product_id: str,
        plan: str,
        issued_at: datetime,
        expires_at: datetime,
        allowed_devices: int,
        device_fingerprint: str,
        features: Iterable[str],
        validation_mode: str = HYBRID,
        revocation_epoch: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        mode = normalize_signature_mode(validation_mode)
        if mode is None:
            raise ValueError(f"unsupported validation mode: {validation_mode}")
        payload = {
            "license_id": license_id,
            "customer_id": customer_id,
            "product_id": product_id,
            "plan": plan,
            "issued_at": utc_iso(issued_at),
            "expires_at": utc_iso(expires_at),
            "allowed_devices": int(allowed_devices),
            "device_fingerprint": device_fingerprint or "",
            "features": sorted(features),
            "validation_mode": mode,
            "revocation_epoch": int(revocation_epoch),
            "metadata": metadata or {},
        }
        return {
            "schema": "pqlicense/v2",
            "payload": payload,
            "signatures": self.crypto_service.sign_payload(payload, self.keys),
            "public_key_ids": {
                "classical": self.keys.classic_key_id,
                "post_quantum": self.keys.pq_key_id,
            },
        }
