from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


class DelayPredictionResult(BaseModel):
    """Delay prediction response, including unavailable-state evidence."""

    work_id: str
    available: bool
    delay_probability: Optional[float] = None
    delay_risk_score: Optional[float] = None
    delay_risk_label: str
    explanation: str
    feature_values: Dict[str, Any]
    model_version: Optional[str] = None


class DelayTargetReport(BaseModel):
    """Assessment of whether the real database supports supervised training."""

    valid_target_available: bool
    target_definition: Optional[str] = None
    missing_outcome_fields: list[str]
    explanation: str
