#!/usr/bin/env python3
"""Run Alembic migrations and ensure Better Auth tables exist (Docker startup)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg

SQL_PATH = Path(
    os.environ.get(
        "BETTER_AUTH_SQL_PATH",
        "/scripts/create-better-auth-tables.sql",
    ),
)


async def ensure_better_auth_tables() -> None:
    sync_url = os.environ.get("DATABASE_URL_SYNC")
    if not sync_url:
        print("DATABASE_URL_SYNC is required", file=sys.stderr)
        raise SystemExit(1)

    if not SQL_PATH.is_file():
        print(f"Better Auth SQL not found at {SQL_PATH}, skipping DDL")
        return

    sql = SQL_PATH.read_text()
    conn = await asyncpg.connect(sync_url)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()
    print("Better Auth tables ensured")


def run_alembic() -> None:
    rc = subprocess.call(["alembic", "upgrade", "head"])
    if rc != 0:
        raise SystemExit(rc)


def main() -> None:
    run_alembic()
    asyncio.run(ensure_better_auth_tables())


if __name__ == "__main__":
    main()
