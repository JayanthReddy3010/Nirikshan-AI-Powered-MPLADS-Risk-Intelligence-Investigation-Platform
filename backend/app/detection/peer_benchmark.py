"""Read-only peer-group benchmarking for work-level expenditure.

The benchmarked financial field is ``work_total_amount``:
SUM(work_transactions.fund_disbursed_amount), aggregated by work_id before any
peer comparison. No individual transaction is treated as a peer work.

Peer hierarchy, selected in this order when the group has enough works:
1. same state and same normalized work description
2. same state and same non-null IDA
3. same state

Descriptions are trimmed and compared case-insensitively. Blank descriptions and
NULL IDA values are not used for their respective specific grouping levels. A group
must contain at least PEER_MIN_GROUP_SIZE works. The default minimum is 10.

Percentile rank uses the PostgreSQL PERCENT_RANK definition: (rank - 1) / (N - 1),
with ties receiving the same rank. Standard deviation is population standard
deviation. The high-cost indicator triggers when amount / peer median is at least
PEER_AMOUNT_RATIO_THRESHOLD (default 1.50). A zero peer median produces no ratio
and cannot trigger the indicator.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from statistics import mean, median, pstdev
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.schemas.peer_benchmark import PeerBenchmarkResult


@dataclass(frozen=True)
class PeerBenchmarkSettings:
    """Configurable peer benchmark thresholds."""

    min_group_size: int = 10
    amount_ratio_threshold: Decimal = Decimal("1.50")

    @classmethod
    def from_environment(cls) -> "PeerBenchmarkSettings":
        return cls(
            min_group_size=_int_env("PEER_MIN_GROUP_SIZE", 10),
            amount_ratio_threshold=_decimal_env("PEER_AMOUNT_RATIO_THRESHOLD", "1.50"),
        )


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer value, got {value!r}") from None
    if parsed < 1:
        raise ValueError(f"{name} must be at least 1, got {value!r}")
    return parsed


def _decimal_env(name: str, default: str) -> Decimal:
    value = os.getenv(name, default)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError(f"{name} must be a decimal value, got {value!r}") from None
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0, got {value!r}")
    return parsed


_PEER_QUERY = text(
    """
    WITH work_totals AS (
        SELECT
            w.work_id,
            NULLIF(BTRIM(w.state), '') AS state_key,
            NULLIF(LOWER(BTRIM(w.work)), '') AS description_key,
            NULLIF(BTRIM(w.ida), '') AS ida_key,
            COALESCE(SUM(wt.fund_disbursed_amount), 0) AS work_total_amount
        FROM works w
        LEFT JOIN work_transactions wt ON wt.work_id = w.work_id
        GROUP BY w.work_id, state_key, description_key, ida_key
    ),
    target AS (
        SELECT *
        FROM work_totals
        WHERE work_id = :work_id
    ),
    candidate_groups AS (
        SELECT
            1 AS level_order,
            'state_and_description' AS level_name,
            t.state_key,
            t.description_key,
            NULL::text AS ida_key
        FROM target t
        WHERE t.state_key IS NOT NULL AND t.description_key IS NOT NULL
        UNION ALL
        SELECT
            2 AS level_order,
            'state_and_ida' AS level_name,
            t.state_key,
            NULL::text AS description_key,
            t.ida_key
        FROM target t
        WHERE t.state_key IS NOT NULL AND t.ida_key IS NOT NULL
        UNION ALL
        SELECT
            3 AS level_order,
            'state' AS level_name,
            t.state_key,
            NULL::text AS description_key,
            NULL::text AS ida_key
        FROM target t
        WHERE t.state_key IS NOT NULL
    ),
    eligible_groups AS (
        SELECT
            cg.level_order,
            cg.level_name,
            cg.state_key,
            cg.description_key,
            cg.ida_key,
            COUNT(wt.work_id)::integer AS peer_group_size
        FROM candidate_groups cg
        JOIN work_totals wt
          ON wt.state_key = cg.state_key
         AND (cg.description_key IS NULL OR wt.description_key = cg.description_key)
         AND (cg.ida_key IS NULL OR wt.ida_key = cg.ida_key)
        GROUP BY cg.level_order, cg.level_name, cg.state_key, cg.description_key, cg.ida_key
        HAVING COUNT(wt.work_id) >= :min_group_size
    ),
    selected_group AS (
        SELECT *
        FROM eligible_groups
        ORDER BY level_order
        LIMIT 1
    ),
    peer_members AS (
        SELECT
            wt.work_id,
            wt.work_total_amount,
            PERCENT_RANK() OVER (ORDER BY wt.work_total_amount) AS percentile_rank
        FROM selected_group sg
        JOIN work_totals wt
          ON wt.state_key = sg.state_key
         AND (sg.description_key IS NULL OR wt.description_key = sg.description_key)
         AND (sg.ida_key IS NULL OR wt.ida_key = sg.ida_key)
    ),
    peer_stats AS (
        SELECT
            COUNT(*)::integer AS peer_group_size,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY work_total_amount) AS peer_group_median_amount,
            AVG(work_total_amount) AS peer_group_mean_amount,
            STDDEV_POP(work_total_amount) AS peer_group_stddev
        FROM peer_members
    )
    SELECT
        t.work_id,
        t.work_total_amount AS actual_value,
        sg.level_name AS peer_group_level,
        ps.peer_group_size,
        ps.peer_group_median_amount,
        ps.peer_group_mean_amount,
        ps.peer_group_stddev,
        t.work_total_amount / NULLIF(ps.peer_group_median_amount, 0) AS amount_ratio_to_peer_median,
        pm.percentile_rank,
        t.work_total_amount - ps.peer_group_median_amount AS deviation_from_peer_median
    FROM target t
    LEFT JOIN selected_group sg ON TRUE
    LEFT JOIN peer_stats ps ON TRUE
    LEFT JOIN peer_members pm ON pm.work_id = t.work_id
    """
)

_ALL_PEER_QUERY = text(
    """
    WITH work_totals AS (
        SELECT
            w.work_id,
            NULLIF(BTRIM(w.state), '') AS state_key,
            NULLIF(LOWER(BTRIM(w.work)), '') AS description_key,
            NULLIF(BTRIM(w.ida), '') AS ida_key,
            COALESCE(SUM(wt.fund_disbursed_amount), 0) AS work_total_amount
        FROM works w
        LEFT JOIN work_transactions wt ON wt.work_id = w.work_id
        GROUP BY w.work_id, state_key, description_key, ida_key
    ),
    candidate_groups AS (
        SELECT t.work_id AS target_work_id, 1 AS level_order,
               'state_and_description' AS level_name, t.state_key,
               t.description_key, NULL::text AS ida_key
        FROM work_totals t
        WHERE t.state_key IS NOT NULL AND t.description_key IS NOT NULL
        UNION ALL
        SELECT t.work_id, 2, 'state_and_ida', t.state_key,
               NULL::text, t.ida_key
        FROM work_totals t
        WHERE t.state_key IS NOT NULL AND t.ida_key IS NOT NULL
        UNION ALL
        SELECT t.work_id, 3, 'state', t.state_key,
               NULL::text, NULL::text
        FROM work_totals t
        WHERE t.state_key IS NOT NULL
    ),
    eligible_groups AS (
        SELECT cg.target_work_id, cg.level_order, cg.level_name,
               cg.state_key, cg.description_key, cg.ida_key,
               COUNT(wt.work_id)::integer AS peer_group_size
        FROM candidate_groups cg
        JOIN work_totals wt
          ON wt.state_key = cg.state_key
         AND (cg.description_key IS NULL OR wt.description_key = cg.description_key)
         AND (cg.ida_key IS NULL OR wt.ida_key = cg.ida_key)
        GROUP BY cg.target_work_id, cg.level_order, cg.level_name,
                 cg.state_key, cg.description_key, cg.ida_key
        HAVING COUNT(wt.work_id) >= :min_group_size
    ),
    selected_group AS (
        SELECT DISTINCT ON (target_work_id) *
        FROM eligible_groups
        ORDER BY target_work_id, level_order
    ),
    peer_members AS (
        SELECT sg.target_work_id, wt.work_id, wt.work_total_amount,
               PERCENT_RANK() OVER (
                   PARTITION BY sg.target_work_id ORDER BY wt.work_total_amount
               ) AS percentile_rank
        FROM selected_group sg
        JOIN work_totals wt
          ON wt.state_key = sg.state_key
         AND (sg.description_key IS NULL OR wt.description_key = sg.description_key)
         AND (sg.ida_key IS NULL OR wt.ida_key = sg.ida_key)
    ),
    peer_stats AS (
        SELECT target_work_id, COUNT(*)::integer AS peer_group_size,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY work_total_amount)
                   AS peer_group_median_amount,
               AVG(work_total_amount) AS peer_group_mean_amount,
               STDDEV_POP(work_total_amount) AS peer_group_stddev
        FROM peer_members
        GROUP BY target_work_id
    )
    SELECT t.work_id, t.work_total_amount AS actual_value,
           sg.level_name AS peer_group_level, ps.peer_group_size,
           ps.peer_group_median_amount, ps.peer_group_mean_amount,
           ps.peer_group_stddev,
           t.work_total_amount / NULLIF(ps.peer_group_median_amount, 0)
               AS amount_ratio_to_peer_median,
           pm.percentile_rank,
           t.work_total_amount - ps.peer_group_median_amount
               AS deviation_from_peer_median
    FROM work_totals t
    LEFT JOIN selected_group sg ON sg.target_work_id = t.work_id
    LEFT JOIN peer_stats ps ON ps.target_work_id = t.work_id
    LEFT JOIN peer_members pm
      ON pm.target_work_id = t.work_id AND pm.work_id = t.work_id
    ORDER BY t.work_id
    """
)


def get_peer_benchmark(
    db: Session,
    work_id: str,
    settings: Optional[PeerBenchmarkSettings] = None,
) -> Optional[PeerBenchmarkResult]:
    """Return a read-only peer benchmark for one existing work."""
    active_settings = settings or PeerBenchmarkSettings.from_environment()
    row = db.execute(
        _PEER_QUERY,
        {"work_id": work_id, "min_group_size": active_settings.min_group_size},
    ).mappings().first()
    if row is None:
        return None

    if not row["peer_group_size"]:
        return PeerBenchmarkResult(
            work_id=work_id,
            triggered=False,
            severity="none",
            explanation="Insufficient comparable works for peer benchmarking.",
            actual_value=row["actual_value"],
            threshold=active_settings.amount_ratio_threshold,
        )

    ratio = row["amount_ratio_to_peer_median"]
    triggered = ratio is not None and ratio >= active_settings.amount_ratio_threshold
    if triggered:
        explanation = (
            f"Current work amount is {ratio:.2f} times the peer median and is above the "
            "peer-group cost benchmark."
        )
        severity = "medium"
    else:
        explanation = "Current work amount is not above the configured peer-group cost benchmark."
        severity = "none"

    return PeerBenchmarkResult(
        work_id=work_id,
        triggered=triggered,
        severity=severity,
        explanation=explanation,
        actual_value=row["actual_value"],
        peer_group_level=row["peer_group_level"],
        peer_group_size=row["peer_group_size"],
        peer_group_median_amount=row["peer_group_median_amount"],
        peer_group_mean_amount=row["peer_group_mean_amount"],
        peer_group_stddev=row["peer_group_stddev"],
        amount_ratio_to_peer_median=ratio,
        percentile_rank=row["percentile_rank"],
        deviation_from_peer_median=row["deviation_from_peer_median"],
        threshold=active_settings.amount_ratio_threshold,
    )


def get_all_peer_benchmarks(
    db: Session,
    settings: Optional[PeerBenchmarkSettings] = None,
) -> dict[str, PeerBenchmarkResult]:
    """Return peer results for all works from one work-level read-only query."""
    active_settings = settings or PeerBenchmarkSettings.from_environment()
    rows = db.execute(
        text(
            """
            SELECT
                w.work_id,
                NULLIF(BTRIM(w.state), '') AS state_key,
                NULLIF(LOWER(BTRIM(w.work)), '') AS description_key,
                NULLIF(BTRIM(w.ida), '') AS ida_key,
                COALESCE(SUM(wt.fund_disbursed_amount), 0) AS work_total_amount
            FROM works w
            LEFT JOIN work_transactions wt ON wt.work_id = w.work_id
            GROUP BY w.work_id, state_key, description_key, ida_key
            ORDER BY w.work_id
            """
        )
    ).mappings().all()

    group_members: dict[tuple, list[tuple[str, Decimal]]] = defaultdict(list)
    work_rows: dict[str, dict] = {}
    for row in rows:
        work_id = row["work_id"]
        amount = Decimal(str(row["work_total_amount"]))
        work_rows[work_id] = {**row, "work_total_amount": amount}
        if row["state_key"] is not None:
            group_members[(1, row["state_key"], row["description_key"], None)].append((work_id, amount))
            if row["ida_key"] is not None:
                group_members[(2, row["state_key"], None, row["ida_key"])] .append((work_id, amount))
            group_members[(3, row["state_key"], None, None)].append((work_id, amount))

    results: dict[str, PeerBenchmarkResult] = {}
    for work_id, row in work_rows.items():
        candidate_keys = (
            (1, row["state_key"], row["description_key"], None),
            (2, row["state_key"], None, row["ida_key"]),
            (3, row["state_key"], None, None),
        )
        selected = next(
            (key for key in candidate_keys if key[1] is not None and len(group_members.get(key, [])) >= active_settings.min_group_size),
            None,
        )
        if selected is None:
            results[work_id] = PeerBenchmarkResult(
                work_id=work_id,
                triggered=False,
                severity="none",
                explanation="Insufficient comparable works for peer benchmarking.",
                actual_value=row["work_total_amount"],
                threshold=active_settings.amount_ratio_threshold,
            )
            continue

        members = group_members[selected]
        amounts = [amount for _, amount in members]
        peer_median = median(amounts)
        peer_mean = mean(amounts)
        peer_stddev = pstdev(amounts)
        target_amount = row["work_total_amount"]
        ratio = target_amount / peer_median if peer_median else None
        less_than_target = sum(amount < target_amount for amount in amounts)
        percentile = Decimal(less_than_target) / Decimal(len(amounts) - 1) if len(amounts) > 1 else Decimal("0")
        triggered = ratio is not None and ratio >= active_settings.amount_ratio_threshold
        results[work_id] = PeerBenchmarkResult(
            work_id=work_id,
            triggered=triggered,
            severity="medium" if triggered else "none",
            explanation=(
                f"Current work amount is {ratio:.2f} times the peer median and is above the "
                "peer-group cost benchmark."
                if triggered
                else "Current work amount is not above the configured peer-group cost benchmark."
            ),
            actual_value=target_amount,
            peer_group_level=(
                "state_and_description" if selected[0] == 1
                else "state_and_ida" if selected[0] == 2
                else "state"
            ),
            peer_group_size=len(members),
            peer_group_median_amount=peer_median,
            peer_group_mean_amount=peer_mean,
            peer_group_stddev=peer_stddev,
            amount_ratio_to_peer_median=ratio,
            percentile_rank=percentile,
            deviation_from_peer_median=target_amount - peer_median,
            threshold=active_settings.amount_ratio_threshold,
        )
    return results
