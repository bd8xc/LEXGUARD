"""Contract ingestion writes traceable, unverified facts to the COI graph."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ingestion_pipeline.contract_ingestion import ingest_contract_bytes, ingest_contract_file
from ingestion_pipeline.graph_facts import clauses_to_graph_facts


class GraphFactTests(unittest.TestCase):
    @patch("agents.cl.confidentiality_leakage.detectors.ner_detector._load_nlp", return_value=None)
    def test_explicit_relationships_keep_direction_and_evidence(self, _nlp):
        text = ("Aarav Mehta is a director of Acme Components Pvt. Ltd. "
                "Beta Dynamics Pvt. Ltd. is owned by Acme Components Pvt. Ltd. "
                "This Agreement is between Acme Components Pvt. Ltd. and Beta Dynamics Pvt. Ltd.")
        facts = clauses_to_graph_facts([{"clause_id": "1", "text": text}])[0]
        self.assertEqual(3, len(facts["entities"]))
        edges = {(edge["from"], edge["to"], edge["type"]) for edge in facts["relationships"]}
        self.assertIn(("Aarav Mehta", "Acme Components Pvt. Ltd.", "BOARD_MEMBER_OF"), edges)
        self.assertIn(("Acme Components Pvt. Ltd.", "Beta Dynamics Pvt. Ltd.", "OWNS"), edges)
        self.assertIn(("Acme Components Pvt. Ltd.", "Beta Dynamics Pvt. Ltd.", "CONTRACT_WITH"), edges)
        self.assertTrue(all(edge["verified"] is False and edge["evidence"] for edge in facts["relationships"]))

    @patch("agents.cl.confidentiality_leakage.detectors.ner_detector._load_nlp", return_value=None)
    def test_cooccurrence_does_not_create_a_relationship(self, _nlp):
        facts = clauses_to_graph_facts([{
            "clause_id": "1", "text": ("Acme Components Pvt. Ltd. met Beta Dynamics Pvt. Ltd. yesterday. "
                                    "Acme Components Pvt. Ltd. does not own Beta Dynamics Pvt. Ltd.")
        }])[0]
        self.assertEqual(2, len(facts["entities"]))
        self.assertEqual([], facts["relationships"])


class IngestionTests(unittest.TestCase):
    @patch("agents.cl.confidentiality_leakage.detectors.ner_detector._load_nlp", return_value=None)
    @patch("agents.coi.graph_manager.get_graph")
    def test_bytes_and_file_ingestion_update_same_source(self, get_graph, _nlp):
        graph = Mock()
        graph.replace_document.return_value = {"status": "complete", "clauses": 1}
        get_graph.return_value = graph
        content = b"Aarav Mehta is a director of Acme Components Pvt. Ltd."
        first = ingest_contract_bytes("contract.txt", content)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.txt"
            path.write_bytes(content)
            second = ingest_contract_file(path)
        self.assertEqual(first["contract_id"], second["contract_id"])
        self.assertEqual(2, graph.setup_schema.call_count)
        self.assertEqual(2, graph.replace_document.call_count)
        doc, clauses = graph.replace_document.call_args.args
        self.assertEqual(first["contract_id"], doc["id"])
        self.assertTrue(clauses[0]["entities"])
        self.assertEqual("BOARD_MEMBER_OF", clauses[0]["relationships"][0]["type"])
        self.assertEqual(1, first["metadata"]["graph_update"]["relationships"])

    @patch("agents.coi.graph_manager.get_graph")
    def test_graph_failure_prevents_successful_ingestion(self, get_graph):
        get_graph.return_value.setup_schema.side_effect = RuntimeError("Neo4j unavailable")
        with self.assertRaisesRegex(RuntimeError, "Neo4j unavailable"):
            ingest_contract_bytes("contract.txt", b"A valid contract between two companies.")


if __name__ == "__main__":
    unittest.main()
