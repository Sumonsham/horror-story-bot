"""ANIMATION RENDERER - plan (scene_planner) -> video.

Per frame: environment rasters (sky / far land / near land + live pond) through the camera with parallax ->
far-bank figure and far tree -> bank grass -> trees -> props (logs, lantern) -> characters (depth-sorted) -> the
big near tree -> foreground grass -> particles -> fog, mist, light -> grade -> fades.
V1.1: any place of location_library (door, window, street lamp, pyre...), single scene audio (dialogue timed inside
it), and the story ops: run, enter / exit, knock, open / close door, stiff, tremble, hold / swing a lantern, point,
reach, hand to head, cower, sad, stare, nod, vanish; looking BEHIND twists the body and shows the face in profile.
Character state at any time comes from the plan's blocking (actions) + dialogue (speaker lip-sync from the real
voice, listener nods and looks at the speaker) + automatic life (blinks, breathing, small gestures).

Rendering is split into chunks (one per camera shot). A finished chunk is kept (checkpoint): a stopped or failed
run continues from the first missing chunk; a failed chunk is retried once. Resolution and FPS are settings
(16:9 1280x720 / 1920x1080, 9:16 720x1280 / 1080x1920; 24 or 30 fps). CPU only.
"""
import hashlib
import json
import math
import os
import subprocess
import time

import cv2
import numpy as np

import cartoon_rig as rig
import cinematic_camera as cc
import lip_sync
from environment_animation import Environment, wind_at

# real speeds (world px per second at scale 1; a person is ~330 px tall = 1.7 m -> ~195 px per metre)
WALK_SPEED = 250.0          # ~1.3 m/s, ~2.1 steps a second - a normal walk, never slow motion
RUN_SPEED = 580.0           # ~3 m/s
STRIDE = {"walk": 118.0, "run": 190.0}


def travel_time(dist, kind="walk", scale=1.0):
    """how long a walk / run of this distance takes at normal speed"""
    return abs(dist) / ((RUN_SPEED if kind == "run" else WALK_SPEED) * scale)


def _ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


