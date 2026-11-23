"""tvtoon - Bengali TV cartoon system: characters, faces, rig, lip-sync, scene, QA, approvals (no network)"""
import json
import os

import numpy as np
import pytest

cairo = pytest.importorskip("cairo")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_twelve_characters_two_per_category_and_six_samples():
    from tvtoon import characters as CH
    cats = {}
    for cid, s in CH.SPECS.items():
        if s.get("cast") != "horror":
            cats.setdefault(s["category"], []).append(cid)
    for cid, v in CH.PENDING.items():
        cats.setdefault(v[0], []).append(cid)
    assert set(cats) == set(CH.CATEGORIES) and all(len(v) == 2 for v in cats.values())
    assert sorted(CH.SPECS[c]["category"] for c in CH.samples()) == sorted(CH.CATEGORIES)


def test_every_sample_is_really_different():
    from tvtoon import characters as CH
    from tvtoon import qa
    ids = CH.samples()
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            assert qa.identity_distance(CH.get(a), CH.get(b)) >= 4, (a, b)


def test_face_asset_counts():
    from tvtoon import face as F
    assert len(F.EYES) == 7 and len(F.BROW_STATES) == 5 and len(F.MOUTHS) == 9
    for e in ("happy", "sad", "angry", "surprised", "laughing", "scared"):
        assert e in F.EXPRESSIONS


def test_bengali_visemes():
    from tvtoon import lipsync as L
    sy = L.syllables("আমি মাঠে খেলতে যাচ্ছি।")
    assert len(sy) >= 6
    vowels = [s[1] for s in sy]
    assert vowels[0] == "A" and "E" in vowels                    # আ ... ি
    assert L.cons_vis("ম") == "MBP" and L.cons_vis("ফ") == "FV" and L.cons_vis("ল") == "LTD"


def test_lipsync_follows_the_real_audio(tmp_path):
    """a synthetic 'voice' with 3 bursts: mouth opens only inside the bursts"""
    import subprocess
    from tvtoon import lipsync as L
    sr = 16000
    t = np.arange(int(sr * 2.4)) / sr
    env = ((t > 0.2) & (t < 0.6)) | ((t > 1.0) & (t < 1.4)) | ((t > 1.8) & (t < 2.2))
    x = (np.sin(2 * np.pi * 220 * t) * 0.5 + np.sin(2 * np.pi * 900 * t) * 0.2) * env
    raw = tmp_path / "a.raw"
    (x * 20000).astype(np.int16).tofile(raw)
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", str(raw), str(wav)], check=True)
    ev, info = L.align(str(wav), "আম আম আম")
    opens = [tt for tt, v in ev if v != "X"]
    assert opens and min(opens) > 0.1 and max(opens) < 2.3
    assert L.viseme_at(ev, 0.05) == "X"


def test_puppet_draws_every_part_and_has_two_of_each_limb():
    from tvtoon import characters as CH
    from tvtoon import qa
    r = qa.validate("bappa")
    assert r["checks"]["limbs"] == {"arms": 2, "legs": 2, "hands": 2, "feet": 2}
    assert all(v == 5 for v in r["checks"]["fingers_per_hand_shape"].values())
    assert r["checks"]["mouths_distinct"] == 9 and r["checks"]["eyes_distinct"] == 7 and r["checks"]["brows_distinct"] == 5


def test_scene_plans_dialogue_and_voices_never_cross_gender(tmp_path):
    from tvtoon import scene as S
    from tvtoon import voices as V
    for f in ("lumi_didi", "sarala_thakuma", "mili"):
        assert f in V.FEMALE
    import extras
    female_voices = set(extras.CHIRP_VOICES[:14])
    for c, (v, _w) in V.VOICE.items():
        if c != "narrator":
            assert (v in female_voices) == (c in V.FEMALE), c
    spec = {"location": "village_courtyard", "fps": 24, "size": [480, 270], "subtitles": False,
            "cast": [{"id": "lumi_didi", "x": 1200}, {"id": "bappa", "x": 1600}],
            "beats": [{"who": "lumi_didi", "say": "বাপ্পা, তুমি কোথায় যাচ্ছ?", "to": "bappa"},
                      {"who": "bappa", "walk_to": 2000, "gait": "run"}]}
    sc = S.Scene(spec)
    assert sc.duration > 2 and len(sc.lines) == 1
    from tvtoon import backgrounds as BG
    img = sc.render_frame(1.0, BG.village_courtyard())
    assert img.shape == (270, 480, 3) and img.std() > 10


def test_no_approval_is_ever_written():
    src = "".join(open(os.path.join(ROOT, "tvtoon", f), encoding="utf-8").read()
                  for f in os.listdir(os.path.join(ROOT, "tvtoon")) if f.endswith(".py"))
    assert "USER_APPROVED" in src                                # it is READ ...
    assert "json.dump(" not in src.split("def approvals")[1].split("def approved")[0]
    ap = json.load(open(os.path.join(ROOT, "tvtoon", "approvals.json"), encoding="utf-8"))
    # the program never approves: every approval carries the owner's own note (23 Nov 2026: he approved in chat)
    assert all("owner" in v.get("note", "") for k, v in ap.items() if not k.startswith("_") and v["status"] == "USER_APPROVED")


def test_tvtoon_needs_no_cloudflare_or_image_api():
    src = "".join(open(os.path.join(ROOT, "tvtoon", f), encoding="utf-8").read().lower()
                  for f in os.listdir(os.path.join(ROOT, "tvtoon")) if f.endswith(".py"))
    assert "cloudflare" not in src and "api.cloudflare" not in src


# ------------------------------------------------------------------ engine v2: real movement, measured
def test_v2_background_really_moves_and_fixed_things_stay():
    from tvtoon import qa_motion as Q, world as WD
    r = Q.background_motion(WD.World({"wind": 0.55}))
    assert r["pass"], r


def test_v2_parallax_layers_move_by_depth():
    from tvtoon import qa_motion as Q, world as WD
    r = Q.parallax(WD.World())
    s = r["screen_shift_px_for_200px_pan"]
    assert r["pass"] and s["sky"] == 0 and s["clouds"] < s["huts"] < s["ground"] < s["foreground"]


