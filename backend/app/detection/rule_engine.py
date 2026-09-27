"""Explainable, rule-based work anomaly indicators.

These rules identify unusual patterns requiring investigation. A triggered rule is
not a finding of fraud and this module deliberately emits no fraud classification.
All rules consume a WorkFeatures vector calculated from PostgreSQL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from backend.app.schemas.detection import RuleResult
from backend.app.schemas.features import WorkFeatures
from backend.app.services.feature_service import get_work_features


@dataclass(frozen=True)
class RuleSettings:
    """Tunable development thresholds for the rule engine."""

    high_transaction_concentration_threshold: Decimal = Decimal("0.50")
    high_vendor_concentration_threshold: Decimal = Decimal("0.60")
    fragmentation_transaction_count_threshold: int = 20
    large_transaction_threshold: Decimal = Decimal("1000000")

    @classmethod
    def from_environment(cls) -> "RuleSettings":
        """Load thresholds from environment variables, using documented defaults."""
        return cls(
            high_transaction_concentration_threshold=_decimal_env(
                "HIGH_TRANSACTION_CONCENTRATION_THRESHOLD", "0.50"
            ),
            high_vendor_concentration_threshold=_decimal_env(
                "HIGH_VENDOR_CONCENTRATION_THRESHOLD", "0.60"
            ),
            fragmentation_transaction_count_threshold=_int_env(
                "FRAGMENTATION_TRANSACTION_COUNT_THRESHOLD", 20
            ),
            large_transaction_threshold=_decimal_env(
                "LARGE_TRANSACTION_THRESHOLD", "1000000"
            ),
        )


def _decimal_env(name: str, default: str) -> Decimal:
    value = os.getenv(name, default)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError(f"{name} must be a decimal value, got {value!r}") from None
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative, got {value!r}")
    return parsed


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer value, got {value!r}") from None
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative, got {value!r}")
    return parsed


def _result(
    features: WorkFeatures,
    rule_id: str,
    rule_name: str,
    triggered: bool,
    severity: str,
    explanation: str,
    evidence_values: dict,
    threshold,
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        rule_name=rule_name,
        triggered=triggered,
        severity=severity,
        explanation=explanation,
        evidence_values=evidence_values,
        threshold=threshold,
        work_id=features.work_id,
    )


def high_transaction_concentration(
    features: WorkFeatures, settings: RuleSettings
) -> RuleResult:
    actual = features.transaction_amount_concentration
    triggered = actual is not None and actual >= settings.high_transaction_concentration_threshold
    percentage = "unavailable" if actual is None else f"{actual * 100:.1f}%"
    explanation = (
        f"One transaction accounts for {percentage} of the total disbursed amount."
        if triggered
        else "The maximum single transaction is below the configured concentration threshold."
    )
    return _result(
        features,
        "R001",
        "High transaction concentration",
        triggered,
        "medium",
        explanation,
        {"transaction_amount_concentration": actual},
        settings.high_transaction_concentration_threshold,
    )


def high_vendor_concentration(features: WorkFeatures, settings: RuleSettings) -> RuleResult:
    actual = features.primary_vendor_share
    triggered = actual is not None and actual >= settings.high_vendor_concentration_threshold
    percentage = "unavailable" if actual is None else f"{actual * 100:.1f}%"
    explanation = (
        f"Primary vendor accounts for {percentage} of the work's total disbursed amount."
        if triggered
        else "The primary vendor share is below the configured concentration threshold."
    )
    return _result(
        features,
        "R002",
        "High vendor concentration",
        triggered,
        "medium",
        explanation,
        {"primary_vendor": features.primary_vendor, "primary_vendor_share": actual},
        settings.high_vendor_concentration_threshold,
    )


def transaction_fragmentation(features: WorkFeatures, settings: RuleSettings) -> RuleResult:
    actual = features.transaction_count
    triggered = actual >= settings.fragmentation_transaction_count_threshold
    explanation = (
        "Work contains an unusually high number of expenditure transactions and may require "
        "review for transaction fragmentation."
        if triggered
        else "The transaction count is below the configured fragmentation threshold."
    )
    return _result(
        features,
        "R003",
        "Many transactions / fragmentation indicator",
        triggered,
        "low",
        explanation,
        {"transaction_count": actual},
        settings.fragmentation_transaction_count_threshold,
    )


def large_single_transaction(features: WorkFeatures, settings: RuleSettings) -> RuleResult:
    actual = features.maximum_transaction_amount
    triggered = actual is not None and actual >= settings.large_transaction_threshold
    explanation = (
        f"The largest single transaction is {actual:.2f}, at or above the configured review threshold."
        if triggered
        else "The maximum transaction amount is below the configured large-transaction threshold."
    )
    return _result(
        features,
        "R004",
        "Large single transaction",
        triggered,
        "high",
        explanation,
        {"maximum_transaction_amount": actual},
        settings.large_transaction_threshold,
    )


_RULES: tuple[Callable[[WorkFeatures, RuleSettings], RuleResult], ...] = (
    high_transaction_concentration,
    high_vendor_concentration,
    transaction_fragmentation,
    large_single_transaction,
)


def detect_work(
    features: WorkFeatures, settings: Optional[RuleSettings] = None
) -> List[RuleResult]:
    """Evaluate all explainable rules for one work-level feature vector."""
    active_settings = settings or RuleSettings.from_environment()
    return [rule(features, active_settings) for rule in _RULES]


def get_work_rule_results(
    db: Session, work_id: str, settings: Optional[RuleSettings] = None
) -> Optional[List[RuleResult]]:
    """Fetch real PostgreSQL-derived features and evaluate all rules for a work."""
    features = get_work_features(db, work_id)
    if features is None:
        return None
    return detect_work(features, settings)