class Scene:
    def __init__(self, plan, clips, fps):
        self.plan, self.fps = plan, fps
        self.env = Environment(plan["environment"])
        self.chars = {}
        for c in plan["characters"]:
            d = c["design"]
            self.chars[c["id"]] = rig.Character(c["id"], dict(rig.DESIGNS[d]) if isinstance(d, str) else dict(d), c.get("scale", 1.0))
        f = plan.get("figure")
        self.figure = rig.Character("figure", dict(rig.DESIGNS[f["design"]]), f["scale"]) if f else None
        self.vis = {}                                      # clip -> per-frame (open, shape)
        for d in plan["dialogue"]:
            if d["clip"] not in self.vis:
                self.vis[d["clip"]] = lip_sync.visemes(clips[d["clip"]][0], fps)
        self.metrics = {"mouth": [], "feet_err": [], "water": [], "trees": [], "frames": 0}
        rng = np.random.default_rng(5)
        self.blinks = {cid: sorted(rng.uniform(0.3, plan["duration"], int(plan["duration"] / 3.2))) for cid in self.chars}
        self.acts = {cid: sorted((a for a in plan["actions"] if a.get("who") == cid), key=lambda a: a["t0"]) for cid in self.chars}
        self.cdef = {c["id"]: c for c in plan["characters"]}
        self._cache = {}

    # -------------------------------------------------------------- where everyone is at time t
    def char_state(self, cid, t):
        key = (cid, round(t, 5))
        if key not in self._cache:
            if len(self._cache) > 400:
                self._cache.clear()
            self._cache[key] = self._state(cid, t)
        return dict(self._cache[key])

    def _state(self, cid, t):
        p = self.plan
        cdef = self.cdef[cid]
        x, gy, facing = cdef["x"], cdef["ground_y"], cdef["facing"]
        pose_name = cdef.get("start_pose", "stand")
        pose = dict(rig.POSES[pose_name])
        sitting = pose_name.startswith("sit")
        yaw = facing
        target = None
        brows = ""
        move = None                                        # (kind, phase)
        looking_back = False
        upper = None
        arm = None                                         # an arm op owns the near arm (no talking gestures then)
        st_extra = {"stiff": False, "stare": False, "lantern": None, "alpha": 1.0, "pitch": None, "jitter": 0.0}
        visible = cdef.get("t_in", -1.0) <= t <= cdef.get("t_out", 1e9)
        for a in self.acts[cid]:
            if t < a["t0"]:
                break
            dur = max(0.01, a["t1"] - a["t0"])
            u = _ease((t - a["t0"]) / dur)
            live = t <= a["t1"]
            typ = a["type"]
            if typ == "stand_up":
                mid = rig.blend(rig.POSES["sit"], rig.POSES["stand"], u)
                mid["torso"] += 28 * math.sin(math.pi * u)          # lean forward while rising (weight shift)
                pose, sitting = mid, u < 1.0
                if u >= 1.0:
                    pose, sitting = dict(rig.POSES["stand"]), False
            elif typ == "sit_down":
                pose = rig.blend(rig.POSES["stand"], rig.POSES["sit"], u)
                sitting = u > 0.5
            elif typ == "turn":
                facing = facing + (a["to"] - facing) * u
                yaw = facing
            elif typ in ("walk", "run"):
                x0 = x
                if live:
                    lin = (t - a["t0"]) / dur
                    x = x0 + (a["to_x"] - x0) * lin
                    stride = STRIDE[typ] * cdef.get("scale", 1.0)  # one step (thigh swing) -> distance: feet never slide
                    move = (typ, abs(x - x0) / stride * math.pi)
                    facing = -1.0 if a["to_x"] < x0 else 1.0
                    yaw = facing
                else:
                    x = a["to_x"]
                    if a.get("face") is not None:
                        facing = yaw = a["face"]
            elif typ in ("look", "look_back"):
                back = t - a["t1"]
                if live or back < 0.5:                     # after the look the head comes back smoothly, never snaps
                    k_ = _ease((t - a["t0"]) / 0.55) * (1 - _ease(back / 0.5) if back > 0 else 1.0)
                    yaw = yaw + (a["yaw"] - yaw) * k_
                    target = a.get("target")
                    if a["yaw"] * facing < 0:              # looking BEHIND, like a real person: hips and legs stay,
                        twist = k_                         # the chest twists ~45 deg, the neck ~90 deg, the eyes the rest
                        upper = math.copysign(max(0.4, abs(facing) * (1 - 0.6 * twist)), facing)
                        looking_back = True
            elif typ == "emotion":
                if live:
                    brows = a.get("brows", "")
                    if a.get("pose") and sitting:
                        fp = dict(rig.POSES[a["pose"]])
                        if looking_back:                   # twisted round: sit upright, no backward bend
                            fp["torso"] = 4
                        pose = rig.blend(pose, fp, _ease((t - a["t0"]) / 0.5))
            elif typ == "stiff" and live:
                if not sitting:
                    pose = rig.blend(pose, rig.POSES["stand_stiff"], _ease((t - a["t0"]) / 0.4))
                st_extra.update(stiff=True, stare=True)
                arm = "stiff"
                brows = brows or "fear"
            elif typ == "tremble" and live:
                st_extra["jitter"] = 2.6
            elif typ == "stare" and live:
                st_extra["stare"] = True
            elif typ in ("hold_lantern", "swing_lantern") and live:
                sw = typ == "swing_lantern"
                if not sitting:
                    hp = dict(rig.POSES["hold_lantern"])
                    if sw:                                 # a signal swing beside the body, not a hand-over
                        hp["uarm_n"] = 18 + 20 * math.sin(t * 3.4)
                        hp["farm_n"] = hp["uarm_n"] + 6
                    pose = rig.blend(pose, hp, _ease((t - a["t0"]) / 0.4))
                st_extra["lantern"] = 1.0 if sw else 0.15
                arm = typ
            elif typ == "knock" and live:
                kp = dict(rig.POSES["knock"])
                kp["farm_n"] += 30 * abs(math.sin(math.pi * (t - a["t0"]) / 0.45))
                pose = rig.blend(pose, kp, _ease((t - a["t0"]) / 0.25))
                arm = "knock"
            elif typ in ("point", "reach", "hand_to_head", "cower") and live:
                name = {"point": "stand_point", "reach": "stand_point", "hand_to_head": "hand_to_head", "cower": "cower"}[typ]
                if sitting and typ in ("point", "reach"):
                    tp = dict(pose, uarm_n=70, farm_n=80)
                else:
                    tp = rig.POSES[name] if not sitting else pose
                pose = rig.blend(pose, tp, _ease((t - a["t0"]) / 0.35) * (1 - _ease((t - a["t1"] + 0.35) / 0.35)))
                arm = typ
                if a.get("target"):
                    target = a["target"]
                if typ == "cower":
                    brows = "fear"
            elif typ == "sad" and live:
                brows = "sad"
                st_extra["pitch"] = 9.0
            elif typ == "nod" and live:
                st_extra["pitch"] = 8 * math.sin(math.pi * ((t - a["t0"]) % 0.7) / 0.7)
            elif typ == "vanish":
                st_extra["alpha"] = max(0.0, 1 - (t - a["t0"]) / dur)
        if looking_back and upper is not None:            # the neck can turn the head only so far from the chest
            yaw = max(upper - 0.95, min(upper + 0.95, yaw))
        if st_extra["jitter"]:
            x += st_extra["jitter"] * math.sin(t * 41) 
        st = {"x": x, "ground_y": gy, "facing": facing, "head_yaw": yaw, "brows": brows, "pose": pose,
              "mouth": (0.0, "rest"), "blink": 0.0, "head_pitch": 0.0, "hand_open": 0.0, "t": t,
              "fingers": {"stiff": "stiff", "swing_lantern": "grip", "hold_lantern": "grip", "knock": "fist", "point": "point",
                          "reach": "open", "hand_to_head": "open", "cower": "spread"}.get(arm) if arm else None}
        if looking_back and upper is not None:
            st["facing_upper"] = upper
        if brows == "fear" and not arm:
            st["fingers"], st["fingers_f"] = "spread", "spread"
        # dialogue: the speaker talks (lip-sync, gestures), the listener listens (nods, looks at the speaker)
        for d in p["dialogue"]:
            if d["t0"] <= t < d["t1"]:
                f = int((t - d["t0"] + d.get("clip_t0", 0.0)) * self.fps)
                vis = self.vis[d["clip"]]
                if d["speaker"] == cid:
                    op, shape = vis[min(max(0, f), len(vis) - 1)]
                    st["mouth"] = (op, shape)
                    st["brows"] = st["brows"] or {"scared": "fear", "angry": "angry", "sad": "sad",
                                                  "surprised": "surprise"}.get(d.get("emotion"), "")
                    if not arm and not st_extra["stiff"] and move is None:
                        g = 0.5 + 0.5 * math.sin(t * 2.3 + (1 if cid > "m" else 0))
                        if sitting and not st["brows"]:
                            pose = rig.blend(pose, rig.POSES["sit_talk"], 0.35 + 0.5 * g)
                            pose["farm_n"] += 25 * op
                            st["hand_open"] = 0.6
                        elif not sitting:
                            pose = rig.blend(pose, rig.POSES["stand_talk"], 0.3 + 0.5 * g)
                            pose["farm_n"] += 20 * op
                            st["hand_open"] = 0.6
                    st["head_pitch"] = 4 * op * math.sin(t * 6)
                    target = target or d.get("listener")
                elif d.get("listener") == cid and not st_extra["stiff"]:
                    if sitting and not st["brows"] and not arm:
                        pose = rig.blend(pose, rig.POSES["sit_listen"], 0.7)
                    beat = (t - d["t0"]) % 2.6
                    st["head_pitch"] = 7 * math.sin(math.pi * beat / 0.6) if beat < 0.6 else 0.0   # a nod now and then
                    target = target or d["speaker"]
        st["pose"] = pose
        if move is not None:
            st["pose"] = (rig.run_pose if move[0] == "run" else rig.walk_pose)(move[1])
            if st_extra["lantern"] is not None:
                st["pose"]["uarm_n"], st["pose"]["farm_n"] = 50, 50
        if st_extra["pitch"] is not None:
            st["head_pitch"] = st_extra["pitch"]
        if not st_extra["stare"]:
            for b0 in self.blinks[cid]:
                if 0 <= t - b0 < 0.16:
                    st["blink"] = math.sin(math.pi * (t - b0) / 0.16)
        if st["brows"] in ("fear", "surprise"):
            st["blink"] = 0.0
        st["target"] = target
        st["lantern"] = st_extra["lantern"]
        st["alpha"] = st_extra["alpha"] if visible else 0.0
        return st

    def head_pos(self, cid, t):
        st = self.char_state(cid, t)
        j = self.chars[cid].joints(dict(st, ground_y=st["ground_y"] + self.chars[cid].foot_floor(st)))
        return j["head"]

    def figure_state(self, t):
        f = self.plan["figure"]
        if not (f["t0"] <= t <= f["t1"] + 1.2):
            return None
        u = min(1.0, (t - f["t0"]) / (f["t1"] - f["t0"]))
        x = f["x0"] + (f["x1"] - f["x0"]) * u
        phase = abs(x - f["x0"]) / (118 * f["scale"]) * math.pi if u < 1 else 0.0
        alpha = 1.0 if t <= f["t1"] else max(0.0, 1 - (t - f["t1"]) / 1.2)
        return {"x": x, "ground_y": f["ground_y"], "facing": -1.0, "head_yaw": -1.0, "pose": rig.walk_pose(phase),
                "mouth": (0, "rest"), "brows": "", "blink": 0, "alpha": alpha}

    def door_state(self, t):
        """knock = the door shakes at every knock; open / close = the panel swings"""
        op, shake = 0.0, 0.0
        for e in self.plan.get("door", []):
            if t < e["t0"]:
                continue
            u = _ease((t - e["t0"]) / max(0.01, e["t1"] - e["t0"]))
            if e["type"] == "open":
                op = u
            elif e["type"] == "close":
                op = 1 - u
            elif e["type"] == "knock" and t <= e["t1"]:
                for k in range(e.get("n", 3)):
                    dt = t - (e["t0"] + k * 0.42)
                    if 0 <= dt < 0.16:
                        shake = 7.0 * (1 - dt / 0.16)
        return {"door_open": op, "door_shake": shake}

    def world(self, t):
        spots = self.plan.get("spots", {})

        def point(name):
            if isinstance(name, str) and name.startswith("head:"):
                return self.head_pos(name[5:], t)
            if isinstance(name, str) and name.startswith("spot:"):
                s = spots.get(name[5:]) or (960, 600)
                return (s[0], s[1] - 260)
            return name
        return {"head": lambda cid: self.head_pos(cid, t),
                "feet": lambda cid: (self.char_state(cid, t)["x"], self.char_state(cid, t)["ground_y"]),
                "point": point}

    # -------------------------------------------------------------- one frame
    def render(self, t, W, H, cam, prev=None):
        p = self.plan
        self._cache.clear()
        shot = next((s for s in p["camera"] if s["t0"] <= t < s["t1"]), p["camera"][-1])
        cx, cy, z, rot = cc.frame_for(shot, self.world(t), t)
        cam.set(cx, cy, z, rot, cc.shake_at(shot, t))
        wind = wind_at(t)
        env = self.env
        frame = env.background(cam, t, wind, None)
        img = np.clip(frame, 0, 255).astype(np.uint8)
        pt = rig.Painter(img, cam, light=0.82)
        far_tree = p["figure"].get("behind_tree") if p.get("figure") else None
        fs = self.figure_state(t) if self.figure else None
        if fs:                                             # the far figure, then the tree it walks behind
            if fs["alpha"] < 1.0:
                layer = img.copy()
                self.figure.draw(rig.Painter(layer, cam, 1.0), fs)
                img[:] = (img * (1 - fs["alpha"]) + layer * fs["alpha"]).astype(np.uint8)
            else:
                self.figure.draw(rig.Painter(img, cam, 1.0), fs)
        env.draw_trees(pt, t, wind, which=[far_tree] if far_tree is not None else None)
        env.draw_bank_grass(pt, t, wind)
        env.draw_trees(pt, t, wind, which=[i for i in range(len(env.trees)) if i not in (0, far_tree)])
        lights = list(env.draw_location(pt, t, wind, self.door_state(t)) or [])
        for pr in p.get("props", []):
            if pr["type"] == "log":
                pt.ellipse((pr["x"], pr["y"] - 34), 60, 34, 0, (36, 52, 70))
                pt.ellipse((pr["x"] + 46, pr["y"] - 34), 14, 30, 0, (70, 96, 120))
            elif pr["type"] == "stool":                    # a low wooden seat (piri / morha)
                pt.poly([(pr["x"] - 52, pr["y"] - 50), (pr["x"] + 52, pr["y"] - 50), (pr["x"] + 44, pr["y"] - 36),
                         (pr["x"] - 44, pr["y"] - 36)], (40, 62, 86))
                for dx in (-38, 38):
                    pt.line((pr["x"] + dx, pr["y"] - 38), (pr["x"] + dx * 1.1, pr["y"]), (30, 46, 64), 9)
            elif pr["type"] == "lantern":
                fl = env.draw_lantern(pt, pr["x"], pr["y"], t)
                lights.append((pr["x"], pr["y"] - 40, 520, (30, 95, 175), 0.62 * fl))
        order = sorted(self.chars, key=lambda c: self.char_state(c, t)["ground_y"])
        for cid in order:
            st = self.char_state(cid, t)
            if st["alpha"] <= 0.01:
                continue
            tgt = st.pop("target", None)
            ch = self.chars[cid]
            if tgt:                                        # the eyes look at the other person / the figure / the door
                hp = self.head_pos(cid, t)
                if tgt == "figure":
                    fsp = self.figure_state(t) or {"x": 1400, "ground_y": 584}
                    tp = (fsp["x"], fsp["ground_y"] - 120)
                elif tgt in self.chars:
                    tp = self.head_pos(tgt, t)
                else:
                    tp = self.world(t)["point"]("spot:" + str(tgt))
                dx, dy = tp[0] - hp[0], tp[1] - hp[1]
                n = math.hypot(dx, dy) or 1
                st["gaze"] = (max(-1, min(1, dx / n * 1.1)), max(-1, min(1, dy / n * 1.4)))
            gy0 = st["ground_y"]
            if st["alpha"] < 0.99:
                layer = img.copy()
                j = ch.draw(rig.Painter(layer, cam, 0.82), st)
                img[:] = (img * (1 - st["alpha"]) + layer * st["alpha"]).astype(np.uint8)
            else:
                j = ch.draw(pt, st)
            if st.get("lantern") is not None:              # a lantern hanging from the near hand (swinging)
                hx, hy = j["hd_n"]
                ang = st["lantern"] * 0.5 * math.sin(t * 3.4 - 0.6) + 0.05 * math.sin(t * 1.3)
                lx, ly = hx + math.sin(ang) * 58 * j["k"], hy + math.cos(ang) * 58 * j["k"] + 10
                pt.line((hx, hy), (lx, ly - 56 * j["k"]), (30, 30, 34), 2)
                fl = env.draw_lantern(pt, lx, ly, t)
                lights.append((lx, ly - 40, 560, (30, 95, 175), 0.66 * fl))
            low = max(j["ft_n"][1], j["ft_f"][1])
            self.metrics["feet_err"].append(abs((low + 4 * j["k"]) - gy0))      # 0 = the foot is on the ground
            speaking = any(d["t0"] <= t < d["t1"] and d["speaker"] == cid for d in p["dialogue"])
            if st["mouth"][0] > 0.3:
                self.metrics["mouth"].append(1 if speaking else -1)           # -1 = a mouth moved without a voice
        env.draw_trees(pt, t, wind, which=[0])
        env.draw_foreground(pt, t, wind)
        env.particles(pt, t, wind)
        f = img.astype("float32")
        f = env.atmosphere(f, cam, t, wind, lights)
        vy = np.linspace(-1, 1, H)[:, None]
        vx = np.linspace(-1, 1, W)[None, :]
        f *= (1 - 0.45 * ((vx ** 2 + vy ** 2) / 2) ** 1.3)[..., None]
        f = f * np.array([1.06, 0.98, 0.9], "float32")      # moonlight grade (BGR: cool)
        tr = p.get("transitions", {})
        if t < tr.get("fade_in", 0):
            f *= t / tr["fade_in"]
        if t > p["duration"] - tr.get("fade_out", 0):
            f *= max(0.0, (p["duration"] - t) / tr["fade_out"])
        out = np.clip(f, 0, 255).astype(np.uint8)
        if prev is not None:                               # motion metrics (is the water / are the trees alive?)
            if env.pond:
                cx_, cy_, rx_, ry_ = env.pond
                x0, y0 = cam.to_screen(cx_ - rx_ * 0.5, cy_ - ry_ * 0.4)
                x1, y1 = cam.to_screen(cx_ + rx_ * 0.5, cy_ + ry_ * 0.2)
                x0, y0, x1, y1 = int(max(0, x0)), int(max(0, y0)), int(min(W, x1)), int(min(H, y1))
                if x1 - x0 > 20 and y1 - y0 > 10 and shot.get("type") in ("wide", "pull_out"):
                    self.metrics["water"].append(float(np.abs(out[y0:y1, x0:x1].astype(int) - prev[y0:y1, x0:x1].astype(int)).mean()))
        self.metrics["frames"] += 1
        return out