def test_v2_day_turns_to_dusk():
    from tvtoon import world as WD
    w = WD.World({"hours": [[0, 16.0], [10, 19.5]]})
    a, b = WD.tod_palette(w.hour(0)), WD.tod_palette(w.hour(10))
    assert sum(a[0]) > sum(b[0]) + 0.5            # the sky darkens
    assert b[3] < a[3]                             # the sun goes down


def test_v2_gestures_anticipate_and_overshoot():
    from tvtoon import animator as AN
    w = [AN.gesture_weight(t, 5.0) for t in [i / 100 for i in range(0, 60)]]
    assert min(w) < 0                              # anticipation: first a small move the other way
    assert max(w) > 1.0                            # overshoot past the pose ...
    assert abs(w[-1] - 1.0) < 0.02                 # ... and settle on it


def _fake_voice(tmp_dir):
    """an offline stand-in voice for the tests: one short tone burst per Bengali syllable (no voice service, no
    recording - the tests never generate or use a real voice; the videos use Chirp in tests, Gemini in production)"""
    import wave
    from tvtoon import lipsync as LS

    def line(cid, text, emotion="neutral", log=print):
        n = max(1, len(LS.syllables(text)))
        sr = 16000
        sig = []
        for k in range(n):
            t = np.arange(int(sr * 0.17)) / sr
            sig.append(np.sin(2 * np.pi * 180 * t) * np.sin(np.pi * t / 0.17) * 9000)
            sig.append(np.zeros(int(sr * 0.05)))
        p = os.path.join(tmp_dir, f"{abs(hash((cid, text))) % 10 ** 8}.wav")
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(np.concatenate(sig).astype(np.int16).tobytes())
        return p, "test tone"
    return line


def test_v2_conversation_acting_lipsync_and_camera(tmp_path, monkeypatch):
    from tvtoon import production as P, qa_motion as Q, scene as S, voices as VO
    monkeypatch.setattr(VO, "line", _fake_voice(str(tmp_path)))       # the same result with any voice setting
    spec = P.v2_test_spec()
    sc = S.Scene(spec)
    assert 30 <= sc.duration <= 45
    types = {s["type"] for s in sc.shots}
    for t in ("establish", "track", "two", "close", "reaction", "ots", "ecu", "medium", "wide"):
        assert t in types, t
    zs = sorted({round(sc.framing(s, s["t0"] + 0.1)[2], 2) for s in sc.shots})
    assert len(zs) >= 6                            # really different shot sizes
    # an eased transition: the camera moves continuously (no jump) through it
    ease = next(s for s in sc.shots if s.get("trans") == "ease")
    cams = [sc.camera(ease["t0"] + k / 24) for k in range(0, 20)]
    assert max(abs(a[0] - b[0]) for a, b in zip(cams, cams[1:])) < 60
    assert Q.facial(S.Scene(spec))["pass"]
    assert Q.lipsync_timing(S.Scene(spec))["pass"]
    assert Q.character_motion(S.Scene(spec), t1=12.0)["pass"]
    # characters stand at different depths (not one straight line)
    assert len({sc.gy(c) for c in sc.order}) >= 4


def test_chirp_only_test_and_female_chirp_voices():
    import extras
    from tvtoon import voices as V
    women = set(extras.CHIRP_VOICES[:14])
    for c, (v, _w) in V.VOICE.items():
        assert v in extras.CHIRP_VOICES, c
        assert (v in women) == (c in V.FEMALE), c
    y = open(os.path.join(ROOT, ".github", "workflows", "tv-cartoon-sample.yml"), encoding="utf-8").read()
    # tests use Chirp only; only the normal story mode (story_episode) uses the Gemini voice (owner, 23 Nov 2026)
    assert "'gemini' || 'chirp'" in y and "inputs.what == 'story_episode'" in y and "GOOGLE_TTS_KEY" in y
    test_step = y.split("Render (tests - Chirp only)")[1].split("Render (normal story mode")[0]
    assert "GEMINI" not in test_step
    import os as _os
    _os.environ["TVTOON_VOICE"] = "chirp"
    _os.environ.pop("GOOGLE_TTS_KEY", None)
    try:
        wav, how = V.line("lumi_didi", "পরীক্ষা")
        assert wav is None and "Chirp" in how                 # no Gemini fallback, no recording
    finally:
        _os.environ.pop("TVTOON_VOICE", None)


# ------------------------------------------------------------------ horror cast, locations, vehicles, ghosts
def test_horror_cast_14_all_valid_and_distinct():
    from tvtoon import characters as CH, qa
    cast = CH.horror_cast()
    assert len(cast) == 14 and len({CH.get(c)["category"] for c in cast}) == 7
    assert sum(1 for c in cast if CH.get(c).get("ghost")) == 4
    for c in ("petni", "ojha", "abhishek", "kishori"):
        r = qa.validate(c)
        assert r["pass"], (c, r["problems"])


def test_every_location_draws_and_moves():
    import cairo
    from tvtoon import locations as L, qa_motion as Q
    for name in L.LOCATIONS:
        w = L.make(name, {})
        f0 = Q._world_frame(w, 320, 180, (1600.0, 420.0, 0.8 * 320 / 1920), 1.0)
        f1 = Q._world_frame(w, 320, 180, (1600.0, 420.0, 0.8 * 320 / 1920), 2.0)
        assert f0.std() > 5, name                                    # something is drawn
        assert (np.abs(f1 - f0).sum(axis=2) > 30).mean() > 0.002, name  # and something moves


def test_vehicles_wheels_turn_and_stop_smoothly():
    from tvtoon import vehicles as V
    for kind in V.SPEC:
        v = V.Vehicle("v", kind, 0.0)
        v.moves = [(0.0, 6.0, 0.0, 3000.0)]
        xs = [v.x_at(i / 24) for i in range(0, 150)]
        sp = np.diff(xs)
        assert xs[0] == 0.0 and abs(xs[-1] - 3000.0) < 1e-6
        assert sp[0] < sp[70] and sp[140] < sp[70]                  # it accelerates, cruises, brakes
        assert max(abs(np.diff(sp))) < 3.0                           # no jerk
    assert V.Vehicle("c", "cycle", 0).open_ride() and not V.Vehicle("b", "bus", 0).open_ride()


