from __future__ import annotations

import unittest

from sqlalchemy import text

from backend.app.database import SessionLocal
from backend.app.services.feature_service import get_work_features


def work_id_where(db, query: str) -> str:
    work_id = db.execute(text(query)).scalar()
    if work_id is None:
        raise unittest.SkipTest("The imported real dataset has no work matching this test case.")
    return str(work_id)


class FeatureServiceTests(unittest.TestCase):
    def test_work_with_one_transaction(self) -> None:
        with SessionLocal() as db:
            work_id = work_id_where(
                db,
                """
                SELECT work_id
                FROM work_transactions
                GROUP BY work_id
                HAVING COUNT(*) = 1
                ORDER BY work_id
                LIMIT 1
                """,
            )
            features = get_work_features(db, work_id)

        self.assertIsNotNone(features)
        self.assertEqual(features.transaction_count, 1)
        self.assertIsNone(features.average_days_between_transactions)
        self.assertEqual(features.days_between_first_and_last_transaction, 0)


    def test_work_with_multiple_transactions(self) -> None:
        with SessionLocal() as db:
            work_id = work_id_where(
                db,
                """
                SELECT work_id
                FROM work_transactions
                GROUP BY work_id
                HAVING COUNT(*) > 1
                ORDER BY work_id
                LIMIT 1
                """,
            )
            features = get_work_features(db, work_id)

        self.assertIsNotNone(features)
        self.assertGreater(features.transaction_count, 1)
        self.assertGreaterEqual(features.total_disbursed_amount, 0)


    def test_work_with_multiple_vendors(self) -> None:
        with SessionLocal() as db:
            work_id = work_id_where(
                db,
                """
                SELECT work_id
                FROM work_transactions
                WHERE NULLIF(BTRIM(vendor_name), '') IS NOT NULL
                GROUP BY work_id
                HAVING COUNT(DISTINCT NULLIF(BTRIM(vendor_name), '')) > 1
                ORDER BY work_id
                LIMIT 1
                """,
            )
            features = get_work_features(db, work_id)

        self.assertIsNotNone(features)
        self.assertGreater(features.unique_vendor_count, 1)
        self.assertIsNotNone(features.primary_vendor)
        self.assertIsNotNone(features.primary_vendor_amount)
        self.assertIsNotNone(features.primary_vendor_share)
        self.assertGreaterEqual(float(features.primary_vendor_share), 0)
        self.assertLessEqual(float(features.primary_vendor_share), 1)


    def test_zero_and_null_safe_calculations(self) -> None:
        with SessionLocal() as db:
            work_id = work_id_where(
                db,
                """
                SELECT w.work_id
                FROM works w
                LEFT JOIN work_transactions wt ON wt.work_id = w.work_id
                GROUP BY w.work_id
                HAVING COALESCE(SUM(wt.fund_disbursed_amount), 0) = 0
                    OR COUNT(wt.id) = 0
                ORDER BY w.work_id
                LIMIT 1
                """,
            )
            features = get_work_features(db, work_id)

        self.assertIsNotNone(features)
        self.assertIsNone(features.transaction_amount_concentration)
        self.assertIsNone(features.primary_vendor_share)


if __name__ == "__main__":
    unittest.main()
