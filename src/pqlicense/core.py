from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from .license_service import LicenseService
from .models import ValidationResult
from .offline_validation_service import OfflineValidationService
from .revocation_service import RevocationService
from .signers import KeyBundle, PublicKeyBundle, create_key_bundle as _create_key_bundle


def create_key_bundle() -> KeyBundle:
    return _create_key_bundle()


def create_license(
    keys: KeyBundle,
    *,
    license_id: str,
    customer_id: str,
    product_id: str,
    issued_at: datetime,
    expires_at: datetime,
    features: Iterable[str],
    device_limit: int,
    redirect_url: str,
    error_url: str,
    plan: str = "professional",
    device_fingerprint: str = "",
    validation_mode: str = "hybrid",
    revocation_epoch: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged_metadata = {"redirect_url": redirect_url, "error_url": error_url}
    if metadata:
        merged_metadata.update(metadata)
    return LicenseService(keys).generate_license(
        license_id=license_id,
        customer_id=customer_id,
        product_id=product_id,
        plan=plan,
        issued_at=issued_at,
        expires_at=expires_at,
        allowed_devices=device_limit,
        device_fingerprint=device_fingerprint,
        features=features,
        validation_mode=validation_mode,
        revocation_epoch=revocation_epoch,
        metadata=merged_metadata,
    )


def create_revocation_list(
    keys: KeyBundle,
    *,
    revoked: Iterable[Dict[str, str]],
    generated_at: datetime,
    revocation_epoch: int = 1,
    grace_period_days: int = 0,
) -> Dict[str, Any]:
    return RevocationService(keys).create_revocation_list(
        revoked=revoked,
        generated_at=generated_at,
        revocation_epoch=revocation_epoch,
        grace_period_days=grace_period_days,
    )


def validate_license(
    license_doc: Dict[str, Any],
    public_keys: PublicKeyBundle,
    *,
    expected_product_id: str,
    revocation_list: Optional[Dict[str, Any]] = None,
    checked_at: Optional[datetime] = None,
    device_fingerprint: str = "",
) -> ValidationResult:
    return OfflineValidationService(public_keys).validate(
        license_doc,
        expected_product_id=expected_product_id,
        revocation_list=revocation_list,
        checked_at=checked_at,
        device_fingerprint=device_fingerprint,
    )
