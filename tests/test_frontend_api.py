"""Smoke tests for the integrated Atelier browser interface."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api import app


class FrontendApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_pages_and_assets_are_served(self):
        for route in ("/", "/review", "/results", "/workspaces", "/advanced",
                      "/tools/conflicts", "/tools/clauses", "/tools/confidentiality",
                      "/tools/litigation", "/static/app.js", "/static/styles.css",
                      "/static/lexguard-logo.svg"):
            with self.subTest(route=route):
                self.assertEqual(200, self.client.get(route).status_code)

    def test_branding_and_theme_script_on_frontend_pages(self):
        for route in ("/", "/review", "/results", "/workspaces",
                      "/tools/conflicts", "/tools/clauses", "/tools/confidentiality",
                      "/tools/litigation"):
            with self.subTest(route=route):
                page = self.client.get(route).text
                self.assertIn("/static/lexguard-logo.svg", self.client.get("/static/styles.css").text)
                self.assertIn("css2?family=DM+Sans", page)
                self.assertIn("t==='light'||t==='dark'?t:", page)
                self.assertNotIn("Instrument+Serif", page)
                self.assertNotIn("&#9671;", page)

    def test_file_preview_does_not_ingest(self):
        with patch("ingestion_pipeline.contract_ingestion.ingest_contract_bytes") as ingest:
            response = self.client.post("/api/extract", files={
                "file": ("example.txt", b"Acme Ltd. and Beta Ltd. signed an agreement.", "text/plain")
            })
        self.assertEqual(200, response.status_code)
        self.assertIn("Acme Ltd.", response.json()["text"])
        ingest.assert_not_called()

    @patch("agents.cl.confidentiality_leakage.detectors.ner_detector._load_nlp", return_value=None)
    @patch("agents.coi.graph_manager.get_graph")
    def test_cl_workspace_ingests_and_returns_redacted_findings(self, get_graph, _nlp):
        graph = Mock()
        graph.replace_document.return_value = {"status": "complete", "clauses": 1}
        get_graph.return_value = graph
        response = self.client.post("/api/cl/analyze", json={
            "contract_text": "Acme Components Pvt. Ltd. shall email notices to alice@example.com."
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("complete", response.json()["status"])
        self.assertTrue(graph.replace_document.called)
        self.assertNotIn("alice@example.com", response.text)

    @patch("api.analyze_contract")
    def test_guided_review_adapts_pipeline_response(self, analyze):
        analyze.return_value = {
            "contract_id": "contract-1", "metadata": {"graph_update": {"entities": 2}},
            "coi": {"graph_result": {"status": "complete", "conflict_detected": False,
                                     "conflict_flag": 0, "severity": "NONE"}},
            "clauses": [{"clause_id": "P1", "cra": {"model": {"prediction": "Baseline", "model_score": 0.3}}}],
            "summary": {"clauses_failed": 0, "clauses_skipped": 0, "human_review_required": True},
            "confidentiality": {"risk_level": "LOW", "total_findings": 0, "findings": []},
            "litigation_exposure": {"status": "complete", "litigation_probability": 0.2, "risk_level": "Low"},
        }
        response = self.client.post("/api/analyze", json={
            "doc_id": "review-1", "client_entity": "Acme Ltd", "counterparty_entity": "Beta Ltd",
            "contract_text": "Acme Ltd contracts with Beta Ltd under the following terms.",
            "features": {}, "clause_deviation_override": 0.3,
        })
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("complete", payload["status"])
        self.assertEqual("Seed", payload["cr"]["clauses"][0]["model"]["prediction"])
        self.assertEqual(0.2, payload["le"]["litigation_probability"])
        self.assertEqual(2, payload["graph_update"]["entities"])


if __name__ == "__main__":
    unittest.main()
