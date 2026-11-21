"""Regression guard: every feature that existed before the V8 upgrade must still exist.
Run:  MOCK=1 python -m pytest -q tests
(No network, no posting: MOCK=1 makes the bot offline.)"""
import ast
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("MOCK", "1")

SNAP = json.load(open(os.path.join(ROOT, "tests", "feature_snapshot.json"), encoding="utf-8"))


def _defs(fname):
    t = ast.parse(open(os.path.join(ROOT, fname), encoding="utf-8").read())
    funcs = {n.name for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    globs = {tg.id for n in t.body if isinstance(n, ast.Assign) for tg in n.targets
             if isinstance(tg, ast.Name) and tg.id.isupper()}
    return funcs, globs


def test_every_old_function_still_exists():
    for f in ("main.py", "extras.py"):
        funcs, globs = _defs(f)
        missing = sorted(set(SNAP[f]) - funcs)
        assert not missing, f"{f}: these old functions disappeared: {missing}"
        missing_g = sorted(set(SNAP[f + ":globals"]) - globs)
        assert not missing_g, f"{f}: these old settings disappeared: {missing_g}"


def test_workflow_keeps_every_secret_mode_and_saved_path():
    wf = open(os.path.join(ROOT, ".github", "workflows", "horror-story.yml"), encoding="utf-8").read()
    secrets = set(re.findall(r"secrets\.([A-Z0-9_]+)", wf))
    assert not (set(SNAP["workflow_secrets"]) - secrets), set(SNAP["workflow_secrets"]) - secrets
    saved = re.search(r"for p in (.*?); do", wf).group(1).split()
    assert not (set(SNAP["workflow_saved_paths"]) - set(saved)), set(SNAP["workflow_saved_paths"]) - set(saved)
    for job in ("post:", "site:"):
        assert job in wf


def test_modules_import_offline():
    import extras  # noqa: F401
    import main  # noqa: F401


def test_old_bengali_commands_still_parse():
    import extras
    assert extras._command("অবস্থা")[0] == "status"
    assert extras._command("বন্ধ ভূত ৩ দিন") == ("pause", "horror", 3)
    assert extras._command("চালু")[0] == "resume"
    assert extras._command("বাদ ভূত ১") == ("skip", "horror", 1)
    assert extras._command("সাহায্য")[0] == "help"
    assert extras._command("আজ কেমন আছো") is None


def test_slots_unchanged():
    import extras
    import main
    assert (main.MORNING, main.NOON, main.EVENING) == (10, 14, 20)
    import datetime as dt
    now = dt.datetime(2026, 11, 21, 12, 0, tzinfo=extras.IST)
    assert extras.current_slot(main.TRIGGERS, now) == "2026-11-21@14"


def test_existing_podcast_feed_is_valid_and_keeps_episodes():
    xml = open(os.path.join(ROOT, "docs", "podcast.xml"), encoding="utf-8").read()
    root = ET.fromstring(xml.encode("utf-8"))
    items = root.findall("./channel/item")
    assert len(items) >= 1
    guids = [i.findtext("guid") for i in items]
    assert len(guids) == len(set(guids)), "duplicate GUIDs in the feed"
    for i in items:
        enc = i.find("enclosure")
        assert enc is not None and enc.get("url", "").startswith("https://") and enc.get("type") == "audio/mpeg"


def test_podcast_feed_rebuild_keeps_old_guids(tmp_path):
    import shutil
    import extras
    docs = tmp_path / "docs"
    shutil.copytree(os.path.join(ROOT, "docs"), docs)
    before = {e["guid"] for e in json.load(open(docs / "podcast.json", encoding="utf-8"))}
    ep = {"guid": "2099-01-01-20", "title": "পরীক্ষা", "url": "https://example.com/a.mp3", "bytes": 10, "secs": 5,
          "date": "Thu, 01 Jan 2099 14:30:00 +0000", "desc": "test"}
    extras.podcast_feed(str(docs), "https://example.com/map/", ep, "Daily Horror Story")
    root = ET.fromstring(open(docs / "podcast.xml", encoding="utf-8").read().encode("utf-8"))
    after = {i.findtext("guid") for i in root.findall("./channel/item")}
    assert before <= after and "2099-01-01-20" in after
