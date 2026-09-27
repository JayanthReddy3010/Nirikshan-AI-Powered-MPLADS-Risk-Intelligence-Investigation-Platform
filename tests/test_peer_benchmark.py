from __future__ import annotations

import unittest
from decimal import Decimal

from backend.app.database import SessionLocal
from backend.app.detection.peer_benchmark import PeerBenchmarkSettings, get_peer_benchmark

WORK_ID = "WS/MP18170/2025-2026/194491"


class PeerBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SessionLocal() as db:
            cls.result = get_peer_benchmark(db, WORK_ID)
        if cls.result is None:
            raise unittest.SkipTest(f"Real work {WORK_ID} is not available.")

    def test_sufficient_peer_group(self) -> None:
        self.assertGreaterEqual(self.result.peer_group_size, 10)
        self.assertIsNotNone(self.result.peer_group_median_amount)
        self.assertIsNotNone(self.result.peer_group_mean_amount)
        self.assertIsNotNone(self.result.peer_group_stddev)
        self.assertIsNotNone(self.result.percentile_rank)

    def test_high_cost_work(self) -> None:
        settings = PeerBenchmarkSettings(
            amount_ratio_threshold=self.result.amount_ratio_to_peer_median - Decimal("0.000001")
        )
        with SessionLocal() as db:
            result = get_peer_benchmark(db, WORK_ID, settings)
        self.assertTrue(result.triggered)
        self.assertIn("above the peer-group cost benchmark", result.explanation)

    def test_normal_cost_work(self) -> None:
        settings = PeerBenchmarkSettings(
            amount_ratio_threshold=self.result.amount_ratio_to_peer_median + Decimal("0.01")
        )
        with SessionLocal() as db:
            result = get_peer_benchmark(db, WORK_ID, settings)
        self.assertFalse(result.triggered)

    def test_insufficient_peer_group(self) -> None:
        settings = PeerBenchmarkSettings(min_group_size=100000)
        with SessionLocal() as db:
            result = get_peer_benchmark(db, WORK_ID, settings)
        self.assertIsNotNone(result)
        self.assertFalse(result.triggered)
        self.assertEqual(result.explanation, "Insufficient comparable works for peer benchmarking.")
        self.assertEqual(result.peer_group_size, 0)
        self.assertIsNone(result.peer_group_median_amount)
        self.assertIsNone(result.amount_ratio_to_peer_median)

    def test_zero_and_null_safe_behavior(self) -> None:
        settings = PeerBenchmarkSettings(min_group_size=100000)
        with SessionLocal() as db:
            result = get_peer_benchmark(db, WORK_ID, settings)
        self.assertIsNotNone(result)
        self.assertFalse(result.triggered)
        self.assertIsNone(result.peer_group_level)
        self.assertIsNone(result.percentile_rank)


if __name__ == "__main__":
    unittest.main()
