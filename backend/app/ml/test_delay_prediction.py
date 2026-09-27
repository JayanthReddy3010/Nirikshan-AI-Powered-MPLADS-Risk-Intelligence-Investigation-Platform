from __future__ import annotations

import unittest

from sqlalchemy import text

from backend.app.database import SessionLocal
from backend.app.ml.delay_prediction import (
    CANDIDATE_FEATURE_NAMES,
    INSUFFICIENT_DATA_MESSAGE,
    MODEL_VERSION,
    assess_delay_target,
    classify_delay_risk,
    construct_delay_target,
    predict_work_delay,
    preprocess_delay_features,
    train_delay_model,
)

WORK_ID = "WS/MP18170/2025-2026/194491"


class DelayPredictionTests(unittest.TestCase):
    def test_target_construction_reports_limitation(self) -> None:
        with SessionLocal() as db:
            report = assess_delay_target(db)
        self.assertFalse(report.valid_target_available)
        self.assertIn("completion_date", report.missing_outcome_fields)
        self.assertIn(INSUFFICIENT_DATA_MESSAGE, report.explanation)
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, INSUFFICIENT_DATA_MESSAGE):
                construct_delay_target(db)

    def test_preprocessing_requires_complete_finite_snapshot(self) -> None:
        values = {name: 1.0 for name in CANDIDATE_FEATURE_NAMES}
        self.assertEqual(len(preprocess_delay_features(values)), len(CANDIDATE_FEATURE_NAMES))
        with self.assertRaisesRegex(ValueError, "Missing pre-prediction feature"):
            preprocess_delay_features({})
        values[CANDIDATE_FEATURE_NAMES[0]] = float("inf")
        with self.assertRaisesRegex(ValueError, "Non-finite pre-prediction feature"):
            preprocess_delay_features(values)

    def test_training_refuses_without_valid_target(self) -> None:
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, INSUFFICIENT_DATA_MESSAGE):
                train_delay_model(db)

    def test_prediction_reports_unavailable_for_real_work(self) -> None:
        with SessionLocal() as db:
            result = predict_work_delay(db, WORK_ID)
        self.assertFalse(result.available)
        self.assertIsNone(result.delay_probability)
        self.assertIsNone(result.delay_risk_score)
        self.assertEqual(result.delay_risk_label, "unavailable")
        self.assertEqual(result.model_version, MODEL_VERSION)
        self.assertEqual(result.explanation, INSUFFICIENT_DATA_MESSAGE)

    def test_risk_score_bands_are_bounded(self) -> None:
        from backend.app.ml.delay_prediction import DelayModelSettings

        settings = DelayModelSettings()
        self.assertEqual(classify_delay_risk(0, settings), "low delay risk")
        self.assertEqual(classify_delay_risk(50, settings), "moderate delay risk")
        self.assertEqual(classify_delay_risk(100, settings), "high delay risk")

    def test_unavailable_prediction_is_deterministic(self) -> None:
        with SessionLocal() as db:
            first = predict_work_delay(db, WORK_ID).model_dump()
            second = predict_work_delay(db, WORK_ID).model_dump()
        self.assertEqual(first, second)

    def test_leakage_checks(self) -> None:
        self.assertTrue(all(name.endswith("_at_prediction_point") for name in CANDIDATE_FEATURE_NAMES))
        self.assertNotIn("final_expenditure_total", CANDIDATE_FEATURE_NAMES)
        with SessionLocal() as db:
            columns = {
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
        self.assertNotIn("actual_completion_date", columns)
        self.assertNotIn("completion_status", columns)


if __name__ == "__main__":
    unittest.main()
