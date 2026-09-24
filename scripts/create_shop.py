"""Onboard a shop by hand (no self-serve signup in v1).

Usage:
    DATABASE_URL=postgresql://... python scripts/create_shop.py "JG Sign Company" HMGR-0001

Prints the raw API key exactly once. It is never stored or shown again -- if it's lost,
re-run with --rotate to issue a new one for the same license serial.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.postgres_store import PostgresStore  # noqa: E402
from app.security import hash_api_key, new_api_key  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shop_name")
    parser.add_argument("license_serial")
    parser.add_argument("--status", default="trial", choices=["trial", "active", "suspended", "expired"])
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL first (the same value configured on the Render service).")

    store = PostgresStore(dsn)
    store.init_schema()

    raw_key = new_api_key()
    shop = store.create_shop(args.shop_name, hash_api_key(raw_key), args.license_serial, args.status)

    print(f"Shop created: {shop.name} ({shop.id})")
    print(f"License serial: {shop.license_serial}")
    print(f"Status: {shop.license_status}")
    print()
    print("API key (copy this into HiveMGR Settings -> Cloud sync now -- it will not be shown again):")
    print(raw_key)


if __name__ == "__main__":
    main()
