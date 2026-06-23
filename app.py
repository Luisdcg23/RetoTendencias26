import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from pqlicense.core import create_key_bundle
from pqlicense.post_quantum_provider import PostQuantumSignatureProvider
from pqlicense.server import serve
from pqlicense.signers import KeyBundle


DATA_DIR = ROOT / "demo_output"
KEYS_PATH = DATA_DIR / "frontend_keys.json"
REVOCATIONS_PATH = DATA_DIR / "frontend_revocations.json"


def load_or_create_keys() -> KeyBundle:
    DATA_DIR.mkdir(exist_ok=True)
    if KEYS_PATH.exists():
        keys = KeyBundle.from_dict(json.loads(KEYS_PATH.read_text(encoding="utf-8")))
        expected_pq_algorithm = PostQuantumSignatureProvider().algorithm
        if keys.pq_algorithm == expected_pq_algorithm:
            return keys
    keys = create_key_bundle()
    KEYS_PATH.write_text(json.dumps(keys.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return keys


def load_revocations():
    if REVOCATIONS_PATH.exists():
        return json.loads(REVOCATIONS_PATH.read_text(encoding="utf-8"))
    return None


if __name__ == "__main__":
    serve(
        keys=load_or_create_keys(),
        revocations=load_revocations(),
        product_id="app-pro",
        host="127.0.0.1",
        port=int(os.environ.get("PQLICENSE_PORT", "8090")),
        revocations_path=str(REVOCATIONS_PATH),
    )
