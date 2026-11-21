"""Tests for V1.1: location library, the three story assistants, story planning, normal walk speed, look-back."""
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("MOCK", "1")

CAST = [{"id": "abhishek", "name": "অভিষেক"}, {"id": "sayan", "name": "সায়ন"}, {"id": "haripada", "name": "হরিপদ"},
        {"id": "taranath", "name": "তারানাথ"}, {"id": "kishori", "name": "কিশোরী"}]


def test_every_location_builds_and_moves():
    import cartoon_rig as R
    import cinematic_camera as cc
    import location_library as L
    from environment_animation import Environment, wind_at
    assert set(L.LOCATIONS) == {"pond", "road", "jungle", "house_interior", "railway_station", "cremation_ground", "rajbari"}
    for loc in L.LOCATIONS:
        env = Environment(L.spec_for(loc, {"rain": 0.5, "lightning": [1.0]}))
        cam = cc.Camera(320, 180)
        frames = []
        for t in (2.0, 2.37):
            img = np.clip(env.background(cam, t, wind_at(t), None), 0, 255).astype(np.uint8)
            pt = R.Painter(img, cam)
            lights = env.draw_location(pt, t, wind_at(t), {"door_open": 0.5, "door_shake": 3})
            env.draw_trees(pt, t, wind_at(t))
            env.particles(pt, t, wind_at(t))
            frames.append(env.atmosphere(img.astype("float32"), cam, t, wind_at(t), lights))
        assert float(np.abs(frames[0] - frames[1]).mean()) > 0.02, loc          # something in the place moves


def test_location_assistant_finds_the_place_and_ignores_comparisons():
    import location_assistant as LA
    assert LA.analyse({"place": "রাতের রাস্তা", "lines": []})["location"] == "road"
    assert LA.analyse({"place": "জঙ্গলের ভেতরের রাস্তা", "lines": []})["location"] == "jungle"
    r = LA.analyse({"place": "তারানাথের কুটির, ঝোড়ো রাত", "lines": [{"speaker": "taranath", "text": "যেন পাথরের তৈরি দুটো শীতল দিঘি।"}]})
    assert r["location"] == "house_interior" and r["weather"]["lightning"] and r["weather"]["rain"] > 0
    assert LA.analyse({"place": "পুরোনো শ্মশানঘাট", "lines": []})["location"] == "cremation_ground"
    assert LA.analyse({"place": "ফাঁকা প্ল্যাটফর্ম", "lines": []})["location"] == "railway_station"
    assert LA.analyse({"place": "জমিদারবাড়ি", "lines": []})["location"] == "rajbari"
    h = LA.analyse({"place": "হাসপাতাল", "lines": []})
    assert h["status"] == "SUBSTITUTE" and h["location"] == "house_interior"


def test_action_assistant_reads_who_does_what():
    import action_assistant as AA
    lines = [{"i": 1, "speaker": "abhishek", "listener": "haripada", "text": "দোকান বন্ধ করার মুখে হঠাৎ মাঝরাস্তায় লণ্ঠন দোলাচ্ছেন কেন?"},
             {"i": 2, "speaker": "abhishek", "listener": "sayan", "text": "হাত দুটো এমন কাঠ হয়ে গেছে কেন?"},
             {"i": 3, "speaker": "abhishek", "listener": "sayan", "text": "আমার দিকে তাকা!"},
             {"i": 4, "speaker": "narrator", "listener": None, "text": "এমনই এক ঝোড়ো রাতে কুটিরের দরজায় ধাক্কা পড়ল।"},
             {"i": 5, "speaker": "taranath", "listener": "kishori", "text": "তাতে কোনো পলক পড়ত না।"},
             {"i": 6, "speaker": "abhishek", "listener": "sayan", "text": "না, সায়ন তো অসাড়!"}]
    r = AA.analyse(lines, CAST)
    assert r["source"] == "offline-rules"
    d = {ln["i"]: {(x["act"], x["who"], x["mode"]) for x in ln["doing"]} for ln in r["lines"]}
    assert ("swing_lantern", "haripada", "happens") in d[1]
    assert ("stiff", "sayan", "happens") in d[2]
    assert ("look", "sayan", "command") in d[3]
    assert ("knock", None, "happens") in d[4] and ("rain", None, "happens") in d[4]
    assert ("stare", None, "mentioned") in d[5]                     # a memory: nothing to show
    assert ("stiff", "sayan", "happens") in d[6]


