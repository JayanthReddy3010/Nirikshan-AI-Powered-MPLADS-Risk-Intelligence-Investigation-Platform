from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.database import SessionLocal
from backend.app.main import app

WORK_ID = "WS/MP18170/2025-2026/194491"


class InvestigationActionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()
        with SessionLocal() as db:
            db.execute(text("DELETE FROM investigation_actions WHERE work_id = :work_id"), {"work_id": WORK_ID})
            db.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        with SessionLocal() as db:
            db.execute(text("DELETE FROM investigation_actions WHERE work_id = :work_id"), {"work_id": WORK_ID})
            db.commit()
        cls.client.__exit__(None, None, None)

    def test_creating_an_investigation_action(self) -> None:
        response = self.client.post(
            f"/api/works/{WORK_ID}/investigation-actions",
            json={"action": "Reviewed", "comment": "Checked expenditure evidence.", "officer_name": "Demo Officer"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["action"], "Reviewed")
        self.assertEqual(response.json()["work_id"], WORK_ID)

    def test_retrieving_action_history(self) -> None:
        response = self.client.get(f"/api/works/{WORK_ID}/investigation-actions")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["action"] == "Reviewed" for item in response.json()))

    def test_invalid_action_rejection(self) -> None:
        response = self.client.post(
            f"/api/works/{WORK_ID}/investigation-actions",
            json={"action": "Fraud Confirmed"},
        )
        self.assertEqual(response.status_code, 422)

    def test_nonexistent_work_rejection(self) -> None:
        response = self.client.post(
            "/api/works/WS%2Fdoes-not-exist/investigation-actions",
            json={"action": "Reviewed"},
        )
        self.assertEqual(response.status_code, 404)

    def test_multiple_actions_for_one_work(self) -> None:
        for action in ("Request Documents", "Escalate", "Close Investigation"):
            response = self.client.post(
                f"/api/works/{WORK_ID}/investigation-actions",
                json={"action": action},
            )
            self.assertEqual(response.status_code, 201)
        history = self.client.get(f"/api/works/{WORK_ID}/investigation-actions").json()
        self.assertGreaterEqual(len(history), 4)

    def test_newest_first_ordering(self) -> None:
        history = self.client.get(f"/api/works/{WORK_ID}/investigation-actions").json()
        timestamps = [item["created_at"] for item in history]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))


if __name__ == "__main__":
    unittest.main()
