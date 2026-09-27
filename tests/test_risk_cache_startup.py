from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import risk_cache


class RiskCacheStartupTests(unittest.TestCase):
    def test_startup_initializes_snapshot(self) -> None:
        risk_cache.clear_risk_snapshot()
        with TestClient(app):
            snapshot = risk_cache.get_risk_snapshot(None)
            self.assertEqual(len(snapshot), 55716)

    def test_repeated_access_reuses_same_snapshot(self) -> None:
        with TestClient(app):
            first = risk_cache.get_risk_snapshot(None)
            second = risk_cache.get_risk_snapshot(None)
            self.assertIs(first, second)

    def test_request_does_not_train_or_rebuild_snapshot(self) -> None:
        with TestClient(app) as client:
            snapshot = risk_cache.get_risk_snapshot(None)
            response = client.get("/api/dashboard/summary")
            self.assertEqual(response.status_code, 200)
            self.assertIs(snapshot, risk_cache.get_risk_snapshot(None))


if __name__ == "__main__":
    unittest.main()
