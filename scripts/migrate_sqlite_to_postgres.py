#!/usr/bin/env python3
"""Migrate SQLite data to PostgreSQL.

Usage:
    # 1. Set PG DATABASE_URL in .env
    # 2. Run migration
    python3 scripts/migrate_sqlite_to_postgres.py

Requires: psycopg2 (pip install psycopg2-binary)
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime

import asyncpg

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_PATH = os.path.join(PROJECT_ROOT, "demumumind.db")
PG_DSN = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/demumumind")

TABLES = [
    "providers",
    "models",
    "groups",
    "api_keys",
    "agent_types",
    "agent_usage",
    "provider_keys",
    "provider_test_runs",
    "plugins",
    "mcp_servers",
    "mcp_permissions",
    "alembic_version",
]


def sqlite_fetch(sqlite: sqlite3.Connection, table: str) -> list[dict]:
    cur = sqlite.execute(f"SELECT * FROM {table}")
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


async def pg_insert(pg: asyncpg.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    for row in rows:
        # JSON fields are stored as TEXT in SQLite, need to ensure they are valid JSONB
        for key, val in row.items():
            if isinstance(val, str):
                try:
                    json.loads(val)
                    row[key] = json.dumps(json.loads(val))  # normalize
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(val, datetime):
                row[key] = val.isoformat()
        await pg.execute(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('$'+str(i+1) for i in range(len(cols)))}) "
            f"ON CONFLICT DO NOTHING",
            *[row[c] for c in cols],
        )


async def main() -> None:
    print(f"Reading SQLite: {SQLITE_PATH}")
    sqlite = sqlite3.connect(SQLITE_PATH)
    sqlite.row_factory = sqlite3.Row

    print(f"Connecting to PostgreSQL: {PG_DSN[:PG_DSN.rfind('@')+1]}...")
    pg = await asyncpg.connect(PG_DSN)

    for table in TABLES:
        try:
            rows = sqlite_fetch(sqlite, table)
            await pg_insert(pg, table, rows)
            print(f"  {table}: {len(rows)} rows migrated")
        except Exception as exc:
            print(f"  {table}: ERROR {exc}")

    await pg.close()
    sqlite.close()
    print("Done. Run `alembic upgrade head` on the PG database.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())