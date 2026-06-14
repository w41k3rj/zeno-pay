#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "server" / "data" / "zeno_pay.db"
FINGERPRINT_INDEX_PATH = ROOT_DIR / "server" / "data" / "fingerprint_hashes.json"
ACCOUNT_PREFIX = "W41K3RJ"


def digits_only(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def build_account_code(value: str) -> str:
    digits = digits_only(value)
    if not digits:
        raise ValueError("Account suffix must contain digits.")
    return f"{ACCOUNT_PREFIX}{digits}"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def export_fingerprint_index(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT account_code, name, fingerprint_hash, updated_at
        FROM users
        WHERE fingerprint_hash IS NOT NULL AND account_type != 'owner'
        ORDER BY account_code
        """
    ).fetchall()
    payload = {
        "generated_at": conn.execute("SELECT datetime('now')").fetchone()[0],
        "users": [
            {
                "account_code": row["account_code"],
                "name": row["name"],
                "fingerprint_hash": row["fingerprint_hash"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
    }
    FINGERPRINT_INDEX_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def list_users(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT
          u.account_code,
          u.name,
          u.balance_cents,
          u.local_sensor_slot,
          COUNT(t.id) AS transaction_count
        FROM users u
        LEFT JOIN transactions t ON t.user_id = u.id
        WHERE u.account_type != 'owner'
        GROUP BY u.id
        ORDER BY u.account_code
        """
    ).fetchall()
    if not rows:
        print("No customer accounts found.")
        return 0

    print("Customer accounts:")
    for row in rows:
        balance = row["balance_cents"] / 100.0
        slot = row["local_sensor_slot"] if row["local_sensor_slot"] is not None else "-"
        print(
            f"- {row['account_code']} | {row['name']} | "
            f"balance=TZS {balance:.2f} | slot={slot} | tx={row['transaction_count']}"
        )
    return 0


def find_user(conn: sqlite3.Connection, account_code: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, account_code, name, local_sensor_slot, account_type
        FROM users
        WHERE account_code = ?
        """,
        (account_code,),
    ).fetchone()


def delete_user(
    conn: sqlite3.Connection,
    *,
    account_code: str,
    delete_transactions: bool,
) -> int:
    row = find_user(conn, account_code)
    if not row:
        print(f"User not found: {account_code}", file=sys.stderr)
        return 1

    if row["account_type"] == "owner":
        print("Refusing to delete the owner account.", file=sys.stderr)
        return 1

    tx_count = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ?",
        (row["id"],),
    ).fetchone()[0]

    if tx_count and not delete_transactions:
        print(
            f"Refusing to delete {account_code}: {tx_count} transaction(s) exist.\n"
            "Run again with --delete-transactions if you really want a hard delete.",
            file=sys.stderr,
        )
        return 1

    if tx_count:
        conn.execute("DELETE FROM transactions WHERE user_id = ?", (row["id"],))

    conn.execute("DELETE FROM users WHERE id = ?", (row["id"],))
    conn.commit()
    export_fingerprint_index(conn)

    print(f"Deleted user: {row['account_code']} ({row['name']})")
    if tx_count:
        print(f"Deleted transactions: {tx_count}")
    if row["local_sensor_slot"] is not None:
        print(
            f"AS608 note: slot {row['local_sensor_slot']} may still exist on the sensor. "
            "If the same finger is scanned, the terminal may still recognize that slot "
            "until you overwrite or clear it on the device."
        )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List or delete customer accounts from the Zeno Pay database.")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to the SQLite database.")
    parser.add_argument("--list", action="store_true", help="List customer accounts and exit.")
    parser.add_argument("--account-code", help="Full account code to delete, e.g. W41K3RJ123456.")
    parser.add_argument("--suffix", help="Account suffix to delete, e.g. 123456.")
    parser.add_argument(
        "--delete-transactions",
        action="store_true",
        help="Also delete the user's transaction history so the account can be removed.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip the delete confirmation prompt.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db.resolve()
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    with connect(db_path) as conn:
        if args.list:
            return list_users(conn)

        account_code = ""
        if args.account_code:
            account_code = args.account_code.strip()
        elif args.suffix:
            try:
                account_code = build_account_code(args.suffix)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        else:
            print("Use --list or provide --account-code/--suffix.", file=sys.stderr)
            return 1

        if not args.yes:
            print(f"About to delete: {account_code}")
            confirm = input("Type DELETE to continue: ").strip()
            if confirm != "DELETE":
                print("Cancelled.")
                return 1

        return delete_user(
            conn,
            account_code=account_code,
            delete_transactions=args.delete_transactions,
        )


if __name__ == "__main__":
    raise SystemExit(main())