def test_ghost_floats_and_rider_follows_vehicle():
    from tvtoon import scene as S
    spec = {"location": "bansh_bon", "fps": 24, "size": [480, 270], "subtitles": False,
            "cast": [{"id": "petni", "x": 1600, "z": 0.4}, {"id": "abhishek", "x": 800}],
            "vehicles": [{"id": "bike", "kind": "bike", "x": 800}],
            "beats": [{"who": "abhishek", "ride": "bike"}, {"vehicle": "bike", "drive_to": 2000, "sec": 3.0},
                      {"pause": 0.5}]}
    sc = S.Scene(spec)
    st, x = sc.perf["petni"].state(1.0, sc)
    assert st["float_y"] > 10                                       # she does not touch the ground
    xa = [sc.perf["abhishek"].state(t, sc)[1] for t in (0.6, 2.0, 3.6)]
    assert xa[0] < xa[1] < xa[2] and abs(xa[2] - sc.vehicle_seat_x("bike", 0, 3.6)) < 1e-6
    img = sc.render_frame(2.0)
    assert img.shape == (270, 480, 3) and img.std() > 5


def test_narrator_is_a_voice_over_not_a_speaker():
    from tvtoon import scene as S
    spec = {"location": "zamindar_bari", "fps": 24, "size": [320, 180], "subtitles": False,
            "cast": [{"id": "parul", "x": 1500}], "beats": [{"narrate": "এক পলকে সব শান্ত।"}]}
    sc = S.Scene(spec)
    assert sc.lines and sc.lines[0]["narrator"] and sc.current_speaker(sc.lines[0]["t0"] + 0.1) is None


def test_story_becomes_an_episode():
    from tvtoon import story as S, scene as SC
    story = {"title": "t", "characters": [
        {"name": "abani", "gender": "male", "age": "old", "kind": "human", "name_local": "অবনীবাবু"},
        {"name": "chhaya", "gender": "female", "age": "young", "kind": "ghost", "name_local": "ছায়া"},
        {"name": "tuli", "gender": "female", "age": "9", "kind": "human"}],
        "scenes": [{"place": "Railway station at midnight, rain", "mood": "scare",
                    "lines": [{"speaker": "narrator", "text": "সেই রাতে বৃষ্টি পড়ছিল।"},
                              {"speaker": "abani", "text": "কে ওখানে?", "emotion": "scared"},
                              {"speaker": "chhaya", "text": "আমি...", "emotion": "eerie"}]},
                   {"place": "Old bedroom, lantern light", "lines": [{"speaker": "tuli", "text": "দাদু!", "emotion": "crying"}]}]}
    ep = S.episode_from_story(story)
    cast = ep["cast"]
    assert cast["chhaya"]["actor"] in ("petni", "shakchunni")             # a female ghost plays the female ghost
    assert cast["tuli"]["actor"] == "kishori" and cast["abani"]["shown"] == "অবনীবাবু"
    s1, s2 = ep["scenes"]
    assert s1["location"] == "station" and s1["world"]["hours"][0][1] > 20 and s1["world"].get("rain")
    assert s2["location"] == "ghar"
    sc = SC.Scene(dict(s1, size=[320, 180]))
    assert sc.lines[0]["narrator"] and sc.lines[1]["who"] == cast["abani"]["actor"]
    assert sc.names[cast["abani"]["actor"]] == "অবনীবাবু"


def test_room_door_opens_and_lamp_dies():
    from tvtoon import locations as L, qa_motion as Q
    w = L.make("ghar", {"door_open_at": 1.0, "lamp_off_at": 3.0})
    cam = (2300.0, 420.0, 0.8 * 320 / 1920)
    a, b = Q._world_frame(w, 320, 180, cam, 0.5), Q._world_frame(w, 320, 180, cam, 4.0)
    assert (abs(b - a).sum(axis=2) > 40).mean() > 0.02                    # the door is open, the light is out


# ---------------------------------------------------------------- side view, rides, interiors (23 Nov 2026)
def _side_state(mode, **kw):
    sd = dict({"d": 1, "t": 0.5, "mode": mode}, **kw)
    return {"rot": {}, "len": {}, "hands": {}, "face": {"lid": 1.0, "mouth": "A"}, "hair": (0, 0), "cloth": 0.0, "side": sd}


def test_every_character_has_a_true_side_view():
    from tvtoon import characters as CH, puppet as PP, profile as PR
    ids = list(dict.fromkeys(list(CH.SPECS) + CH.horror_cast()))
    for cid in ids:
        if CH.get(cid).get("animal"):                     # (animals have their own drawing: test_animals_draw)
            continue
        pp = PP.Puppet(CH.get(cid))
        P = pp.P
        for st in (_side_state("stand"), _side_state("sit", sit=(1.0, P["foot_h"] + P["shin"] + P["thigh"] * 0.34)),
                   _side_state("walk", walk={"phase": 0.3, "S": P["leg"] * 0.85, "duty": 0.62, "d": 1, "run": False})):
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 700)
            ctx = cairo.Context(surf)
            J = pp.draw(ctx, st, 200, 680, 0.6)
            a = np.ndarray((700, 400, 4), np.uint8, surf.get_data())[:, :, 3]
            assert (a > 0).sum() > 8000, cid                              # a whole body was drawn
            if st["side"]["mode"] == "sit":                               # thighs forward, knees in front of the hip
                assert J["knee_near"][0] - J["hip"][0] > P["thigh"] * 0.7
                assert abs(J["knee_near"][1] - J["hip"][1]) < P["thigh"] * 0.45


def test_side_walk_plants_the_foot():
    from tvtoon import characters as CH, puppet as PP, profile as PR
    pp = PP.Puppet(CH.get("abhishek"))
    P = pp.P
    S = P["leg"] * 0.85
    xs = []
    for k in range(6):                                                   # inside the stance of the near foot
        ph = 0.05 + k * 0.06
        body_x = ph * S                                                  # the body moves one cycle length per cycle
        J = PR.solve(pp, _side_state("walk", walk={"phase": ph, "S": S, "duty": 0.62, "d": 1, "run": False}))
        xs.append(body_x + J["ankle_near"][0])
    assert max(xs) - min(xs) < P["leg"] * 0.03                           # no sliding
    J = PR.solve(pp, _side_state("walk", walk={"phase": 0.0, "S": S, "duty": 0.62, "d": 1, "run": False}))
    assert J["knee_near"][0] > J["hip"][0] - 1                           # knees bend forward


