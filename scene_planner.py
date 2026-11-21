"""SCENE PLANNER - the JSON animation timeline every scene is rendered from.

plan = {
  "id", "duration", "environment": {moon, pond, trees, grass, fireflies, falling_leaves, ripples, rain, lightning},
  "characters": [{"id", "design", "x", "ground_y", "facing", "scale", "start_pose"}],
  "props": [{"type": "log"|"lantern", "x", "y"}],
  "dialogue": [{"t0", "t1", "speaker", "listener", "clip", "emotion"}],      # voice timing = lip-sync timing
  "actions": [{"t0", "t1", "who", "type": stand_up|sit_down|turn|walk|look|emotion, ...}],  # blocking
  "camera": [{"t0", "t1", "type": wide|two_shot|ots|close_up|reaction|reveal|follow|pull_out, ...}],
  "sfx": [{"t", "type"}], "figure": {...} (a figure that walks through the background), "transitions"
}
Positions, facing directions, speaker / listener, walking paths, shots, weather, light and sound times are all
decided here BEFORE anything is drawn - nothing is placed at random while rendering.
"""
import json

import numpy as np

from animation_renderer import RUN_SPEED, STRIDE, WALK_SPEED, travel_time


def pond_test_plan(clips):
    """the 60-second test: two men talk by a village pond at night; one hears something and looks back; a dark
    figure crosses the far bank and vanishes behind a tree; the other stands up and walks away, the camera follows.
    clips: {name: (path, seconds)} of the real voice clips."""
    A, B = "haren", "bishu"
    t = {}
    cur = 6.0
    order = [("c1", A, B, "normal"), ("c2", B, A, "normal"), ("c3", A, B, "normal")]
    dia = []
    for name, spk, lis, emo in order:
        d = clips[name][1]
        dia.append({"t0": round(cur, 2), "t1": round(cur + d, 2), "speaker": spk, "listener": lis, "clip": name, "emotion": emo})
        t[name] = (cur, cur + d)
        cur += d + 0.45
    c3_end = t["c3"][1]
    turn0 = c3_end + 0.2
    reveal0, reveal1 = turn0 + 2.6, turn0 + 9.6
    c4 = (reveal1 + 0.4, reveal1 + 0.4 + clips["c4"][1])
    dia.append({"t0": round(c4[0], 2), "t1": round(c4[1], 2), "speaker": B, "listener": A, "clip": "c4", "emotion": "scared"})
    c5 = (c4[1] + 0.4, c4[1] + 0.4 + clips["c5"][1])
    dia.append({"t0": round(c5[0], 2), "t1": round(c5[1], 2), "speaker": A, "listener": B, "clip": "c5", "emotion": "normal"})
    stand0 = c5[1] - 1.2
    turnA = stand0 + 1.8
    walk0 = turnA + 0.8
    walk_t = travel_time(790 - (-220))                     # a normal walk (~1.3 m/s) - never slow motion
    end = max(60.0, walk0 + walk_t + 1.8)
    fig0 = reveal0 + 1.0
    fig1 = fig0 + travel_time(1760 - 1398, scale=0.42)
    plan = {
        "id": "pond_test", "duration": round(end, 2),
        "environment": {"moon": (1430, 175), "pond": (1110, 720, 560, 128),
                        "trees": [{"x": 250, "y": 960, "h": 760, "depth": 5, "seed": 3},
                                  {"x": 1760, "y": 900, "h": 640, "depth": 5, "seed": 11},
                                  {"x": 1395, "y": 586, "h": 250, "depth": 4, "seed": 21, "scale": 0.5}],
                        "grass": 420, "bank_grass": 260, "fireflies": 18, "falling_leaves": 10, "clouds": 3,
                        "ripples": [(round(t["c3"][1] - 1.2, 2), 900, 700)], "rain": 0.0, "lightning": []},
        "characters": [{"id": A, "design": "old_man", "x": 790, "ground_y": 935, "facing": 1.0, "scale": 1.0, "start_pose": "sit"},
                       {"id": B, "design": "man", "x": 1075, "ground_y": 935, "facing": -1.0, "scale": 1.0, "start_pose": "sit"}],
        "props": [{"type": "log", "x": 790, "y": 935}, {"type": "log", "x": 1075, "y": 935}, {"type": "lantern", "x": 932, "y": 942}],
        "dialogue": dia,
        "actions": [
            {"t0": turn0, "t1": reveal1, "who": B, "type": "look", "yaw": 1.0, "target": "figure"},      # holds while he looks
            {"t0": turn0, "t1": c4[1], "who": B, "type": "emotion", "brows": "fear", "pose": "sit_fear"},
            {"t0": turn0 + 0.4, "t1": reveal1, "who": A, "type": "look", "yaw": 0.6, "target": "figure"},
            {"t0": turn0 + 0.4, "t1": reveal1, "who": A, "type": "emotion", "brows": "surprise", "pose": "sit"},
            {"t0": reveal1, "t1": walk0, "who": B, "type": "look", "yaw": -1.0, "target": A},
            {"t0": reveal1, "t1": stand0, "who": A, "type": "look", "yaw": 1.0, "target": B},
            {"t0": stand0, "t1": stand0 + 1.6, "who": A, "type": "stand_up"},
            {"t0": turnA, "t1": turnA + 0.8, "who": A, "type": "turn", "to": -1.0},
            {"t0": walk0, "t1": walk0 + walk_t, "who": A, "type": "walk", "to_x": -220},
            {"t0": walk0, "t1": end, "who": B, "type": "look", "yaw": -1.0, "target": A},
        ],
        "figure": {"design": "shadow", "scale": 0.42, "ground_y": 584, "t0": fig0, "t1": fig1,
                   "x0": 1760, "x1": 1398, "behind_tree": 2},
        "camera": [
            {"t0": 0.0, "t1": 6.0, "type": "wide", "z0": 1.0, "z1": 1.12, "cx": 1000, "cy": 600},
            {"t0": 6.0, "t1": t["c1"][0] + 2.6, "type": "two_shot", "a": A, "b": B, "z": 1.85, "push": 0.05},
            {"t0": t["c1"][0] + 2.6, "t1": t["c2"][0] - 0.2, "type": "ots", "speaker": A, "listener": B, "z": 3.0},
            {"t0": t["c2"][0] - 0.2, "t1": t["c3"][0] - 0.2, "type": "ots", "speaker": B, "listener": A, "z": 3.0},
            {"t0": t["c3"][0] - 0.2, "t1": turn0, "type": "close_up", "who": A, "push": 0.08},
            {"t0": turn0, "t1": reveal0, "type": "reaction", "who": B, "dutch": -5.0, "dutch_grow": True, "push": 0.1, "shake": 1.5},
            {"t0": reveal0, "t1": reveal1, "type": "reveal", "from": "head:" + B, "to": (1440, 560), "z0": 2.0, "z1": 2.6},
            {"t0": reveal1, "t1": c5[0] - 0.1, "type": "two_shot", "a": A, "b": B, "z": 1.9, "push": 0.06},
            {"t0": c5[0] - 0.1, "t1": stand0 + 0.2, "type": "close_up", "who": A, "push": 0.05},
            {"t0": stand0 + 0.2, "t1": walk0, "type": "medium", "a": A, "z": 1.45},
            {"t0": walk0, "t1": walk0 + walk_t * 0.6, "type": "follow", "who": A, "z": 1.7, "lead": -140},
            {"t0": walk0 + walk_t * 0.6, "t1": end, "type": "pull_out", "z0": 1.4, "z1": 1.0, "cx": 700, "cy0": 640, "cy1": 560},
        ],
        "sfx": [{"t": t["c3"][1] - 1.2, "type": "plop"}, {"t": reveal0, "t1": reveal1, "type": "heartbeat"},
                {"t": walk0, "t1": walk0 + walk_t, "type": "footsteps", "step": STRIDE["walk"] / WALK_SPEED}],
        "transitions": {"fade_in": 0.8, "fade_out": 1.2},
    }
    return plan


