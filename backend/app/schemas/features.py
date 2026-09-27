from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class WorkFeatures(BaseModel):
    """Investigation features derived from one work and its transactions."""

    work_id: str
    total_disbursed_amount: Decimal
    transaction_count: int
    average_transaction_amount: Optional[Decimal] = None
    maximum_transaction_amount: Optional[Decimal] = None
    minimum_transaction_amount: Optional[Decimal] = None
    transaction_amount_stddev: Decimal
    transaction_amount_concentration: Optional[Decimal] = None
    unique_vendor_count: int
    days_between_first_and_last_transaction: Optional[int] = None
    average_days_between_transactions: Optional[Decimal] = None
    latest_expenditure_date: Optional[date] = None
    first_expenditure_date: Optional[date] = None
    primary_vendor: Optional[str] = None
    primary_vendor_amount: Optional[Decimal] = None
    primary_vendor_share: Optional[Decimal] = None
    amount_ratio_to_peer_median: Optional[Decimal] = None
    percentile_rank: Optional[Decimal] = None
