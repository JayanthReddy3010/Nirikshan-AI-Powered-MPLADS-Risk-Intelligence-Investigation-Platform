from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


class RuleResult(BaseModel):
    """Explainable evidence from one rule; it is not a fraud classification."""

    rule_id: str
    rule_name: str
    triggered: bool
    severity: str
    explanation: str
    evidence_values: Dict[str, Any]
    threshold: Any
    work_id: str
