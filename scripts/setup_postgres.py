#!/usr/bin/env python3
"""
TRIAL: create the gsc-seo Postgres tables in Railway.

This is a standalone setup probe — it does NOT touch the running app.
It connects to a Postgres database, runs scripts/db_schema.sql (idempotent),
then lists the tables so you can confirm it worked.

────────────────────────────────────────────────────────────────────────
HOW TO USE (the "how hard is it" test)
────────────────────────────────────────────────────────────────────────
1. In Railway: open your project → "New" → "Database" → "Add PostgreSQL".
   Railway provisions it and exposes a connection string.
2. Get the connection string:
     - In the Postgres service → "Variables" → copy DATABASE_URL
       (or the "Public Network" connection URL if you run this from your
        laptop instead of inside Railway).
3. Run this script with that URL:

     # PowerShell (Windows):
     $env:DATABASE_URL = "postgresql://user:pass@host:port/dbname"
     python scripts/setup_postgres.py

     # or pass it as an argument:
     python scripts/setup_postgres.py "postgresql://user:pass@host:port/dbname"

   Needs the driver once:  pip install psycopg2-binary

That's the whole setup. Re-running is safe (CREATE TABLE IF NOT EXISTS).
"""

import os
import sys


def _get_database_url() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print(
            "ERROR: no database URL.\n"
            "  Set DATABASE_URL env var, or pass it as the first argument:\n"
            "    python scripts/setup_postgres.py "
            '"postgresql://user:pass@host:port/dbname"\n'
            "  (Copy it from your Railway Postgres service → Variables → DATABASE_URL)"
        )
        sys.exit(1)
    return url


def _load_schema_sql() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "db_schema.sql")
    if not os.path.exists(path):
        print(f"ERROR: schema file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main() -> None:
    try:
        import psycopg2
    except ImportError:
        print(
            "ERROR: psycopg2 not installed.\n"
            "  Install the driver first:  pip install psycopg2-binary"
        )
        sys.exit(1)

    db_url = _get_database_url()
    schema_sql = _load_schema_sql()

    # Hide credentials in the printed host
    safe = db_url
    if "@" in safe:
        safe = "postgresql://***@" + safe.split("@", 1)[1]
    print(f"Connecting to: {safe}")

    try:
        conn = psycopg2.connect(db_url)
    except Exception as e:
        print(f"ERROR: could not connect — {type(e).__name__}: {e}")
        sys.exit(1)

    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Running scripts/db_schema.sql ...")
            cur.execute(schema_sql)

            # Confirm what now exists
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
            tables = [r[0] for r in cur.fetchall()]

            print("\nOK — tables in this database (public schema):")
            for t in tables:
                cur.execute(f"SELECT count(*) FROM {t}")
                n = cur.fetchone()[0]
                print(f"  - {t:<16} ({n} rows)")

        print(
            "\nDone. The schema is created. Re-running this script is safe.\n"
            "Next decision: whether to migrate the app's JSON data into these "
            "tables — say the word and I'll write a separate, reversible "
            "migration script."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
