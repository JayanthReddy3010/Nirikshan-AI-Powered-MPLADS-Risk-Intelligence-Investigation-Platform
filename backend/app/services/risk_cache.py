"""Process-local cache for the immutable imported-data demo snapshot."""

from __future__ import annotations

from threading import Lock

from sqlalchemy.orm import Session

from backend.app.detection.risk_score import RiskScoreSettings, score_all_works
from backend.app.schemas.risk_score import RiskScoreResult

_cache: dict[str, RiskScoreResult] | None = None
_cache_lock = Lock()


def initialize_risk_snapshot(db: Session) -> dict[str, RiskScoreResult]:
    """Build the complete composite snapshot once during application startup."""
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = {
                result.work_id: result
                for result in score_all_works(db, RiskScoreSettings.from_environment())
            }
        return _cache


def get_risk_snapshot(db: Session) -> dict[str, RiskScoreResult]:
    """Return the startup-built snapshot without doing request-time computation."""
    if _cache is None:
        raise RuntimeError("Risk snapshot is not initialized; application startup did not complete")
    return _cache


def clear_risk_snapshot() -> None:
    """Clear only the process-local cache; never changes database data."""
    global _cache
    with _cache_lock:
        _cache = None
