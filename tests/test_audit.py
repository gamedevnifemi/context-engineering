import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ctxeng import audit

from . import fixtures

PLUGIN_LIST = json.dumps([
    {"id": "webtools@demo-market", "version": "1.2.0", "scope": "user", "enabled": True,
     "installPath": "{root}/plugins/cache/demo-market/webtools/1.2.0"},
    {"id": "linter@demo-market", "version": "0.1.0", "scope": "user", "enabled": False,
     "installPath": "{root}/plugins/cache/demo-market/linter/0.1.0"},
])


def fake_runner_for(root: Path):
    def run(args, timeout):
        if args[:3] == ["claude", "plugin", "list"]:
            return PLUGIN_LIST.replace("{root}", str(root).replace("\\", "/"))
        if args[:3] == ["claude", "plugin", "details"]:
            return "Projected token cost\n  Always-on:   ~1,200 tok   added to every session\n"
        if args[:3] == ["claude", "mcp", "list"]:
            return "demo-notes: https://example.com/mcp - ✔ Connected\n"
        if args[:3] in (["claude", "plugin", "disable"], ["claude", "plugin", "enable"]):
            return "ok"
        return None
    return run


def write_config(root: Path) -> Path:
    cfg = root / "cfg"
    (cfg / "skills" / "used-skill").mkdir(parents=True)
    (cfg / "skills" / "used-skill" / "SKILL.md").write_text(
        "---\ndescription: Used often\n---\nbody", encoding="utf-8")
    (cfg / "skills" / "idle-skill").mkdir(parents=True)
    (cfg / "skills" / "idle-skill" / "SKILL.md").write_text(
        "---\ndescription: >\n  Folded description\n  over two lines\n---\n" + "x" * 30000, encoding="utf-8")
    (cfg / "skills" / "hidden-skill").mkdir(parents=True)
    (cfg / "skills" / "hidden-skill" / "SKILL.md").write_text(
        "---\ndescription: Hidden\ndisable-model-invocation: true\n---\nbody", encoding="utf-8")
    (cfg / "agents").mkdir()
    (cfg / "agents" / "idle-agent.md").write_text("---\ndescription: Never delegated to\n---\nprompt", encoding="utf-8")
    (cfg / "CLAUDE.md").write_text("\n".join(f"line {i}" for i in range(250)), encoding="utf-8")
    (cfg / "settings.json").write_text(json.dumps({
        "hooks": {"Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "echo done"}]}]},
        "enabledPlugins": {"webtools@demo-market": True},
    }), encoding="utf-8")
    plugin_root = root / "plugins" / "cache" / "demo-market" / "webtools" / "1.2.0"
    (plugin_root / "skills" / "fetch").mkdir(parents=True)
    (plugin_root / "skills" / "fetch" / "SKILL.md").write_text("---\ndescription: Fetch pages\n---\nbody", encoding="utf-8")
    state = {"skillUsage": {"used-skill": {"usageCount": 4, "lastUsedAt": int(datetime.now().timestamp() * 1000)}},
             "toolUsage": {}, "pluginUsage": {}}
    (root / ".claude.json").write_text(json.dumps(state), encoding="utf-8")
    return cfg


def write_transcripts(root: Path) -> Path:
    projects = root / "projects"
    fixtures.write_store(projects)
    main = next(projects.glob("*/*.jsonl"))
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    extra = [
        fixtures.attachment(now, "skill_listing", content="- used-skill: Used often\n- idle-skill: Folded description over two lines\n- webtools:fetch: Fetch pages\n- bundled-thing: Something bundled", isInitial=True),
        fixtures.attachment(now, "agent_listing_delta", addedLines=["- idle-agent: Never delegated to"]),
        fixtures.attachment(now, "mcp_instructions_delta", addedNames=["demo-notes"], addedBlocks=["## demo-notes\nuse me"]),
        fixtures.attachment(now, "deferred_tools_delta", addedNames=["mcp__demo-notes__search", "mcp__demo-notes__read"]),
        fixtures._rec("attachment", now, attachment={"type": "hook_success", "hookName": "Stop", "command": "echo done", "durationMs": 40}),
    ]
    extra += fixtures.assistant(now, "req_9", [{"type": "tool_use", "id": "toolu_9", "name": "Skill", "input": {"skill": "used-skill"}}],
                                fixtures.usage(context=30_000, output=10, cache_creation=10), stop="tool_use")
    with main.open("a", encoding="utf-8") as fh:
        for rec in extra:
            fh.write(json.dumps(rec) + "\n")
    return projects


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = write_config(self.root)
        self.projects = write_transcripts(self.root)
        self.out = self.root / "out"
        audit.run_audit(self.out, window_days=90, cfg=self.cfg, projects=self.projects,
                        run=fake_runner_for(self.root))
        self.plan = json.loads((self.out / "plan.json").read_text(encoding="utf-8"))
        self.report = (self.out / "report.md").read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_frontmatter_folded_value(self):
        fm = audit.frontmatter("---\ndescription: >\n  one\n  two\nother: x\n---\nbody")
        self.assertEqual(fm, {"description": "one two", "other": "x"})

    def test_idle_skill_is_proposed_for_hiding_and_used_skill_is_not(self):
        ops = {(a["op"], a.get("skill")) for a in self.plan["actions"]}
        self.assertIn(("skill_override", "idle-skill"), ops)
        self.assertNotIn(("skill_override", "used-skill"), ops)
        self.assertNotIn(("skill_override", "hidden-skill"), ops)

    def test_plugin_skill_is_not_overridden_but_plugin_is_disabled(self):
        ops = [(a["op"], a.get("skill") or a.get("plugin")) for a in self.plan["actions"]]
        self.assertNotIn(("skill_override", "webtools:fetch"), ops)
        self.assertIn(("plugin_disable", "webtools@demo-market"), ops)

    def test_bundled_skill_from_listing_is_included(self):
        self.assertIn("bundled-thing", self.report)
        self.assertIn(("skill_override", "bundled-thing"),
                      {(a["op"], a.get("skill")) for a in self.plan["actions"]})

    def test_idle_agent_and_unused_server_and_notes(self):
        ops = {a["op"] for a in self.plan["actions"]}
        self.assertIn("archive_file", ops)
        self.assertIn("deny_mcp", ops)
        kinds = {(n["kind"], n["item"]) for n in self.plan["notes"]}
        self.assertIn(("skill", "idle-skill"), kinds)              # oversized body
        self.assertIn(("settings", "cleanupPeriodDays"), kinds)
        self.assertTrue(any(k == "instructions" for k, _ in kinds))

    def test_apply_and_undo_round_trip(self):
        applied = audit.apply_plan(self.out / "plan.json", cfg=self.cfg, run=fake_runner_for(self.root))
        settings = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["skillOverrides"]["idle-skill"], "user-invocable-only")
        self.assertIn("demo-notes", settings["deniedMcpServers"])
        self.assertFalse((self.cfg / "agents" / "idle-agent.md").exists())
        n = audit.undo(applied, run=fake_runner_for(self.root))
        self.assertGreaterEqual(n, 2)
        restored = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("skillOverrides", restored)
        self.assertTrue((self.cfg / "agents" / "idle-agent.md").exists())


if __name__ == "__main__":
    unittest.main()
