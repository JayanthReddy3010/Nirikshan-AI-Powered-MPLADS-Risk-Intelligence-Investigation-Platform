from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


class WorkAnomalyResult(BaseModel):
    """Unsupervised anomaly evidence, never a fraud classification."""

    work_id: str
    anomaly_score: float
    anomaly_label: str
    model_version: str
    key_feature_values: Dict[str, Any]
