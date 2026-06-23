from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class RedirectService:
    def access_url(self, payload: Dict[str, Any]) -> str:
        base_url = str(payload.get("metadata", {}).get("redirect_url") or payload.get("redirect_url") or "")
        parsed = urlparse(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update(
            {
                "license_id": str(payload.get("license_id", "")),
                "customer_id": str(payload.get("customer_id", "")),
                "product_id": str(payload.get("product_id", "")),
                "plan": str(payload.get("plan", "")),
            }
        )
        return urlunparse(parsed._replace(query=urlencode(query)))

    def error_url(self, payload: Dict[str, Any]) -> str:
        return str(payload.get("metadata", {}).get("error_url") or payload.get("error_url") or "")
