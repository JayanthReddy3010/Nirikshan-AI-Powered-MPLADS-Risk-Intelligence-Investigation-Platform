from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.ml.delay_prediction import INSUFFICIENT_DATA_MESSAGE
from backend.app.schemas.api import (
    CompositeRiskEvidence,
    DashboardSummary,
    DelayAvailability,
    FinancialEvidence,
    MlEvidence,
    PaginatedTransactions,
    PaginatedWorks,
    PeerEvidence,
    RiskDistribution,
    RiskExposureItem,
    RiskWorkItem,
    StateSummaryItem,
    TemporalEvidence,
    TransactionItem,
    VendorEvidence,
    VendorSummaryItem,
    WorkDetailResponse,
    WorkInformation,
    WorkListItem,
)
from backend.app.models.investigation_action import InvestigationAction
from backend.app.schemas.investigation_action import InvestigationActionCreate, InvestigationActionResponse
from backend.app.services.feature_service import get_work_features
from backend.app.services.risk_cache import get_risk_snapshot
from backend.app.detection.rule_engine import get_work_rule_results

router = APIRouter(prefix="/api", tags=["investigation"])
ALLOWED_ACTIONS = {"Reviewed", "Request Documents", "Escalate", "Close Investigation"}


def _page(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise HTTPException(status_code=422, detail="page must be at least 1")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="page_size must be between 1 and 100")
    return (page - 1) * page_size, page_size


def _safe_read(operation):
    try:
        return operation()
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database query unavailable") from None
    except (FileNotFoundError, KeyError, ValueError):
        raise HTTPException(status_code=503, detail="Investigation service temporarily unavailable") from None


def _safe_write(operation, db: Session):
    try:
        return operation()
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Investigation action could not be saved") from None


@router.post(
    "/works/{work_id:path}/investigation-actions",
    response_model=InvestigationActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an officer investigation action",
)
def create_investigation_action(
    work_id: str,
    payload: InvestigationActionCreate,
    db: Session = Depends(get_db),
) -> InvestigationActionResponse:
    if payload.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=422, detail=f"action must be one of: {', '.join(sorted(ALLOWED_ACTIONS))}")

    def write():
        exists = db.execute(text("SELECT 1 FROM works WHERE work_id = :work_id"), {"work_id": work_id}).scalar()
        if exists is None:
            raise HTTPException(status_code=404, detail="Work not found")
        action = InvestigationAction(
            work_id=work_id,
            action=payload.action,
            comment=payload.comment,
            officer_name=payload.officer_name,
        )
        db.add(action)
        db.commit()
        db.refresh(action)
        return action

    return _safe_write(write, db)


@router.get(
    "/works/{work_id:path}/investigation-actions",
    response_model=list[InvestigationActionResponse],
    summary="Get officer investigation action history",
)
def list_investigation_actions(
    work_id: str,
    db: Session = Depends(get_db),
) -> list[InvestigationActionResponse]:
    def read():
        exists = db.execute(text("SELECT 1 FROM works WHERE work_id = :work_id"), {"work_id": work_id}).scalar()
        if exists is None:
            raise HTTPException(status_code=404, detail="Work not found")
        return db.query(InvestigationAction).filter(
            InvestigationAction.work_id == work_id
        ).order_by(InvestigationAction.created_at.desc(), InvestigationAction.id.desc()).all()

    return _safe_read(read)


@router.get("/works", response_model=PaginatedWorks, summary="Paginated works for investigation")
def list_works(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    state: Optional[str] = None,
    mp_name: Optional[str] = None,
    constituency: Optional[str] = None,
    search: Optional[str] = None,
    risk_band: Optional[str] = None,
    min_risk_score: Optional[float] = Query(None, ge=0, le=100),
    max_risk_score: Optional[float] = Query(None, ge=0, le=100),
    db: Session = Depends(get_db),
) -> PaginatedWorks:
    offset, limit = _page(page, page_size)
    if min_risk_score is not None and max_risk_score is not None and min_risk_score > max_risk_score:
        raise HTTPException(status_code=422, detail="min_risk_score cannot exceed max_risk_score")

    def read():
        rows = db.execute(
            text(
                """
                SELECT work_id, state, mp_name, constituency, work, ida
                FROM works
                WHERE (:state IS NULL OR state ILIKE :state_pattern)
                  AND (:mp_name IS NULL OR mp_name ILIKE :mp_name_pattern)
                  AND (:constituency IS NULL OR constituency ILIKE :constituency_pattern)
                  AND (:search IS NULL OR work_id ILIKE :search_pattern OR work ILIKE :search_pattern)
                ORDER BY work_id
                """
            ),
            {
                "state": state,
                "state_pattern": f"%{state}%" if state else None,
                "mp_name": mp_name,
                "mp_name_pattern": f"%{mp_name}%" if mp_name else None,
                "constituency": constituency,
                "constituency_pattern": f"%{constituency}%" if constituency else None,
                "search": search,
                "search_pattern": f"%{search}%" if search else None,
            },
        ).mappings().all()
        snapshot = get_risk_snapshot(db)
        items = []
        for row in rows:
            risk = snapshot.get(row["work_id"])
            if risk is None:
                continue
            if risk_band and risk.risk_band != risk_band:
                continue
            if min_risk_score is not None and risk.final_risk_score < min_risk_score:
                continue
            if max_risk_score is not None and risk.final_risk_score > max_risk_score:
                continue
            items.append(
                WorkListItem(
                    **dict(row), risk_score=risk.final_risk_score, risk_band=risk.risk_band
                )
            )
        return PaginatedWorks(page=page, page_size=page_size, total=len(items), items=items[offset : offset + limit])

    return _safe_read(read)