def test_walker_and_cyclist_turn_to_the_side_view():
    from tvtoon import scene as SC
    sc = SC.Scene({"location": "village_road", "size": [320, 180],
                   "cast": [{"id": "abhishek", "x": 600}, {"id": "sayan", "x": 300}],
                   "vehicles": [{"id": "cyc", "kind": "cycle", "x": 300}],
                   "beats": [{"who": "abhishek", "walk_to": 2400}, {"who": "sayan", "ride": "cyc", "with_prev": True},
                             {"vehicle": "cyc", "drive_to": 2500, "sec": 4.0, "with_prev": True}]})
    side = None
    for f in range(0, 60):
        st, x = sc.perf["abhishek"].state(f / 24.0, sc)
        side = st.get("side")
    assert side and side["mode"] == "walk" and side["d"] == 1.0
    st, x = sc.perf["sayan"].state(2.0, sc)
    assert st["side"]["mode"] == "pedal"
    rg = st["side"]["rig"]
    assert rg["bars"] is not None and len(rg["feet"]) == 2 and rg["hip"][1] < 0
    # the pedals turn: the feet change place over time
    st2, _ = sc.perf["sayan"].state(2.3, sc)
    assert st2["side"]["rig"]["feet"][0] != rg["feet"][0]
    assert abs(sc.perf["sayan"].x_at(2.0) - sc.vehicle_seat_x("cyc", 0, 2.0)) < 1e-6   # the camera finds the rider


def test_look_back_and_face_to_face():
    from tvtoon import scene as SC
    sc = SC.Scene({"location": "train_inside", "size": [320, 180],
                   "cast": [{"id": "abhishek", "x": 1250}, {"id": "riya", "x": 1950}],
                   "beats": [{"who": "abhishek", "sit": True, "prop": False, "already": True, "side": True},
                             {"who": "riya", "sit": True, "prop": False, "already": True, "side": True, "with_prev": True},
                             {"who": "riya", "look_back": 2.0}]})
    for f in range(0, 30):
        a, _ = sc.perf["abhishek"].state(f / 24.0, sc)
        b, _ = sc.perf["riya"].state(f / 24.0, sc)
    assert a["side"]["d"] == 1.0 and b["side"]["d"] == -1.0               # they face each other
    assert a["side"]["mode"] == "sit" and b["side"]["mode"] == "sit"
    b, _ = sc.perf["riya"].state(1.5, sc)
    assert b["side"]["head_back"] > 0.5                                   # she looks back over her shoulder


def test_passengers_are_seen_in_bus_windows_and_in_the_toto():
    from tvtoon import scene as SC
    spec = {"location": "city_street", "size": [480, 270], "world": {"hours": [[0, 21.0]]},
            "cast": [{"id": "parul", "x": 900}], "vehicles": [{"id": "bus", "kind": "bus", "x": 900}],
            "beats": [{"who": "parul", "ride": "bus", "seat": 2}, {"pause": 1.0, "shot": {"type": "track", "who": "bus"}}]}
    with_p = SC.Scene(spec).render_frame(1.0).astype(int)
    empty = SC.Scene(dict(spec, cast=[], beats=[{"pause": 1.0, "shot": {"type": "track", "who": "bus"}}])).render_frame(1.0).astype(int)
    assert (abs(with_p - empty).sum(axis=2) > 60).mean() > 0.003         # a face in a window
    sc = SC.Scene({"location": "village_road", "size": [320, 180],
                   "cast": [{"id": "ramu_chowkidar", "x": 0}, {"id": "riya", "x": 0}], "vehicles": [{"id": "t", "kind": "toto", "x": 0}],
                   "beats": [{"who": "ramu_chowkidar", "ride": "t", "seat": 0}, {"who": "riya", "ride": "t", "seat": 1, "with_prev": True},
                             {"vehicle": "t", "drive_to": 3000, "sec": "end", "background": True}, {"pause": 3.0}]})
    v = sc.vehicles["t"]
    assert v.moves[-1][1] >= sc.duration - 0.5                           # the drive lasts the whole talk
    st, _ = sc.perf["riya"].state(1.0, sc)
    assert st["side"]["mode"] == "ride" and st["side"]["rig"]["bars"] is None   # a passenger: hands on the lap


def test_story_travel_places_and_night_stays_night():
    from tvtoon import story as S
    assert S.place_of("A crowded night train compartment") == "train_inside"
    assert S.place_of("inside the bus to Barasat") == "bus_inside"
    assert S.place_of("on the tram through Kolkata") == "tram_inside"
    assert S.place_of("in a toto on the village road") == "ride"
    assert S.place_of("autumn evening by the pond") == "pukur_ghat"
    story = {"title": "night", "logline": "one night on the road", "characters": [
        {"name": "a", "gender": "male", "age": "adult"}, {"name": "b", "gender": "female", "age": "adult"}],
        "scenes": [{"place": "in a toto on the village road", "lines": [{"speaker": "a", "text": "চলো।"}, {"speaker": "b", "text": "হ্যাঁ।"}]},
                   {"place": "the train compartment", "lines": [{"speaker": "a", "text": "কে?"}, {"speaker": "b", "text": "আমি।"}]},
                   {"place": "a field", "lines": [{"speaker": "a", "text": "দেখো।"}]}]}
    ep = S.episode_from_story(story)
    s1, s2, s3 = ep["scenes"]
    assert s1["location"] == "village_road" and s1["vehicles"][0]["kind"] == "toto"
    assert any(b.get("ride") == "ride" for b in s1["beats"])
    assert s2["location"] == "train_inside" and all(b.get("side") for b in s2["beats"] if b.get("sit"))
    assert all(s["world"]["hours"][0][1] > 20 for s in (s1, s2, s3))     # a night story: every scene is night


