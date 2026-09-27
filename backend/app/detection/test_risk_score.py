from __future__ import annotations

import unittest
from decimal import Decimal

from backend.app.database import SessionLocal
from backend.app.detection.peer_benchmark import PeerBenchmarkSettings, get_peer_benchmark
from backend.app.detection.risk_score import (
    RiskScoreSettings,
    compose_risk_score,
    get_work_risk_score,
    risk_band,
)
from backend.app.detection.rule_engine import RuleSettings, get_work_rule_results
from backend.app.ml.isolation_forest import predict_work_anomaly

WORK_ID = "WS/MP18170/2025-2026/194491"
HIGH_PEER_WORK_ID = "WS/\t MP005/2024-2025/145074"
HIGH_COMPOSITE_WORK_ID = "WS/MP492/2025-2026/194809"


class RiskScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SessionLocal() as db:
            cls.result = get_work_risk_score(db, WORK_ID)
        if cls.result is None:
            raise unittest.SkipTest("Required real work is not available.")

    def test_normal_work_configuration(self) -> None:
        rule_settings = RuleSettings(
            high_transaction_concentration_threshold=Decimal("2"),
            high_vendor_concentration_threshold=Decimal("2"),
            fragmentation_transaction_count_threshold=100000,
            large_transaction_threshold=Decimal("1000000000"),
        )
        with SessionLocal() as db:
            rules = get_work_rule_results(db, WORK_ID, rule_settings)
            peer = get_peer_benchmark(db, WORK_ID)
            isolation = predict_work_anomaly(db, WORK_ID)
        result = compose_risk_score(
            WORK_ID,
            rules,
            peer,
            isolation,
            settings=RiskScoreSettings(peer_weight=0, isolation_forest_weight=0),
        )
        self.assertEqual(result.rule_score, 0)
        self.assertEqual(result.final_risk_score, 0)

    def test_one_rule_triggered(self) -> None:
        with SessionLocal() as db:
            rules = get_work_rule_results(
                db,
                WORK_ID,
                RuleSettings(
                    high_vendor_concentration_threshold=Decimal("2"),
                    fragmentation_transaction_count_threshold=100000,
                    large_transaction_threshold=Decimal("1000000000"),
                ),
            )
            peer = get_peer_benchmark(db, WORK_ID)
            isolation = predict_work_anomaly(db, WORK_ID)
        result = compose_risk_score(WORK_ID, rules, peer, isolation)
        self.assertGreater(result.rule_score, 0)
        self.assertEqual(len(result.triggered_rules), 1)

    def test_multiple_rules_triggered(self) -> None:
        self.assertGreaterEqual(len(self.result.triggered_rules), 2)
        self.assertLess(self.result.rule_score, 100)

    def test_high_peer_deviation(self) -> None:
        with SessionLocal() as db:
            peer = get_peer_benchmark(db, HIGH_PEER_WORK_ID)
            rules = get_work_rule_results(db, HIGH_PEER_WORK_ID)
            isolation = predict_work_anomaly(db, HIGH_PEER_WORK_ID)
        result = compose_risk_score(HIGH_PEER_WORK_ID, rules, peer, isolation)
        self.assertGreaterEqual(result.peer_score, 40.0)

    def test_high_isolation_forest_score(self) -> None:
        self.assertIsNotNone(self.result.isolation_forest_score)
        self.assertGreaterEqual(self.result.isolation_forest_score, 0)

    def test_all_three_signals_elevated(self) -> None:
        with SessionLocal() as db:
            result = get_work_risk_score(db, HIGH_COMPOSITE_WORK_ID)
        self.assertIn("rule", result.available_signals)
        self.assertIn("peer", result.available_signals)
        self.assertIn("isolation_forest", result.available_signals)
        self.assertGreater(result.rule_score, 0)
        self.assertGreaterEqual(result.peer_score, 40)
        self.assertGreaterEqual(result.isolation_forest_score, 70)
        self.assertIn("delay", result.unavailable_signals)

    def test_peer_unavailable(self) -> None:
        with SessionLocal() as db:
            rules = get_work_rule_results(db, WORK_ID)
            peer = get_peer_benchmark(db, WORK_ID, PeerBenchmarkSettings(min_group_size=100000))
            isolation = predict_work_anomaly(db, WORK_ID)
        result = compose_risk_score(WORK_ID, rules, peer, isolation)
        self.assertIsNone(result.peer_score)
        self.assertIn("peer", result.unavailable_signals)
        self.assertNotIn("peer", result.available_signals)

    def test_delay_model_unavailable(self) -> None:
        self.assertIsNone(self.result.delay_score)
        self.assertIn("delay", self.result.unavailable_signals)

    def test_final_score_bounds(self) -> None:
        self.assertGreaterEqual(self.result.final_risk_score, 0)
        self.assertLessEqual(self.result.final_risk_score, 100)

    def test_risk_band_boundaries(self) -> None:
        self.assertEqual(risk_band(0), "Low investigation priority")
        self.assertEqual(risk_band(29.99), "Low investigation priority")
        self.assertEqual(risk_band(30), "Moderate investigation priority")
        self.assertEqual(risk_band(59.99), "Moderate investigation priority")
        self.assertEqual(risk_band(60), "High investigation priority")
        self.assertEqual(risk_band(79.99), "High investigation priority")
        self.assertEqual(risk_band(80), "Critical investigation priority")

    def test_deterministic_output(self) -> None:
        with SessionLocal() as db:
            first = get_work_risk_score(db, WORK_ID).model_dump()
            second = get_work_risk_score(db, WORK_ID).model_dump()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
