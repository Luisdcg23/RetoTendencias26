import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from .core import create_key_bundle, create_license, create_revocation_list, validate_license
from .server import serve
from .signers import KeyBundle, PublicKeyBundle


def _read_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str, value: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _read_key_bundle(path: str) -> KeyBundle:
    return KeyBundle.from_dict(_read_json(path))


def _read_public_bundle(path: str) -> PublicKeyBundle:
    data = _read_json(path)
    if "classic_private_key" in data:
        return KeyBundle.from_dict(data).public_bundle()
    return PublicKeyBundle.from_dict(data)


def _cmd_init_keys(args: argparse.Namespace) -> int:
    keys = create_key_bundle()
    _write_json(args.out, keys.to_dict())
    _write_json(args.public_out, keys.public_bundle().to_dict())
    print(f"keys written to {args.out}")
    print(f"public keys written to {args.public_out}")
    return 0


def _cmd_generate_license(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    license_doc = create_license(
        _read_key_bundle(args.keys),
        license_id=args.license_id,
        customer_id=args.customer_id,
        product_id=args.product_id,
        issued_at=now,
        expires_at=now + timedelta(days=args.days),
        features=args.feature,
        device_limit=args.device_limit,
        redirect_url=args.redirect_url,
        error_url=args.error_url,
    )
    _write_json(args.out, license_doc)
    print(f"license written to {args.out}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    revocations = _read_json(args.revocations) if args.revocations else None
    result = validate_license(
        _read_json(args.license),
        _read_public_bundle(args.keys),
        expected_product_id=args.product_id,
        revocation_list=revocations,
    )
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    return 0 if result.status == "valid" else 2


def _cmd_revoke(args: argparse.Namespace) -> int:
    current = []
    if args.existing and Path(args.existing).exists():
        current = _read_json(args.existing).get("payload", {}).get("revoked", [])
    current.append(
        {
            "license_id": args.license_id,
            "reason": args.reason,
            "revoked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    revocations = create_revocation_list(
        _read_key_bundle(args.keys),
        revoked=current,
        generated_at=datetime.now(timezone.utc),
    )
    _write_json(args.out, revocations)
    print(f"revocation list written to {args.out}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    revocations = _read_json(args.revocations) if args.revocations and Path(args.revocations).exists() else None
    serve(
        keys=_read_key_bundle(args.keys),
        revocations=revocations,
        product_id=args.product_id,
        host=args.host,
        port=args.port,
        revocations_path=args.revocations,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post-quantum-ready license system prototype")
    subcommands = parser.add_subparsers(required=True)

    init_keys = subcommands.add_parser("init-keys", help="generate issuer keys")
    init_keys.add_argument("--out", default="keys.json")
    init_keys.add_argument("--public-out", default="public_keys.json")
    init_keys.set_defaults(func=_cmd_init_keys)

    generate = subcommands.add_parser("generate-license", help="generate a signed license")
    generate.add_argument("--keys", required=True)
    generate.add_argument("--out", required=True)
    generate.add_argument("--license-id", required=True)
    generate.add_argument("--customer-id", required=True)
    generate.add_argument("--product-id", required=True)
    generate.add_argument("--days", type=int, default=365)
    generate.add_argument("--feature", action="append", default=[])
    generate.add_argument("--device-limit", type=int, default=1)
    generate.add_argument("--redirect-url", required=True)
    generate.add_argument("--error-url", required=True)
    generate.set_defaults(func=_cmd_generate_license)

    validate = subcommands.add_parser("validate", help="validate a license offline")
    validate.add_argument("--keys", required=True, help="public or private key bundle")
    validate.add_argument("--license", required=True)
    validate.add_argument("--product-id", required=True)
    validate.add_argument("--revocations")
    validate.set_defaults(func=_cmd_validate)

    revoke = subcommands.add_parser("revoke", help="create or update a signed revocation list")
    revoke.add_argument("--keys", required=True)
    revoke.add_argument("--license-id", required=True)
    revoke.add_argument("--reason", default="manual cancellation")
    revoke.add_argument("--existing")
    revoke.add_argument("--out", required=True)
    revoke.set_defaults(func=_cmd_revoke)

    server = subcommands.add_parser("serve", help="start online validation API")
    server.add_argument("--keys", required=True)
    server.add_argument("--product-id", required=True)
    server.add_argument("--revocations")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8080)
    server.set_defaults(func=_cmd_serve)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)
