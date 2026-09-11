import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ctxeng import patterns
from ctxeng import redact

ROOT = Path(__file__).resolve().parents[1]


def j(*parts: str) -> str:
    """Assemble a test input at runtime. See docs/privacy.md, "Limits"."""
    return "".join(parts)


def load_checker():
    spec = importlib.util.spec_from_file_location("privacy_check", ROOT / "scripts" / "privacy_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PatternTests(unittest.TestCase):
    def test_flags_personal_fragments(self):
        text = " ".join([
            j("someone@", "example-corp.io"),
            j("C:", "\\Users\\jdoe\\code"),
            j("/home/", "jdoe/x"),
            j("C--Users-", "jdoe-code-demo"),
            j("sk-ant-", "abcdefghijklmnop"),
        ])
        kinds = [k for k, _ in patterns.find_personal(text)]
        self.assertEqual(kinds, ["email address", "home-directory path", "home-directory path",
                                 "project slug with username", "anthropic api key"])

    def test_allows_placeholders_and_relay_addresses(self):
        text = ("C:\\Users\\<you>\\.claude ~/.claude/projects /home/$USER/x "
                "12345+someone@users.noreply.github.com noreply@anthropic.com C--Users-<user>-demo")
        self.assertEqual(patterns.find_personal(text), [])

    def test_scrub(self):
        out = patterns.scrub(" ".join([j("C:", "\\Users\\jdoe\\code"), j("jdoe@", "example-corp.io"),
                                       j("C--Users-", "jdoe-code")]))
        self.assertNotIn("jdoe", out)
        self.assertIn("<user>", out)
        self.assertIn("<email>", out)


class RedactTests(unittest.TestCase):
    def test_aliases_are_stable_and_opaque(self):
        slug = j("C--Users-", "jdoe-code-demo")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CTXENG_HOME"] = tmp
            redact._SALT = None
            try:
                a = redact.project_alias(slug)
                b = redact.project_alias(slug)
                self.assertEqual(a, b)
                self.assertTrue(a.startswith("project-"))
                self.assertNotIn("jdoe", a)
                self.assertNotEqual(a, redact.project_alias(slug + "-other"))
            finally:
                redact._SALT = None
                os.environ.pop("CTXENG_HOME")


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_checker()
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "terms.txt"
        path.write_text("# configured\nSecretName\n", encoding="utf-8")
        os.environ["CTXENG_TERMS_FILE"] = str(path)
        os.environ.pop("CTXENG_TERMS", None)

    def tearDown(self):
        os.environ.pop("CTXENG_TERMS_FILE", None)
        os.environ.pop("CTXENG_TERMS", None)
        self.tmp.cleanup()

    def test_terms_match_on_word_boundaries(self):
        terms = self.mod.load_terms()
        hits = self.mod.scan_text("nothing here\nby SecretName today\nsecretnames plural", terms)
        self.assertEqual([(h[0], h[1]) for h in hits], [(2, "configured term")])

    def test_terms_from_environment_are_merged(self):
        os.environ["CTXENG_TERMS"] = "OtherTerm\n# comment\n"
        terms = self.mod.load_terms()
        self.assertEqual(len(self.mod.scan_text("SecretName and OtherTerm", terms)), 2)

    def test_untracked_paths_and_binaries(self):
        with redirect_stdout(io.StringIO()):
            problems = self.mod.check_blobs([
                ("out/report.md", b"clean"),
                ("data.jsonl", b"{}"),
                ("docs/img/chart.png", b"\x89PNG\x00"),
                ("docs/ok.md", b"clean text"),
            ], [])
        self.assertEqual(problems, 2)

    def test_no_snippets_mode_hides_matched_text(self):
        terms = self.mod.load_terms()
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.mod.check_blobs([("a.md", b"mentions SecretName")], terms, snippets=False)
        self.assertIn("configured term", buf.getvalue())
        self.assertNotIn("SecretName", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
