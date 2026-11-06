"""Explicitly assign a legacy invoice to a verified local account."""

import argparse
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.accounts import Accounts
from backend.config import load, setting
from backend.db import DB


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("invoice")
    parser.add_argument("account_id")
    args = parser.parse_args()
    config = load()
    with closing(DB(config.db_path)) as db:
        Accounts(db, setting("SENFUND_OIDC_ISSUER", ""), setting("SENFUND_API_BRIDGE_SECRET", "")).assign_legacy_invoice(
            args.invoice, args.account_id,
        )
    print("Invoice owner recorded.")


if __name__ == "__main__":
    main()
