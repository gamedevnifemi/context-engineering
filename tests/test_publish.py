import tempfile
import unittest
from pathlib import Path

from ctxeng import metrics, publish
from ctxeng.locate import iter_sessions
from ctxeng.parse import parse_session

from . import fixtures


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = fixtures.write_store(Path(self.tmp.name))
        self.session = parse_session(next(iter_sessions(root)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_fills_by_model(self):
        rows = publish.fills_by_model([metrics.session_summary(self.session)])
        self.assertEqual(rows, [{"model": "claude-demo", "sessions": 1, "min": 2.0, "median": 2.0, "max": 2.0}])

    def test_compactions_by_trigger_reports_ranges_not_events(self):
        rows = publish.compactions_by_trigger(metrics.compaction_rows(self.session))
        self.assertEqual(rows[0]["trigger"], "auto")
        self.assertEqual(rows[0]["events"], 1)
        self.assertEqual(rows[0]["retained"], "13.9%")
        self.assertNotIn("session", rows[0])

    def test_aggregate_composition_shares_sum_to_100(self):
        rows, pooled = publish.aggregate_composition([self.session], top=6)
        self.assertEqual(pooled, 1)
        self.assertAlmostEqual(sum(r["pooled_pct"] for r in rows), 100.0, delta=0.5)
        self.assertAlmostEqual(sum(r["median_session_pct"] for r in rows), 100.0, delta=0.5)
        self.assertTrue(all("range across sessions" in r for r in rows))

    def test_drops_summary_empty(self):
        self.assertEqual(publish.drops_summary([]), [])

    def test_report_contains_no_session_identifiers(self):
        out = Path(self.tmp.name) / "pub"
        path = publish.build_publish_report([self.session], out, min_calls=1)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn(fixtures.SESSION_ID, text)
        self.assertNotIn("session-", text)
        self.assertIn("Prompts per window fill", text)


if __name__ == "__main__":
    unittest.main()
