import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from ctxeng import patterns
from ctxeng import redact

ROOT = Path(__file__).resolve().parents[1]


def j(*parts: str) -> str:
    """Join fragments at runtime.

    The detection tests need real-looking personal fragments, but the repository's own privacy
    scan reads this source file. Splitting the fragments keeps the scan clean while the tests
    still exercise the complete patterns.
    """
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
    def test_denylist_and_forbidden_paths(self):
        mod = load_checker()
        with tempfile.TemporaryDirectory() as tmp:
            deny = Path(tmp) / "deny.txt"
            deny.write_text("# personal\nSecretName\n", encoding="utf-8")
            os.environ["CTXENG_DENYLIST"] = str(deny)
            try:
                denylist = mod.load_denylist()
                hits = mod.scan_text("nothing here\nby SecretName today\nsecretnames plural", denylist)
                self.assertEqual([(h[0], h[1]) for h in hits], [(2, "denylisted term")])
                problems = mod.check_blobs([("out/report.md", b"clean"), ("data.jsonl", b"{}"),
                                            ("docs/ok.md", b"clean text")], denylist)
                self.assertEqual(problems, 2)
            finally:
                os.environ.pop("CTXENG_DENYLIST")


if __name__ == "__main__":
    unittest.main()