def test_match_assistant_is_honest():
    import match_assistant as MA
    an = [{"i": 1, "speaker": "a", "emotion": "calm", "who": "a", "target": "b",
           "doing": [{"act": "talk", "who": "a", "mode": "happens"}, {"act": "fall", "who": "b", "mode": "happens"},
                     {"act": "ride_vehicle", "who": "b", "mode": "happens"}, {"act": "knock", "who": None, "mode": "happens"},
                     {"act": "run", "who": "b", "mode": "command"}, {"act": "other:juggles", "who": "a", "mode": "happens"}]}]
    r = MA.judge(an, "road", ["a", "b"])
    st = {it["act"]: it["status"] for it in r["lines"][0]["items"]}
    assert st == {"talk": "MATCH", "fall": "SUBSTITUTE", "ride_vehicle": "MISSING", "knock": "SUBSTITUTE",
                  "run": "COMMAND", "other:juggles": "MISSING"}
    assert not any(o["op"] == "run" for o in r["ops"])             # a command is not shown as done
    r2 = MA.judge(an, "house_interior", ["a", "b"])
    assert {it["act"]: it["status"] for it in r2["lines"][0]["items"]}["knock"] == "MATCH"


def test_walk_is_normal_speed_never_slow_motion():
    import animation_renderer as AR
    assert 1.0 <= AR.WALK_SPEED / 195.0 <= 1.6                     # ~1.3 m/s
    steps_per_s = AR.WALK_SPEED / AR.STRIDE["walk"]
    assert 1.7 <= steps_per_s <= 2.4
    assert AR.travel_time(1000) < 4.5
    import scene_planner as SP
    clips = {k: ("x", 4.0) for k in ("c1", "c2", "c3", "c4", "c5")}
    p = SP.pond_test_plan(clips)
    w = next(a for a in p["actions"] if a["type"] == "walk")
    speed = abs(w["to_x"] - 790) / (w["t1"] - w["t0"])
    assert speed >= 0.9 * AR.WALK_SPEED


def test_look_back_turns_face_and_body():
    import animation_renderer as AR
    import scene_planner as SP
    plan = {"id": "t", "duration": 6.0, "environment": {"location": "pond", "pond": (1110, 720, 560, 128), "grass": 0, "bank_grass": 0,
                                                        "fireflies": 0, "falling_leaves": 0},
            "characters": [{"id": "a", "design": "man", "x": 800, "ground_y": 935, "facing": -1.0, "start_pose": "sit"}],
            "dialogue": [], "camera": [{"t0": 0, "t1": 6, "type": "wide"}],
            "actions": [{"t0": 1.0, "t1": 5.0, "who": "a", "type": "look", "yaw": 1.0, "target": None}]}
    sc = AR.Scene(plan, {}, 24)
    st = sc.char_state("a", 3.0)
    assert st["facing"] == -1.0                                      # hips + legs stay where they were
    assert -0.6 < st["facing_upper"] < -0.3                          # the chest twists part of the way
    assert st["head_yaw"] > 0.3                                      # the face turns towards what is behind ...
    assert st["head_yaw"] - st["facing_upper"] <= 0.951              # ... but never further than a real neck
    back = sc.char_state("a", 5.6)                                   # after the look: all of him faces front again
    assert back["head_yaw"] == -1.0 and "facing_upper" not in back