@router.get("/works/{work_id:path}", response_model=WorkDetailResponse, summary="Complete investigation view for one work")
def work_detail(
    work_id: str,
    transaction_page: int = Query(1, ge=1),
    transaction_page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> WorkDetailResponse:
    offset, limit = _page(transaction_page, transaction_page_size)

    def read():
        work = db.execute(
            text("SELECT work_id, state, mp_name, constituency, work, ida FROM works WHERE work_id = :work_id"),
            {"work_id": work_id},
        ).mappings().first()
        if work is None:
            raise HTTPException(status_code=404, detail="Work not found")
        features = get_work_features(db, work_id)
        snapshot = get_risk_snapshot(db)
        risk = snapshot.get(work_id)
        if features is None or risk is None:
            raise HTTPException(status_code=404, detail="Work detection evidence not found")
        all_rules = get_work_rule_results(db, work_id)
        transaction_total = db.execute(
            text("SELECT COUNT(*) FROM work_transactions WHERE work_id = :work_id"),
            {"work_id": work_id},
        ).scalar_one()
        transactions = db.execute(
            text(
                """
                SELECT source_row_number, expenditure_date, vendor_name,
                       payment_status, fund_disbursed_amount
                FROM work_transactions
                WHERE work_id = :work_id
                ORDER BY source_row_number
                OFFSET :offset LIMIT :limit
                """
            ),
            {"work_id": work_id, "offset": offset, "limit": limit},
        ).mappings().all()
        peer = risk.peer_evidence
        ml = risk.ml_evidence
        return WorkDetailResponse(
            work_information=WorkInformation(**dict(work)),
            financial_evidence=FinancialEvidence(
                total_disbursed_amount=features.total_disbursed_amount,
                transaction_count=features.transaction_count,
                average_transaction_amount=features.average_transaction_amount,
                maximum_transaction_amount=features.maximum_transaction_amount,
                minimum_transaction_amount=features.minimum_transaction_amount,
                transaction_amount_stddev=features.transaction_amount_stddev,
            ),
            vendor_evidence=VendorEvidence(
                unique_vendor_count=features.unique_vendor_count,
                primary_vendor=features.primary_vendor,
                primary_vendor_amount=features.primary_vendor_amount,
                primary_vendor_share=features.primary_vendor_share,
            ),
            temporal_evidence=TemporalEvidence(
                first_expenditure_date=features.first_expenditure_date,
                latest_expenditure_date=features.latest_expenditure_date,
                days_between_first_and_last_transaction=features.days_between_first_and_last_transaction,
                average_days_between_transactions=features.average_days_between_transactions,
            ),
            rule_evidence=all_rules or [],
            peer_evidence=PeerEvidence(**peer, available=risk.peer_score is not None),
            ml_evidence=MlEvidence(
                model_name="IsolationForest",
                model_version=ml.get("model_version"),
                anomaly_score=ml.get("anomaly_score"),
                anomaly_label=ml.get("anomaly_label"),
                important_feature_values=ml.get("key_feature_values", {}),
            ),
            delay_prediction=DelayAvailability(available=False, reason=INSUFFICIENT_DATA_MESSAGE),
            composite_risk=CompositeRiskEvidence(
                final_score=risk.final_risk_score,
                risk_band=risk.risk_band,
                rule_score=risk.rule_score,
                peer_score=risk.peer_score,
                isolation_forest_score=risk.isolation_forest_score,
                delay_score=None,
                available_signals=risk.available_signals,
                unavailable_signals=risk.unavailable_signals,
                explanation=risk.explanation,
            ),
            transactions=PaginatedTransactions(
                page=transaction_page,
                page_size=transaction_page_size,
                total=transaction_total,
                items=[TransactionItem(**dict(row)) for row in transactions],
            ),
        )

    return _safe_read(read)


def _risk_counts(snapshot):
    return Counter(result.risk_band for result in snapshot.values())


def _dashboard_dataset_metrics(db: Session):
    works = db.execute(text("SELECT COUNT(*) FROM works")).scalar_one()
    transactions = db.execute(text("SELECT COUNT(*) FROM work_transactions")).scalar_one()
    import_errors = db.execute(text("SELECT COUNT(*) FROM import_errors")).scalar_one()
    return {
        "works": int(works),
        "transactions": int(transactions),
        "source_rows": int(transactions + import_errors),
        "valid_rows": int(transactions),
        "import_errors": int(import_errors),
    }


def _matches_dashboard_filters(row, snapshot_entry, state=None, risk_band=None, min_risk_score=None, max_risk_score=None, search=None):
    if state and (not row["state"] or state.lower() not in str(row["state"]).lower()):
        return False
    if risk_band and snapshot_entry.risk_band != risk_band:
        return False
    if min_risk_score is not None and snapshot_entry.final_risk_score < min_risk_score:
        return False
    if max_risk_score is not None and snapshot_entry.final_risk_score > max_risk_score:
        return False
    if search:
        needle = search.lower()
        work_text = str(row.get("work") or "").lower()
        work_id_text = str(row.get("work_id") or "").lower()
        if needle not in work_text and needle not in work_id_text:
            return False
    return True


@router.get("/dashboard/summary", response_model=DashboardSummary, summary="Dashboard totals and top investigation candidates")
def dashboard_summary(
    state: Optional[str] = None,
    risk_band: Optional[str] = None,
    min_risk_score: Optional[float] = Query(None, ge=0, le=100),
    max_risk_score: Optional[float] = Query(None, ge=0, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
) -> DashboardSummary:
    def read():
        snapshot = get_risk_snapshot(db)
        dataset = _dashboard_dataset_metrics(db)
        work_totals = db.execute(
            text(
                """
                SELECT w.work_id, w.state, w.work,
                       COUNT(wt.id)::integer AS transaction_count,
                       COALESCE(SUM(wt.fund_disbursed_amount), 0) AS total_amount
                FROM works w
                LEFT JOIN work_transactions wt ON wt.work_id = w.work_id
                GROUP BY w.work_id, w.state, w.work
                """
            )
        ).mappings().all()

        any_filter_applied = any(value not in (None, "") for value in [state, risk_band, search, min_risk_score, max_risk_score])
        filtered = []
        for row in work_totals:
            risk = snapshot.get(row["work_id"])
            if risk is None:
                continue
            if not _matches_dashboard_filters(row, risk, state=state, risk_band=risk_band, min_risk_score=min_risk_score, max_risk_score=max_risk_score, search=search):
                continue
            filtered.append((row, risk))

        filtered_work_count = len(filtered)
        filtered_total_amount = sum((row["total_amount"] for row, _ in filtered), Decimal("0"))
        filtered_transaction_count = sum((row["transaction_count"] for row, _ in filtered), 0)
        counts = _risk_counts({row["work_id"]: risk for row, risk in filtered}) if filtered else {}
        full_counts = _risk_counts(snapshot)
        top = sorted((risk for _, risk in filtered), key=lambda item: item.final_risk_score, reverse=True)[:10]
        total_works = filtered_work_count if any_filter_applied else dataset["works"]
        total_transactions = filtered_transaction_count if any_filter_applied else dataset["transactions"]
        total_amount = filtered_total_amount if any_filter_applied else db.execute(
            text("SELECT COALESCE(SUM(fund_disbursed_amount), 0) FROM work_transactions")
        ).scalar_one() or Decimal("0")

        return DashboardSummary(
            total_works=total_works,
            works=dataset["works"],
            total_transactions=total_transactions,
            transactions=dataset["transactions"],
            total_disbursed_amount=total_amount,
            source_rows=dataset["source_rows"],
            valid_rows=dataset["valid_rows"],
            import_errors=dataset["import_errors"],
            low_risk_count=counts.get("Low investigation priority", 0 if any_filter_applied else full_counts.get("Low investigation priority", 0)),
            moderate_risk_count=counts.get("Moderate investigation priority", 0 if any_filter_applied else full_counts.get("Moderate investigation priority", 0)),
            high_risk_count=counts.get("High investigation priority", 0 if any_filter_applied else full_counts.get("High investigation priority", 0)),
            critical_risk_count=counts.get("Critical investigation priority", 0 if any_filter_applied else full_counts.get("Critical investigation priority", 0)),
            investigation_candidate_count=sum(item.final_risk_score >= 60 for item in top) if any_filter_applied else sum(item.final_risk_score >= 60 for item in snapshot.values()),
            top_10_highest_risk_works=[
                RiskWorkItem(
                    work_id=item.work_id,
                    risk_score=item.final_risk_score,
                    risk_band=item.risk_band,
                    amount=next((row["total_amount"] for row, risk in filtered if risk.work_id == item.work_id), Decimal("0")),
                )
                for item in top
            ],
        )

    return _safe_read(read)


@router.get("/dashboard/state-summary", response_model=list[StateSummaryItem], summary="State-level investigation summary")
def state_summary(
    state: Optional[str] = None,
    risk_band: Optional[str] = None,
    min_risk_score: Optional[float] = Query(None, ge=0, le=100),
    max_risk_score: Optional[float] = Query(None, ge=0, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[StateSummaryItem]:
    def read():
        rows = db.execute(
            text(
                """
                SELECT w.state, w.work_id, COUNT(wt.id)::integer AS transaction_count,
                       COALESCE(SUM(wt.fund_disbursed_amount), 0) AS total_amount
                FROM works w
                LEFT JOIN work_transactions wt ON wt.work_id = w.work_id
                GROUP BY w.state, w.work_id
                ORDER BY w.state, w.work_id
                """
            )
        ).mappings().all()
        snapshot = get_risk_snapshot(db)
        grouped = defaultdict(list)
        for row in rows:
            risk = snapshot.get(row["work_id"])
            if risk is None:
                continue
            if not _matches_dashboard_filters({"state": row["state"], "work_id": row["work_id"]}, risk, state=state, risk_band=risk_band, min_risk_score=min_risk_score, max_risk_score=max_risk_score, search=search):
                continue
            grouped[row["state"]].append(row)
        output = []
        for state_name, works in grouped.items():
            amounts = [row["total_amount"] for row in works]
            output.append(
                StateSummaryItem(
                    state=state_name,
                    work_count=len(works),
                    transaction_count=sum(row["transaction_count"] for row in works),
                    total_amount=sum(amounts, Decimal("0")),
                    average_work_amount=sum(amounts, Decimal("0")) / len(amounts),
                    high_risk_work_count=sum(snapshot[row["work_id"]].risk_band == "High investigation priority" for row in works),
                    critical_risk_work_count=sum(snapshot[row["work_id"]].risk_band == "Critical investigation priority" for row in works),
                )
            )
        return output

    return _safe_read(read)


@router.get("/dashboard/vendor-summary", response_model=list[VendorSummaryItem], summary="Vendor-level investigation summary")
def vendor_summary(
    state: Optional[str] = None,
    risk_band: Optional[str] = None,
    min_risk_score: Optional[float] = Query(None, ge=0, le=100),
    max_risk_score: Optional[float] = Query(None, ge=0, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[VendorSummaryItem]:
    def read():
        rows = db.execute(
            text(
                """
                WITH vendor_work AS (
                    SELECT NULLIF(BTRIM(wt.vendor_name), '') AS vendor_name,
                           wt.work_id, w.state,
                           SUM(wt.fund_disbursed_amount) AS work_vendor_amount,
                           COUNT(*) AS transaction_count
                    FROM work_transactions wt
                    JOIN works w ON w.work_id = wt.work_id
                    WHERE NULLIF(BTRIM(wt.vendor_name), '') IS NOT NULL
                    GROUP BY NULLIF(BTRIM(wt.vendor_name), ''), wt.work_id, w.state
                )
                SELECT vendor_name, work_id, state, work_vendor_amount
                FROM vendor_work
                WHERE transaction_count >= 2
                ORDER BY vendor_name, work_id
                """
            )
        ).mappings().all()
        snapshot = get_risk_snapshot(db)
        grouped = defaultdict(list)
        for row in rows:
            risk = snapshot.get(row["work_id"])
            if risk is None:
                continue
            if not _matches_dashboard_filters({"state": row["state"], "work_id": row["work_id"]}, risk, state=state, risk_band=risk_band, min_risk_score=min_risk_score, max_risk_score=max_risk_score, search=search):
                continue
            grouped[row["vendor_name"]].append(row)
        output = []
        for vendor, works in grouped.items():
            amounts = [row["work_vendor_amount"] for row in works]
            output.append(
                VendorSummaryItem(
                    vendor_name=vendor,
                    work_count=len(works),
                    transaction_count=sum(1 for row in works),
                    total_amount=sum(amounts, Decimal("0")),
                    average_work_amount=sum(amounts, Decimal("0")) / len(amounts),
                    unique_states=len({row["state"] for row in works}),
                    high_risk_work_count=sum(snapshot[row["work_id"]].risk_band == "High investigation priority" for row in works),
                )
            )
        return sorted(output, key=lambda item: item.total_amount, reverse=True)

    return _safe_read(read)


@router.get("/dashboard/risk-distribution", response_model=RiskDistribution, summary="Risk score distribution")
def risk_distribution(
    state: Optional[str] = None,
    risk_band: Optional[str] = None,
    min_risk_score: Optional[float] = Query(None, ge=0, le=100),
    max_risk_score: Optional[float] = Query(None, ge=0, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
) -> RiskDistribution:
    def read():
        snapshot = get_risk_snapshot(db)
        if any(value not in (None, "") for value in [state, risk_band, search, min_risk_score, max_risk_score]):
            work_rows = db.execute(
                text(
                    """
                    SELECT work_id, state, work
                    FROM works
                    WHERE (:state IS NULL OR state ILIKE :state_pattern)
                      AND (:search IS NULL OR work_id ILIKE :search_pattern OR work ILIKE :search_pattern)
                    ORDER BY work_id
                    """
                ),
                {
                    "state": state,
                    "state_pattern": f"%{state}%" if state else None,
                    "search": search,
                    "search_pattern": f"%{search}%" if search else None,
                },
            ).mappings().all()
            subset = {}
            for row in work_rows:
                risk = snapshot.get(row["work_id"])
                if risk is None:
                    continue
                if not _matches_dashboard_filters(row, risk, state=state, risk_band=risk_band, min_risk_score=min_risk_score, max_risk_score=max_risk_score, search=search):
                    continue
                subset[row["work_id"]] = risk
            snapshot = subset
        scores = [item.final_risk_score for item in snapshot.values()]
        counts = _risk_counts(snapshot)
        ordered = sorted(scores)
        middle = len(ordered) // 2
        median_score = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        return RiskDistribution(
            minimum_score=min(scores),
            median_score=median_score,
            maximum_score=max(scores),
            low_risk_count=counts["Low investigation priority"],
            moderate_risk_count=counts["Moderate investigation priority"],
            high_risk_count=counts["High investigation priority"],
            critical_risk_count=counts["Critical investigation priority"],
        )

    return _safe_read(read)


@router.get(
    "/dashboard/risk-exposure",
    response_model=list[RiskExposureItem],
    summary="Disbursed amount by investigation priority",
)
def risk_exposure(
    state: Optional[str] = None,
    risk_band: Optional[str] = None,
    min_risk_score: Optional[float] = Query(None, ge=0, le=100),
    max_risk_score: Optional[float] = Query(None, ge=0, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[RiskExposureItem]:
    """Aggregate real transaction amounts by work, then join cached risk bands."""
    def read():
        rows = db.execute(
            text(
                """
                SELECT wt.work_id, w.state, w.work,
                       COALESCE(SUM(wt.fund_disbursed_amount), 0) AS total_amount
                FROM work_transactions wt
                JOIN works w ON w.work_id = wt.work_id
                GROUP BY wt.work_id, w.state, w.work
                """
            )
        ).mappings().all()
        snapshot = get_risk_snapshot(db)
        if any(value not in (None, "") for value in [state, risk_band, search, min_risk_score, max_risk_score]):
            filtered_rows = []
            for row in rows:
                risk = snapshot.get(row["work_id"])
                if risk is None:
                    continue
                if not _matches_dashboard_filters(row, risk, state=state, risk_band=risk_band, min_risk_score=min_risk_score, max_risk_score=max_risk_score, search=search):
                    continue
                filtered_rows.append(row)
            rows = filtered_rows
        totals = defaultdict(lambda: {"work_count": 0, "total_amount": Decimal("0")})
        for row in rows:
            risk = snapshot.get(row["work_id"])
            if risk is None:
                continue
            totals[risk.risk_band]["work_count"] += 1
            totals[risk.risk_band]["total_amount"] += row["total_amount"]
        order = [
            "Low investigation priority",
            "Moderate investigation priority",
            "High investigation priority",
            "Critical investigation priority",
        ]
        return [RiskExposureItem(risk_band=band, **totals[band]) for band in order]

    return _safe_read(read)
