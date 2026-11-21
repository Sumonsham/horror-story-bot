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


def test_slash_menu_is_valid_and_every_item_is_understood():
    import re
    import control
    assert control.TG_UPDATES == __import__("extras").TG_UPDATES      # every reader asks Telegram the same
    for c, d in control.MENU:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", c) and 3 <= len(d) <= 256
        assert control.parse("/" + c) is not None, c                   # tapping it always gets an answer


# ---------------------------------------------------------------- character pipeline
def _fake_person(prompt, ref, seed, w, h):
    """a 'photo' on a plain grey studio background (stands in for the free Cloudflare picture)"""
    import io
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (178, 178, 178))
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.35, h * 0.3, w * 0.65, h * 0.95], fill=(90, 40, 40))
    d.ellipse([w * 0.38, h * 0.1, w * 0.62, h * 0.3], fill=(200, 150, 120))
    if "speaking" in prompt or "open" in prompt:
        d.ellipse([w * 0.47, h * 0.23, w * 0.53, h * 0.27], fill=(30, 10, 10))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_character_library_makes_once_and_reuses(tmp_path, monkeypatch):
    import characters
    monkeypatch.setattr(characters, "face_box", lambda img: [int(img.width * 0.38), int(img.height * 0.1),
                                                            int(img.width * 0.24), int(img.height * 0.2)])
    lib = characters.Library(str(tmp_path), str(tmp_path / "cache"), image_fn=_fake_person)
    c = {"name": "Taranath", "gender": "male", "age": "old", "look": "old tantrik"}
    rec = lib.ensure(c, "taranath", seed=3)
    assert rec["mode"] == "photo" and {"reference", "neutral", "talking", "fear", "shock"} <= set(rec["expr"])
    made = lib.stats["images_made"]
    lib2 = characters.Library(str(tmp_path), str(tmp_path / "cache"), image_fn=_fake_person)
    lib2.ensure(c, "taranath", seed=3)
    assert lib2.stats["images_made"] == 0 and lib2.stats["cache_hits"] == 1      # never made twice
    assert made == 5
    sp = lib2.sprites(lib2.get("taranath"))
    assert sp["neutral"].mode == "RGBA" and sp["neutral"].getpixel((2, 2))[3] == 0    # transparent background


def test_character_falls_back_to_silhouette_without_pictures(tmp_path):
    import characters
    lib = characters.Library(str(tmp_path), str(tmp_path / "c"), image_fn=None)
    rec = lib.ensure({"name": "Chhaya", "gender": "female", "age": "old", "kind": "ghost"}, "chhaya-x")
    assert rec["mode"] == "silhouette" and rec["rig"]["ghost"] is True
    p, key = lib.background("old rajbari courtyard", "village", "creepy")
    assert os.path.exists(p) and key.endswith("procedural")


def test_manifest_and_compositor_render(tmp_path, monkeypatch):
    import subprocess
    import characters
    import compositor
    import manifest
    monkeypatch.setattr(characters, "face_box", lambda img: [int(img.width * 0.38), int(img.height * 0.1),
                                                            int(img.width * 0.24), int(img.height * 0.2)])
    lib = characters.Library(str(tmp_path), str(tmp_path / "cache"), image_fn=_fake_person)
    recs = {"rana": lib.ensure({"name": "Rana", "gender": "male"}, "rana-1", seed=1),
            "chhaya": characters.Library(str(tmp_path / "b"), str(tmp_path / "c2")).ensure(
                {"name": "Chhaya", "kind": "ghost", "gender": "female"}, "chhaya-1")}
    bg = lib.background("rainy station", "night", "scare")
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", "-ac", "2",
                    str(wav)], check=True)
    scene = {"characters": ["Rana", "Chhaya"], "place": "rainy station", "mood": "scare",
             "lines": [{"speaker": "Rana", "text": "কে ওখানে? বৃষ্টি", "emotion": "scared"}]}
    m = manifest.build_scene(0, scene, [(0.0, 2.0, "Rana", "normal", "কে ওখানে?")], 2.0, recs, bg)
    assert {c["id"] for c in m["characters"]} == {"rana-1", "chhaya-1"} and "rain" in m["effects"]
    assert m["beats"][0]["speaker"] == "rana-1"
    out = tmp_path / "c.mp4"
    rep = compositor.render_scene(m, {r["id"]: r for r in recs.values()}, lib, str(wav), str(out), quality="FAST")
    assert out.stat().st_size > 1000 and rep["characters"]["rana-1"]["lip_sync"] is True
    assert rep["characters"]["chhaya-1"]["mode"] == "cartoon"          # (no photo -> a drawn face, not a black shape)
    assert rep["lip_frames"] > 0


