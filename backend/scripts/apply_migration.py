"""Apply one numbered SQL migration from backend/migrations/ to the DB in .env.

Usage: venv/Scripts/python scripts/apply_migration.py 003_ledger_status.sql

Runs each ;-terminated statement in order and prints affected row counts.
The target comes from backend/.env (DB_HOST/DB_USER/DB_PASSWORD/DB_NAME) —
the same variables the server reads, so it applies to whatever database the
local .env points at. Statements are executed one by one; DDL in MySQL
auto-commits, DML is committed at the end.
"""
import sys
from pathlib import Path

import pymysql
from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parent.parent


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    sql_path = BACKEND / "migrations" / sys.argv[1]
    raw = sql_path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.lstrip().startswith("--")]
    statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]

    env = dotenv_values(BACKEND / ".env")
    print(f"applying {sql_path.name} to {env['DB_HOST']}/{env['DB_NAME']} "
          f"({len(statements)} statements)")
    conn = pymysql.connect(
        host=env["DB_HOST"], port=int(env.get("DB_PORT") or 3306),
        user=env["DB_USER"], password=env["DB_PASSWORD"], database=env["DB_NAME"],
    )
    try:
        with conn.cursor() as cur:
            for i, stmt in enumerate(statements, 1):
                cur.execute(stmt)
                print(f"  [{i}/{len(statements)}] ok — {cur.rowcount} rows: "
                      f"{' '.join(stmt.split())[:80]}")
        conn.commit()
    finally:
        conn.close()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
