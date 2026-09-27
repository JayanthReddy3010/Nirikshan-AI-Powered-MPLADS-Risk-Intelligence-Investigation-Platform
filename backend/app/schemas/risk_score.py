from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.app.schemas.detection import RuleResult


class RiskScoreResult(BaseModel):
    """Explainable investigation-priority score, not a classification."""

    work_id: str
    final_risk_score: float
    risk_band: str
    rule_score: Optional[float] = None
    peer_score: Optional[float] = None
    isolation_forest_score: Optional[float] = None
    delay_score: Optional[float] = None
    available_signals: List[str]
    unavailable_signals: List[str]
    triggered_rules: List[RuleResult]
    peer_evidence: Dict[str, Any]
    ml_evidence: Dict[str, Any]
    explanation: str
    model_versions_configuration: Dict[str, Any]