def test_wheels_and_pedals_turn_forward_and_feet_reach_the_pedals():
    from tvtoon import scene as SC, vehicles as V, profile as PR
    for xb in (2000, -2000):                                              # going right or left
        v = V.Vehicle("c", "cycle", 0)
        v.moves = [(0, 4, 0, xb)]
        a = [v.crank_angle(t, 0.6) for t in (1.0, 1.2, 1.4)]
        assert a[0] < a[1] < a[2]                                         # forward in the rider's own frame
    for cid in ("sayan", "abhishek", "kishori"):                          # a child gets a cycle that fits
        sc = SC.Scene({"location": "village_road", "size": [320, 180], "cast": [{"id": cid, "x": 300}],
                       "vehicles": [{"id": "c", "kind": "cycle", "x": 300}],
                       "beats": [{"who": cid, "ride": "c"}, {"vehicle": "c", "drive_to": 2500, "sec": 4.0}]})
        for f in range(14, 90, 7):
            st, _ = sc.perf[cid].state(f / 24.0, sc)
            J = PR.solve(sc.puppets[cid], st)
            want = st["side"]["rig"]["feet"]
            fl, fh = J["fl"], sc.puppets[cid].P["foot_h"]
            for side, p in zip(("near", "far"), want):
                tgt = (p[0] - fl * 0.25, p[1] - fh * 0.9)
                assert abs(J["ankle_" + side][0] - tgt[0]) + abs(J["ankle_" + side][1] - tgt[1]) < 6.0, (cid, f)


def test_side_sitters_get_a_real_seat_and_voice_rule():
    from tvtoon import scene as SC, voices as VO
    sc = SC.Scene({"location": "train_inside", "size": [480, 270],
                   "cast": [{"id": "abhishek", "x": 1250}, {"id": "riya", "x": 1950}],
                   "beats": [{"who": "abhishek", "sit": True, "prop": False, "already": True, "side": True},
                             {"who": "riya", "sit": True, "prop": False, "already": True, "side": True, "with_prev": True},
                             {"pause": 1.0}]})
    assert sum(1 for p in sc.props if p["type"] == "side_seat") == 2
    old = {k: os.environ.pop(k, None) for k in ("TVTOON_VOICE", "GEMINI_TTS_KEY")}
    try:
        os.environ["GEMINI_TTS_KEY"] = "x"
        assert VO.engine() == "gemini"                                    # the normal story mode: Gemini
        os.environ["TVTOON_VOICE"] = "chirp"
        assert VO.engine() == "chirp"                                     # tests: Chirp only
    finally:
        for k, v in old.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    wf = open(os.path.join(ROOT, ".github", "workflows", "tv-cartoon-sample.yml"), encoding="utf-8").read()
    assert "story_test" in wf and "secrets.GEMINI_TTS_KEY" in wf and "secrets.GOOGLE_TTS_KEY" in wf


def test_ghost_comes_disguised_and_changes_in_the_reveal_scene():
    from tvtoon import story as S, scene as SC, characters as CH
    h = CH.get("petni__human")
    assert h.get("ghost") is None and not h["face"].get("ghost_eyes") and h["colours"]["skin"] != CH.get("petni")["colours"]["skin"]
    story = {"title": "night", "characters": [{"name": "a", "gender": "male", "age": "adult"},
                                               {"name": "g", "gender": "female", "age": "young", "kind": "ghost"}],
             "ghost_reveal": {"g": 2},
             "scenes": [{"place": "village road at night", "lines": [{"speaker": "a", "text": "কে?"}, {"speaker": "g", "text": "আমি।"}]},
                        {"place": "an old room", "lines": [{"speaker": "a", "text": "তুমি কে?"}, {"speaker": "g", "text": "বলছি।"},
                                                           {"speaker": "g", "text": "আমি মরে গেছি!", "emotion": "eerie"}]},
                        {"place": "the pond", "lines": [{"speaker": "g", "text": "হি হি!"}]}]}
    ep = S.episode_from_story(story)
    s1, s2, s3 = ep["scenes"]
    g = ep["cast"]["g"]["actor"]
    assert [c for c in s1["cast"] if c["id"] == g][0].get("disguise")          # scene 1: an ordinary girl
    assert [c for c in s2["cast"] if c["id"] == g][0].get("disguise")
    ib = [i for i, b in enumerate(s2["beats"]) if b.get("transform")]
    assert len(ib) == 1 and s2["beats"][ib[0] + 1].get("say") == "আমি মরে গেছি!"   # the change before her last line
    assert not [c for c in s3["cast"] if c["id"] == g][0].get("disguise")      # afterwards: the ghost
    sc = SC.Scene(dict(s2, size=[320, 180]))
    pf = sc.perf[g]
    t0 = sc.transforms[0][0]
    pf.state(t0 - 0.2, sc)
    assert pf.pp.spec.get("ghost") is None                                   # still the girl
    st, _ = pf.state(t0 + 2.5, sc)
    assert pf.pp.spec.get("ghost") is not None and st["float_y"] > 0         # the ghost, floating
    other = [c for c in sc.order if c != g][0]
    assert sc.perf[other].emotion(t0 + 1.5) == "scared"
    assert sc.world.lamp_off <= t0 + 1.0                                     # the lantern goes out


