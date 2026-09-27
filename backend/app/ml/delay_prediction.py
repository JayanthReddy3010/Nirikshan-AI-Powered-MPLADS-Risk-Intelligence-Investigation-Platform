"""Safe architecture for supervised work-completion delay prediction.

The current MPLADS schema has expenditure dates and payment status, but no actual
completion date, completion status, expected completion date, or historical delay
outcome. Payment status is a payment workflow field, not a completion outcome.
Consequently no defensible supervised target can be constructed from this data.

This module deliberately does not fit LogisticRegression, persist a model, report
metrics, or produce probabilities until a real historical outcome and a defined
prediction timestamp are added. Using final expenditure totals or future
transactions as predictors would leak information from after the prediction point.

The intended future architecture is:
1. define a real target from an observed completion outcome;
2. create a time-aware snapshot of predictors at the prediction point;
3. fit sklearn.linear_model.LogisticRegression on those snapshots;
4. persist preprocessing, model, target definition, and time split metadata.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Optional

from sklearn.linear_model import LogisticRegression
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.schemas.delay_prediction import DelayPredictionResult, DelayTargetReport

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "backend" / "app" / "ml" / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "delay_prediction.joblib"
METADATA_PATH = ARTIFACT_DIR / "delay_model_metadata.json"
MODEL_VERSION = "delay_prediction_untrained_v1"
INSUFFICIENT_DATA_MESSAGE = "Insufficient historical outcome data for supervised delay prediction."

# These are candidate snapshot fields for a future labeled dataset. They are not
# used for training against the current database because no valid target exists.
CANDIDATE_FEATURE_NAMES = [
    "transaction_count_at_prediction_point",
    "amount_disbursed_at_prediction_point",
    "average_transaction_amount_at_prediction_point",
    "days_since_first_expenditure_at_prediction_point",
    "payment_success_count_at_prediction_point",
    "payment_in_progress_count_at_prediction_point",
]


@dataclass(frozen=True)
class DelayModelSettings:
    """Future Logistic Regression configuration and configurable risk bands."""

    random_state: int = 42
    max_iter: int = 1000
    low_risk_upper_bound: float = 39.0
    moderate_risk_upper_bound: float = 69.0

    @classmethod
    def from_environment(cls) -> "DelayModelSettings":
        return cls(
            random_state=int(os.getenv("DELAY_MODEL_RANDOM_STATE", "42")),
            max_iter=int(os.getenv("DELAY_MODEL_MAX_ITER", "1000")),
            low_risk_upper_bound=float(os.getenv("DELAY_LOW_RISK_UPPER_BOUND", "39")),
            moderate_risk_upper_bound=float(os.getenv("DELAY_MODERATE_RISK_UPPER_BOUND", "69")),
        )


def assess_delay_target(db: Session) -> DelayTargetReport:
    """Inspect the live schema and report why no historical target is available."""
    fields = {
        row[0]
        for row in db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name IN ('works', 'work_transactions')
                """
            )
        ).all()
    }
    expected_outcome_fields = {
        "actual_completion_date",
        "completion_date",
        "actual_completion_status",
        "completion_status",
        "expected_completion_date",
        "delay_label",
    }
    missing_fields = sorted(expected_outcome_fields - fields)
    return DelayTargetReport(
        valid_target_available=False,
        target_definition=None,
        missing_outcome_fields=missing_fields,
        explanation=(
            f"{INSUFFICIENT_DATA_MESSAGE} The current schema contains expenditure dates "
            "and payment status, but no observed completion outcome."
        ),
    )


def construct_delay_target(db: Session) -> None:
    """Refuse target construction until an observed completion outcome exists."""
    report = assess_delay_target(db)
    if not report.valid_target_available:
        raise ValueError(report.explanation)
    raise NotImplementedError("A validated target definition is required before training.")


def preprocess_delay_features(values: Mapping[str, Any]) -> list[float]:
    """Prepare a future snapshot vector without inventing missing values.

    This interface validates finite numeric snapshot values. It intentionally does
    not impute or derive values from post-prediction transactions.
    """
    vector: list[float] = []
    for name in CANDIDATE_FEATURE_NAMES:
        value = values.get(name)
        if value is None:
            raise ValueError(f"Missing pre-prediction feature: {name}")
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            raise ValueError(f"Non-finite pre-prediction feature: {name}")
        vector.append(number)
    return vector


def train_delay_model(db: Session, settings: Optional[DelayModelSettings] = None) -> dict[str, Any]:
    """Stop safely; no model is trained without real historical outcomes."""
    report = assess_delay_target(db)
    if not report.valid_target_available:
        raise ValueError(report.explanation)
    raise NotImplementedError("Training requires a validated, leakage-safe historical target.")


def classify_delay_risk(score: float, settings: DelayModelSettings) -> str:
    """Map a future probability-derived score to a schedule-monitoring label."""
    if score < settings.low_risk_upper_bound:
        return "low delay risk"
    if score <= settings.moderate_risk_upper_bound:
        return "moderate delay risk"
    return "high delay risk"


def predict_work_delay(db: Session, work_id: str) -> DelayPredictionResult:
    """Return the explicit unavailable state instead of an unsupported probability."""
    return DelayPredictionResult(
        work_id=work_id,
        available=False,
        delay_probability=None,
        delay_risk_score=None,
        delay_risk_label="unavailable",
        explanation=INSUFFICIENT_DATA_MESSAGE,
        feature_values={},
        model_version=MODEL_VERSION,
    )
