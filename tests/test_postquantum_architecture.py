import copy
import json
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pqlicense.license_service import LicenseService  # noqa: E402
from pqlicense.offline_validation_service import OfflineValidationService  # noqa: E402
from pqlicense.revocation_service import RevocationService  # noqa: E402
from pqlicense.server import make_handler  # noqa: E402
from pqlicense.signers import create_key_bundle  # noqa: E402


class PostQuantumArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.keys = create_key_bundle()
        self.public_keys = self.keys.public_bundle()
        self.now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
        self.license_service = LicenseService(self.keys)
        self.validator = OfflineValidationService(self.public_keys)
        self.revocations = RevocationService(self.keys)

    def make_license(self, **overrides):
        defaults = {
            "license_id": "LIC-V2-001",
            "customer_id": "customer-v2",
            "product_id": "app-pro",
            "plan": "professional",
            "issued_at": self.now,
            "expires_at": self.now + timedelta(days=30),
            "allowed_devices": 3,
            "device_fingerprint": "device-sha256-demo",
            "features": ["offline", "reports"],
            "validation_mode": "hybrid",
            "revocation_epoch": 1,
            "metadata": {
                "redirect_url": "https://app.example.com/start",
                "error_url": "https://app.example.com/license-error",
            },
        }
        defaults.update(overrides)
        return self.license_service.generate_license(**defaults)

    def test_v2_hybrid_license_contains_required_payload_and_signatures(self):
        license_doc = self.make_license()

        self.assertEqual(license_doc["schema"], "pqlicense/v2")
        self.assertEqual(license_doc["payload"]["plan"], "professional")
        self.assertEqual(license_doc["payload"]["allowed_devices"], 3)
        self.assertEqual(license_doc["payload"]["device_fingerprint"], "device-sha256-demo")
        self.assertEqual(license_doc["payload"]["validation_mode"], "hybrid")
        self.assertEqual(license_doc["payload"]["revocation_epoch"], 1)
        self.assertIn("classical", license_doc["signatures"])
        self.assertIn("post_quantum", license_doc["signatures"])
        self.assertIn("public_key_ids", license_doc)

    def test_hybrid_validation_requires_both_signatures(self):
        license_doc = self.make_license(validation_mode="hybrid")

        valid = self.validator.validate(
            license_doc,
            expected_product_id="app-pro",
            checked_at=self.now,
            device_fingerprint="device-sha256-demo",
        )
        self.assertTrue(valid.valid)
        self.assertEqual(valid.status, "valid")

        tampered_classical = copy.deepcopy(license_doc)
        tampered_classical["signatures"]["classical"]["value"] = "invalid"
        classical_result = self.validator.validate(
            tampered_classical,
            expected_product_id="app-pro",
            checked_at=self.now,
            device_fingerprint="device-sha256-demo",
        )
        self.assertFalse(classical_result.valid)
        self.assertEqual(classical_result.status, "invalid_signature")
        self.assertFalse(classical_result.verification["classical_signature"])

        tampered_pq = copy.deepcopy(license_doc)
        tampered_pq["signatures"]["post_quantum"]["value"] = "invalid"
        pq_result = self.validator.validate(
            tampered_pq,
            expected_product_id="app-pro",
            checked_at=self.now,
            device_fingerprint="device-sha256-demo",
        )
        self.assertFalse(pq_result.valid)
        self.assertEqual(pq_result.status, "invalid_signature")
        self.assertFalse(pq_result.verification["post_quantum_signature"])

    def test_classical_only_and_post_quantum_only_modes_work(self):
        classical_license = self.make_license(validation_mode="classical_only")
        classical_license["signatures"]["post_quantum"]["value"] = "invalid"
        classical_result = self.validator.validate(
            classical_license,
            expected_product_id="app-pro",
            checked_at=self.now,
            device_fingerprint="device-sha256-demo",
        )
        self.assertTrue(classical_result.valid)

        pq_license = self.make_license(validation_mode="post_quantum_only")
        pq_license["signatures"]["classical"]["value"] = "invalid"
        pq_result = self.validator.validate(
            pq_license,
            expected_product_id="app-pro",
            checked_at=self.now,
            device_fingerprint="device-sha256-demo",
        )
        self.assertTrue(pq_result.valid)

    def test_tampered_payload_expired_wrong_device_and_offline_revocation_fail(self):
        license_doc = self.make_license()

        tampered_payload = copy.deepcopy(license_doc)
        tampered_payload["payload"]["plan"] = "enterprise"
        tampered_result = self.validator.validate(
            tampered_payload,
            expected_product_id="app-pro",
            checked_at=self.now,
            device_fingerprint="device-sha256-demo",
        )
        self.assertEqual(tampered_result.status, "invalid_signature")

        expired = self.validator.validate(
            license_doc,
            expected_product_id="app-pro",
            checked_at=self.now + timedelta(days=40),
            device_fingerprint="device-sha256-demo",
        )
        self.assertEqual(expired.status, "expired")

        wrong_device = self.validator.validate(
            license_doc,
            expected_product_id="app-pro",
            checked_at=self.now,
            device_fingerprint="another-device",
        )
        self.assertEqual(wrong_device.status, "wrong_device")

        revocation_list = self.revocations.create_revocation_list(
            revoked=[
                {
                    "license_id": "LIC-V2-001",
                    "reason": "manual cancellation",
                    "revoked_at": self.now.isoformat().replace("+00:00", "Z"),
                }
            ],
            generated_at=self.now,
            revocation_epoch=1,
        )
        revoked = self.validator.validate(
            license_doc,
            expected_product_id="app-pro",
            checked_at=self.now,
            device_fingerprint="device-sha256-demo",
            revocation_list=revocation_list,
        )
        self.assertEqual(revoked.status, "revoked")