def test_bot_cartoon_follows_the_bots_own_line_timing(tmp_path):
    import wave
    from tvtoon import bot as B, scene as SC, production as PRD
    story = {"title": "t", "characters": [{"name": "Rana", "gender": "male", "age": "adult"},
                                          {"name": "Chhaya", "gender": "female", "age": "young", "kind": "ghost"}],
             "ghost_reveal": {"Chhaya": 1},
             "scenes": [{"place": "an old room at night", "lines": [
                 {"speaker": "narrator", "text": "রাত গভীর।"}, {"speaker": "Rana", "text": "কে ওখানে?", "emotion": "scared"},
                 {"speaker": "Chhaya", "text": "আমি..."}, {"speaker": "Chhaya", "text": "আমি মরে গেছি!", "emotion": "eerie"}]}]}
    ep = B.plan(story)
    lines = story["scenes"][0]["lines"]
    subs = [(0.4, 1.2, True, "রাত গভীর।"), (2.0, 1.0, False, "কে ওখানে?"), (3.5, 1.0, False, "আমি..."), (7.0, 1.4, False, "আমি মরে গেছি!")]
    wavs = []
    for k, (st, du, _n, _t) in enumerate(subs):
        p = str(tmp_path / f"l{k}.wav")
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes((np.sin(np.arange(int(16000 * du)) * 0.05) * 8000).astype(np.int16).tobytes())
        wavs.append(p)
    spec = B.part_spec(ep, 0, lines, subs, wavs, 9.5, 320, 180, 25)
    assert spec["subtitles"] is False and spec["size"] == [320, 180]
    sc = SC.Scene(spec)
    starts = [round(ln["t0"], 2) for ln in sc.lines]
    assert starts == [0.4, 2.0, 3.5, 7.0]                                # exactly when the bot's sound says them
    tf = sc.transforms[0]
    assert tf[0] <= 7.0 - 1.8 and tf[1] <= 7.0 + 0.05                    # the change is over before she speaks
    assert all(ln.get("voice") == "given" for ln in sc.lines)            # no voice is generated here
    ap = PRD.approvals()
    assert PRD.approved("petni") and PRD.approved("some_new_character") and ap["_all"]["status"] == "USER_APPROVED"
    wf = open(os.path.join(ROOT, ".github", "workflows", "horror-story.yml"), encoding="utf-8").read()
    assert "|| 'tvtoon' }}" in wf and "pycairo" in wf                    # production makes the cartoon by default
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert 'env("ANIM_MODE") == "tvtoon"' in src and "made the classic way" in src


def test_places_change_with_the_story_many_rooms_and_the_boat():
    from tvtoon import story as S, locations as L, qa_motion as Q
    cases = {"Dilapidated quarter kitchen, night, glowing embers of wood stove": ("ghar", "kitchen"),
             "Sambhunath Pandit Hospital ward, Kolkata, twilight": ("ghar", "hospital"),
             "Kolkata radio station studio, midnight": ("ghar", "studio"),
             "Inside the grand stone hall of the palace, dusk": ("ghar", "hall"),
             "Hallway outside the bedchamber, early morning": ("ghar", "corridor"),
             "Damp tool shed adjoining quarter, night": ("ghar", "shed"),
             "Kolkata apartment, night, dim red light": ("ghar", "flat"),
             "Kolkata study room, midnight, dim amber table lamp": ("ghar", "office"),
             "boat bilge under floorboards, damp mud smell": ("ghar", "hold"),
             "inside the cramped dark palanquin": ("ghar", "palki"),
             "River boat deck under heavy wooden canopy, roaring river": ("boat", None),
             "Rangtong railway cutting, night, thick mountain fog": ("mountain", None),
             "Railway station waiting room at midnight": ("station", None)}
    for text, (loc, kind) in cases.items():
        assert S.place_of(text) == loc, text
        if kind:
            assert S.room_kind(text) == kind, text
    cam = (1600.0, 500.0, 320 / 1920)
    frames = {}
    for k in ("bedroom", "kitchen", "hall", "hospital", "office", "studio", "corridor", "shed", "flat", "hold", "palki"):
        w = L.make("ghar", {"kind": k, "text": k, "hours": [[0, 20.0]]})
        frames[k] = Q._world_frame(w, 320, 180, cam, 1.0).astype(int)
    ks = list(frames)
    for i in range(len(ks)):                                             # every room really looks different
        for j in range(i + 1, len(ks)):
            assert abs(frames[ks[i]] - frames[ks[j]]).mean() > 4, (ks[i], ks[j])
    b = L.make("boat", {"storm": 1.0, "palki": True})
    a1, a2 = Q._world_frame(b, 320, 180, cam, 0.5), Q._world_frame(b, 320, 180, cam, 1.5)
    assert abs(a1.astype(int) - a2.astype(int)).mean() > 0.5 and b.shake(0.7) != (0.0, 0.0)   # waves move, it rocks
    ep = S.episode_from_story({"title": "x", "characters": [{"name": "a", "gender": "male"}],
                               "scenes": [{"place": "Inside a train compartment, heavy rain outside", "lines": [{"speaker": "a", "text": "হুঁ।"}]},
                                          {"place": "inside the dark palanquin", "lines": [{"speaker": "a", "text": "কে?"}]}]})
    assert not ep["scenes"][0]["world"].get("rain")                       # no rain falls inside
    assert any(b_.get("sit") for b_ in ep["scenes"][1]["beats"])          # in a palanquin one sits


def test_studio_story_in_episode_out(tmp_path, monkeypatch):
    """the multi-agent studio end to end on a small story (small picture, offline voice stand-in)"""
    from tvtoon import studio as ST, voices as VO
    monkeypatch.setattr(VO, "line", _fake_voice(str(tmp_path)))
    monkeypatch.setenv("STUDIO_GEMINI", "0")
    story = ("সন্ধের হাট\n\nসন্ধেবেলা গ্রামের হাটে খুব ভিড়। দোকানে আলো জ্বলছে।\n"
             "রিনা: দাদা, এই আলুর দাম কত?\nদোকানদার কানুদা: কুড়ি টাকা কিলো দিদি!\n\n"
             "রাতে রিনা বাড়ির রান্নাঘরে উনুনে ভাত চাপাল।\nরিনা: আজ হাটে খুব মজা হল।\n")
    out = str(tmp_path / "episode_001")
    assert ST.produce(story, out, voice="gemini", preview=True, log=lambda *a: None)
    ep = ST.Episode(out, {})
    for f in ("final_episode.mp4", "screenplay.md", "scene_breakdown.json", "production_report.md", "qc_report.md",
              "episode_state.json", "casting.json", "locations.json", "voice_map.json"):
        assert os.path.exists(ep.p(f)), f
    st = json.load(open(ep.p("episode_state.json"), encoding="utf-8"))
    assert all(st["stages"][c.id]["status"] == "done" for c in ST.PIPELINE)          # every agent ran and checked itself
    locs = ep.read("locations.json")
    assert [o["location"] for o in locs] == ["market", "ghar"] and locs[1]["room"] == "kitchen"   # the story's own places
    cast = ep.read("casting.json")["cast"]
    assert set(cast) == {"রিনা", "দোকানদার কানুদা"}
    qc = ep.read("qc_report.json")
    assert qc["pass"], [c for c in qc["checks"] if not c["pass"]]
    assert len(os.listdir(ep.p("audio"))) == 5                                        # every line (2 narration + 3) once
    # resume: nothing is made again when nothing changed
    msgs = []
    assert ST.produce(story, out, voice="gemini", preview=True, log=msgs.append)
    assert sum("kept" in m for m in msgs) >= len(ST.PIPELINE)