def render(plan, clips, out_path, workdir, W=1280, H=720, fps=24, audio=None, log=print, chunk_shots=True):
    """render the whole plan; returns a report dict (time, frames, metrics)"""
    os.makedirs(workdir, exist_ok=True)
    scene = Scene(plan, clips, fps)
    cam = cc.Camera(W, H)
    total = int(round(plan["duration"] * fps))
    key = hashlib.sha1(json.dumps(plan, sort_keys=True, default=str).encode() + f"{W}x{H}@{fps}".encode()).hexdigest()[:10]
    bounds = sorted({0} | {min(total, int(round(s["t0"] * fps))) for s in plan["camera"]} | {total}) if chunk_shots else [0, total]
    chunks, t0 = [], time.time()
    resumed = 0
    for ci in range(len(bounds) - 1):
        a, b = bounds[ci], bounds[ci + 1]
        if b <= a:
            continue
        cp = os.path.join(workdir, f"chunk_{key}_{ci:02d}.mp4")
        chunks.append(cp)
        if os.path.exists(cp) and os.path.getsize(cp) > 1000:
            resumed += 1
            continue                                       # checkpoint: already rendered
        for attempt in range(2):                           # a failed chunk is tried once more
            try:
                ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                                       "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                                       "-crf", "20", "-pix_fmt", "yuv420p", cp + ".part.mp4"],
                                      stdin=subprocess.PIPE, stderr=subprocess.PIPE)
                prev = None
                for fi in range(a, b):
                    fr = scene.render(fi / fps, W, H, cam, prev)
                    ff.stdin.write(fr.tobytes())
                    prev = fr
                ff.stdin.close()
                if ff.wait() != 0:
                    raise RuntimeError(ff.stderr.read().decode()[-300:])
                os.replace(cp + ".part.mp4", cp)
                break
            except Exception as e:
                log(f"  chunk {ci} failed (attempt {attempt + 1}): {str(e)[:150]}")
                if attempt == 1:
                    raise
        log(f"  chunk {ci + 1}/{len(bounds) - 1} ({(b - a) / fps:.1f}s) done - {time.time() - t0:.0f}s so far")
    lst = os.path.join(workdir, "chunks.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(c)}'\n" for c in chunks)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst]
    if audio:
        cmd += ["-i", audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True)
    m = scene.metrics
    rep = {"frames": total, "rendered_frames": m["frames"], "chunks": len(chunks), "chunks_resumed": resumed,
           "render_seconds": round(time.time() - t0, 1), "resolution": f"{W}x{H}", "fps": fps,
           "feet_error_px_max": round(max(m["feet_err"] or [0]), 2),
           "water_motion_mean": round(float(np.mean(m["water"])) if m["water"] else 0.0, 2),
           "lip_sync_frames": sum(1 for x in m["mouth"] if x == 1),
           "mouth_without_voice_frames": sum(1 for x in m["mouth"] if x == -1)}
    for tmp in os.listdir(workdir):                        # temporary files cleaned (the chunks stay as checkpoint)
        if tmp.endswith(".part.mp4"):
            os.remove(os.path.join(workdir, tmp))
    return rep, scene
