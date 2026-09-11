import tempfile
import unittest
from pathlib import Path

from ctxeng.locate import iter_sessions
from ctxeng.parse import classify_prompt, parse_session

from . import fixtures


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = fixtures.write_store(Path(self.tmp.name))
        self.ref = next(iter_sessions(self.root))
        self.session = parse_session(self.ref)

    def tearDown(self):
        self.tmp.cleanup()

    def test_locates_session_and_subagent(self):
        self.assertEqual(self.ref.session_id, fixtures.SESSION_ID)
        self.assertEqual(len(self.ref.subagent_paths), 1)

    def test_usage_counted_once_per_request(self):
        # req_1 has two content blocks that repeat the same usage; it must be one call.
        self.assertEqual(len(self.session.api_calls), 4)
        self.assertEqual(self.session.api_calls[0].usage.output, 300)
        self.assertEqual(self.session.api_calls[0].usage.context, 20_000)
        self.assertEqual(self.session.api_calls[0].thinking_chars, 100)

    def test_prompt_kinds(self):
        kinds = [p.kind for p in self.session.prompts]
        self.assertEqual(kinds, ["user", "user", "compaction_summary", "command", "command"])
        self.assertEqual(len(self.session.user_prompts), 2)

    def test_tool_results_resolve_tool_name(self):
        self.assertEqual(len(self.session.tool_results), 1)
        self.assertEqual(self.session.tool_results[0].tool_name, "Bash")
        self.assertEqual(self.session.tool_results[0].prompt_index, 2)

    def test_compaction_metadata_and_summary_size(self):
        self.assertEqual(len(self.session.compactions), 1)
        c = self.session.compactions[0]
        self.assertEqual((c.trigger, c.pre_tokens, c.post_tokens), ("auto", 21_540, 3_000))
        self.assertEqual(c.api_call_index, 3)
        self.assertGreater(c.summary_chars, 2000)

    def test_attachments_measured(self):
        kinds = {a.kind: a.chars for a in self.session.attachments}
        self.assertEqual(kinds["prompt_snapshot"], 4000)
        self.assertEqual(kinds["instructions"], 800)
        self.assertEqual(kinds["skill_listing"], 1200)

    def test_subagent_summary(self):
        self.assertEqual(len(self.session.subagents), 1)
        self.assertEqual(self.session.subagents[0].output_tokens, 500)

    def test_classify_prompt(self):
        self.assertEqual(classify_prompt("<system-reminder>x</system-reminder>", {}), "reminder")
        self.assertEqual(classify_prompt("", {}), "empty")
        self.assertEqual(classify_prompt("real question", {}), "user")
        self.assertEqual(classify_prompt("anything", {"isCompactSummary": True}), "compaction_summary")


if __name__ == "__main__":
    unittest.main()
