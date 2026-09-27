#!/usr/bin/env python3
"""Audit the real MPLADS dataset and produce a cleaned CSV copy.

This script is intentionally limited to dataset inspection and data preparation.
It does not create database tables, endpoints, ML models, or synthetic data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw" / "real_mplads.csv"
AUDIT_JSON = ROOT / "data" / "processed" / "real_data_audit.json"
CLEAN_CSV = ROOT / "data" / "processed" / "real_mplads_clean.csv"


def normalize_name(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().lower().replace("’", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def find_column(df: pd.DataFrame, aliases: Iterable[str], required: bool = False) -> Optional[str]:
    alias_list = [normalize_name(alias) for alias in aliases]
    for column in df.columns:
        candidate = normalize_name(column)
        if candidate in alias_list:
            return str(column)
    for column in df.columns:
        candidate = normalize_name(column)
        for alias in alias_list:
            if alias in candidate or candidate in alias:
                return str(column)
    if required:
        raise KeyError(f"Required column not found. Expected one of: {list(aliases)}")
    return None


def safe_strip(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def clean_numeric_amount(series: pd.Series) -> pd.Series:
    cleaned = series.copy()
    cleaned = cleaned.map(lambda x: x.strip() if isinstance(x, str) else x)
    cleaned = cleaned.map(
        lambda x: re.sub(r"[₹,\s]", "", str(x)).replace("(", "-").replace(")", "") if not pd.isna(x) else x
    )
    cleaned = cleaned.map(lambda x: re.sub(r"[^0-9.\-]", "", str(x)) if not pd.isna(x) else x)
    cleaned = pd.to_numeric(cleaned, errors="coerce")
    return cleaned


def percent_of(value: float, total: float) -> float:
    if total == 0 or pd.isna(value):
        return 0.0
    return round((value / total) * 100, 4)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    AUDIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    CLEAN_CSV.parent.mkdir(parents=True, exist_ok=True)

    if not RAW_CSV.exists():
        raise FileNotFoundError(f"Source CSV not found: {RAW_CSV}")

    print(f"Reading dataset from: {RAW_CSV}")
    df = pd.read_csv(RAW_CSV, low_memory=False)

    original_cols = list(df.columns)
    print(f"Rows: {len(df)}")
    print(f"Columns: {len(df.columns)}")
    print("Original columns:")
    for col in original_cols:
        print(f" - {col}")
    print("Data types:")
    print(df.dtypes.to_string())

    # Determine required source columns using robust matching
    state_col = find_column(df, ["State", "State Name"], required=False)
    mp_col = find_column(df, ["Hon'ble Members of Parliament", "Honble Members of Parliament", "Member of Parliament", "MP Name", "Hon'ble MP", "MP"], required=False)
    constituency_col = find_column(df, ["Constituency", "Constituency Name"], required=False)
    work_col = find_column(df, ["Work", "Work Type", "Work Description", "Description of Work"], required=False)
    work_id_col = find_column(df, ["Work ID", "Work Id", "WorkID"], required=False)
    ida_col = find_column(df, ["IDA", "IDA Name"], required=False)
    vendor_col = find_column(df, ["Vendor Name", "Vendor", "Name of Vendor"], required=False)
    payment_status_col = find_column(df, ["Payment Status", "Status"], required=False)
    date_col = find_column(df, ["Expenditure Date", "Date of Expenditure", "Expenditure date", "Date"], required=False)
    amount_col = find_column(df, ["Fund Disbursed Amount", "Amount", "Fund Amount", "Total Amount", "Amount Disbursed"], required=False)

    # Missing value analysis for every column
    missing_summary = []
    for column in df.columns:
        series = df[column]
        missing_count = int(series.isna().sum())
        missing_pct = round((missing_count / len(df)) * 100, 4) if len(df) else 0.0
        missing_summary.append({
            "column": column,
            "missing_count": missing_count,
            "missing_percentage": missing_pct,
        })

    print("\nMissing value analysis for every column:")
    for item in missing_summary:
        print(f" - {item['column']}: missing={item['missing_count']}, percentage={item['missing_percentage']}%")

    # Unique counts for required fields
    unique_targets = {
        "State": state_col,
        "Hon'ble Members of Parliament": mp_col,
        "Constituency": constituency_col,
        "Work": work_col,
        "Work ID": work_id_col,
        "IDA": ida_col,
        "Vendor Name": vendor_col,
        "Payment Status": payment_status_col,
    }
    print("\nUnique counts for key fields:")
    for label, col in unique_targets.items():
        if col is None:
            print(f" - {label}: not found in source CSV")
            continue
        value = df[col]
        unique_count = int(value.nunique(dropna=True))
        print(f" - {label}: {unique_count}")

    # Work ID analysis
    work_id_series = pd.Series([], dtype="object")
    if work_id_col:
        work_id_series = df[work_id_col].map(safe_strip)
    else:
        work_id_series = pd.Series([None] * len(df), index=df.index)

    work_id_total = int(work_id_series.notna().sum())
    unique_work_ids = int(work_id_series.dropna().nunique())
    work_id_counts = work_id_series.dropna().value_counts()
    duplicate_work_ids = int((work_id_counts > 1).sum())
    max_records_for_one_work_id = int(work_id_counts.max()) if not work_id_counts.empty else 0
    top_work_ids = work_id_counts.head(10).to_dict()

    print("\nWork ID analysis:")
    print(f" - total Work ID records: {work_id_total}")
    print(f" - unique Work IDs: {unique_work_ids}")
    print(f" - Work IDs appearing more than once: {duplicate_work_ids}")
    print(f" - max records belonging to one Work ID: {max_records_for_one_work_id}")
    print(" - top 10 Work IDs by number of records:")
    for work_id, count in top_work_ids.items():
        print(f"    * {work_id}: {count}")

    # Exact duplicate rows analysis
    duplicate_mask = df.duplicated(keep=False)
    duplicate_count = int(duplicate_mask.sum())
    duplicate_percentage = round((duplicate_count / len(df)) * 100, 4) if len(df) else 0.0
    print("\nExact duplicate rows:")
    print(f" - number of completely duplicated rows: {duplicate_count}")
    print(f" - percentage of dataset: {duplicate_percentage}%")

    # Expenditure date analysis
    invalid_dates = 0
    missing_dates = 0
    date_year_counts = pd.Series(dtype="int64")
    min_date = None
    max_date = None
    if date_col:
        date_series = pd.to_datetime(df[date_col], errors="coerce")
        missing_dates = int(date_series.isna().sum())
        invalid_dates = int(date_series.isna().sum() - df[date_col].isna().sum())
        valid_date_series = date_series.dropna()
        if not valid_date_series.empty:
            min_date = valid_date_series.min().strftime("%Y-%m-%d")
            max_date = valid_date_series.max().strftime("%Y-%m-%d")
            date_year_counts = valid_date_series.dt.year.value_counts().sort_index()
        print("\nExpenditure Date analysis:")
        print(f" - minimum date: {min_date}")
        print(f" - maximum date: {max_date}")
        print(f" - invalid dates: {invalid_dates}")
        print(f" - missing dates: {missing_dates}")
        print(" - number of records per year:")
        for year, count in date_year_counts.items():
            print(f"    * {int(year)}: {int(count)}")
    else:
        print("\nExpenditure Date analysis: date column not found")

    # Amount analysis
    amount_series = pd.Series([None] * len(df), index=df.index)
    if amount_col:
        amount_series = df[amount_col].map(safe_strip)
    amount_numeric = clean_numeric_amount(amount_series)
    invalid_amount_count = int((amount_series.notna() & amount_numeric.isna()).sum())
    missing_amount_count = int(amount_series.isna().sum())
    zero_amount_count = int((amount_numeric == 0).sum())
    negative_amount_count = int((amount_numeric < 0).sum())
    valid_amounts = amount_numeric.dropna()

    print("\nFund Disbursed Amount analysis:")
    print(f" - invalid/non-numeric values: {invalid_amount_count}")
    print(f" - missing values: {missing_amount_count}")
    if not valid_amounts.empty:
        print(f" - minimum: {float(valid_amounts.min())}")
        print(f" - maximum: {float(valid_amounts.max())}")
        print(f" - mean: {float(valid_amounts.mean())}")
        print(f" - median: {float(valid_amounts.median())}")
        print(f" - total: {float(valid_amounts.sum())}")
        print(f" - standard deviation: {float(valid_amounts.std())}")
    else:
        print(" - minimum: NaN")
        print(" - maximum: NaN")
        print(" - mean: NaN")
        print(" - median: NaN")
        print(" - total: NaN")
        print(" - standard deviation: NaN")
    print(f" - records with zero amount: {zero_amount_count}")
    print(f" - records with negative amount: {negative_amount_count}")

    # Payment status analysis
    if payment_status_col:
        status_series = df[payment_status_col].map(safe_strip)
        status_counts = status_series.dropna().value_counts(dropna=True)
        print("\nPayment Status analysis:")
        print(" - unique payment statuses:")
        for status, count in status_counts.items():
            pct = percent_of(float(count), float(len(status_series.dropna())))
            print(f"    * {status}: count={int(count)}, percentage={pct}%")
    else:
        print("\nPayment Status analysis: payment status column not found")

    # State analysis
    if state_col and amount_col:
        state_counts = df[state_col].fillna("Unknown").astype(str).str.strip().value_counts()
        state_mp_counts = df.groupby(state_col)[mp_col].nunique() if mp_col else pd.Series(dtype="float64")
        state_const_counts = df.groupby(state_col)[constituency_col].nunique() if constituency_col else pd.Series(dtype="float64")
        state_amounts = df.groupby(state_col)[amount_col].apply(lambda x: clean_numeric_amount(x).sum()) if amount_col else pd.Series(dtype="float64")
        print("\nState analysis:")
        print(" - number of records per state:")
        for state, count in state_counts.items():
            print(f"    * {state}: {int(count)}")
        print(" - number of unique MPs per state:")
        for state, count in state_mp_counts.items():
            print(f"    * {state}: {int(count)}")
        print(" - number of unique constituencies per state:")
        for state, count in state_const_counts.items():
            print(f"    * {state}: {int(count)}")
        print(" - total fund disbursed per state:")
        for state, total in state_amounts.items():
            print(f"    * {state}: {float(total)}")
    else:
        print("\nState analysis: required columns not found")

    # Vendor analysis
    if vendor_col:
        vendor_counts = df[vendor_col].fillna("Unknown").astype(str).str.strip().value_counts()
        if amount_col:
            vendor_amounts = df.groupby(vendor_col)[amount_col].apply(lambda x: clean_numeric_amount(x).sum())
        else:
            vendor_amounts = pd.Series(dtype="float64")
        print("\nVendor analysis:")
        print(" - number of unique vendors:", int(vendor_counts.shape[0]))
        print(" - top 20 vendors by number of records:")
        for vendor, count in vendor_counts.head(20).items():
            print(f"    * {vendor}: {int(count)}")
        print(" - top 20 vendors by total fund disbursed:")
        for vendor, total in vendor_amounts.sort_values(ascending=False).head(20).items():
            print(f"    * {vendor}: {float(total)}")

    # MP analysis
    if mp_col and amount_col:
        mp_counts = df[mp_col].fillna("Unknown").astype(str).str.strip().value_counts()
        mp_amounts = df.groupby(mp_col)[amount_col].apply(lambda x: clean_numeric_amount(x).sum())
        print("\nMP analysis:")
        print(" - number of records per MP:")
        for mp, count in mp_counts.head(20).items():
            print(f"    * {mp}: {int(count)}")
        print(" - total fund disbursed per MP:")
        for mp, total in mp_amounts.sort_values(ascending=False).head(20).items():
            print(f"    * {mp}: {float(total)}")

    # Work analysis
    if work_col and amount_col:
        work_counts = df[work_col].fillna("Unknown").astype(str).str.strip().value_counts()
        work_amounts = df.groupby(work_col)[amount_col].apply(lambda x: clean_numeric_amount(x).sum())
        print("\nWork analysis:")
        print(" - number of records per Work type/description:")
        for work_name, count in work_counts.head(20).items():
            print(f"    * {work_name}: {int(count)}")
        print(" - top 20 work types by total fund disbursed:")
        for work_name, total in work_amounts.sort_values(ascending=False).head(20).items():
            print(f"    * {work_name}: {float(total)}")

    # JSON report assembly
    audit_report = {
        "source_file": str(RAW_CSV.relative_to(ROOT)),
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "original_columns": original_cols,
        "data_types": {str(k): str(v) for k, v in df.dtypes.to_dict().items()},
        "unique_counts": {label: int(df[col].nunique(dropna=True)) if col else None for label, col in unique_targets.items()},
        "missing_values": missing_summary,
        "work_id_analysis": {
            "total_work_id_records": work_id_total,
            "unique_work_ids": unique_work_ids,
            "work_ids_appearing_more_than_once": duplicate_work_ids,
            "max_records_for_one_work_id": max_records_for_one_work_id,
            "top_10_work_ids_by_record_count": {str(k): int(v) for k, v in top_work_ids.items()},
        },
        "duplicate_rows": {
            "duplicated_row_count": duplicate_count,
            "duplicate_percentage": duplicate_percentage,
        },
        "expenditure_date": {
            "minimum_date": min_date,
            "maximum_date": max_date,
            "invalid_dates": invalid_dates,
            "missing_dates": missing_dates,
            "records_per_year": {str(k): int(v) for k, v in date_year_counts.to_dict().items()},
        },
        "fund_disbursed_amount": {
            "invalid_or_non_numeric_values": invalid_amount_count,
            "missing_values": missing_amount_count,
            "minimum": float(valid_amounts.min()) if not valid_amounts.empty else None,
            "maximum": float(valid_amounts.max()) if not valid_amounts.empty else None,
            "mean": float(valid_amounts.mean()) if not valid_amounts.empty else None,
            "median": float(valid_amounts.median()) if not valid_amounts.empty else None,
            "total": float(valid_amounts.sum()) if not valid_amounts.empty else None,
            "standard_deviation": float(valid_amounts.std()) if not valid_amounts.empty else None,
            "records_with_zero_amount": int(zero_amount_count),
            "records_with_negative_amount": int(negative_amount_count),
        },
        "payment_status": {
            "unique_statuses": [str(s) for s in status_counts.index.tolist()] if payment_status_col else [],
            "counts": {str(k): int(v) for k, v in status_counts.to_dict().items()} if payment_status_col else {},
        },
        "state_analysis": {},
        "vendor_analysis": {},
        "mp_analysis": {},
        "work_analysis": {},
    }

    if state_col and amount_col:
        state_counts = df[state_col].fillna("Unknown").astype(str).str.strip().value_counts()
        state_mp_counts = df.groupby(state_col)[mp_col].nunique() if mp_col and state_col else pd.Series(dtype="float64")
        state_const_counts = df.groupby(state_col)[constituency_col].nunique() if constituency_col and state_col else pd.Series(dtype="float64")
        state_amounts = df.groupby(state_col)[amount_col].apply(lambda x: clean_numeric_amount(x).sum()) if amount_col else pd.Series(dtype="float64")
        audit_report["state_analysis"] = {
            "records_per_state": {str(k): int(v) for k, v in state_counts.to_dict().items()},
            "unique_mps_per_state": {str(k): int(v) for k, v in state_mp_counts.to_dict().items()},
            "unique_constituencies_per_state": {str(k): int(v) for k, v in state_const_counts.to_dict().items()},
            "total_fund_disbursed_per_state": {str(k): float(v) for k, v in state_amounts.to_dict().items()},
        }

    if vendor_col:
        vendor_counts = df[vendor_col].fillna("Unknown").astype(str).str.strip().value_counts()
        vendor_amounts = df.groupby(vendor_col)[amount_col].apply(lambda x: clean_numeric_amount(x).sum()) if amount_col else pd.Series(dtype="float64")
        audit_report["vendor_analysis"] = {
            "unique_vendors": int(vendor_counts.shape[0]),
            "top_20_vendors_by_record_count": {str(k): int(v) for k, v in vendor_counts.head(20).to_dict().items()},
            "top_20_vendors_by_total_fund_disbursed": {str(k): float(v) for k, v in vendor_amounts.sort_values(ascending=False).head(20).to_dict().items()},
        }

    if mp_col:
        mp_counts = df[mp_col].fillna("Unknown").astype(str).str.strip().value_counts()
        mp_amounts = df.groupby(mp_col)[amount_col].apply(lambda x: clean_numeric_amount(x).sum()) if amount_col else pd.Series(dtype="float64")
        audit_report["mp_analysis"] = {
            "records_per_mp": {str(k): int(v) for k, v in mp_counts.head(20).to_dict().items()},
            "total_fund_disbursed_per_mp": {str(k): float(v) for k, v in mp_amounts.sort_values(ascending=False).head(20).to_dict().items()},
        }

    if work_col:
        work_counts = df[work_col].fillna("Unknown").astype(str).str.strip().value_counts()
        work_amounts = df.groupby(work_col)[amount_col].apply(lambda x: clean_numeric_amount(x).sum()) if amount_col else pd.Series(dtype="float64")
        audit_report["work_analysis"] = {
            "records_per_work_type": {str(k): int(v) for k, v in work_counts.head(20).to_dict().items()},
            "top_20_work_types_by_frequency": {str(k): int(v) for k, v in work_counts.head(20).to_dict().items()},
            "top_20_work_types_by_total_fund_disbursed": {str(k): float(v) for k, v in work_amounts.sort_values(ascending=False).head(20).to_dict().items()},
        }

    with AUDIT_JSON.open("w", encoding="utf-8") as f:
        json.dump(audit_report, f, indent=2, ensure_ascii=False)

    # Create cleaned copy only after auditing
    clean_df = df.copy()
    clean_df.columns = [str(c).strip() for c in clean_df.columns]

    source_columns = {
        "sr_no": find_column(clean_df, ["Sr No", "Sr. No", "S.No", "Serial No", "Sl No"], required=False),
        "state": find_column(clean_df, ["State", "State Name"], required=False),
        "work": find_column(clean_df, ["Work", "Work Type", "Work Description", "Description of Work"], required=False),
        "work_id": find_column(clean_df, ["Work ID", "Work Id", "WorkID"], required=False),
        "ida": find_column(clean_df, ["IDA", "IDA Name"], required=False),
        "mp_name": find_column(clean_df, ["Hon'ble Members of Parliament", "Honble Members of Parliament", "Member of Parliament", "MP Name", "Hon'ble MP", "MP"], required=False),
        "constituency": find_column(clean_df, ["Constituency", "Constituency Name"], required=False),
        "expenditure_date": find_column(clean_df, ["Expenditure Date", "Date of Expenditure", "Expenditure date", "Date"], required=False),
        "vendor_name": find_column(clean_df, ["Vendor Name", "Vendor", "Name of Vendor"], required=False),
        "payment_status": find_column(clean_df, ["Payment Status", "Status"], required=False),
        "fund_disbursed_amount": find_column(clean_df, ["Fund Disbursed Amount", "Amount", "Fund Amount", "Total Amount", "Amount Disbursed"], required=False),
    }

    cleaned_rows = []
    for idx, row in clean_df.iterrows():
        cleaned_row = {}
        for canonical_name, source_name in source_columns.items():
            if source_name is None:
                continue
            value = row[source_name]
            if isinstance(value, str):
                value = value.strip()
            cleaned_row[canonical_name] = value
        cleaned_rows.append(cleaned_row)

    clean_df_out = pd.DataFrame(cleaned_rows, index=clean_df.index)

    for col in ["sr_no", "state", "work", "work_id", "ida", "mp_name", "constituency", "vendor_name", "payment_status"]:
        if col in clean_df_out.columns:
            clean_df_out[col] = clean_df_out[col].map(safe_strip)

    if "expenditure_date" in clean_df_out.columns:
        clean_df_out["expenditure_date"] = pd.to_datetime(clean_df_out["expenditure_date"], errors="coerce")
        clean_df_out["expenditure_date"] = clean_df_out["expenditure_date"].dt.strftime("%Y-%m-%d")

    if "fund_disbursed_amount" in clean_df_out.columns:
        clean_df_out["fund_disbursed_amount"] = clean_numeric_amount(clean_df_out["fund_disbursed_amount"])

    # Keep only required canonical columns in fixed order and preserve all rows
    ordered_columns = [
        "sr_no",
        "state",
        "work",
        "work_id",
        "ida",
        "mp_name",
        "constituency",
        "expenditure_date",
        "vendor_name",
        "payment_status",
        "fund_disbursed_amount",
    ]
    final_columns = [col for col in ordered_columns if col in clean_df_out.columns]
    final_df = clean_df_out[final_columns].copy()
    final_df.to_csv(CLEAN_CSV, index=False)

    unreadable_rows = int(clean_df_out.isna().all(axis=1).sum())
    print(f"\nCreated cleaned copy: {CLEAN_CSV}")
    print(f"Created audit JSON: {AUDIT_JSON}")
    print(f"Rows unreadable: {unreadable_rows}")

    print("\n" + "=" * 80)
    print("FINAL AUDIT SUMMARY")
    print("=" * 80)
    print(f"Rows read: {len(df)}")
    print(f"Columns: {len(df.columns)}")
    print(f"Unique Work IDs: {unique_work_ids}")
    print(f"Duplicate Work IDs: {duplicate_work_ids}")
    print(f"Missing value summary: {sum(item['missing_count'] for item in missing_summary)} total missing cells across all columns")
    print(f"Date range: {min_date} to {max_date}")
    if not valid_amounts.empty:
        print(f"Amount statistics: min={float(valid_amounts.min())}, max={float(valid_amounts.max())}, mean={float(valid_amounts.mean())}, median={float(valid_amounts.median())}, total={float(valid_amounts.sum())}")
    else:
        print("Amount statistics: no valid numeric amounts found")
    if payment_status_col:
        print("Payment status distribution:")
        for status, count in status_counts.items():
            pct = percent_of(float(count), float(len(status_series.dropna())))
            print(f"  * {status}: {int(count)} ({pct}%)")
    print(f"Rows unreadable: {unreadable_rows}")


if __name__ == "__main__":
    main()
