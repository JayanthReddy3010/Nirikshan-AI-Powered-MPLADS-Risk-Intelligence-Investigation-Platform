#!/usr/bin/env python3
"""Read-only validation report for the imported MPLADS dataset."""

from __future__ import annotations

import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "processed" / "real_mplads_clean.csv"
sys.path.insert(0, str(ROOT))

from backend.app.database import SessionLocal


def normalize_work_id(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip()
    return normalized if normalized else None


def load_valid_source_row_numbers() -> tuple[int, set[int]]:
    source = pd.read_csv(CSV_PATH, low_memory=False)
    if "work_id" not in source.columns:
        raise ValueError("Clean CSV is missing the work_id column.")

    valid_row_numbers = {
        index + 1
        for index, value in enumerate(source["work_id"])
        if normalize_work_id(value) is not None
    }
    return len(source), valid_row_numbers


def fetch_scalar(session, query: str) -> Any:
    return session.execute(text(query)).scalar_one()


def fetch_rows(session, query: str) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in session.execute(text(query)).all()]


def validate() -> None:
    source_rows, valid_source_row_numbers = load_valid_source_row_numbers()

    with SessionLocal() as session:
        total_works = fetch_scalar(session, "SELECT COUNT(*) FROM works")
        total_transactions = fetch_scalar(session, "SELECT COUNT(*) FROM work_transactions")

        transaction_distribution = fetch_rows(
            session,
            """
            SELECT
                COUNT(*) FILTER (WHERE transaction_count = 0),
                COUNT(*) FILTER (WHERE transaction_count = 1),
                COUNT(*) FILTER (WHERE transaction_count > 1)
            FROM (
                SELECT w.work_id, COUNT(wt.id) AS transaction_count
                FROM works w
                LEFT JOIN work_transactions wt ON wt.work_id = w.work_id
                GROUP BY w.work_id
            ) work_counts;
            """,
        )[0]

        orphan_transactions = fetch_scalar(
            session,
            """
            SELECT COUNT(*)
            FROM work_transactions wt
            LEFT JOIN works w ON w.work_id = wt.work_id
            WHERE w.work_id IS NULL;
            """,
        )
        duplicate_source_rows = fetch_scalar(
            session,
            """
            SELECT COUNT(*)
            FROM (
                SELECT source_row_number
                FROM work_transactions
                GROUP BY source_row_number
                HAVING COUNT(*) > 1
            ) duplicates;
            """,
        )
        null_blank_work_ids = fetch_scalar(
            session,
            """
            SELECT COUNT(*)
            FROM work_transactions
            WHERE work_id IS NULL OR BTRIM(work_id) = '';
            """,
        )
        null_expenditure_dates = fetch_scalar(
            session,
            "SELECT COUNT(*) FROM work_transactions WHERE expenditure_date IS NULL",
        )
        null_blank_vendors = fetch_scalar(
            session,
            """
            SELECT COUNT(*)
            FROM work_transactions
            WHERE vendor_name IS NULL OR BTRIM(vendor_name) = '';
            """,
        )
        payment_status_counts = fetch_rows(
            session,
            """
            SELECT COALESCE(payment_status, '<NULL>') AS payment_status, COUNT(*)
            FROM work_transactions
            GROUP BY payment_status
            ORDER BY COUNT(*) DESC, payment_status;
            """,
        )
        total_amount = fetch_scalar(
            session,
            "SELECT COALESCE(SUM(fund_disbursed_amount), 0) FROM work_transactions",
        )
        top_works = fetch_rows(
            session,
            """
            SELECT w.work_id, COALESCE(SUM(wt.fund_disbursed_amount), 0), COUNT(wt.id)
            FROM works w
            JOIN work_transactions wt ON wt.work_id = w.work_id
            GROUP BY w.work_id
            ORDER BY SUM(wt.fund_disbursed_amount) DESC NULLS LAST, w.work_id
            LIMIT 10;
            """,
        )
        top_vendors = fetch_rows(
            session,
            """
            SELECT COALESCE(NULLIF(BTRIM(vendor_name), ''), '<NULL/BLANK>'),
                   COALESCE(SUM(fund_disbursed_amount), 0), COUNT(*)
            FROM work_transactions
            GROUP BY COALESCE(NULLIF(BTRIM(vendor_name), ''), '<NULL/BLANK>')
            ORDER BY SUM(fund_disbursed_amount) DESC NULLS LAST, 1
            LIMIT 10;
            """,
        )
        top_states = fetch_rows(
            session,
            """
            SELECT COALESCE(NULLIF(BTRIM(w.state), ''), '<NULL/BLANK>'),
                   COALESCE(SUM(wt.fund_disbursed_amount), 0), COUNT(wt.id)
            FROM work_transactions wt
            JOIN works w ON w.work_id = wt.work_id
            GROUP BY COALESCE(NULLIF(BTRIM(w.state), ''), '<NULL/BLANK>')
            ORDER BY SUM(wt.fund_disbursed_amount) DESC NULLS LAST, 1
            LIMIT 10;
            """,
        )
        database_source_rows = [
            int(row[0])
            for row in fetch_rows(
                session,
                "SELECT source_row_number FROM work_transactions ORDER BY source_row_number",
            )
        ]
        foreign_key_check = fetch_rows(
            session,
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
            """,
        )[0][0]

    database_source_row_counts = Counter(database_source_rows)
    duplicate_source_row_values = {
        row_number for row_number, count in database_source_row_counts.items() if count > 1
    }
    database_source_row_set = set(database_source_rows)
    missing_source_rows = valid_source_row_numbers - database_source_row_set
    unexpected_source_rows = database_source_row_set - valid_source_row_numbers
    represented_exactly_once = (
        not missing_source_rows
        and not unexpected_source_rows
        and not duplicate_source_row_values
        and len(database_source_rows) == len(valid_source_row_numbers)
    )

    print("=" * 88)
    print("NIRIKSHAN FINAL REAL DATA DATABASE VALIDATION")
    print("=" * 88)
    print("Read-only validation: no INSERT, UPDATE, DELETE, DDL, reset, or CSV writes performed.")
    print()
    print("1. Total works")
    print(f"   {total_works}")
    print("2. Total transactions")
    print(f"   {total_transactions}")
    print()
    print("3. Works by transaction count")
    print(f"   - 0 transactions: {transaction_distribution[0]}")
    print(f"   - exactly 1 transaction: {transaction_distribution[1]}")
    print(f"   - more than 1 transaction: {transaction_distribution[2]}")
    print()
    print("4. Transactions with work_id missing from works")
    print(f"   {orphan_transactions}")
    print("5. Duplicate source_row_number values")
    print(f"   {duplicate_source_rows}")
    print("6. NULL/blank work_id values in work_transactions")
    print(f"   {null_blank_work_ids}")
    print("7. Transactions with NULL expenditure_date")
    print(f"   {null_expenditure_dates}")
    print("8. Transactions with NULL/blank vendor_name")
    print(f"   {null_blank_vendors}")
    print("9. Transactions by payment_status")
    for status, count in payment_status_counts:
        print(f"   - {status}: {count}")
    print("10. Total fund_disbursed_amount")
    print(f"   {Decimal(str(total_amount)):.2f}")

    print("11. Top 10 works by total transaction amount")
    for work_id, amount, count in top_works:
        print(f"   - {work_id}: {Decimal(str(amount)):.2f} ({count} transactions)")
    print("12. Top 10 vendors by total transaction amount")
    for vendor, amount, count in top_vendors:
        print(f"   - {vendor}: {Decimal(str(amount)):.2f} ({count} transactions)")
    print("13. Top 10 states by total transaction amount")
    for state, amount, count in top_states:
        print(f"   - {state}: {Decimal(str(amount)):.2f} ({count} transactions)")

    print("14. Every valid source row represented exactly once")
    print(f"   - source rows: {source_rows}")
    print(f"   - valid source rows: {len(valid_source_row_numbers)}")
    print(f"   - database source rows: {len(database_source_rows)}")
    print(f"   - missing valid source rows: {len(missing_source_rows)}")
    print(f"   - unexpected database source rows: {len(unexpected_source_rows)}")
    print(f"   - duplicate source row values: {len(duplicate_source_row_values)}")
    print(f"   - represented exactly once: {represented_exactly_once}")
    print("15. Foreign key: work_transactions.work_id -> works.work_id")
    print(f"   {bool(foreign_key_check)}")


if __name__ == "__main__":
    validate()
