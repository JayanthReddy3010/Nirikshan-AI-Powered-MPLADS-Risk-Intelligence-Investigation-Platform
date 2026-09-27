"""Explainable composite investigation-priority scoring.

This engine combines rule, peer, and Isolation Forest signals. It never treats an
unavailable signal as a zero-risk signal: unavailable weights are removed from the
normalization denominator. Delay prediction is currently unavailable because the
real dataset has no defensible completion outcome.

Defaults:
- RULE_WEIGHT=0.30
- PEER_WEIGHT=0.25
- ISOLATION_FOREST_WEIGHT=0.45
- DELAY_WEIGHT=0.10 (used only if a trained delay model becomes available)

Rule score: triggered rules are assigned high=70, medium=45, low=20. After sorting
by contribution, the highest contribution is used in full and each subsequent one
is multiplied by 0.5, then 0.25, and so on. The result is capped at 100.

Peer score: ratio <= 1 maps linearly from 0 to 10; ratio 1 to 1.5 maps from 10
to 40; ratio 1.5 to 3 maps from 40 to 100; ratios >= 3 are capped at 100.
Missing peer benchmarks and zero peer medians are unavailable.

The final score is the weighted mean of available signals only. Risk bands are
0-29 Low, 30-59 Moderate, 60-79 High, and 80-100 Critical investigation priority.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.detection.peer_benchmark import get_peer_benchmark
from backend.app.detection.rule_engine import get_work_rule_results
from backend.app.ml.delay_prediction import predict_work_delay
from backend.app.ml.isolation_forest import predict_work_anomaly
from backend.app.schemas.anomaly import WorkAnomalyResult
from backend.app.schemas.detection import RuleResult
from backend.app.schemas.peer_benchmark import PeerBenchmarkResult
from backend.app.schemas.risk_score import RiskScoreResult


@dataclass(frozen=True)
class RiskScoreSettings:
    rule_weight: float = 0.30
    peer_weight: float = 0.25
    isolation_forest_weight: float = 0.45
    delay_weight: float = 0.10
    high_rule_score: float = 70.0
    medium_rule_score: float = 45.0
    low_rule_score: float = 20.0

    @classmethod
    def from_environment(cls) -> "RiskScoreSettings":
        settings = cls(
            rule_weight=float(os.getenv("RULE_WEIGHT", "0.30")),
            peer_weight=float(os.getenv("PEER_WEIGHT", "0.25")),
            isolation_forest_weight=float(os.getenv("ISOLATION_FOREST_WEIGHT", "0.45")),
            delay_weight=float(os.getenv("DELAY_WEIGHT", "0.10")),
        )
        if any(weight < 0 for weight in (settings.rule_weight, settings.peer_weight, settings.isolation_forest_weight, settings.delay_weight)):
            raise ValueError("Risk signal weights must be non-negative")
        if settings.rule_weight + settings.peer_weight + settings.isolation_forest_weight + settings.delay_weight == 0:
            raise ValueError("At least one risk signal weight must be positive")
        return settings


def rule_score(rule_results: Sequence[RuleResult], settings: RiskScoreSettings) -> float:
    severity_scores = {
        "high": settings.high_rule_score,
        "medium": settings.medium_rule_score,
        "low": settings.low_rule_score,
    }
    contributions = sorted(
        (severity_scores.get(rule.severity, 0.0) for rule in rule_results if rule.triggered),
        reverse=True,
    )
    return min(100.0, sum(value * (0.5**index) for index, value in enumerate(contributions)))


def peer_score(peer: Optional[PeerBenchmarkResult]) -> Optional[float]:
    if peer is None or peer.amount_ratio_to_peer_median is None:
        return None
    ratio = float(peer.amount_ratio_to_peer_median)
    if ratio <= 0:
        return 0.0
    if ratio <= 1:
        return ratio * 10.0
    if ratio <= 1.5:
        return 10.0 + (ratio - 1.0) * 60.0
    return min(100.0, 40.0 + (ratio - 1.5) * 40.0)


def risk_band(score: float) -> str:
    if score < 30:
        return "Low investigation priority"
    if score < 60:
        return "Moderate investigation priority"
    if score < 80:
        return "High investigation priority"
    return "Critical investigation priority"


def _weighted_score(signals: dict[str, tuple[Optional[float], float]]) -> tuple[float, list[str], list[str]]:
    available = {name: (value, weight) for name, (value, weight) in signals.items() if value is not None and weight > 0}
    available_names = list(available)
    unavailable_names = [name for name, (value, _) in signals.items() if value is None]
    denominator = sum(weight for _, weight in available.values())
    if denominator == 0:
        return 0.0, available_names, unavailable_names
    score = sum(value * weight for value, weight in available.values()) / denominator
    return max(0.0, min(100.0, score)), available_names, unavailable_names


def compose_risk_score(
    work_id: str,
    rule_results: Sequence[RuleResult],
    peer: Optional[PeerBenchmarkResult],
    isolation_forest: Optional[WorkAnomalyResult],
    delay_score: Optional[float] = None,
    delay_available: bool = False,
    settings: Optional[RiskScoreSettings] = None,
) -> RiskScoreResult:
    active_settings = settings or RiskScoreSettings.from_environment()
    rules = list(rule_results)
    calculated_rule_score = rule_score(rules, active_settings)
    calculated_peer_score = peer_score(peer)
    isolation_score = isolation_forest.anomaly_score if isolation_forest is not None else None
    signals = {
        "rule": (calculated_rule_score, active_settings.rule_weight),
        "peer": (calculated_peer_score, active_settings.peer_weight),
        "isolation_forest": (isolation_score, active_settings.isolation_forest_weight),
        "delay": (delay_score if delay_available else None, active_settings.delay_weight),
    }
    final_score, available_signals, unavailable_signals = _weighted_score(signals)
    triggered = [rule for rule in rules if rule.triggered]
    peer_evidence = peer.model_dump() if peer is not None else {"available": False}
    ml_evidence = isolation_forest.model_dump() if isolation_forest is not None else {"available": False}
    explanation = (
        f"Nirikshan Risk Score: {final_score:.1f} - {risk_band(final_score)}. "
        f"Available signals: {', '.join(available_signals)}."
    )
    if triggered:
        explanation += f" {len(triggered)} rule indicator(s) were triggered."
    if unavailable_signals:
        explanation += f" Unavailable signals: {', '.join(unavailable_signals)}."
    return RiskScoreResult(
        work_id=work_id,
        final_risk_score=final_score,
        risk_band=risk_band(final_score),
        rule_score=calculated_rule_score,
        peer_score=calculated_peer_score,
        isolation_forest_score=isolation_score,
        delay_score=delay_score if delay_available else None,
        available_signals=available_signals,
        unavailable_signals=unavailable_signals,
        triggered_rules=triggered,
        peer_evidence=peer_evidence,
        ml_evidence=ml_evidence,
        explanation=explanation,
        model_versions_configuration={
            "isolation_forest": isolation_forest.model_version if isolation_forest else None,
            "delay": "unavailable",
            "weights": {
                "rule": active_settings.rule_weight,
                "peer": active_settings.peer_weight,
                "isolation_forest": active_settings.isolation_forest_weight,
                "delay": active_settings.delay_weight,
            },
        },
    )


def get_work_risk_score(
    db: Session, work_id: str, settings: Optional[RiskScoreSettings] = None
) -> Optional[RiskScoreResult]:
    """Read real detection signals and return one explainable composite result."""
    rule_results = get_work_rule_results(db, work_id)
    peer = get_peer_benchmark(db, work_id)
    isolation = predict_work_anomaly(db, work_id)
    delay = predict_work_delay(db, work_id)
    if rule_results is None or isolation is None:
        return None
    return compose_risk_score(
        work_id,
        rule_results,
        peer,
        isolation,
        delay_score=delay.delay_risk_score if delay.available else None,
        delay_available=delay.available,
        settings=settings,
    )


def score_all_works(db: Session, settings: Optional[RiskScoreSettings] = None) -> list[RiskScoreResult]:
    """Score all works using the persisted Isolation Forest and real detection data."""
    from backend.app.detection.peer_benchmark import get_all_peer_benchmarks
    from backend.app.ml.isolation_forest import score_all_works as score_all_anomalies
    from backend.app.services.feature_service import get_all_work_features
    from backend.app.detection.rule_engine import detect_work

    active_settings = settings or RiskScoreSettings.from_environment()
    anomaly_results = {result.work_id: result for result in score_all_anomalies(db)}
    peers = get_all_peer_benchmarks(db)
    output = []
    for features in get_all_work_features(db):
        result = compose_risk_score(
            features.work_id,
            detect_work(features),
            peers.get(features.work_id),
            anomaly_results.get(features.work_id),
            settings=active_settings,
        )
        output.append(result)
    return output
