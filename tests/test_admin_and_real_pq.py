import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pqlicense.post_quantum_provider import PostQuantumSignatureProvider  # noqa: E402
from pqlicense.core import create_revocation_list  # noqa: E402
from pqlicense.license_controller import LicenseController  # noqa: E402
from pqlicense.server import make_handler  # noqa: E402
from pqlicense.signers import create_key_bundle  # noqa: E402


class RealPostQuantumProviderTests(unittest.TestCase):
    def test_post_quantum_provider_uses_real_ml_dsa_when_pqcrypto_is_available(self):
        provider = PostQuantumSignatureProvider()
        key_pair = provider.generate_key_pair()
        message = b"canonical payload"
        signature = provider.sign(message, key_pair.private_key)

        self.assertEqual(provider.algorithm, "ML-DSA-65")
        self.assertTrue(provider.uses_real_pqc)
        self.assertTrue(provider.verify(message, signature, key_pair.public_key))
        self.assertFalse(provider.verify(b"tampered", signature, key_pair.public_key))


class AdminAndListingEndpointTests(unittest.TestCase):
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

    def get_json(self, path, token=None):
        req = request.Request(self.base_url + path, method="GET")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with request.urlopen(req, timeout=5) as response:
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

    def test_admin_login_is_required_for_generation_listing_and_cancel(self):
        with self.assertRaises(error.HTTPError) as denied:
            self.post_json("/api/licenses/generate", self.license_payload())
        self.assertEqual(denied.exception.code, 401)

        login = self.post_json(
            "/api/admin/login",
            {"username": "admin", "password": "admin123"},
        )
        token = login["token"]
        self.assertEqual(login["status"], "authenticated")

        created = self.post_json("/api/licenses/generate", self.license_payload(), token=token)
        license_doc = created["license"]

        licenses = self.get_json("/api/licenses", token=token)
        self.assertEqual(len(licenses["licenses"]), 1)
        self.assertEqual(licenses["licenses"][0]["license_id"], "LIC-ADMIN-1")
        self.assertNotIn("signatures", json.dumps(licenses))

        with self.assertRaises(error.HTTPError) as list_denied:
            self.get_json("/api/licenses")
        self.assertEqual(list_denied.exception.code, 401)

        valid = self.post_json(
            "/api/licenses/validate",
            {"license": license_doc, "device_fingerprint": "admin-device"},
        )
        self.assertTrue(valid["valid"])

        revoked = self.post_json(
            "/api/licenses/LIC-ADMIN-1/cancel",
            {"reason": "admin cancellation"},
            token=token,
        )
        self.assertEqual(revoked["status"], "revoked")

        revocations = self.get_json("/api/licenses/revocations")
        self.assertEqual(revocations["payload"]["revoked"][0]["license_id"], "LIC-ADMIN-1")

    def test_demo_admin_password_works_even_when_environment_password_is_set(self):
        old_password = os.environ.get("PQLICENSE_ADMIN_PASSWORD")
        os.environ["PQLICENSE_ADMIN_PASSWORD"] = "custom-secret"
        try:
            controller = LicenseController(
                keys=self.keys,
                revocations=None,
                product_id="app-pro",
                revocations_path=None,
            )
            login = controller.login({"username": "admin", "password": "admin123"})
            self.assertEqual(login["status"], "authenticated")
            self.assertIn("token", login)
        finally:
            if old_password is None:
                os.environ.pop("PQLICENSE_ADMIN_PASSWORD", None)
            else:
                os.environ["PQLICENSE_ADMIN_PASSWORD"] = old_password

    def test_stale_revocation_list_signed_by_old_keys_is_ignored_on_startup(self):
        stale_keys = create_key_bundle()
        stale_revocations = create_revocation_list(
            stale_keys,
            revoked=[
                {
                    "license_id": "OTHER-LICENSE",
                    "reason": "old data",
                    "revoked_at": "2026-06-23T00:00:00Z",
                }
            ],
            generated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
        handler = make_handler(
            keys=self.keys,
            revocations=stale_revocations,
            product_id="app-pro",
            revocations_path=None,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            token = self._post_to(base_url, "/api/admin/login", {"username": "admin", "password": "admin123"})["token"]
            created = self._post_to(base_url, "/api/licenses/generate", self.license_payload(), token=token)
            valid = self._post_to(
                base_url,
                "/api/licenses/validate",
                {"license": created["license"], "device_fingerprint": "admin-device"},
            )
            self.assertEqual(valid["status"], "valid")
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def license_payload(self):
        return {
            "license_id": "LIC-ADMIN-1",
            "customer_id": "admin-customer",
            "product_id": "app-pro",
            "plan": "professional",
            "days": 30,
            "allowed_devices": 1,
            "device_fingerprint": "admin-device",
            "features": ["offline"],
            "validation_mode": "hybrid",
            "redirect_url": "https://app.example.com/start",
            "error_url": "https://app.example.com/license-error",
        }

    def _post_to(self, base_url, path, payload, token=None):
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
