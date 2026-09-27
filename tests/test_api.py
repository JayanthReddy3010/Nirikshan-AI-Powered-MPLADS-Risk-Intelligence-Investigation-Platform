from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.app.main import app


WORK_ID = "WS/MP18170/2025-2026/194491"


class InvestigationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_works_pagination(self) -> None:
        response = self.client.get("/api/works?page=1&page_size=2")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 2)
        self.assertLessEqual(payload["page_size"], 100)

    def test_state_filtering(self) -> None:
        response = self.client.get("/api/works?state=Uttar%20Pradesh&page_size=2")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["state"] == "Uttar Pradesh" for item in response.json()["items"]))

    def test_risk_band_filtering(self) -> None:
        response = self.client.get("/api/works?risk_band=Critical%20investigation%20priority&page_size=2")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["risk_band"] == "Critical investigation priority" for item in response.json()["items"]))

    def test_work_detail(self) -> None:
        response = self.client.get(f"/api/works/{WORK_ID}?transaction_page_size=2")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["work_information"]["work_id"], WORK_ID)
        self.assertEqual(len(payload["rule_evidence"]), 4)
        self.assertEqual(len(payload["transactions"]["items"]), 2)
        self.assertFalse(payload["delay_prediction"]["available"])
        self.assertIsNone(payload["composite_risk"]["delay_score"])

    def test_nonexistent_work_returns_404(self) -> None:
        response = self.client.get("/api/works/not-a-real-work")
        self.assertEqual(response.status_code, 404)

    def test_dashboard_summary(self) -> None:
        response = self.client.get("/api/dashboard/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_works"], payload["works"])
        self.assertEqual(payload["total_transactions"], payload["transactions"])
        self.assertEqual(payload["source_rows"], payload["valid_rows"] + payload["import_errors"])
        self.assertEqual(payload["total_works"], 55716)
        self.assertEqual(payload["total_transactions"], 82788)
        self.assertEqual(len(payload["top_10_highest_risk_works"]), 10)

    def test_dashboard_summary_filters(self) -> None:
        response = self.client.get("/api/dashboard/summary?state=Rajasthan&risk_band=High%20investigation%20priority")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertLessEqual(payload["total_works"], 55716)
        self.assertGreaterEqual(payload["total_works"], 0)

    def test_state_summary(self) -> None:
        response = self.client.get("/api/dashboard/state-summary")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.json()) > 0)

    def test_vendor_summary(self) -> None:
        response = self.client.get("/api/dashboard/vendor-summary")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.json()) > 0)
        self.assertTrue(all(item["work_count"] > 0 for item in response.json()))

    def test_risk_distribution(self) -> None:
        response = self.client.get("/api/dashboard/risk-distribution")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["low_risk_count"]
            + payload["moderate_risk_count"]
            + payload["high_risk_count"]
            + payload["critical_risk_count"],
            55716,
        )

    def test_risk_exposure(self) -> None:
        response = self.client.get("/api/dashboard/risk-exposure")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 4)
        self.assertEqual(sum(item["work_count"] for item in payload), 55716)
        self.assertEqual(
            round(sum(float(item["total_amount"]) for item in payload), 2),
            27330241496.45,
        )

    def test_invalid_page_size(self) -> None:
        response = self.client.get("/api/works?page_size=101")
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
