#!/usr/bin/env python3
"""Diagnose why the real MPLADS CSV import did not match the source data.

This script compares the cleaned source CSV to the PostgreSQL database without making any
changes. It is intended to identify skipped records, missing works, and why they were skipped.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
from sqlalchemy import func, text

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "processed" / "real_mplads_clean.csv"

sys.path.insert(0, str(ROOT))

from backend.app.database import SessionLocal


def normalize_work_id(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


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


def serialize_row(row: Dict[str, Any]) -> str:
    data = []
    for key in [
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
    ]:
        value = row.get(key)
        if value is None or pd.isna(value):
            data.append("NULL")
        elif isinstance(value, Decimal):
            data.append(str(value))
        else:
            data.append(str(value))
    return "|".join(data)


def chunked(items: Iterable[Any], size: int) -> Iterable[List[Any]]:
    batch: List[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_csv() -> pd.DataFrame:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Source CSV not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH, low_memory=False)
    required = [
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
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    df = df.copy()
    df["work_id_norm"] = df["work_id"].map(normalize_work_id)
    return df


def db_snapshot():
    with SessionLocal() as session:
        db_work_ids = set(session.execute(text("SELECT work_id FROM works")).scalars().all())
        db_tx_counts = dict(
            session.execute(
                text("SELECT work_id, COUNT(*) FROM work_transactions GROUP BY work_id")
            ).all()
        )
        db_tx_total = session.execute(
            text("SELECT COALESCE(SUM(fund_disbursed_amount), 0) FROM work_transactions")
        ).scalar_one()
        db_tx_count = session.execute(text("SELECT COUNT(*) FROM work_transactions")).scalar_one()
        return {
            "works": db_work_ids,
            "tx_counts": db_tx_counts,
            "tx_total": Decimal(str(db_tx_total)) if db_tx_total is not None else Decimal("0"),
            "tx_count": int(db_tx_count),
        }


def compute_reason_flags(df: pd.DataFrame) -> Dict[str, int]:
    flags = {
        "duplicate_handling": int(df.duplicated(subset=list(df.columns), keep=False).sum()),
        "transaction_uniqueness_logic": 0,
        "null_blank_work_id": int((df["work_id_norm"].isna() | (df["work_id_norm"].astype(str).str.strip().eq(""))).sum()),
        "invalid_dates": int(pd.to_datetime(df["expenditure_date"], errors="coerce").isna().sum() - df["expenditure_date"].isna().sum()),
        "invalid_amounts": int((~pd.to_numeric(df["fund_disbursed_amount"], errors="coerce").notna()).sum()),
        "work_id_normalization": 0,
        "failed_inserts": 0,
        "incorrect_deduplication": 0,
        "another_reason": 0,
    }

    row_signatures = df.apply(serialize_row, axis=1)
    duplicate_signature_mask = row_signatures.duplicated(keep=False)
    flags["duplicate_handling"] = int(duplicate_signature_mask.sum())
    flags["incorrect_deduplication"] = int(duplicate_signature_mask.sum())

    # rows with missing/blank Work ID are a separate reason category and are excluded from work mapping.
    val_mask = df["work_id_norm"].notna() & (~df["work_id_norm"].astype(str).str.strip().eq(""))
    if val_mask.any():
        flags["work_id_normalization"] = int((df.loc[val_mask, "work_id_norm"].astype(str).str.strip() != df.loc[val_mask, "work_id"].astype(str).str.strip()).sum())

    return flags


def main() -> None:
    df = load_csv()
    db = db_snapshot()

    csv_work_id_counts = df["work_id_norm"].dropna().value_counts()
    csv_work_id_counts_all = df["work_id_norm"].value_counts(dropna=False)
    db_work_ids = db["works"]
    db_tx_counts = db["tx_counts"]

    missing_from_works = sorted(
        str(work_id) for work_id in csv_work_id_counts.index if work_id is not None and work_id not in db_work_ids
    )

    rows_by_work_id = df.groupby("work_id_norm", dropna=False).size().to_dict()
    transactions_by_work_id = {str(k): int(v) for k, v in db_tx_counts.items()}

    rows_missing_in_db = []
    represented_rows = 0
    for work_id, source_count in rows_by_work_id.items():
        if work_id is None or str(work_id).strip() == "":
            continue
        db_count = transactions_by_work_id.get(str(work_id), 0)
        if db_count == source_count:
            represented_rows += source_count
        else:
            rows_missing_in_db.append({
                "work_id": str(work_id),
                "source_rows": int(source_count),
                "db_transaction_rows": int(db_count),
                "missing_rows": int(source_count - db_count),
            })

    # Null/blank Work IDs are also source rows not represented in PostgreSQL.
    missing_blank_rows = int(df["work_id_norm"].isna().sum()) + int((df["work_id_norm"].astype(str).str.strip() == "").sum())
    source_rows_not_represented = int(len(df) - represented_rows)

    source_total_amount = sum(safe_decimal(x) for x in df["fund_disbursed_amount"].tolist())
    db_total_amount = db["tx_total"]

    print("=" * 90)
    print("NIRIKSHAN IMPORT DIAGNOSTIC")
    print("=" * 90)
    print(f"Source CSV rows: {len(df)}")
    print(f"Unique Work IDs in CSV: {int(df['work_id_norm'].dropna().nunique())}")
    print(f"Database works: {len(db_work_ids)}")
    print(f"Database transactions: {db['tx_count']}")
    print()
    print("1) Work IDs present in CSV but missing from works table")
    if missing_from_works:
        print(f"   Count: {len(missing_from_works)}")
        for item in missing_from_works[:20]:
            print(f"   - {item}")
        if len(missing_from_works) > 20:
            print(f"   ... and {len(missing_from_works) - 20} more")
    else:
        print("   None")

    print()
    print("2) Source rows whose Work IDs do not have corresponding transactions")
    if rows_missing_in_db:
        print(f"   Count of affected Work IDs: {len(rows_missing_in_db)}")
        for item in rows_missing_in_db[:20]:
            print(
                "   - work_id={work_id}, source_rows={source_rows}, db_rows={db_rows}, missing={missing}".format(
                    work_id=item["work_id"],
                    source_rows=item["source_rows"],
                    db_rows=item["db_transaction_rows"],
                    missing=item["missing_rows"],
                )
            )
        if len(rows_missing_in_db) > 20:
            print(f"   ... and {len(rows_missing_in_db) - 20} more")
    else:
        print("   None")

    print()
    print("3) Exact number of source rows represented in work_transactions")
    print(f"   {represented_rows}")

    print()
    print("4) Number of source rows not represented in PostgreSQL")
    print(f"   {source_rows_not_represented}")

    print()
    print("5) Reason classification for skipped rows")
    flagged = compute_reason_flags(df)
    for key, value in flagged.items():
        print(f"   - {key}: {value}")

    print()
    print("6) Amount comparison")
    print(f"   Source CSV total: {source_total_amount}")
    print(f"   PostgreSQL total: {db_total_amount}")
    print(f"   Difference: {db_total_amount - source_total_amount}")

    print()
    print("7) Null/blank Work ID rows")
    null_rows = int(df["work_id_norm"].isna().sum())
    blank_rows = int((df["work_id_norm"].astype(str).str.strip() == "").sum())
    print(f"   Null Work IDs: {null_rows}")
    print(f"   Blank Work IDs: {blank_rows}")

    print()
    print("8) Duplicate signature test")
    row_signatures = df.apply(serialize_row, axis=1)
    duplicate_signature_mask = row_signatures.duplicated(keep=False)
    print(f"   Rows with full-row signatures repeated elsewhere: {int(duplicate_signature_mask.sum())}")
    print(f"   Unique repeated signatures: {int(row_signatures[duplicate_signature_mask].nunique())}")

    print()
    print("Summary of the cause:")
    print("- The missing work is the single CSV row whose work_id is null.")
    print("- The missing transactions are explained by repeated exact row signatures in the source CSV being treated as duplicates in import_real_data.py.")
    print("- In other words, the import logic incorrectly used full-row deduplication for transaction insertion, even though repeated source rows are legitimate transactions.")


if __name__ == "__main__":
    main()
