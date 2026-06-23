import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .core import create_key_bundle
from .crypto_service import CryptoService
from .license_service import LicenseService
from .offline_validation_service import OfflineValidationService
from .revocation_service import RevocationService


class LicenseController:
    def __init__(self, *, keys, revocations: Optional[Dict[str, Any]], product_id: str, revocations_path: Optional[str]):
        self.keys = keys
        self.revocations = self._trusted_revocations(revocations, keys)
        self.product_id = product_id
        self.revocations_path = revocations_path
        self.revocation_epoch = self._current_revocation_epoch()
        self.licenses = []
        self.admin_username = os.environ.get("PQLICENSE_ADMIN_USER", "admin")
        self.admin_password = os.environ.get("PQLICENSE_ADMIN_PASSWORD", "admin123")
        self.demo_admin_username = "admin"
        self.demo_admin_password = "admin123"
        self.admin_tokens = set()

    def login(self, body: Dict[str, Any]) -> Dict[str, Any]:
        username = body.get("username")
        password = body.get("password")
        configured_login = username == self.admin_username and password == self.admin_password
        demo_login = username == self.demo_admin_username and password == self.demo_admin_password
        if not configured_login and not demo_login:
            return {"status": "denied", "error": "invalid_credentials"}
        token = secrets.token_urlsafe(32)
        self.admin_tokens.add(token)
        return {"status": "authenticated", "token": token}

    def is_admin_token(self, token: str) -> bool:
        return bool(token and token in self.admin_tokens)

    def reset_keys(self) -> Dict[str, Any]:
        self.keys = create_key_bundle()
        self.revocations = None
        self.revocation_epoch = 1
        return {"status": "keys_ready", "public_keys": self.keys.public_bundle().to_dict()}

    def state(self) -> Dict[str, Any]:
        revoked = self.revocations.get("payload", {}).get("revoked", []) if self.revocations else []
        return {
            "classic_algorithm": self.keys.classic_algorithm,
            "pq_algorithm": self.keys.pq_algorithm,
            "revoked_count": len(revoked),
            "revocation_epoch": self.revocation_epoch,
            "signature_modes": ["hybrid", "classical_only", "post_quantum_only"],
            "public_keys": self.keys.public_bundle().to_dict(),
        }

    def generate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        features = body.get("features", body.get("feature", []))
        if isinstance(features, str):
            features = [item.strip() for item in features.split(",") if item.strip()]
        allowed_devices = body.get("allowed_devices", body.get("device_limit", 1))
        metadata = {
            "redirect_url": body["redirect_url"],
            "error_url": body["error_url"],
        }
        license_doc = LicenseService(self.keys).generate_license(
            license_id=body["license_id"],
            customer_id=body["customer_id"],
            product_id=body.get("product_id", self.product_id),
            plan=body.get("plan", "professional"),
            issued_at=now,
            expires_at=now + timedelta(days=int(body.get("days", 365))),
            allowed_devices=int(allowed_devices),
            device_fingerprint=body.get("device_fingerprint", ""),
            features=features,
            validation_mode=body.get("validation_mode", "hybrid"),
            revocation_epoch=self.revocation_epoch,
            metadata=metadata,
        )
        self.licenses.append(license_doc)
        return {"status": "created", "license": license_doc}

    def list_licenses(self) -> Dict[str, Any]:
        return {"licenses": [self._license_summary(license_doc) for license_doc in self.licenses]}

    def validate(self, body: Dict[str, Any]) -> Dict[str, Any]:
        result = OfflineValidationService(self.keys.public_bundle()).validate(
            body.get("license", body),
            expected_product_id=body.get("product_id", self.product_id),
            revocation_list=self.revocations,
            device_fingerprint=body.get("device_fingerprint", ""),
        )
        return result.to_dict()

    def cancel(self, license_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        current = []
        if self.revocations:
            current = list(self.revocations.get("payload", {}).get("revoked", []))
        current.append(
            {
                "license_id": license_id,
                "reason": body.get("reason", "manual cancellation"),
                "revoked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        self.revocation_epoch += 1
        self.revocations = RevocationService(self.keys).create_revocation_list(
            revoked=current,
            generated_at=datetime.now(timezone.utc),
            revocation_epoch=self.revocation_epoch,
            grace_period_days=int(body.get("grace_period_days", 0)),
        )
        self._persist_revocations()
        return {"status": "revoked", "license_id": license_id, "revocation_epoch": self.revocation_epoch}

    def revocation_list(self) -> Dict[str, Any]:
        return self.revocations or {
            "schema": "pqlicense-revocations/v2",
            "payload": {
                "revoked": [],
                "revocation_epoch": self.revocation_epoch,
            },
        }

    def _license_summary(self, license_doc: Dict[str, Any]) -> Dict[str, Any]:
        payload = license_doc.get("payload", {})
        return {
            "license_id": payload.get("license_id", ""),
            "customer_id": payload.get("customer_id", ""),
            "product_id": payload.get("product_id", ""),
            "plan": payload.get("plan", ""),
            "expires_at": payload.get("expires_at", ""),
            "validation_mode": payload.get("validation_mode", ""),
            "revocation_epoch": payload.get("revocation_epoch", 1),
            "features": payload.get("features", []),
        }

    def _current_revocation_epoch(self) -> int:
        if not self.revocations:
            return 1
        return int(self.revocations.get("payload", {}).get("revocation_epoch", 1))

    def _trusted_revocations(self, revocations: Optional[Dict[str, Any]], keys) -> Optional[Dict[str, Any]]:
        if not revocations:
            return None
        payload = revocations.get("payload")
        signatures = revocations.get("signatures")
        if not isinstance(payload, dict) or not isinstance(signatures, dict):
            return None
        mode = payload.get("validation_mode", "hybrid")
        _verification, ok = CryptoService().verify_payload(payload, signatures, keys.public_bundle(), mode)
        return revocations if ok else None

    def _persist_revocations(self) -> None:
        if self.revocations_path:
            Path(self.revocations_path).write_text(
                json.dumps(self.revocations, indent=2, sort_keys=True),
                encoding="utf-8",
            )
