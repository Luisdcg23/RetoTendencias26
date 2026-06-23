from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .crypto_service import CryptoService
from .models import HYBRID, ValidationResult, normalize_signature_mode
from .redirect_service import RedirectService
from .time_utils import parse_utc_iso


class OfflineValidationService:
    def __init__(self, public_keys, crypto_service: Optional[CryptoService] = None, redirect_service: Optional[RedirectService] = None):
        self.public_keys = public_keys
        self.crypto_service = crypto_service or CryptoService()
        self.redirect_service = redirect_service or RedirectService()

    def validate(
        self,
        license_doc: Dict[str, Any],
        *,
        expected_product_id: str,
        checked_at: Optional[datetime] = None,
        device_fingerprint: str = "",
        revocation_list: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        checked_at = (checked_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        payload = license_doc.get("payload")
        signatures = license_doc.get("signatures")
        if license_doc.get("schema") != "pqlicense/v2" or not isinstance(payload, dict) or not isinstance(signatures, dict):
            return self._result("invalid_format", payload if isinstance(payload, dict) else {}, "license document has invalid structure")

        mode = normalize_signature_mode(payload.get("validation_mode", HYBRID))
        if mode is None:
            return self._result("invalid_format", payload, "unsupported validation mode")

        verification, signatures_ok = self.crypto_service.verify_payload(payload, signatures, self.public_keys, mode)
        verification_dict = verification.to_dict()
        if not signatures_ok:
            return self._result("invalid_signature", payload, "required signature verification failed", verification_dict)

        if str(payload.get("product_id")) != expected_product_id:
            return self._result("wrong_product", payload, "license is for another product", verification_dict)

        expected_device = str(payload.get("device_fingerprint") or "")
        if expected_device and device_fingerprint and expected_device != device_fingerprint:
            return self._result("wrong_device", payload, "license is bound to another device", verification_dict)

        try:
            expires_at = parse_utc_iso(str(payload["expires_at"]))
        except (KeyError, ValueError):
            return self._result("invalid_format", payload, "expiration timestamp is invalid", verification_dict)
        if checked_at > expires_at:
            return self._result("expired", payload, "license is expired", verification_dict)

        if revocation_list is not None:
            revoked_ids = self._revoked_ids(revocation_list, mode)
            if revoked_ids is None:
                return self._result("invalid_revocation_signature", payload, "revocation list signature verification failed", verification_dict)
            if str(payload.get("license_id")) in revoked_ids:
                return self._result("revoked", payload, "license is revoked", verification_dict)

        details = "license accepted"
        if revocation_list is None:
            details = "license accepted; offline revocation freshness unknown"
        return ValidationResult(
            status="valid",
            valid=True,
            reason="valid",
            redirect_url=self.redirect_service.access_url(payload),
            error_redirect_url=self.redirect_service.error_url(payload),
            details=details,
            verification=verification_dict,
        )

    def _revoked_ids(self, revocation_list: Dict[str, Any], mode: str) -> Optional[List[str]]:
        payload = revocation_list.get("payload")
        signatures = revocation_list.get("signatures")
        if not isinstance(payload, dict) or not isinstance(signatures, dict):
            return None
        verification, ok = self.crypto_service.verify_payload(payload, signatures, self.public_keys, mode)
        if not ok:
            return None
        revoked = payload.get("revoked", [])
        if not isinstance(revoked, list):
            return None
        return [str(item["license_id"]) for item in revoked if isinstance(item, dict) and "license_id" in item]

    def _result(self, status: str, payload: Dict[str, Any], details: str, verification: Optional[Dict[str, Any]] = None) -> ValidationResult:
        return ValidationResult(
            status=status,
            valid=False,
            reason=status,
            redirect_url=self.redirect_service.error_url(payload),
            error_redirect_url=self.redirect_service.error_url(payload),
            details=details,
            verification=verification or {},
        )
