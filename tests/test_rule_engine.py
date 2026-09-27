from __future__ import annotations

import unittest

from backend.app.database import SessionLocal
from backend.app.detection.rule_engine import RuleSettings, detect_work
from backend.app.services.feature_service import get_work_features

WORK_ID = "WS/MP18170/2025-2026/194491"


class RuleEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SessionLocal() as db:
            cls.features = get_work_features(db, WORK_ID)
        if cls.features is None:
            raise unittest.SkipTest(f"Real work {WORK_ID} is not available.")

    def triggered_ids(self, settings: RuleSettings):
        return {result.rule_id for result in detect_work(self.features, settings) if result.triggered}

    def test_no_rules_triggered(self) -> None:
        settings = RuleSettings(
            high_transaction_concentration_threshold=self.features.transaction_amount_concentration + 1,
            high_vendor_concentration_threshold=self.features.primary_vendor_share + 1,
            fragmentation_transaction_count_threshold=self.features.transaction_count + 1,
            large_transaction_threshold=self.features.maximum_transaction_amount + 1,
        )
        self.assertEqual(self.triggered_ids(settings), set())

    def test_high_transaction_concentration(self) -> None:
        settings = RuleSettings(high_transaction_concentration_threshold=self.features.transaction_amount_concentration)
        self.assertIn("R001", self.triggered_ids(settings))

    def test_high_vendor_concentration(self) -> None:
        settings = RuleSettings(high_vendor_concentration_threshold=self.features.primary_vendor_share)
        self.assertIn("R002", self.triggered_ids(settings))

    def test_high_transaction_count(self) -> None:
        settings = RuleSettings(fragmentation_transaction_count_threshold=self.features.transaction_count)
        self.assertIn("R003", self.triggered_ids(settings))

    def test_large_transaction(self) -> None:
        settings = RuleSettings(large_transaction_threshold=self.features.maximum_transaction_amount)
        self.assertIn("R004", self.triggered_ids(settings))

    def test_multiple_rules_trigger_simultaneously(self) -> None:
        settings = RuleSettings(large_transaction_threshold=300000)
        self.assertEqual(self.triggered_ids(settings), {"R001", "R002", "R003", "R004"})


if __name__ == "__main__":
    unittest.main()