def test_no_simple_motion_before_four_hours():
    """the owner (23 Nov 2026): the bot may fall back to the simpler motion for lack of time only after the run has
    gone 4 hours (or when GitHub's 6-hour limit is really near) - never because the publish time is close"""
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    body = src.split("def render_clips(jobs):")[1].split("\ndef ")[0]
    assert 'FULL_MOTION_MINUTES") or 240' in body and "ran >= full_for" in body
    head = body.split("workers =")[0]
    assert head.count('os.environ["SIMPLE_MOTION"] = "1"') == 1


# ----------------------------------------------------------------- 23 Nov 2026: the story moves the characters
def test_actions_read_the_story_in_three_languages():
    from tvtoon import actions as AC
    acts = lambda t, sp=False: [a for a, _ in AC.cues(t, speech=sp)]
    assert acts("গোপাল দৌড়ে রাজার কাছে এল।")[:1] == ["run"]
    assert "run_away" in acts("The fox ran away into the forest.")
    assert acts("He arranged the range randomly.") == []          # 'ran' is not 'range'
    assert acts("बच्चे नाचने लगे और ताली बजाई") == ["dance", "clap"]
    assert acts("সে হাসপাতালে গেল") == []                           # hospital is not laughing
    assert acts("Don't be afraid", True) == []
    assert acts("আমি দৌড়ে যাব!", True) == []                       # speech: saying is not doing
    assert "point" in acts("ওই দেখো!", True)
    assert AC.orders("हाँ, ठीक है। बैठो!") == ["sit"]


def test_story_actions_become_movements_in_the_scene():
    from tvtoon import kids as K
    story = {"title": "t", "characters": [{"name": "Gopal", "gender": "male"}, {"name": "Raja", "gender": "male"},
                                          {"name": "Monkey", "name_local": "বাঁদর", "kind": "animal", "look": "brown monkey"}],
             "scenes": [{"place": "the royal court (darbar)", "lines": [
                 {"speaker": "narrator", "text": "গোপাল দৌড়ে রাজসভায় এল।"},
                 {"speaker": "Gopal", "text": "প্রণাম মহারাজ!"},
                 {"speaker": "Raja", "text": "এসো গোপাল, বসো।", "action": "the king points to a seat"},
                 {"speaker": "narrator", "text": "হঠাৎ একটা বাঁদর লাফিয়ে সভায় ঢুকল।"},
                 {"speaker": "narrator", "text": "বাঁদরটা ভয় পেয়ে পালিয়ে গেল।"}]}]}
    sc = K.plan(story, "gopal")["scenes"][0]
    x0 = {c["id"]: c["x"] for c in sc["cast"]}
    beats = [b for b in sc["beats"] if b.get("from_story")]
    monkey = next(c for c in x0 if c.startswith("ka_"))
    assert x0["gopal"] < 300 and x0[monkey] < 0                        # both wait off screen: they COME IN
    assert any(b.get("who") == "gopal" and b.get("gait") == "run" for b in beats)
    assert any(b.get("who") == "gopal" and b.get("sit") for b in beats)
    assert any(b.get("who") == monkey and b.get("act") == "jump" for b in beats)
    assert any(b.get("who") == monkey and b.get("gait") == "run" and b["walk_to"] < -500 for b in beats)   # runs off
    says = {b["who"]: b for b in sc["beats"] if "say" in b}
    assert says["gopal"]["gesture"] == "namaste" and says["raja"]["gesture"] == "point"


def test_bot_parts_put_the_actions_on_the_bots_own_times():
    from tvtoon import bot, kids as K
    story = {"title": "t2", "characters": [{"name": "Tukai", "gender": "male", "age": "child"}],
             "scenes": [{"place": "village", "lines": [{"speaker": "narrator", "text": "টুকাই লাফিয়ে উঠল আর নাচতে লাগল।"},
                                                       {"speaker": "Tukai", "text": "হ্যাঁ!"}]}]}
    ep = K.plan(story, "")
    spec = bot.part_spec(ep, 0, story["scenes"][0]["lines"], [(0.5, 2.0, True, "x"), (3.0, 1.0, False, "y")], [], 5.0,
                         640, 360, 24)
    acts = [b for b in spec["beats"] if b.get("from_story")]
    assert acts and all("at" in b and b["background"] for b in acts)
    assert {b.get("act") for b in acts} >= {"jump", "dance"}


def test_the_place_is_alive_by_day_and_lonely_at_night():
    from tvtoon import life as LF, scene as SC
    day = {"location": "market", "world": {"hours": [[0, 10.0]]}, "cast": [{"id": "abhishek", "x": 1600}], "beats": []}
    cast, beats = LF.plan(day)
    assert len(cast) >= 4 and all(b.get("life") for b in beats)
    assert not LF.plan(dict(day, location="village_road", look="horror", world={"hours": [[0, 22.0]]}))[0]
    assert not LF.plan(dict(day, location="ghar"))[0]
    sc = SC.Scene({"location": "school", "size": [320, 180], "world": {"hours": [[0, 10.0]]},
                   "cast": [{"id": "abhishek", "x": 1600}], "beats": [{"pause": 1.0}]})
    assert sc.life and not set(sc.life) & set(sc.order)                # passers-by never take the camera
    assert all(s.get("who") not in sc.life for s in sc.shots)


