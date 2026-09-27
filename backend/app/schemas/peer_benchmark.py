from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class PeerBenchmarkResult(BaseModel):
    """Explainable peer-group comparison; it is not a fraud classification."""

    work_id: str
    triggered: bool
    severity: str
    explanation: str
    actual_value: Optional[Decimal] = None
    peer_group_level: Optional[str] = None
    peer_group_size: int = 0
    peer_group_median_amount: Optional[Decimal] = None
    peer_group_mean_amount: Optional[Decimal] = None
    peer_group_stddev: Optional[Decimal] = None
    amount_ratio_to_peer_median: Optional[Decimal] = None
    percentile_rank: Optional[Decimal] = None
    deviation_from_peer_median: Optional[Decimal] = None
    threshold: Decimal