class LicenseEndpointTests(unittest.TestCase):
    def setUp(self):
        self.keys = create_key_bundle()
        handler = make_handler(
            keys=self.keys,
            revocations=None,
            product_id="app-pro",
            revocations_path=None,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def get_json(self, path):
        with request.urlopen(self.base_url + path, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path, payload, token=None):
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def admin_token(self):
        return self.post_json("/api/admin/login", {"username": "admin", "password": "admin123"})["token"]

    def test_new_license_endpoints_generate_validate_cancel_and_hide_private_keys(self):
        state = self.get_json("/api/licenses/state")
        serialized = json.dumps(state)
        self.assertNotIn("private", serialized)
        self.assertIn("public_keys", state)

        token = self.admin_token()
        created = self.post_json(
            "/api/licenses/generate",
            {
                "license_id": "LIC-API-1",
                "customer_id": "api-customer",
                "product_id": "app-pro",
                "plan": "professional",
                "days": 30,
                "allowed_devices": 2,
                "device_fingerprint": "api-device",
                "features": ["offline"],
                "validation_mode": "hybrid",
                "redirect_url": "https://app.example.com/start",
                "error_url": "https://app.example.com/license-error",
            },
            token=token,
        )
        license_doc = created["license"]
        self.assertEqual(license_doc["schema"], "pqlicense/v2")
        self.assertNotIn("private", json.dumps(created))

        valid = self.post_json(
            "/api/licenses/validate",
            {"license": license_doc, "device_fingerprint": "api-device"},
        )
        self.assertTrue(valid["valid"])
        self.assertEqual(valid["status"], "valid")
        self.assertIn("verification", valid)

        revoked = self.post_json(
            "/api/licenses/LIC-API-1/cancel",
            {"reason": "manual cancellation"},
            token=token,
        )
        self.assertEqual(revoked["status"], "revoked")

        invalid = self.post_json(
            "/api/licenses/validate",
            {"license": license_doc, "device_fingerprint": "api-device"},
        )
        self.assertFalse(invalid["valid"])
        self.assertEqual(invalid["status"], "revoked")

    def test_old_frontend_aliases_still_work(self):
        token = self.admin_token()
        created = self.post_json(
            "/api/create-license",
            {
                "license_id": "LIC-ALIAS-1",
                "customer_id": "alias-customer",
                "product_id": "app-pro",
                "days": 30,
                "device_limit": 1,
                "features": ["offline"],
                "redirect_url": "https://app.example.com/start",
                "error_url": "https://app.example.com/license-error",
            },
            token=token,
        )
        valid = self.post_json("/api/validate", {"license": created["license"]})

        self.assertTrue(valid["valid"])
        self.assertEqual(valid["status"], "valid")


if __name__ == "__main__":
    unittest.main()
