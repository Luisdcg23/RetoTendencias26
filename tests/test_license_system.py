import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pqlicense.core import (  # noqa: E402
    create_key_bundle,
    create_license,
    create_revocation_list,
    validate_license,
)


class LicenseSystemTests(unittest.TestCase):
    def setUp(self):
        self.keys = create_key_bundle()
        self.now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
        self.license = create_license(
            self.keys,
            license_id="LIC-001",
            customer_id="customer-a",
            product_id="product-pro",
            issued_at=self.now,
            expires_at=self.now + timedelta(days=30),
            features=["reports", "offline"],
            device_limit=3,
            redirect_url="https://app.example.test/start",
            error_url="https://app.example.test/license-error",
        )

    def test_valid_license_returns_access_redirect(self):
        result = validate_license(
            self.license,
            self.keys.public_bundle(),
            expected_product_id="product-pro",
            checked_at=self.now,
        )

        self.assertEqual(result.status, "valid")
        self.assertTrue(result.redirect_url.startswith("https://app.example.test/start?"))
        self.assertIn("license_id=LIC-001", result.redirect_url)
        self.assertIn("customer_id=customer-a", result.redirect_url)

    def test_tampered_license_is_rejected(self):
        tampered = copy.deepcopy(self.license)
        tampered["payload"]["features"].append("enterprise")

        result = validate_license(
            tampered,
            self.keys.public_bundle(),
            expected_product_id="product-pro",
            checked_at=self.now,
        )

        self.assertEqual(result.status, "invalid_signature")
        self.assertEqual(result.redirect_url, "https://app.example.test/license-error")

    def test_expired_license_is_rejected(self):
        result = validate_license(
            self.license,
            self.keys.public_bundle(),
            expected_product_id="product-pro",
            checked_at=self.now + timedelta(days=40),
        )

        self.assertEqual(result.status, "expired")
        self.assertEqual(result.redirect_url, "https://app.example.test/license-error")

    def test_signed_revocation_list_blocks_license(self):
        revocations = create_revocation_list(
            self.keys,
            revoked=[
                {
                    "license_id": "LIC-001",
                    "reason": "manual cancellation",
                    "revoked_at": self.now.isoformat().replace("+00:00", "Z"),
                }
            ],
            generated_at=self.now,
        )

        result = validate_license(
            self.license,
            self.keys.public_bundle(),
            expected_product_id="product-pro",
            revocation_list=revocations,
            checked_at=self.now,
        )

        self.assertEqual(result.status, "revoked")

    def test_tampered_revocation_list_is_rejected(self):
        revocations = create_revocation_list(
            self.keys,
            revoked=[],
            generated_at=self.now,
        )
        revocations["payload"]["revoked"].append(
            {
                "license_id": "LIC-001",
                "reason": "tampered",
                "revoked_at": self.now.isoformat().replace("+00:00", "Z"),
            }
        )

        result = validate_license(
            self.license,
            self.keys.public_bundle(),
            expected_product_id="product-pro",
            revocation_list=revocations,
            checked_at=self.now,
        )

        self.assertEqual(result.status, "invalid_revocation_signature")


if __name__ == "__main__":
    unittest.main()
