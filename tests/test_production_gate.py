"""24 Nov 2026: the story ledger, the quality gate before posting, the narration style profile"""
import json
import os
import subprocess

import numpy as np


def _mp4(path, black_from=None, seconds=30):
    vf = "color=c=0x406080:s=320x180:d=%d" % seconds
    filt = []
    if black_from is not None:
        filt = ["-vf", f"drawbox=t=fill:c=black:enable='between(t,{black_from},{black_from + 6})'"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf, "-f", "lavfi", "-i",
                    f"sine=frequency=300:duration={seconds}"] + filt + ["-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                                                       "-c:a", "aac", path], check=True)


def test_quality_gate_passes_a_good_video_and_stops_a_bad_one(tmp_path):
    import episode_ledger as EL
    good, bad = str(tmp_path / "good.mp4"), str(tmp_path / "bad.mp4")
    _mp4(good)
    _mp4(bad, black_from=10)
    ok, rep = EL.quality_gate(good, 30, (320, 180), log=lambda *a: None)
    assert ok, rep
    ok2, rep2 = EL.quality_gate(bad, 30, (320, 180), log=lambda *a: None)
    assert not ok2 and any("black" in p for p in rep2["problems"])
    ok3, rep3 = EL.quality_gate(good, 60, (320, 180), log=lambda *a: None)
    assert not ok3 and any("length" in p for p in rep3["problems"])


def test_story_ledger_finds_missing_and_twice():
    import episode_ledger as EL
    story = {"scenes": [{"lines": [{"speaker": "narrator", "text": "রাত তখন অনেক। হঠাৎ দরজায় কে যেন টোকা দিল!"},
                                   {"speaker": "Bapi", "text": "কে ওখানে?"}]},
                        {"lines": [{"speaker": "narrator", "text": "কেউ উত্তর দিল না। শুধু বাতাসের শব্দ।"}]}]}
    segs = [(1, 2, True, "রাত তখন অনেক। হঠাৎ দরজায় কে যেন টোকা দিল!"), (4, 1, False, "কে ওখানে?"),
            (6, 1, False, "কে ওখানে?"), (8, 2, True, "শুধু বাতাসের শব্দ।")]
    r = EL.integrity(story, segs)
    assert r["sentences"] == 5
    assert r["missing"] == ["P02.L01.S01"] and r["said_twice"] == ["P01.L02.S01"] and r["ending_present"]


def test_package_files(tmp_path):
    import episode_ledger as EL
    story = {"title": "t", "scenes": [{"place": "ঘাট", "lines": [{"speaker": "narrator", "text": "এক।"}]}]}
    d = EL.write_package(str(tmp_path), "2026-11-24@14", story, [{"lines": story["scenes"][0]["lines"]}],
                         [(0.5, 1.0, True, "এক।")], "t", "d", ["x"], None, {"youtube": "abc"}, {"passed": True},
                         EL.integrity(story, [(0.5, 1.0, True, "এক।")]), {}, log=lambda *a: None)
    names = set(os.listdir(d))
    for f in ("complete_story.md", "approved_screenplay.md", "scene_breakdown.json", "audio_timeline.json",
              "dialogue_manifest.json", "story_sources.json", "seo_metadata.json", "story_integrity_report.json",
              "animation_qc_report.json", "publication_report.json", "production_report.md"):
        assert f in names, f
    pub = json.load(open(os.path.join(d, "publication_report.json")))
    assert pub["youtube_url"] == "https://youtu.be/abc" and pub["facebook_url"] is None
    assert "| 20 | Publishing and Delivery Manager" in open(os.path.join(d, "production_report.md")).read()


def test_voice_style_profile_is_locked_and_used():
    import voice_style as VS
    p = VS.profile()
    assert p and p["locked"] and p["measured"]["all"]["syllables_per_second"] > 0
    assert p["direction_short"] and len(p["direction_short"]) < 400
    assert 0.3 <= p["pauses_for_the_sound_track"]["between_lines_s"] <= 0.9
    sr = VS.SR
    t = np.arange(sr * 20) / sr
    burst = (np.sin(2 * np.pi * 140 * t) * (np.sin(2 * np.pi * 3.0 * t) > 0)) * 0.3
    f = VS.features(burst, "x")
    assert f and f["syllables_per_second"] > 0