def test_compositor_silhouette_when_asked(tmp_path, monkeypatch):
    import subprocess
    import characters
    import compositor
    import manifest
    monkeypatch.setenv("ANIM_FALLBACK", "silhouette")
    lib = characters.Library(str(tmp_path), str(tmp_path / "c"))
    recs = {"chhaya": lib.ensure({"name": "Chhaya", "kind": "ghost", "gender": "female"}, "chhaya-1")}
    bg = lib.background("pond", "night", "creepy")
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1", "-ac", "2", str(wav)], check=True)
    m = manifest.build_scene(0, {"characters": ["Chhaya"]}, [(0.0, 1.0, None, "", "")], 1.0, recs, bg)
    rep = compositor.render_scene(m, {r["id"]: r for r in recs.values()}, lib, str(wav), str(tmp_path / "o.mp4"), quality="FAST")
    assert rep["characters"]["chhaya-1"]["mode"] == "silhouette" and rep["characters"]["chhaya-1"]["lip_sync"] is False


# ---------------------------------------------------------------- cartoon rig + environment + renderer
def test_cartoon_rig_parts_and_feet():
    import numpy as np
    import cartoon_rig as R
    import cinematic_camera as cc
    cam = cc.Camera(640, 360)
    cam.set(960, 700, 1.5)
    img = np.zeros((360, 640, 3), np.uint8)
    ch = R.Character("a", dict(R.DESIGNS["old_man"]))
    for pose in ("stand", "sit", "sit_talk", "stand_fear"):
        st = {"x": 960, "ground_y": 935, "facing": 1.0, "head_yaw": 0.4, "pose": dict(R.POSES[pose]),
              "mouth": (0.8, "A"), "blink": 0.0, "gaze": (0.5, 0), "brows": "fear"}
        j = ch.draw(R.Painter(img, cam), st)
        assert abs(max(j["ft_n"][1], j["ft_f"][1]) + 4 * j["k"] - 935) < 0.5        # the feet are on the ground
    for ph in np.linspace(0, 6.28, 9):
        st = {"x": 900, "ground_y": 935, "facing": -1.0, "pose": R.walk_pose(ph), "mouth": (0, "rest")}
        j = ch.draw(R.Painter(img, cam), st)
        assert abs(max(j["ft_n"][1], j["ft_f"][1]) + 4 * j["k"] - 935) < 0.5
    assert img.mean() > 1                                    # something was drawn
    sp = R.sprite(ch, {"facing": 1, "pose": dict(R.POSES["stand"]), "mouth": (0, "rest")}, 300)
    assert sp.shape[2] == 4 and sp[..., 3].max() == 255 and sp[2, 2, 3] == 0


def test_lip_sync_follows_the_voice(tmp_path):
    import subprocess
    import lip_sync
    wav = tmp_path / "v.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=500:duration=1", "-f", "lavfi", "-i",
                    "anullsrc=r=44100:cl=mono", "-filter_complex", "[1]atrim=0:1[s];[0][s]concat=n=2:v=0:a=1", str(wav)], check=True)
    v = lip_sync.visemes(str(wav), 24)
    first, second = [o for o, _ in v[:20]], [o for o, _ in v[28:46]]
    assert max(first) > 0.5 and max(second) < 0.1                  # open with sound, closed in silence


def test_renderer_frame_and_plan(tmp_path):
    import numpy as np
    import animation_renderer as AR
    import cinematic_camera as cc
    import scene_planner
    clips = {}
    import subprocess
    for k, d in (("c1", 2.0), ("c2", 2.0), ("c3", 1.0), ("c4", 1.0), ("c5", 1.0)):
        p = tmp_path / f"{k}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=duration={d}", str(p)], check=True)
        clips[k] = (str(p), d)
    plan = scene_planner.pond_test_plan(clips)
    assert plan["duration"] >= 60 and {s["type"] for s in plan["camera"]} >= {"wide", "ots", "close_up", "reveal", "follow"}
    sc = AR.Scene(plan, clips, 12)
    cam = cc.Camera(320, 180)
    a = sc.render(1.0, 320, 180, cam)
    b = sc.render(1.5, 320, 180, cam)
    assert a.shape == (180, 320, 3) and np.abs(a.astype(int) - b.astype(int)).mean() > 0.2   # the world moves
