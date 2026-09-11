import tempfile
import unittest
from pathlib import Path

from ctxeng import metrics
from ctxeng.locate import iter_sessions
from ctxeng.parse import parse_session

from . import fixtures


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = fixtures.write_store(Path(self.tmp.name))
        self.session = parse_session(next(iter_sessions(root)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_session_summary(self):
        s = metrics.session_summary(self.session)
        self.assertEqual(s["prompts"], 2)
        self.assertEqual(s["api_calls"], 4)
        self.assertEqual(s["baseline_context"], 20_000)
        self.assertEqual(s["peak_context"], 21_500)
        self.assertEqual(s["compactions"], 1)
        # One compaction plus a 3,600-token current window against a 1M limit.
        self.assertEqual(s["window_fills"], 1.0)
        self.assertEqual(s["prompts_per_fill"], 2.0)
        self.assertEqual(s["subagent_output_tokens"], 500)

    def test_prompt_costs(self):
        rows = {r["prompt_index"]: r for r in metrics.prompt_costs(self.session)}
        # Prompt 2: 20,400 -> 21,500 across two calls, plus 40 output tokens on the last call.
        self.assertEqual(rows[2]["added_tokens"], 1_100 + 40)
        self.assertEqual(rows[2]["api_calls"], 2)
        self.assertEqual(rows[2]["tool_calls"], 1)
        self.assertEqual(rows[1]["added_tokens"], 300)
        # The compaction fired while prompt 2 was being handled; prompt 3 is the summary that follows it.
        self.assertTrue(rows[2]["compaction"])
        self.assertEqual(rows[3]["kind"], "compaction_summary")
        self.assertFalse(rows[3]["compaction"])
        self.assertEqual(rows[4]["api_calls"], 0)

    def test_aggregate_skips_prompts_that_never_reached_the_model(self):
        agg = metrics.aggregate_prompt_costs(metrics.prompt_costs(self.session), "model")
        self.assertEqual(len(agg), 1)
        self.assertEqual(agg[0]["prompts"], 3)

    def test_composition_sources(self):
        sources = {r["source"]: r for r in metrics.composition(self.session)}
        self.assertIn("system prompt", sources)
        self.assertIn("tool results: Bash", sources)
        self.assertAlmostEqual(sum(r["share"] for r in sources.values()), 1.0, places=6)

    def test_compaction_rows(self):
        row = metrics.compaction_rows(self.session)[0]
        self.assertEqual(row["retained_pct"], 13.9)
        self.assertEqual(row["calls_after"], 1)

    def test_percentile(self):
        self.assertEqual(metrics.percentile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertIsNone(metrics.percentile([], 0.9))


if __name__ == "__main__":
    unittest.main()