def save(plan, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)


# =========================================================================== V1.1: the plan FROM THE STORY
BROWS = {"scared": "fear", "sad": "sad", "angry": "angry", "surprised": "surprise"}
STATE_OPS = ("stiff", "tremble", "swing_lantern", "hold_lantern", "stare")


def plan_from_story(scene):
    """scene = {"id", "location", "weather", "duration", "lead_in",
                "characters": [{"id", "design", "name"}],
                "lines": [{"i", "speaker" (id or "narrator"), "listener", "t0", "t1", "clip", "clip_t0", "emotion"}],
                "ops": the Match assistant's ops [{"line", "op", "who", "target", "ongoing"}]}
    Everything placed here comes from the story lines + the assistants; returns (plan, reactions) - the reactions
    (heads turning to a knock) are reported by the Match assistant as REACTION, never hidden."""
    import location_library as L
    loc = scene["location"]
    info = L.LOCATIONS[loc]
    spots = dict(info["spots"])
    dur = float(scene["duration"])
    lines = sorted(scene["lines"], key=lambda l: l["t0"])
    by_i = {l["i"]: l for l in lines}
    ops = scene.get("ops", [])
    ids = [c["id"] for c in scene["characters"]]
    # who is in the scene: speakers, listeners and anybody an op names (order of first appearance)
    order = []
    for l in lines:
        for c in (l.get("speaker"), l.get("listener")):
            if c in ids and c not in order:
                order.append(c)
    for o in ops:
        if o.get("who") in ids and o["who"] not in order:
            order.append(o["who"])
    w = scene.get("weather") or {}
    light_t = []
    if w.get("lightning"):
        light_t = [round(float(x), 2) for x in np.arange(scene.get("lead_in", 2.0) + 1.0, dur - 1.0, 9.0)]
    for o in ops:                                          # lightning the story names: at that line
        if o["op"] == "lightning":
            light_t.append(round(by_i[o["line"]]["t0"] + 0.3, 2))
    env = L.spec_for(loc, {"rain": w.get("rain", 0.0) or (0.8 if any(o["op"] == "rain" for o in ops) else 0.0),
                           "lightning": sorted(set(light_t))})
    # ------------------------------------------------ blocking: places, facing, sitting
    slot = ["a", "b", "c"]
    chars, props, actions, door, sfx, reactions = [], [], [], [], [], []
    standing_ops = {"stiff", "walk", "run", "swing_lantern", "hold_lantern", "knock", "enter", "exit", "pose_stand"}
    pos = {}
    for k, cid in enumerate(order[:3]):
        x, gy = spots[slot[k]]
        my = [o for o in ops if o.get("who") == cid]
        sit = info["seat"] is not None and not any(o["op"] in standing_ops for o in my) or any(o["op"] == "pose_sit" for o in my)
        cdef = next(c for c in scene["characters"] if c["id"] == cid)
        chars.append({"id": cid, "design": cdef["design"], "x": x, "ground_y": gy, "facing": 1.0 if k == 0 else -1.0,
                      "scale": 1.0, "start_pose": "sit" if sit else "stand"})
        pos[cid] = x
        if sit and info["seat"] in ("log", "stool"):
            props.append({"type": info["seat"], "x": x, "y": gy})
    if len(chars) == 3:                                    # the third person faces the other two
        chars[2]["facing"] = 1.0 if chars[2]["x"] < chars[0]["x"] else -1.0
    cd = {c["id"]: c for c in chars}
    facing = {c["id"]: c["facing"] for c in chars}

    def act(**a):
        if a not in actions:                               # the same state named twice is one action
            actions.append(a)
    # ------------------------------------------------ story ops -> timed actions
    for o in sorted(ops, key=lambda o: by_i[o["line"]]["t0"]):
        ln = by_i[o["line"]]
        who = o.get("who")
        t0, t1 = ln["t0"], ln["t1"]
        if o.get("ongoing"):
            t0 = 0.0                                       # the state was already there when the line is spoken
        if o["op"] in STATE_OPS and who in cd:
            act(t0=t0, t1=dur, who=who, type=o["op"])
            if o["op"] == "stiff":
                sfx.append({"t": max(0.5, ln["t0"]), "t1": min(dur, ln["t0"] + 8), "type": "heartbeat"})
        elif o["op"] in ("walk", "run") and who in cd:
            tgt = o.get("target")
            x0 = pos[who]
            to = (pos[tgt] - 170 * (1 if pos[tgt] > x0 else -1)) if tgt in pos else spots["exit_to"][0]
            d_ = travel_time(to - x0, o["op"])
            act(t0=ln["t0"], t1=ln["t0"] + d_, who=who, type=o["op"], to_x=to)
            sfx.append({"t": ln["t0"], "t1": ln["t0"] + d_, "type": "footsteps", "step": STRIDE[o["op"]] / (RUN_SPEED if o["op"] == "run" else WALK_SPEED)})
            pos[who] = to
        elif o["op"] == "enter" and who in cd:
            x_from = spots["enter_from"][0]
            x_to = cd[who]["x"]
            cd[who]["x"] = x_from
            cd[who]["start_pose"] = "stand"
            cd[who]["t_in"] = ln["t0"]
            d_ = travel_time(x_to - x_from)
            act(t0=ln["t0"], t1=ln["t0"] + d_, who=who, type="walk", to_x=x_to, face=cd[who]["facing"])
            if loc == "house_interior":
                door.append({"t0": ln["t0"] - 1.2, "t1": ln["t0"], "type": "open"})
            sfx.append({"t": ln["t0"], "t1": ln["t0"] + d_, "type": "footsteps", "step": STRIDE["walk"] / WALK_SPEED})
        elif o["op"] == "exit" and who in cd:
            to = spots["exit_to"][0]
            d_ = travel_time(to - pos[who])
            act(t0=ln["t0"], t1=ln["t0"] + d_, who=who, type="walk", to_x=to)
            cd[who]["t_out"] = ln["t0"] + d_
            sfx.append({"t": ln["t0"], "t1": ln["t0"] + d_, "type": "footsteps", "step": STRIDE["walk"] / WALK_SPEED})
        elif o["op"] == "knock":
            door.append({"t0": ln["t0"] + 0.4, "t1": ln["t0"] + 1.9, "type": "knock", "n": 3})
            sfx.append({"t": ln["t0"] + 0.4, "type": "knock", "n": 3})
            for cid in cd:                                 # everybody in the room turns to the door
                yaw = -1.0 if spots.get("door") and spots["door"][0] < cd[cid]["x"] else 1.0
                act(t0=ln["t0"] + 0.7, t1=ln["t1"] + 1.2, who=cid, type="look", yaw=yaw, target="door")
                reactions.append({"line": o["line"], "act": "look_at_door", "who": cid,
                                  "why": "দরজায় ধাক্কার শব্দে মাথা ঘুরিয়ে দরজার দিকে তাকায় (গল্পে আলাদা করে বলা নেই - স্বাভাবিক প্রতিক্রিয়া)"})
        elif o["op"] in ("open_door", "close_door"):
            door.append({"t0": ln["t0"] + 0.3, "t1": ln["t0"] + 1.5, "type": "open" if o["op"] == "open_door" else "close"})
            sfx.append({"t": ln["t0"] + 0.3, "type": "creak"})
        elif o["op"] == "sfx_knock":
            sfx.append({"t": ln["t0"] + 0.4, "type": "knock", "n": 3})
        elif o["op"] == "sfx_breath":
            sfx.append({"t": ln["t0"], "t1": ln["t1"] + 2.0, "type": "breath"})
        elif o["op"] in ("stand_up", "sit_down") and who in cd:
            act(t0=ln["t0"], t1=ln["t0"] + 1.5, who=who, type=o["op"])
        elif o["op"] in ("look", "look_back") and who in cd:
            tgt = o.get("target")
            yaw = (1.0 if pos.get(tgt, 0) > pos[who] else -1.0) if tgt in pos else -facing[who]
            act(t0=ln["t0"], t1=ln["t1"] + 1.0, who=who, type=o["op"] if tgt not in pos else "look", yaw=yaw, target=tgt)
        elif o["op"] in ("point", "reach", "hand_to_head", "cower", "nod") and who in cd:
            act(t0=ln["t0"] + 0.2, t1=min(ln["t1"], ln["t0"] + 2.6), who=who, type=o["op"], target=o.get("target"))
        elif o["op"] in ("sad",) and who in cd:
            act(t0=ln["t0"], t1=ln["t1"], who=who, type="sad")
        elif o["op"] == "vanish" and who in cd:
            act(t0=ln["t0"], t1=ln["t0"] + 1.5, who=who, type="vanish")
        elif o["op"] == "lightning":
            sfx.append({"t": ln["t0"] + 0.6, "type": "thunder"})
    for lt in env["lightning"]:
        sfx.append({"t": lt + 0.5, "type": "thunder"})
    # ------------------------------------------------ dialogue: speaker faces the listener, feelings on the face
    dia = []
    for l in lines:
        spk, lis = l.get("speaker"), l.get("listener")
        if spk not in cd:
            continue                                       # the narrator: a voice, no mouth on screen
        dia.append({"t0": l["t0"], "t1": l["t1"], "speaker": spk, "listener": lis if lis in cd else None, "clip": l["clip"],
                    "clip_t0": l.get("clip_t0", 0.0), "emotion": l.get("emotion", "calm")})
        busy = any(a["who"] == spk and a["type"] in ("walk", "run", "stiff") and a["t0"] <= l["t0"] <= a["t1"] for a in actions)
        if lis in pos and not busy:
            want = 1.0 if pos[lis] > pos[spk] else -1.0
            if want != facing[spk]:                         # turn to face the person spoken to
                act(t0=max(0.0, l["t0"] - 0.5), t1=l["t0"] + 0.2, who=spk, type="turn", to=want)
                facing[spk] = want
        b = BROWS.get(l.get("emotion"))
        if b:
            act(t0=l["t0"], t1=l["t1"], who=spk, type="emotion", brows=b,
                pose="sit_fear" if cd[spk]["start_pose"] == "sit" and b == "fear" else None)
            if b == "fear":
                sfx.append({"t": l["t0"], "t1": l["t1"], "type": "heartbeat"})
    # ------------------------------------------------ camera: one shot per line, chosen by what the line is
    cam = []
    lead = min(scene.get("lead_in", 2.0), lines[0]["t0"] if lines else 2.0)
    foc = spots["focus"]
    mid_x = sum(c["x"] for c in chars) / max(1, len(chars))
    cam.append({"t0": 0.0, "t1": max(1.5, lead), "type": "wide", "z0": 1.0, "z1": 1.1, "cx": mid_x, "cy": 600})
    stiff_who = {a["who"] for a in actions if a["type"] == "stiff"}
    k = 0
    for n, l in enumerate(lines):
        s0 = max(cam[-1]["t1"], l["t0"] - 0.15)
        s1 = lines[n + 1]["t0"] - 0.15 if n + 1 < len(lines) else dur
        if s1 - s0 < 0.6:
            cam[-1]["t1"] = s1
            continue
        spk, lis = l.get("speaker"), l.get("listener")
        my_ops = [o for o in ops if o["line"] == l["i"]]
        if spk not in cd:                                  # narration: the place, or the thing it talks about
            if any(o["op"] in ("knock", "open_door", "close_door", "sfx_knock") for o in my_ops) and spots.get("door"):
                cam.append({"t0": s0, "t1": s1, "type": "push_in", "z0": 1.2, "z1": 1.9, "cx": spots["door"][0] + 260,
                            "cy0": 620, "cy1": 600})
            else:
                cam.append({"t0": s0, "t1": s1, "type": "wide", "z0": 1.05, "z1": 1.2, "cx": mid_x, "cy": 600})
            continue
        walking = [a for a in actions if a["who"] == spk and a["type"] in ("walk", "run") and a["t0"] < s1 and a["t1"] > s0]
        scared = l.get("emotion") == "scared"
        if walking:
            cam.append({"t0": s0, "t1": s1, "type": "follow", "who": spk, "z": 1.6, "lead": -120 * facing[spk]})
        elif lis in cd and lis in stiff_who and (s1 - s0) > 2.4:   # the frozen one is what the line is about
            m = s0 + (s1 - s0) * 0.5
            cam.append({"t0": s0, "t1": m, "type": "ots", "speaker": spk, "listener": lis, "z": 2.8, "shake": 1.2 if scared else 0})
            cam.append({"t0": m, "t1": s1, "type": "reaction", "who": lis, "dutch": -4.0, "dutch_grow": True, "push": 0.08})
        elif lis in cd and (s1 - s0) > 5.0:
            m = s0 + (s1 - s0) * 0.5
            cam.append({"t0": s0, "t1": m, "type": "ots", "speaker": spk, "listener": lis, "z": 2.9})
            cam.append({"t0": m, "t1": s1, "type": "close_up", "who": spk, "push": 0.08,
                        "dutch": 4.0 if scared else 0.0, "dutch_grow": scared})
        elif scared:
            cam.append({"t0": s0, "t1": s1, "type": "close_up", "who": spk, "push": 0.1, "dutch": -4.0, "dutch_grow": True, "shake": 1.0})
        elif lis in cd:
            typ = "two_shot" if k % 2 == 0 else "ots"
            cam.append({"t0": s0, "t1": s1, "type": typ, "a": spk, "b": lis, "speaker": spk, "listener": lis,
                        "z": 1.8 if typ == "two_shot" else 2.9, "push": 0.05})
            k += 1
        else:
            cam.append({"t0": s0, "t1": s1, "type": "medium", "a": spk, "z": 1.6})
    cam[-1]["t1"] = dur
    plan = {"id": scene["id"], "location": loc, "duration": round(dur, 2), "environment": env, "spots": spots,
            "characters": chars, "props": props, "dialogue": dia, "actions": actions, "door": door, "camera": cam,
            "sfx": sorted(sfx, key=lambda s: s["t"]), "transitions": {"fade_in": 0.6, "fade_out": 0.8}}
    return plan, reactions
