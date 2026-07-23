#!/usr/bin/env python
"""‌⁠‍Rotate the manifest signing key (Audit A1).

Emergency-rotation flow:

    1. Generate a fresh Ed25519 keypair
    2. Write the new public key into
       ``backend/app/modules/takeoff/manifest_verifier.py`` between
       the ROTATION_SENTINEL_BEGIN / END markers
    3. Print the new private key in PEM form to stdout — the operator
       captures this OFFLINE (paper backup + HSM import) and clears
       their terminal scrollback before stepping away from the
       keyboard

This script intentionally does NOT:

    * Re-sign the manifest (that lives in a separate, air-gapped repo
      with its own audit log)
    * Touch any other file (clean diff = easy review)
    * Talk to the network (no telemetry, no remote upload)

Usage::

    python scripts/rotate_manifest_signing_key.py --confirm

The ``--confirm`` flag is mandatory: running with no args prints a
warning and exits 2 so a tab-completion accident doesn't generate a
fresh key that then needs to be reverted from git history.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_VERIFIER_PATH = (
    Path(__file__).resolve().parent.parent
    / "backend" / "app" / "modules" / "takeoff" / "manifest_verifier.py"
)

_SENTINEL_RE = re.compile(
    r"# ROTATION_SENTINEL_BEGIN.*?# ROTATION_SENTINEL_END",
    re.DOTALL,
)


def generate_keypair() -> tuple[str, bytes]:
    """‌⁠‍Return (pubkey_hex, private_pem_bytes)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    private = Ed25519PrivateKey.generate()
    pubkey_hex = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pubkey_hex, private_pem


def write_new_pubkey(pubkey_hex: str) -> None:
    """‌⁠‍Replace the sentinel-marked block with the new pubkey constant.

    Preserves surrounding comments so reviewers see context. Aborts
    if the sentinel can't be found — better to fail loudly than to
    write the new key somewhere unexpected.
    """
    source = _VERIFIER_PATH.read_text(encoding="utf-8")
    replacement = (
        "# ROTATION_SENTINEL_BEGIN — do not edit by hand; script writes here\n"
        f'CURRENT_PUBKEY_HEX: str = (\n    "{pubkey_hex}"\n)\n'
        "# ROTATION_SENTINEL_END"
    )
    new_source, n_subs = _SENTINEL_RE.subn(replacement, source, count=1)
    if n_subs != 1:
        raise SystemExit(
            f"Could not find ROTATION_SENTINEL markers in {_VERIFIER_PATH}. "
            "Has the file been renamed or the sentinel removed?"
        )
    _VERIFIER_PATH.write_text(new_source, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rotate the manifest signing key.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required — explicitly confirm rotation.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help=(
            "Generate + print a keypair but do NOT modify "
            "manifest_verifier.py. Useful for dry runs."
        ),
    )
    args = parser.parse_args()

    if not args.confirm and not args.print_only:
        print(
            "Refusing to rotate without --confirm. Pass --confirm to "
            "actually rotate, or --print-only for a dry run.",
            file=sys.stderr,
        )
        return 2

    pubkey_hex, private_pem = generate_keypair()

    if not args.print_only:
        write_new_pubkey(pubkey_hex)
        print(f"Wrote new public key to {_VERIFIER_PATH}")
    else:
        print("(--print-only) Not writing to source. New public key:")

    print(f"\nNew public key (hex, 32 bytes / 64 chars):\n{pubkey_hex}\n")
    print("New PRIVATE key (PEM) — capture offline + clear scrollback:\n")
    print(private_pem.decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
