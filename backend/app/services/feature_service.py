"""Read-only work-level feature engineering from PostgreSQL.

Feature formulas:
- transaction_amount_stddev uses population standard deviation, with one or fewer
  non-null amounts represented as zero.
- transaction_amount_concentration is maximum transaction amount divided by total
  disbursed amount; it is NULL when the total is zero or no amount is available.
- average_days_between_transactions is the date span divided by one fewer than the
  number of transactions with dates; it is NULL when fewer than two dates exist.
- primary_vendor is the non-blank vendor with the largest aggregate amount for the
  work. Its share is primary_vendor_amount / total_disbursed_amount and is NULL
  when the total is zero.

The service uses PostgreSQL aggregation and returns no raw transaction collection.
It never writes to the database.
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.schemas.features import WorkFeatures

_FEATURE_QUERY = text(
    """
    WITH transaction_stats AS (
        SELECT
            work_id,
            COALESCE(SUM(fund_disbursed_amount), 0) AS total_disbursed_amount,
            COUNT(*)::integer AS transaction_count,
            AVG(fund_disbursed_amount) AS average_transaction_amount,
            MAX(fund_disbursed_amount) AS maximum_transaction_amount,
            MIN(fund_disbursed_amount) AS minimum_transaction_amount,
            COALESCE(STDDEV_POP(fund_disbursed_amount), 0) AS transaction_amount_stddev,
            MAX(fund_disbursed_amount) / NULLIF(SUM(fund_disbursed_amount), 0)
                AS transaction_amount_concentration,
            COUNT(DISTINCT NULLIF(BTRIM(vendor_name), ''))::integer AS unique_vendor_count,
            MIN(expenditure_date) AS first_expenditure_date,
            MAX(expenditure_date) AS latest_expenditure_date,
            (MAX(expenditure_date) - MIN(expenditure_date))::integer
                AS days_between_first_and_last_transaction,
            (MAX(expenditure_date) - MIN(expenditure_date))::numeric
                / NULLIF(COUNT(expenditure_date) - 1, 0)
                AS average_days_between_transactions
        FROM work_transactions
        {where_clause}
        GROUP BY work_id
    ),
    vendor_totals AS (
        SELECT
            work_id,
            NULLIF(BTRIM(vendor_name), '') AS vendor_name,
            SUM(fund_disbursed_amount) AS vendor_amount
        FROM work_transactions
        WHERE NULLIF(BTRIM(vendor_name), '') IS NOT NULL
          {vendor_work_clause}
        GROUP BY work_id, NULLIF(BTRIM(vendor_name), '')
    ),
    ranked_vendors AS (
        SELECT
            work_id,
            vendor_name,
            vendor_amount,
            ROW_NUMBER() OVER (
                PARTITION BY work_id
                ORDER BY vendor_amount DESC NULLS LAST, vendor_name
            ) AS vendor_rank
        FROM vendor_totals
    )
    SELECT
        w.work_id,
        COALESCE(ts.total_disbursed_amount, 0) AS total_disbursed_amount,
        COALESCE(ts.transaction_count, 0)::integer AS transaction_count,
        ts.average_transaction_amount,
        ts.maximum_transaction_amount,
        ts.minimum_transaction_amount,
        COALESCE(ts.transaction_amount_stddev, 0) AS transaction_amount_stddev,
        ts.transaction_amount_concentration,
        COALESCE(ts.unique_vendor_count, 0)::integer AS unique_vendor_count,
        ts.days_between_first_and_last_transaction,
        ts.average_days_between_transactions,
        ts.latest_expenditure_date,
        ts.first_expenditure_date,
        rv.vendor_name AS primary_vendor,
        rv.vendor_amount AS primary_vendor_amount,
        rv.vendor_amount / NULLIF(ts.total_disbursed_amount, 0) AS primary_vendor_share
    FROM works w
    LEFT JOIN transaction_stats ts ON ts.work_id = w.work_id
    LEFT JOIN ranked_vendors rv
      ON rv.work_id = w.work_id
     AND rv.vendor_rank = 1
    {work_clause}
    ORDER BY w.work_id
    """
)


def _query_features(db: Session, work_id: Optional[str] = None) -> Iterable[WorkFeatures]:
    if work_id is None:
        params = {}
        where_clause = ""
        vendor_work_clause = ""
        work_clause = ""
    else:
        params = {"work_id": work_id}
        where_clause = "WHERE work_id = :work_id"
        vendor_work_clause = "AND work_id = :work_id"
        work_clause = "WHERE w.work_id = :work_id"

    query = text(
        _FEATURE_QUERY.text.format(
            where_clause=where_clause,
            vendor_work_clause=vendor_work_clause,
            work_clause=work_clause,
        )
    )
    rows = db.execute(query, params).mappings()
    return (WorkFeatures.model_validate(row) for row in rows)


def get_work_features(db: Session, work_id: str) -> Optional[WorkFeatures]:
    """Return calculated features for one work, or None when the work does not exist."""
    return next(iter(_query_features(db, work_id)), None)


def get_all_work_features(db: Session) -> Iterable[WorkFeatures]:
    """Yield calculated features for every work without loading transactions into memory."""
    return _query_features(db)
