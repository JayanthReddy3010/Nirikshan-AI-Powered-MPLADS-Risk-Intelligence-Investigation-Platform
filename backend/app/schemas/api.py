from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.detection import RuleResult


class WorkListItem(BaseModel):
    work_id: str
    state: Optional[str] = None
    mp_name: Optional[str] = None
    constituency: Optional[str] = None
    work: Optional[str] = None
    ida: Optional[str] = None
    risk_score: float
    risk_band: str


class PaginatedWorks(BaseModel):
    page: int
    page_size: int
    total: int
    items: List[WorkListItem]


class TransactionItem(BaseModel):
    source_row_number: int
    expenditure_date: Optional[date] = None
    vendor_name: Optional[str] = None
    payment_status: Optional[str] = None
    fund_disbursed_amount: Optional[Decimal] = None


class PaginatedTransactions(BaseModel):
    page: int
    page_size: int
    total: int
    items: List[TransactionItem]


class WorkInformation(BaseModel):
    work_id: str
    state: Optional[str] = None
    mp_name: Optional[str] = None
    constituency: Optional[str] = None
    work: Optional[str] = None
    ida: Optional[str] = None


class FinancialEvidence(BaseModel):
    total_disbursed_amount: Decimal
    transaction_count: int
    average_transaction_amount: Optional[Decimal] = None
    maximum_transaction_amount: Optional[Decimal] = None
    minimum_transaction_amount: Optional[Decimal] = None
    transaction_amount_stddev: Decimal


class VendorEvidence(BaseModel):
    unique_vendor_count: int
    primary_vendor: Optional[str] = None
    primary_vendor_amount: Optional[Decimal] = None
    primary_vendor_share: Optional[Decimal] = None


class TemporalEvidence(BaseModel):
    first_expenditure_date: Optional[date] = None
    latest_expenditure_date: Optional[date] = None
    days_between_first_and_last_transaction: Optional[int] = None
    average_days_between_transactions: Optional[Decimal] = None


class PeerEvidence(BaseModel):
    peer_group_level: Optional[str] = None
    peer_group_size: int = 0
    actual_value: Optional[Decimal] = None
    peer_group_median_amount: Optional[Decimal] = None
    peer_group_mean_amount: Optional[Decimal] = None
    peer_group_stddev: Optional[Decimal] = None
    amount_ratio_to_peer_median: Optional[Decimal] = None
    percentile_rank: Optional[Decimal] = None
    deviation_from_peer_median: Optional[Decimal] = None
    triggered: bool = False
    explanation: str
    available: bool = True


class MlEvidence(BaseModel):
    model_name: str
    model_version: Optional[str] = None
    anomaly_score: Optional[float] = None
    anomaly_label: Optional[str] = None
    important_feature_values: Dict[str, Any] = Field(default_factory=dict)
    available: bool = True


class DelayAvailability(BaseModel):
    available: bool = False
    reason: str


class CompositeRiskEvidence(BaseModel):
    final_score: float
    risk_band: str
    rule_score: Optional[float] = None
    peer_score: Optional[float] = None
    isolation_forest_score: Optional[float] = None
    delay_score: Optional[float] = None
    available_signals: List[str]
    unavailable_signals: List[str]
    explanation: str


class WorkDetailResponse(BaseModel):
    work_information: WorkInformation
    financial_evidence: FinancialEvidence
    vendor_evidence: VendorEvidence
    temporal_evidence: TemporalEvidence
    rule_evidence: List[RuleResult]
    peer_evidence: PeerEvidence
    ml_evidence: MlEvidence
    delay_prediction: DelayAvailability
    composite_risk: CompositeRiskEvidence
    transactions: PaginatedTransactions


class RiskWorkItem(BaseModel):
    work_id: str
    risk_score: float
    risk_band: str
    amount: Optional[Decimal] = None


class DashboardSummary(BaseModel):
    total_works: int
    works: int
    total_transactions: int
    transactions: int
    total_disbursed_amount: Decimal
    source_rows: int
    valid_rows: int
    import_errors: int
    low_risk_count: int
    moderate_risk_count: int
    high_risk_count: int
    critical_risk_count: int
    investigation_candidate_count: int
    top_10_highest_risk_works: List[RiskWorkItem]


class StateSummaryItem(BaseModel):
    state: Optional[str] = None
    work_count: int
    transaction_count: int
    total_amount: Decimal
    average_work_amount: Decimal
    high_risk_work_count: int
    critical_risk_work_count: int


class VendorSummaryItem(BaseModel):
    vendor_name: str
    work_count: int
    transaction_count: int = 0
    total_amount: Decimal
    average_work_amount: Decimal
    unique_states: int
    high_risk_work_count: int


class RiskDistribution(BaseModel):
    minimum_score: float
    median_score: float
    maximum_score: float
    low_risk_count: int
    moderate_risk_count: int
    high_risk_count: int
    critical_risk_count: int


class RiskExposureItem(BaseModel):
    risk_band: str
    work_count: int
    total_amount: Decimal
