import os
import sys

import psycopg
from dotenv import load_dotenv


def main():
    # Load DATABASE_URL from the project's .env file.
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("FAIL: DATABASE_URL is not configured.")
        sys.exit(1)

    try:
        with psycopg.connect(
            database_url,
            connect_timeout=10,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version(), NOW()")
                version, database_time = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename
                    """
                )
                tables = [row[0] for row in cursor.fetchall()]

        print("SUCCESS: Connected to PostgreSQL.")
        print("Database time:", database_time)
        print("PostgreSQL version:", version.split(",")[0])
        print("\nTables found:")

        for table in tables:
            print("-", table)

        expected_tables = {
            "suppliers",
            "inventory",
            "driver_locations",
            "plans",
            "dispatches",
            "audit_events",
        }

        missing = expected_tables - set(tables)

        if missing:
            print("\nWARNING: Missing tables:", ", ".join(sorted(missing)))
            print("Apply db/schema.sql using your database SQL editor.")
            sys.exit(1)

        print("\nSUCCESS: All six expected tables exist.")

    except psycopg.Error as exc:
        # Print the error type, but never print the connection string.
        print("FAIL: PostgreSQL connection or query failed.")
        print("Error type:", type(exc).__name__)
        print("Details:", str(exc).splitlines()[0])
        sys.exit(1)


if __name__ == "__main__":
    main()