def test_cinematic_look_and_people_face_each_other():
    import numpy as np
    from tvtoon import scene as SC
    spec = {"location": "village_courtyard", "life": False, "size": [320, 180], "world": {"hours": [[0, 11.0]]},
            "cast": [{"id": "abhishek", "x": 1450}, {"id": "parul", "x": 1750}],
            "beats": [{"pause": 0.5}, {"who": "abhishek", "say": "চলো।", "to": "parul"}, {"pause": 1.0}]}
    flat = SC.Scene(dict(spec, look="flat")).render_frame(1.0).astype(int)
    film = SC.Scene(dict(spec, look="horror")).render_frame(1.0).astype(int)
    assert np.abs(flat - film).mean() > 2                              # graded
    assert film[:8, :8].mean() < flat[:8, :8].mean()                   # the vignette darkens the corners
    sc = SC.Scene(spec)
    st_a, _ = sc.perf["abhishek"].state(1.2, sc)
    st_b, _ = sc.perf["parul"].state(1.2, sc)
    assert st_a["turn"] > 0.3 and st_b["turn"] < -0.3                  # turned to each other


def test_night_assets_scout_and_builder(tmp_path, monkeypatch):
    from tvtoon import prep as P, story as STY, characters as CH, kids as K
    monkeypatch.setattr(P, "LIB_FILE", str(tmp_path / "lib.json"))
    monkeypatch.setattr(P, "REPORT_DIR", str(tmp_path / "rep"))
    P._LOADED["mtime"] = None
    men = [{"name": f"Man{k}", "gender": "male", "age": "adult"} for k in range(5)]
    story = {"title": "assets", "characters": men + [
        {"name": "Sadhu Baba", "gender": "male", "age": "old", "look": "a tall sadhu in a saffron robe, white beard"},
        {"name": "Mrs Sen", "gender": "female", "age": "adult", "look": "red saree, glasses, married"}],
        "scenes": [{"place": "under the old well", "lines": [{"speaker": "Sadhu Baba", "text": "কে?"}]}]}
    path, rep = P.make_assets(story, "2026-11-24@14", bot="horror", log=lambda *a: None)
    names = {b["name"] for b in rep["new"]}
    assert "Sadhu Baba" in names and rep["built"] and not rep["failed"]
    lib = P._read_lib()["characters"]
    sadhu = next(r for r in lib.values() if "Sadhu Baba" in r["names"])
    assert sadhu["spec"]["hair"]["style"] == "jata" and "rudraksha" in sadhu["spec"]["accessories"]
    sen = next((r for r in lib.values() if "Mrs Sen" in r["names"]), None)
    if sen:
        assert sen["spec"]["colours"].get("saree") == "#c62828" and "glasses_round" in sen["spec"]["accessories"]
    cast = STY.cast_story(story["characters"])                      # at video time: the very same characters
    assert cast["Sadhu Baba"][0] == next(k for k, r in lib.items() if "Sadhu Baba" in r["names"])
    rep2 = P.StoryScout("horror", log=lambda *a: None).run(story)    # the next night: nothing new any more
    assert not rep2["new"]
    kid = {"title": "k", "characters": [{"name": "Gajraj", "kind": "animal", "look": "big grey elephant"}], "scenes": []}
    _p, rk = P.make_assets(kid, "2026-11-24@07", bot="kids", log=lambda *a: None)
    assert rk["built"] and CH.get(rk["built"][0])["animal"]["species"] == "elephant"
    assert K.kids_cast(kid)["Gajraj"][0] == rk["built"][0]


def test_voice_that_repeats_itself_is_cut():
    import numpy as np
    from tvtoon import voicecheck as VC
    sr = 24000
    rng = np.random.default_rng(1)

    def phrase(seed, n=12):
        r = np.random.default_rng(seed)
        out = []
        for _ in range(n):
            d = r.uniform(0.12, 0.3)
            t = np.arange(int(sr * d)) / sr
            f0, f1 = r.uniform(100, 250), r.uniform(400, 2500)
            out.append(np.sin(np.pi * t / d) ** 0.5 * (np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * f1 * t)) * 0.3)
        return np.concatenate(out) + rng.normal(0, 0.01, sum(len(o) for o in out))
    A, B = phrase(5), phrase(9)
    text = "এক দুই তিন চার পাঁচ ছয় সাত আট নয় দশ এগারো বারো তেরো"
    same, note = VC.fix_repeats(np.concatenate([A, B]), sr, text)
    assert note == "" and len(same) == len(A) + len(B)
    cut, note = VC.fix_repeats(np.concatenate([A, B, A, B]), sr, text)
    assert note and abs(len(cut) - (len(A) + len(B))) < sr * 0.3
    cut3, note3 = VC.fix_repeats(np.concatenate([A, A, A]), sr, "এক দুই তিন চার পাঁচ ছয় সাত আট")
    assert note3 and len(cut3) < len(A) * 1.2


def test_hands_have_fingers_drawn():
    import numpy as np
    from tvtoon import puppet as PP, characters as CH
    pp = PP.Puppet(CH.get("abhishek"))
    for shape in ("open", "point", "fist", "relax"):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
        ctx = cairo.Context(surf)
        ctx.translate(100, 60)
        ctx.scale(2.5, 2.5)
        PP.hand_shape(ctx, pp.P, shape, 1)
        ctx.set_source_rgb(0.8, 0.6, 0.4)
        ctx.fill()
        PP.hand_detail(ctx, pp.P, shape, 1, (0.8, 0.6, 0.4), pp.P["lw"])
        a = np.ndarray((200, 200, 4), np.uint8, surf.get_data())
        assert (a[:, :, 3] > 0).sum() > 500


def test_kids_cast_and_host():
    from tvtoon import kids as K, kidsbot as KB, characters as CH, scene as SC
    assert len(K.KIDS) >= 60
    cast = K.kids_cast({"characters": [{"name": "Krishna"}, {"name": "बीरबल"}, {"name": "Crocodile", "kind": "animal"},
                                       {"name": "Ramu", "gender": "male"}]}, "")
    assert cast["Krishna"][0] == "krishna" and cast["बीरबल"][0] == "birbal"
    assert CH.get(cast["Crocodile"][0])["animal"]["species"] == "crocodile"
    assert K.kids_place("under the big tree").startswith("village courtyard")
    sp = KB.host_spec([{"speaker": "narrator", "text": "নমস্কার!"}], [(0.3, 1.0, True, "নমস্কার!")], [], 2.0, 320, 180, 24)
    sc = SC.Scene(sp)
    assert set(sc.order) == {"lumi_didi", "mithu"} and sc.lines[0]["who"] == "lumi_didi"
