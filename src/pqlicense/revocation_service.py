from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

from .crypto_service import CryptoService
from .time_utils import utc_iso


class RevocationService:
    def __init__(self, keys, crypto_service: Optional[CryptoService] = None):
        self.keys = keys
        self.crypto_service = crypto_service or CryptoService()

    def create_revocation_list(
        self,
        *,
        revoked: Iterable[Dict[str, str]],
        generated_at: datetime,
        revocation_epoch: int = 1,
        grace_period_days: int = 0,
        next_online_check_required_at: Optional[datetime] = None,
    ) -> Dict:
        if next_online_check_required_at is None:
            next_online_check_required_at = generated_at + timedelta(days=max(grace_period_days, 0))
        payload = {
            "schema": "pqlicense-revocations/v2",
            "generated_at": utc_iso(generated_at),
            "revocation_epoch": int(revocation_epoch),
            "grace_period_days": int(grace_period_days),
            "next_online_check_required_at": utc_iso(next_online_check_required_at),
            "revoked": sorted(list(revoked), key=lambda item: item["license_id"]),
        }
        return {
            "schema": "pqlicense-revocations/v2",
            "payload": payload,
            "signatures": self.crypto_service.sign_payload(payload, self.keys),
            "public_key_ids": {
                "classical": self.keys.classic_key_id,
                "post_quantum": self.keys.pq_key_id,
            },
        }
