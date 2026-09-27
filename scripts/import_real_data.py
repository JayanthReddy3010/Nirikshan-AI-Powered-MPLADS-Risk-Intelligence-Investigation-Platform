#!/usr/bin/env python3
"""Import the cleaned MPLADS dataset into PostgreSQL using SQLAlchemy models.

This import is intentionally strict about data integrity:
- one work per valid unique Work ID
- one transaction per valid source CSV row with a valid Work ID
- source_row_number is used for safe reruns and exact row accountability
- rows with missing Work IDs are logged to import_errors rather than silently discarded
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import func, text

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "processed" / "real_mplads_clean.csv"

sys.path.insert(0, str(ROOT))

from backend.app.database import Base, SessionLocal
from backend.app.models import ImportErrorRecord, Work, WorkTransaction


def normalize_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def normalize_date(value: Any):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def normalize_amount(value: Any) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace(",", "").replace("₹", "").replace(" ", "")
    if cleaned in {"", "-", "--"}:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def safe_decimal(value: Any) -> Decimal:
    if value is None or pd.isna(value):
        return Decimal("0")
    text = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
    if text in {"", "-", "--"}:
        return Decimal("0")
    try:
        return Decimal(text)
    except Exception:
        return Decimal("0")


def chunked(iterable: Iterable[Any], size: int) -> Iterable[List[Any]]:
    batch: List[Any] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def reset_database(session) -> None:
    print("Resetting works, work_transactions, and import_errors tables...")
    session.execute(text("DELETE FROM work_transactions"))
    session.execute(text("DELETE FROM import_errors"))
    session.execute(text("DELETE FROM works"))
    session.commit()
    print("Reset complete.")


def import_dataset(reset_requested: bool = False, confirm_reset: bool = False) -> Dict[str, Any]:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Clean CSV not found: {CSV_PATH}")

    print(f"Reading source CSV: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, low_memory=False)
    if df.empty:
        raise ValueError("Source CSV is empty.")

    required_columns = [
        "work_id",
        "state",
        "mp_name",
        "constituency",
        "work",
        "ida",
        "expenditure_date",
        "vendor_name",
        "payment_status",
        "fund_disbursed_amount",
    ]
    missing_required = [col for col in required_columns if col not in df.columns]
    if missing_required:
        raise ValueError(f"The cleaned CSV is missing required columns: {missing_required}")

    df = df.reset_index().rename(columns={"index": "source_row_number"})
    df["source_row_number"] = df["source_row_number"] + 1

    rows_with_missing_work_id = 0
    valid_rows = 0
    work_rows_by_id: Dict[str, Dict[str, Any]] = {}
    transaction_rows_to_insert: List[Dict[str, Any]] = []
    import_errors_to_insert: List[Dict[str, Any]] = []

    for row in df.to_dict(orient="records"):
        source_row_number = int(row["source_row_number"])
        work_id = normalize_text(row.get("work_id"))

        if not work_id:
            rows_with_missing_work_id += 1
            details = {
                "state": normalize_text(row.get("state")),
                "mp_name": normalize_text(row.get("mp_name")),
                "constituency": normalize_text(row.get("constituency")),
                "work": normalize_text(row.get("work")),
                "ida": normalize_text(row.get("ida")),
                "expenditure_date": normalize_date(row.get("expenditure_date")),
                "vendor_name": normalize_text(row.get("vendor_name")),
                "payment_status": normalize_text(row.get("payment_status")),
                "fund_disbursed_amount": str(normalize_amount(row.get("fund_disbursed_amount"))) if normalize_amount(row.get("fund_disbursed_amount")) is not None else None,
            }
            import_errors_to_insert.append({
                "source_row_number": source_row_number,
                "reason": "Missing Work ID",
                "details": json.dumps(details, default=str, ensure_ascii=False),
            })
            continue

        valid_rows += 1
        work_record = {
            "work_id": work_id,
            "state": normalize_text(row.get("state")),
            "mp_name": normalize_text(row.get("mp_name")),
            "constituency": normalize_text(row.get("constituency")),
            "work": normalize_text(row.get("work")),
            "ida": normalize_text(row.get("ida")),
        }
        if work_id not in work_rows_by_id:
            work_rows_by_id[work_id] = work_record

        transaction_rows_to_insert.append({
            "source_row_number": source_row_number,
            "work_id": work_id,
            "expenditure_date": normalize_date(row.get("expenditure_date")),
            "vendor_name": normalize_text(row.get("vendor_name")),
            "payment_status": normalize_text(row.get("payment_status")),
            "fund_disbursed_amount": normalize_amount(row.get("fund_disbursed_amount")),
        })

    session = SessionLocal()
    try:
        Base.metadata.create_all(bind=session.bind, checkfirst=True)

        if reset_requested:
            if not confirm_reset:
                raise RuntimeError("A destructive reset requires both --reset and --confirm. No database reset was executed.")
            reset_database(session)

        existing_work_ids = set(session.execute(text("SELECT work_id FROM works")).scalars().all())
        existing_transaction_source_rows = set(
            session.execute(text("SELECT source_row_number FROM work_transactions")).scalars().all()
        )
        existing_import_error_rows = set(
            session.execute(text("SELECT source_row_number FROM import_errors")).scalars().all()
        )

        works_to_insert: List[Dict[str, Any]] = []
        for row in work_rows_by_id.values():
            work_id = row["work_id"]
            if work_id in existing_work_ids:
                continue
            works_to_insert.append(row)

        import_errors_to_write: List[Dict[str, Any]] = []
        for error_row in import_errors_to_insert:
            if error_row["source_row_number"] in existing_import_error_rows:
                continue
            import_errors_to_write.append(error_row)

        transactions_to_write: List[Dict[str, Any]] = []
        for row in transaction_rows_to_insert:
            source_row_number = row["source_row_number"]
            if source_row_number in existing_transaction_source_rows:
                continue
            transactions_to_write.append(row)

        unique_valid_work_ids = len(work_rows_by_id)
        print(f"Valid source rows: {valid_rows}")
        print(f"Unique valid Work IDs: {unique_valid_work_ids}")
        print(f"Works inserted: {len(works_to_insert)}")
        print(f"Transactions inserted: {len(transactions_to_write)}")
        print(f"Import errors: {len(import_errors_to_write)}")

        if works_to_insert:
            for batch in chunked(works_to_insert, 1000):
                session.bulk_insert_mappings(Work, batch)
                session.flush()

        if import_errors_to_write:
            print(f"Recording import errors: {len(import_errors_to_write)}")
            for batch in chunked(import_errors_to_write, 500):
                session.bulk_insert_mappings(ImportErrorRecord, batch)
                session.flush()

        if transactions_to_write:
            print(f"Inserting transactions: {len(transactions_to_write)}")
            for batch in chunked(transactions_to_write, 1000):
                session.bulk_insert_mappings(WorkTransaction, batch)
                session.flush()

        session.commit()

        work_count = session.execute(func.count(Work.id)).scalar_one()
        transaction_count = session.execute(func.count(WorkTransaction.id)).scalar_one()
        import_error_count = session.execute(func.count(ImportErrorRecord.id)).scalar_one()

        valid_amount_total = sum(
            safe_decimal(value)
            for value in df.loc[df["work_id"].notna() & df["work_id"].astype(str).str.strip().ne(""), "fund_disbursed_amount"].tolist()
        )

        database_total_amount = session.execute(
            text("SELECT COALESCE(SUM(fund_disbursed_amount), 0) FROM work_transactions")
        ).scalar_one() or Decimal("0")

        validation = {
            "source_rows_total": int(len(df)),
            "rows_with_valid_work_id": int(valid_rows),
            "rows_with_missing_work_id": int(rows_with_missing_work_id),
            "unique_valid_work_ids": int(unique_valid_work_ids),
            "database_works": int(work_count),
            "database_transactions": int(transaction_count),
            "database_import_errors": int(import_error_count),
            "works_inserted": int(len(works_to_insert)),
            "transactions_inserted": int(len(transactions_to_write)),
            "import_errors_inserted": int(len(import_errors_to_write)),
            "source_total_fund_amount_for_valid_rows": float(valid_amount_total),
            "database_total_transaction_amount": float(database_total_amount),
            "difference": float(database_total_amount - valid_amount_total),
        }

        print("\nValidation summary:")
        for key, value in validation.items():
            print(f" - {key}: {value}")

        return validation

    except Exception as exc:
        session.rollback()
        raise RuntimeError(f"Import failed and transaction was rolled back: {exc}") from exc
    finally:
        session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import cleaned MPLADS CSV data into PostgreSQL while preserving one transaction per valid source row.")
    parser.add_argument("--reset", action="store_true", help="Reset works/work_transactions/import_errors tables before importing. Requires --confirm.")
    parser.add_argument("--confirm", action="store_true", help="Confirm destructive reset of the development database. Must be paired with --reset.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT / "backend" / ".env")
    print("Connecting to PostgreSQL using SQLAlchemy configuration...")
    print(f"Database URL configured: {os.getenv('DATABASE_URL')}")

    if args.reset and not args.confirm:
        print("Reset requested but not confirmed. No destructive action was executed.")
        print("Use: python scripts/import_real_data.py --reset --confirm")
        return

    try:
        import_dataset(reset_requested=args.reset, confirm_reset=args.confirm)
        print("\nImport completed successfully.")
    except Exception as exc:
        print(f"\nERROR: {exc}")
        raise


if __name__ == "__main__":
    main()