def test_hands_never_left_behind_and_fingers_drawn():
    import cartoon_rig as R
    import cinematic_camera as cc
    for name in ("sit_fear", "stand_fear"):
        p = R.POSES[name]
        assert p["uarm_n"] > 0 and p["farm_n"] > 0 and p["uarm_f"] > 0     # arms come forward / up, never behind
    ch = R.Character("a", dict(R.DESIGNS["man"]))
    cam = cc.Camera(400, 400)
    cam.set(1000, 620, 5.0)
    imgs = []
    for mode in ("point", "fist"):
        img = np.zeros((400, 400, 3), np.uint8)
        ch.draw(R.Painter(img, cam), {"x": 960, "ground_y": 935, "facing": 1.0, "head_yaw": 1.0, "pose": dict(R.POSES["stand_point"]),
                                      "fingers": mode, "t": 0.0})
        imgs.append(img.astype(int))
    assert np.abs(imgs[0] - imgs[1]).sum() > 0                         # the fingers really change shape


def test_plan_from_story_matches_the_lines(tmp_path):
    import cartoon_rig as R
    import scene_planner as SP
    lines = [{"i": 1, "speaker": "taranath", "listener": "kishori", "t0": 2.0, "t1": 5.0, "clip": "x", "emotion": "calm"},
             {"i": 2, "speaker": "narrator", "listener": None, "t0": 5.4, "t1": 8.0, "clip": "y", "emotion": "scared"},
             {"i": 3, "speaker": "taranath", "listener": "kishori", "t0": 8.4, "t1": 11.0, "clip": "z", "emotion": "scared"}]
    ops = [{"line": 2, "op": "knock", "who": None, "target": None, "ongoing": False}]
    plan, reac = SP.plan_from_story({"id": "C", "location": "house_interior", "weather": {"rain": 0.8, "lightning": True},
                                     "duration": 12.0, "lead_in": 2.0, "lines": lines, "ops": ops,
                                     "characters": [{"id": "taranath", "design": R.DESIGNS["old_man"]},
                                                    {"id": "kishori", "design": R.DESIGNS["young_man"]}]})
    assert plan["door"] and plan["door"][0]["type"] == "knock" and 5.4 <= plan["door"][0]["t0"] <= 6.0
    assert any(s["type"] == "knock" for s in plan["sfx"]) and any(s["type"] == "thunder" for s in plan["sfx"])
    assert {c["start_pose"] for c in plan["characters"]} == {"sit"} and len(plan["props"]) == 2   # on stools
    assert [d["speaker"] for d in plan["dialogue"]] == ["taranath", "taranath"]                    # no narrator mouth
    assert len(reac) == 2 and all(r["act"] == "look_at_door" for r in reac)
    assert plan["camera"][0]["t0"] == 0 and plan["camera"][-1]["t1"] == 12.0
    for a, b in zip(plan["camera"], plan["camera"][1:]):
        assert abs(a["t1"] - b["t0"]) < 1e-6                         # no gap between shots


def test_cartoon_mode_is_off_unless_asked():
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert 'env("ANIM_MODE") == "cartoon"' in src
    assert "this scene is made the classic way" in src                # a failed cartoon scene falls back
    import story_engine
    cast = story_engine.cast_of([{"name": "অভিষেক", "gender": "male", "age": "40"},
                                 {"name": "সায়ন", "gender": "male", "age": "young 22"},
                                 {"name": "মধুসুন্দরী", "gender": "female", "kind": "ghost"}])
    assert [c["id"] for c in cast] == ["অভিষেক", "সায়ন", "মধুসুন্দরী"] or len(cast) == 3
    assert cast[2]["design"].get("faceless")


def test_gemini_cannot_invent_actions():
    import json
    import action_assistant as AA
    import match_assistant as MA
    lines = [{"i": 1, "speaker": "a", "listener": "b", "text": "সায়ন! ভাই আমার... কী হয়েছে তোর?"}]
    fake = lambda p: json.dumps({"lines": [{"i": 1, "doing": [{"act": "grab", "who": "a", "mode": "happens", "words": "হাত ধরে"}]}]})
    r = AA.analyse(lines, [{"id": "a", "name": "অভিষেক"}, {"id": "b", "name": "সায়ন"}], "", llm=fake)
    assert r["source"] == "gemini" and not any(d["act"] == "grab" for d in r["lines"][0]["doing"])
    m = MA.judge(r["lines"], "road", ["a", "b"])
    assert m["counts"].get("REJECTED") == 1 and not any(o["op"] == "reach" for o in m["ops"])
