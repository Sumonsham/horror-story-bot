"""Tests for the V8 additions (offline)."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("MOCK", "1")


# ---------------------------------------------------------------- ZERO_COST
def test_zero_cost_blocks_paid_and_unknown_senders(monkeypatch):
    import zerocost
    monkeypatch.delenv("ZERO_COST_MODE", raising=False)
    monkeypatch.delenv("ZERO_COST_EXTRA_ALLOW", raising=False)
    assert zerocost.check("POST", "https://api.openai.com/v1/chat")[0] is False
    assert zerocost.check("POST", "https://aiplatform.googleapis.com/v1/x")[0] is False
    assert zerocost.check("POST", "https://unknown-ai.example.com/v1/gen")[0] is False
    assert zerocost.check("GET", "https://www.anandabazar.com/some-news")[0] is True       # reading is free
    assert zerocost.check("POST", "https://generativelanguage.googleapis.com/v1beta/x")[0] is True
    assert zerocost.check("POST", "https://graph-video.facebook.com/v21.0/1/videos")[0] is True
    assert zerocost.check("POST", "https://api.telegram.org/botX/sendMessage")[0] is True


def test_chirp_stays_as_approved_fallback(monkeypatch):
    import zerocost
    monkeypatch.delenv("CHIRP_APPROVED", raising=False)
    assert zerocost.check("POST", "https://texttospeech.googleapis.com/v1/text:synthesize")[0] is True
    monkeypatch.setenv("CHIRP_APPROVED", "0")
    assert zerocost.check("POST", "https://texttospeech.googleapis.com/v1/text:synthesize")[0] is False


def test_guard_raises_a_normal_requests_error(monkeypatch):
    import requests
    import zerocost
    zerocost.install()
    with pytest.raises(requests.exceptions.RequestException):
        requests.post("https://api.openai.com/v1/x", timeout=1)


def test_paid_gemini_voice_key_ignored(monkeypatch):
    import extras
    monkeypatch.setenv("GEMINI_TTS_KEY", "free")
    monkeypatch.setenv("GEMINI_API_KEY", "paid")
    monkeypatch.setenv("TTS_PAID", "1")
    monkeypatch.delenv("ZERO_COST_MODE", raising=False)
    assert extras.tts_keys() == ["free"]


# ---------------------------------------------------------------- style assistants
def test_style_pick_prefers_matching_sample():
    import main
    sm = {"samples": {
        "a.mp3": {"profile": {"steps": [{"pct": 100, "do": "x"}], "suits": {"settings": ["hills", "travel road"],
                                                                         "ghosts": ["unseen presence"]}}},
        "b.mp3": {"profile": {"steps": [{"pct": 100, "do": "y"}], "suits": {"settings": ["village pond"],
                                                                         "ghosts": ["folk spirit shankchunni"]}}},
    }}
    ranked = main.style_pick("a shankchunni near the village pond", "gram", sm)
    assert ranked[0][0] == "b.mp3"
    ranked = main.style_pick("travellers stranded on a hills road", "jayga", sm)
    assert ranked[0][0] == "a.mp3"


def test_style_pick_works_for_any_number_of_samples():
    import main
    sm = {"samples": {f"s{i}.mp3": {"profile": {"steps": [{"pct": 100, "do": "x"}], "suits": {}}} for i in range(9)}}
    assert len(main.style_pick("anything", "gram", sm)) == 9
    assert main.style_pick("anything", "gram", {"samples": {}}) == []


# ---------------------------------------------------------------- AUTO_DISCOVER (offline, fake web)
NEWS_XML = """<?xml version="1.0"?><rss><channel>
<item><title>Villagers report eerie lights at abandoned rajbari in Bankura - Anandabazar</title>
<link>https://news.google.com/a1</link><pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate>
<source url="https://www.anandabazar.com">Anandabazar</source></item>
<item><title>Minor girl found dead, villagers blame ghost - Some Site</title>
<link>https://news.google.com/a2</link><pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate>
<source url="https://x.com">Some Site</source></item>
</channel></rss>"""
TRENDS_XML = """<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>cricket score</title><ht:approx_traffic>500+</ht:approx_traffic></item></channel></rss>"""


class _R:
    def __init__(self, content=b"", js=None, ok=True, url="", ctype="text/html"):
        self.content, self._js, self.ok, self.url = content, js, ok, url
        self.text = content.decode("utf-8", "ignore") if isinstance(content, bytes) else str(content)
        self.headers = {"content-type": ctype}
        self.status_code = 200 if ok else 404

    def json(self):
        return self._js


def _fake_get(url, params=None, headers=None, timeout=None, allow_redirects=True):
    if "news.google.com" in url:
        return _R(NEWS_XML.encode())
    if "trends.google.com" in url:
        return _R(TRENDS_XML.encode())
    if "wikipedia.org" in url:
        return _R(js={"query": {"search": []}})
    if "anandabazar" in url or "telegraphindia" in url:
        return _R(b"<html>Bankura rajbari strange lights</html>", url=url)
    return _R(b"", ok=False)


def test_discovery_true_path_with_checked_sources(monkeypatch):
    import discovery
    monkeypatch.setattr(discovery.requests, "get", _fake_get)

    def gsearch(prompt):
        return ({"found": True, "place": "Bankura, West Bengal", "era": "2026", "title_en": "Bankura rajbari lights",
                 "what_is_reported": "x" * 300, "claims": [{"text": "lights seen", "type": "REPORTED_CLAIM"}],
                 "sensitivity": "low", "key_words": ["Bankura", "rajbari"]},
                [{"title": "ABP", "url": "https://www.anandabazar.com/a"},
                 {"title": "TT", "url": "https://www.telegraphindia.com/b"}])
    out = discovery.discover(["a shankchunni story"], gemini_search=gsearch, prefer="mixed")
    assert out and out["class"] == "true" and len(out["sources"]) == 2
    assert "Bankura" in out["theme"]


def test_discovery_rejects_sensitive_and_never_fakes_true(monkeypatch, tmp_path):
    import discovery
    monkeypatch.setattr(discovery.requests, "get", _fake_get)
    led = tmp_path / "ledger.json"
    out = discovery.discover([], gemini_search=lambda p: (None, []), prefer="mixed",
                             trend_topics=["a night guard alone in an abandoned hospital"], ledger_path=str(led))
    assert out["class"] == "fiction" and out["sources"] == []           # no dossier -> no factual claim
    rec = json.load(open(led, encoding="utf-8"))["entries"][-1]
    minor = [c for c in rec["candidates"] if "Minor" in c["title"]]
    assert minor and minor[0]["eligible"] is False                        # sensitive news never used
    assert rec["queries"] and all("at" in q for q in rec["queries"])      # every search is logged


def test_discovery_skips_used_topics(monkeypatch):
    import discovery
    monkeypatch.setattr(discovery.requests, "get", _fake_get)
    out = discovery.discover(["Villagers report eerie lights at abandoned rajbari in Bankura"],
                             gemini_search=None, prefer="trend", trend_topics=["a haunted ferry ghat"])
    assert out["title"] == "a haunted ferry ghat"


def test_discovery_survives_network_failure(monkeypatch):
    import discovery

    def boom(*a, **k):
        raise discovery.requests.exceptions.ConnectionError("offline")
    monkeypatch.setattr(discovery.requests, "get", boom)
    out = discovery.discover([], gemini_search=None, trend_topics=[])
    assert out is None


# ---------------------------------------------------------------- Telegram control centre
def test_control_parse_new_and_old_commands():
    import control
    assert control.parse("/autodiscover_off") == ("/autodiscover_off", "")
    assert control.parse("/topic_mode true_incident_priority") == ("/topic_mode", "TRUE_INCIDENT_PRIORITY")
    assert control.parse("/topic পুরুলিয়ার পরিত্যক্ত স্টেশন")[0] == "/topic"
    assert control.parse("অবস্থা") == ("/status", "")
    assert control.parse("বন্ধ ভূত ৩ দিন") == ("/pause", "3")
    assert control.parse("বন্ধ কার্টুন") is None                       # the cartoon bot's own command
    assert control.parse("বাদ ভূত ১") is None                          # still done by the story run
    assert control.parse("১ বদলাও") is None
    assert control.parse("আজকের জন্য নিজে সবচেয়ে ভালো সত্য ঘটনা খুঁজে গল্প বানাও")[0] == "/discover_true"
    assert control.parse("ট্রেন্ডিং হরর বিষয় খুঁজে তৈরি করো")[0] == "/discover_trend"
    assert control.parse("আজকের গল্প সব প্ল্যাটফর্মে প্রকাশ করো")[0] == "/publish_all"
    assert control.parse("Spotify আর Apple Podcasts-এর অবস্থা দেখাও")[0] == "/podcast_status"
    assert control.parse("x" * 300) is None                              # a story is never a command


def test_control_toggles_and_defaults(tmp_path, monkeypatch):
    import control
    s = control._merge(control.DEFAULT, {})
    assert s["autodiscover"] and s["autopublish"] and s["topic_mode"] == "AUTO_DISCOVER"
    control.handle("/youtube_off", "", s, ROOT)
    assert s["destinations"]["youtube"] is False and s["destinations"]["facebook"] is True
    control.handle("/pause", "2", s, ROOT)
    assert control.paused(s)
    control.handle("/resume", "", s, ROOT)
    assert not control.paused(s) and s["resumed_at"]
    control.handle("/topic", "একটা পুরোনো রাজবাড়ি", s, ROOT, uid=5)
    assert s["user_topics"][-1]["id"] == 5
    for cmd in ("/status", "/calendar", "/destinations", "/podcast_status", "/research_sources", "/topic_queue", "/help"):
        assert isinstance(control.handle(cmd, "", s, ROOT), str)
    f = tmp_path / "control.json"
    f.write_text(json.dumps({"autodiscover": False, "destinations": {"podcast": False}}), encoding="utf-8")
    monkeypatch.setenv("CONTROL_FILE", str(f))
    g = control.get(fresh=True)
    assert g["autodiscover"] is False and g["destinations"]["youtube"] is True
    assert control.dest_on("podcast") is False and control.dest_on("youtube") is True
    control._CACHE.clear()


# ---------------------------------------------------------------- animation helpers
def test_animate_module_exists_and_is_safe(tmp_path):
    import subprocess
    import numpy as np
    import animate
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=2", str(wav)], check=True)
    env = animate.voice_envelope(str(wav), 25)
    assert 45 <= len(env) <= 55 and float(env.max()) <= 1.0
    assert animate.viseme_at("মা", 0.0, 1.0) == "m"
    assert animate.viseme_at("ও", 0.0, 1.0) == "o"
    img = np.full((200, 200, 3), 120, np.float32)
    faces = [{"box": (50, 50, 100, 100), "eyes": [(80, 90, 8), (120, 90, 8)], "mouth": (100, 128, 36), "skin": (150, 110, 90)}]
    out = animate.draw_face(img, faces, blink=1.0, mouth=0.8, shape="o", gaze=(0.5, 0))
    assert out.shape == img.shape and not np.array_equal(out, img)
    assert animate.find_faces(np.zeros((100, 100, 3), np.uint8)) == []


# ---------------------------------------------------------------- main.py V8 glue (offline smoke)
def test_main_v8_glue_runs_offline(monkeypatch):
    import discovery
    import main
    monkeypatch.setattr(discovery.requests, "get", _fake_get)
    monkeypatch.setattr(main.extras, "trending_topics", lambda *a, **k: ["zqx unusual lighthouse keeper riddle"])
    monkeypatch.setattr(main, "push_now", lambda *a, **k: None)
    monkeypatch.setattr(main, "_jsave", lambda *a, **k: None)
    monkeypatch.setattr(discovery, "save_ledger", lambda *a, **k: None)
    out = main.discover_topic(main.load_history(), "bn", "gram", 14, report_only=True)
    assert out and out["class"] in ("true", "inspired", "fiction")
    theme, rules = main.apply_discovery(out, "")
    assert theme and main.STATE["story_class"] == out["class"]
    notes = main.podcast_notes({"summary": "একটা গল্প।\nকমেন্টে লিখুন 👇\nhttps://youtu.be/x"}, "bn")
    assert "youtu.be" not in notes and "কমেন্ট" not in notes and "কাল্পনিক" in notes
    assert main.paused_now() in (True, False)
    assert main.dest_on("youtube") is True
