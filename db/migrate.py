"""Versioned PostgreSQL migration runner for ReliefRoute."""

import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATION_PATTERN = re.compile(r"^(\d{3,})_([a-zA-Z0-9_-]+)\.sql$")


def discover_migrations() -> list[tuple[str, Path]]:
    """Discover SQL migrations in version order."""
    if not MIGRATIONS_DIR.is_dir():
        raise RuntimeError(f"Migration directory not found: {MIGRATIONS_DIR}")

    migrations: list[tuple[str, Path]] = []

    for path in MIGRATIONS_DIR.iterdir():
        if not path.is_file():
            continue

        match = MIGRATION_PATTERN.fullmatch(path.name)
        if match:
            migrations.append((match.group(1), path))

    migrations.sort(key=lambda item: int(item[0]))

    versions = [version for version, _ in migrations]
    if len(versions) != len(set(versions)):
        raise RuntimeError("Duplicate migration versions found.")

    return migrations


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is not configured.", file=sys.stderr)
        return 1

    try:
        migrations = discover_migrations()
        if not migrations:
            print("ERROR: No SQL migrations found.", file=sys.stderr)
            return 1

        with psycopg.connect(database_url, connect_timeout=10) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            for version, path in migrations:
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

                existing = conn.execute(
                    """
                    SELECT filename, checksum
                    FROM schema_migrations
                    WHERE version = %s
                    """,
                    (version,),
                ).fetchone()

                if existing:
                    filename, old_checksum = existing
                    if filename != path.name or old_checksum != checksum:
                        raise RuntimeError(
                            f"Migration {path.name} differs from its recorded version. "
                            "Do not edit applied migrations; create a new migration."
                        )
                    print(f"SKIP {path.name} (already applied)")
                    continue

                print(f"Applying {path.name}...")
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute(
                        """
                        INSERT INTO schema_migrations
                            (version, filename, checksum)
                        VALUES (%s, %s, %s)
                        """,
                        (version, path.name, checksum),
                    )
                print(f"APPLIED {path.name}")

        print("Migration run completed successfully.")
        return 0

    except (psycopg.Error, OSError, RuntimeError) as exc:
        print(
            f"ERROR: Migration failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
