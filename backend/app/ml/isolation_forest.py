"""Reproducible Isolation Forest anomaly detection for real work features.

The model consumes only numerical, work-level features produced by the feature
service and peer benchmark service. It does not consume categorical strings,
raw transactions, labels, or synthetic data.

Preprocessing:
- None and non-finite values become missing values.
- Missing values are replaced with the training-column median.
- ``log1p`` is applied after imputation to nonnegative monetary, count, and
  duration features with potentially heavy right skew.
- Ratio, share, percentile, and concentration features remain on their original
  numeric scale.

The sklearn decision_function is higher for more normal observations. The public
anomaly score reverses and min-max normalizes the training decision range:

    score = clip(100 * (train_max_decision - decision) /
                 (train_max_decision - train_min_decision), 0, 100)

Thus 0 is the least unusual within the training range and 100 is the most
unusual. Scores outside the training range are clipped. If the training range
is constant, all scores are 0. This normalization and the fixed random state
make results deterministic for the same dataset and configuration.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Sequence

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sqlalchemy.orm import Session

from backend.app.detection.peer_benchmark import (
    get_all_peer_benchmarks,
    get_peer_benchmark,
)
from backend.app.schemas.anomaly import WorkAnomalyResult
from backend.app.schemas.features import WorkFeatures
from backend.app.services.feature_service import get_all_work_features, get_work_features

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "backend" / "app" / "ml" / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "isolation_forest.joblib"
METADATA_PATH = ARTIFACT_DIR / "model_metadata.json"
MODEL_VERSION = "isolation_forest_v1"

FEATURE_NAMES = [
    "total_disbursed_amount",
    "transaction_count",
    "average_transaction_amount",
    "maximum_transaction_amount",
    "minimum_transaction_amount",
    "transaction_amount_stddev",
    "transaction_amount_concentration",
    "unique_vendor_count",
    "days_between_first_and_last_transaction",
    "average_days_between_transactions",
    "primary_vendor_share",
    "amount_ratio_to_peer_median",
    "percentile_rank",
]
LOG_FEATURES = {
    "total_disbursed_amount",
    "transaction_count",
    "average_transaction_amount",
    "maximum_transaction_amount",
    "minimum_transaction_amount",
    "transaction_amount_stddev",
    "unique_vendor_count",
    "days_between_first_and_last_transaction",
    "average_days_between_transactions",
}


@dataclass(frozen=True)
class IsolationForestSettings:
    n_estimators: int = 300
    contamination: str = "auto"
    random_state: int = 42
    anomaly_score_threshold: float = 70.0

    @classmethod
    def from_environment(cls) -> "IsolationForestSettings":
        n_estimators = int(os.getenv("ISOLATION_FOREST_N_ESTIMATORS", "300"))
        random_state = int(os.getenv("ISOLATION_FOREST_RANDOM_STATE", "42"))
        threshold = float(os.getenv("ANOMALY_SCORE_THRESHOLD", "70"))
        if n_estimators < 1:
            raise ValueError("ISOLATION_FOREST_N_ESTIMATORS must be at least 1")
        if not 0 <= threshold <= 100:
            raise ValueError("ANOMALY_SCORE_THRESHOLD must be between 0 and 100")
        return cls(
            n_estimators=n_estimators,
            contamination="auto",
            random_state=random_state,
            anomaly_score_threshold=threshold,
        )


def _feature_value(features: WorkFeatures, name: str) -> float:
    value = getattr(features, name)
    if value is None:
        return np.nan
    return float(value)


def build_feature_matrix(features: Sequence[WorkFeatures]) -> np.ndarray:
    """Build the finite-safe raw numerical matrix before imputation/transforms."""
    matrix = np.array(
        [[_feature_value(record, name) for name in FEATURE_NAMES] for record in features],
        dtype=float,
    )
    if matrix.ndim != 2 or matrix.shape[1] != len(FEATURE_NAMES):
        raise ValueError("Feature matrix has an unexpected shape")
    return matrix


def _transform_matrix(matrix: np.ndarray, imputer: SimpleImputer) -> np.ndarray:
    finite_matrix = np.where(np.isfinite(matrix), matrix, np.nan)
    transformed = imputer.transform(finite_matrix)
    for index, name in enumerate(FEATURE_NAMES):
        if name in LOG_FEATURES:
            transformed[:, index] = np.log1p(np.clip(transformed[:, index], 0, None))
    transformed = np.nan_to_num(transformed, nan=0.0, posinf=0.0, neginf=0.0)
    if not np.isfinite(transformed).all():
        raise ValueError("Non-finite values remain after preprocessing")
    return transformed


def _fit_transform_matrix(matrix: np.ndarray) -> tuple[np.ndarray, SimpleImputer]:
    finite_matrix = np.where(np.isfinite(matrix), matrix, np.nan)
    imputer = SimpleImputer(strategy="median")
    transformed = _transform_matrix(matrix, imputer.fit(finite_matrix))
    return transformed, imputer


def _normalize_scores(decisions: np.ndarray, train_min: float, train_max: float) -> np.ndarray:
    if train_max == train_min:
        return np.zeros_like(decisions, dtype=float)
    scores = 100.0 * (train_max - decisions) / (train_max - train_min)
    return np.clip(scores, 0.0, 100.0)


def _label(score: float, threshold: float) -> str:
    return "requires investigation" if score >= threshold else "within expected pattern"


def _key_features(features: WorkFeatures) -> dict[str, Any]:
    return {
        "total_disbursed_amount": features.total_disbursed_amount,
        "transaction_count": features.transaction_count,
        "transaction_amount_concentration": features.transaction_amount_concentration,
        "unique_vendor_count": features.unique_vendor_count,
        "primary_vendor_share": features.primary_vendor_share,
        "amount_ratio_to_peer_median": features.amount_ratio_to_peer_median,
        "percentile_rank": features.percentile_rank,
    }


def _metadata(settings: IsolationForestSettings, count: int, train_min: float, train_max: float) -> dict[str, Any]:
    return {
        "model_type": "sklearn.ensemble.IsolationForest",
        "sklearn_version": sklearn.__version__,
        "feature_names": FEATURE_NAMES,
        "transformations": {
            "missing_values": "median imputation fitted on training works",
            "non_finite_values": "treated as missing before imputation",
            "log1p_features": sorted(LOG_FEATURES),
            "raw_scale_features": [name for name in FEATURE_NAMES if name not in LOG_FEATURES],
        },
        "n_estimators": settings.n_estimators,
        "contamination": settings.contamination,
        "random_state": settings.random_state,
        "anomaly_score_threshold": settings.anomaly_score_threshold,
        "training_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "number_of_training_works": count,
        "model_version": MODEL_VERSION,
        "score_normalization": {
            "method": "reversed min-max of decision_function, clipped to 0-100",
            "training_decision_min": train_min,
            "training_decision_max": train_max,
        },
    }


def train_isolation_forest(
    db: Session, settings: IsolationForestSettings | None = None
) -> dict[str, Any]:
    """Train and persist the forest using all real PostgreSQL-derived work features."""
    active_settings = settings or IsolationForestSettings.from_environment()
    records = list(get_all_work_features(db))
    if not records:
        raise ValueError("No work features available for Isolation Forest training")
    peer_results = get_all_peer_benchmarks(db)
    records = [
        record.model_copy(
            update={
                "amount_ratio_to_peer_median": peer_results[record.work_id].amount_ratio_to_peer_median,
                "percentile_rank": peer_results[record.work_id].percentile_rank,
            }
        )
        for record in records
    ]

    raw_matrix = build_feature_matrix(records)
    matrix, imputer = _fit_transform_matrix(raw_matrix)
    model = IsolationForest(
        n_estimators=active_settings.n_estimators,
        contamination=active_settings.contamination,
        random_state=active_settings.random_state,
    )
    model.fit(matrix)
    decisions = model.decision_function(matrix)
    train_min = float(np.min(decisions))
    train_max = float(np.max(decisions))
    metadata = _metadata(active_settings, len(records), train_min, train_max)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "imputer": imputer,
            "feature_names": FEATURE_NAMES,
            "model_version": MODEL_VERSION,
            "settings": active_settings,
            "training_decision_min": train_min,
            "training_decision_max": train_max,
        },
        MODEL_PATH,
    )
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "model_path": str(MODEL_PATH),
        "metadata_path": str(METADATA_PATH),
        "number_of_training_works": len(records),
        "feature_matrix_shape": list(matrix.shape),
        "training_decision_min": train_min,
        "training_decision_max": train_max,
        "model_version": MODEL_VERSION,
    }


@lru_cache(maxsize=1)
def _load_bundle() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model artifact not found at {MODEL_PATH}. Run train_isolation_forest() first."
        )
    return joblib.load(MODEL_PATH)


def _predict(features: WorkFeatures, bundle: dict[str, Any]) -> WorkAnomalyResult:
    matrix = _transform_matrix(build_feature_matrix([features]), bundle["imputer"])
    decision = float(bundle["model"].decision_function(matrix)[0])
    score = float(
        _normalize_scores(
            np.array([decision]),
            bundle["training_decision_min"],
            bundle["training_decision_max"],
        )[0]
    )
    settings = bundle["settings"]
    return WorkAnomalyResult(
        work_id=features.work_id,
        anomaly_score=score,
        anomaly_label=_label(score, settings.anomaly_score_threshold),
        model_version=bundle["model_version"],
        key_feature_values=_key_features(features),
    )


def predict_work_anomaly(db: Session, work_id: str) -> WorkAnomalyResult | None:
    """Predict one real work using the persisted model and preprocessing bundle."""
    features = get_work_features(db, work_id)
    if features is None:
        return None
    peer = get_peer_benchmark(db, work_id)
    if peer is not None:
        features = features.model_copy(
            update={
                "amount_ratio_to_peer_median": peer.amount_ratio_to_peer_median,
                "percentile_rank": peer.percentile_rank,
            }
        )
    return _predict(features, _load_bundle())


def score_all_works(db: Session) -> List[WorkAnomalyResult]:
    """Score all works from work-level feature rows, without loading raw transactions."""
    bundle = _load_bundle()
    peer_results = get_all_peer_benchmarks(db)
    records = [
        features.model_copy(
            update={
                "amount_ratio_to_peer_median": peer_results[features.work_id].amount_ratio_to_peer_median,
                "percentile_rank": peer_results[features.work_id].percentile_rank,
            }
        )
        for features in get_all_work_features(db)
    ]
    matrix = _transform_matrix(build_feature_matrix(records), bundle["imputer"])
    decisions = bundle["model"].decision_function(matrix)
    scores = _normalize_scores(
        decisions,
        bundle["training_decision_min"],
        bundle["training_decision_max"],
    )
    settings = bundle["settings"]
    return [
        WorkAnomalyResult(
            work_id=features.work_id,
            anomaly_score=float(score),
            anomaly_label=_label(float(score), settings.anomaly_score_threshold),
            model_version=bundle["model_version"],
            key_feature_values=_key_features(features),
        )
        for features, score in zip(records, scores)
    ]
