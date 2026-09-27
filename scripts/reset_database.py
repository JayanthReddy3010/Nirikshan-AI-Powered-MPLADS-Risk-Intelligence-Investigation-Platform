#!/usr/bin/env python3
"""Safely reset the Nirikshan development tables.

This script intentionally deletes only the Nirikshan tables used by the current model layer:
- work_transactions
- import_errors
- works

It then recreates them from the current SQLAlchemy metadata using Base.metadata.create_all(...).
This operation is destructive for the development database only and is guarded by --confirm.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.database import Base, SessionLocal
from backend.app.models import ImportErrorRecord, Work, WorkTransaction  # noqa: F401

# Force the model classes to register with Base.metadata before create_all().
# Without importing these classes, SQLAlchemy has no mapped tables to create.


def ensure_models_loaded() -> None:
    """Ensure the project model classes are imported and registered with SQLAlchemy metadata."""
    _ = (Work, WorkTransaction, ImportErrorRecord)

TARGET_TABLES = ["work_transactions", "import_errors", "works"]


def safe_drop(session) -> None:
    """Drop only the Nirikshan development tables used by this project."""
    for table_name in TARGET_TABLES:
        session.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;'))
    session.commit()


def verify_schema(session) -> dict:
    tables = session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() "
            "AND table_name IN ('works', 'work_transactions', 'import_errors') "
            "ORDER BY table_name;"
        )
    ).scalars().all()

    columns = session.execute(
        text(
            "SELECT column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'work_transactions' "
            "ORDER BY ordinal_position;"
        )
    ).scalars().all()

    fk_exists = session.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.table_schema = ccu.table_schema
                WHERE tc.table_schema = current_schema()
                  AND tc.table_name = 'work_transactions'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'work_id'
                  AND ccu.table_name = 'works'
                  AND ccu.column_name = 'work_id'
            );
            """
        )
    ).scalar()

    result = {
        "works_exists": "works" in tables,
        "work_transactions_exists": "work_transactions" in tables,
        "import_errors_exists": "import_errors" in tables,
        "source_row_number_exists": "source_row_number" in columns,
        "work_id_fk_to_works_exists": bool(fk_exists),
        "tables_found": tables,
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset only the Nirikshan development tables and recreate them from the current SQLAlchemy metadata."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required explicit confirmation before dropping and recreating the Nirikshan development tables.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Nirikshan database reset check")
    print("Target tables: work_transactions, import_errors, works")

    if not args.confirm:
        print("\nNo destructive action performed.")
        print("To reset the development tables, run:")
        print("    python scripts/reset_database.py --confirm")
        return

    print("\nConfirmation received. Proceeding with database reset...")

    ensure_models_loaded()

    session = SessionLocal()
    try:
        safe_drop(session)
        Base.metadata.create_all(bind=session.bind, checkfirst=False)

        result = verify_schema(session)

        print("\nPost-reset verification:")
        print(f" - works exists: {result['works_exists']}")
        print(f" - work_transactions exists: {result['work_transactions_exists']}")
        print(f" - import_errors exists: {result['import_errors_exists']}")
        print(f" - source_row_number exists in work_transactions: {result['source_row_number_exists']}")
        print(f" - work_transactions.work_id foreign key to works.work_id: {result['work_id_fk_to_works_exists']}")

        if result["work_transactions_exists"]:
            print("\nRecreated work_transactions columns:")
            columns = session.execute(
                text(
                    "SELECT column_name "
                    "FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'work_transactions' "
                    "ORDER BY ordinal_position;"
                )
            ).scalars().all()
            print(" - " + "\n - ".join(columns))

        if not all(
            [
                result["works_exists"],
                result["work_transactions_exists"],
                result["import_errors_exists"],
                result["source_row_number_exists"],
                result["work_id_fk_to_works_exists"],
            ]
        ):
            raise RuntimeError(
                "Schema verification failed after recreation. "
                f"Result={result}"
            )

        print("\nReset and recreation complete for the Nirikshan development tables only.")
    except Exception as exc:
        session.rollback()
        raise RuntimeError(f"Reset failed: {exc}") from exc
    finally:
        session.close()


if __name__ == "__main__":
    # Ensure environment is loaded before connecting to PostgreSQL.
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
    main()
