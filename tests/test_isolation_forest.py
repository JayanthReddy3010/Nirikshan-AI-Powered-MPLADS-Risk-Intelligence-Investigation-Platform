from __future__ import annotations

import unittest

import numpy as np

from backend.app.database import SessionLocal
from backend.app.detection.peer_benchmark import get_peer_benchmark
from backend.app.ml.isolation_forest import (
    MODEL_PATH,
    _load_bundle,
    _transform_matrix,
    build_feature_matrix,
    predict_work_anomaly,
    train_isolation_forest,
)
from backend.app.services.feature_service import get_all_work_features, get_work_features

WORK_IDS = [
    "WS/MP18170/2025-2026/194491",
]


class IsolationForestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SessionLocal() as db:
            result = train_isolation_forest(db)
            cls.training_result = result
            cls.features = get_work_features(db, WORK_IDS[0])
            peer = get_peer_benchmark(db, WORK_IDS[0])
        if cls.features is None or peer is None:
            raise unittest.SkipTest("Required real work is not available.")
        cls.features = cls.features.model_copy(
            update={
                "amount_ratio_to_peer_median": peer.amount_ratio_to_peer_median,
                "percentile_rank": peer.percentile_rank,
            }
        )

    def test_model_trains_on_real_data(self) -> None:
        self.assertEqual(self.training_result["number_of_training_works"], 55716)
        self.assertEqual(self.training_result["feature_matrix_shape"], [55716, 13])
        self.assertTrue(MODEL_PATH.exists())

    def test_expected_feature_matrix_shape(self) -> None:
        with SessionLocal() as db:
            records = list(get_all_work_features(db))[:5]
        matrix = build_feature_matrix(records)
        self.assertEqual(matrix.shape, (5, 13))

    def test_no_nan_or_infinite_values_reach_model(self) -> None:
        bundle = _load_bundle()
        matrix = _transform_matrix(build_feature_matrix([self.features]), bundle["imputer"])
        self.assertTrue(np.isfinite(matrix).all())

    def test_prediction_works_for_real_work(self) -> None:
        with SessionLocal() as db:
            result = predict_work_anomaly(db, WORK_IDS[0])
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.anomaly_score, 0)
        self.assertLessEqual(result.anomaly_score, 100)

    def test_repeated_prediction_is_deterministic(self) -> None:
        with SessionLocal() as db:
            first = predict_work_anomaly(db, WORK_IDS[0])
            second = predict_work_anomaly(db, WORK_IDS[0])
        self.assertEqual(first.model_dump(), second.model_dump())


if __name__ == "__main__":
    unittest.main()
