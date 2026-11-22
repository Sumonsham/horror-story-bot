"""RIG TEST (GitHub: mode = rig_test) - the first proof for ONE character (Hari), from its rig in
assets/character_rigs/<id>/ (made once by build_rig.py; nothing here generates an image or calls Cloudflare).

Writes work/rig_test/<id>/:
  A_original_reference.png        the Cloudflare reference, untouched
  B_clean_artwork.png             the rig in its setup pose (must equal A without its background / ground shadow)
  C_layers.png                    every prepared layer alone (checkerboard = transparent)
  D_rig_joints.png                bones + joints + layer outlines on the artwork (2x)
  E..H poses                      open palms, indicating, talking, listening, sitting ON a stool
  I_walk_cycle.png                the cycle: contact, down, passing, up, opposite contact, down, passing, up
  K_hands_feet_closeups.png       hands and feet at 100 % and 300 % in several poses
  hari_proof_720p.mp4             ~10 s at 1280x720 / 24 fps: idle, talking (real voice + lip-sync), walking (camera
                                  follows, feet planted), indicating, sitting down on a stool and talking
  hari_walk_slow.mp4              the walk cycle at half speed beside a ruler (foot contact can be checked)
  qa_report.json                  TECHNICAL checks only (an approval is the owner's alone)
Every frame of every video carries 'PREVIEW - NOT APPROVED'.
"""
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

W, H, FPS = 1280, 720, 24
MARK = "PREVIEW - NOT APPROVED - engine 2 rig test (nothing is published)"
SLOTS_ARM = {"r": ("arm_r", "hand_r"), "l": ("arm_l", "hand_l")}
SLOTS_LEG = {"r": ("leg_r", "foot_r"), "l": ("leg_l", "foot_l")}


def _mark(img):
    cv2.rectangle(img, (0, 0), (img.shape[1], 30), (20, 20, 20), -1)
    cv2.putText(img, MARK, (10, 21), 0, 0.56, (80, 200, 255), 1, cv2.LINE_AA)


def _label(img, txt, y=None):
    y = y or img.shape[0] - 12
    cv2.putText(img, txt, (10, y), 0, 0.62, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, txt, (10, y), 0, 0.62, (255, 255, 255), 1, cv2.LINE_AA)


def _xf(m, p):
    return m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5]


class Stage:
    """the existing scene engine's room (location_library 'house_interior') as the background + a world camera.
    Character placement: world x, ground y; rig px -> world px by `k`."""

    def __init__(self, loc="house_interior"):
        import cinematic_camera as cc
        import location_library
        from environment_animation import Environment
        self.env = Environment(location_library.spec_for(loc))
        self.cam = cc.Camera(W, H)
        self.ground = 935.0

    def frame(self, t, cx, cy, z):
        import cartoon_rig as R
        self.cam.set(cx, cy, z)
        wind = 0.0
        img = self.env.background(self.cam, t, wind, None)
        if img.dtype != np.uint8:
            img = np.clip(img, 0, 255).astype(np.uint8)
        pt = R.Painter(img, self.cam)
        self.lights = list(self.env.draw_location(pt, t, wind, None) or [])
        return img, pt

    def finish(self, img, t):
        try:
            self.env.atmosphere(img, self.cam, t, 0.0, self.lights)
        except Exception:
            pass

    def to_screen_xf(self, wx, k, sole_y):
        """(scale, ox, oy) for raster.draw: rig (x, y up) at world (wx + x*k, ground - (y - sole_y)*k)"""
        s = self.cam.s * k
        sx0, sy0 = self.cam.to_screen(wx, self.ground)
        return s, sx0, sy0 + sole_y * s


def _stool(pt, x, ground, top, k):
    """a wooden stool (world px): seat at `top`, legs to the ground"""
    pt.poly([(x - 96 * k, top), (x + 96 * k, top), (x + 88 * k, top + 18 * k), (x - 88 * k, top + 18 * k)], (38, 64, 96))
    for dx in (-76, 76):
        pt.line((x + dx * k, top + 14 * k), (x + dx * 1.12 * k, ground), (28, 50, 78), 10 * k)


def _alpha(rig, pose, only, size=(1400, 1400), scale=1.0):
    from engine2.rigby import raster as RS
    f = np.zeros((size[1], size[0], 3), np.uint8)
    a = RS.draw(rig, pose, f, scale, size[0] / 2, size[1] - 150, only=set(only))
    return a > 0.5


_REST_PIECES = {}


def _pieces(rig, pose, slots):
    al = _alpha(rig, pose, slots)
    n, lab, st, _ = cv2.connectedComponentsWithStats(al.astype(np.uint8), connectivity=8)
    return sum(1 for v in st[1:, 4] if v > 60)


def qa_pose(rig, pose, setup_area, name):
    """technical checks of one pose: every limb is ONE connected piece (no detached hand / foot, no elbow or knee
    gap), every layer keeps its size (no missing or broken costume)"""
    probs, m = [], {}
    for sd, slots in list(SLOTS_ARM.items()) + list(SLOTS_LEG.items()):
        al = _alpha(rig, pose, slots)
        n, lab, st, _ = cv2.connectedComponentsWithStats(al.astype(np.uint8), connectivity=8)
        big = sorted(st[1:, 4], reverse=True)
        pieces = sum(1 for v in big if v > 60)
        m[f"{slots[0]}+{slots[1]} pieces"] = int(pieces)
        if pieces != 1:
            probs.append(f"{name}: {slots[1]} is not joined to {slots[0]} ({pieces} pieces)")
        for s in slots:                                     # a gap INSIDE a limb (elbow / knee): the limb alone has
            key = (id(rig), s)                              # more pieces than in the drawing
            if key not in _REST_PIECES:
                _REST_PIECES[key] = _pieces(rig, rig.pose(), [s])
            p1 = _pieces(rig, pose, [s])
            if p1 > _REST_PIECES[key]:
                probs.append(f"{name}: {s} falls apart into {p1} pieces (drawn: {_REST_PIECES[key]}) - a joint gap")
    for s, a0 in setup_area.items():
        a = int(_alpha(rig, pose, [s]).sum())
        r = a / max(1, a0)
        m[f"area {s}"] = round(r, 3)
        if not 0.72 <= r <= 1.35:
            probs.append(f"{name}: {s} changes size to {r:.0%} of the drawing (stretched / squashed / missing)")
    return probs, m


def foot_slide(rig, step_speed, T, dt=1.0 / 96):
    """world movement of each sole while it is ON the ground (the body moves at step_speed rig px / s)"""
    worst = {}
    for sd in ("r", "l"):
        prev = None
        mx = 0.0
        t = 0.0
        while t < T * 2:
            p = rig.pose("walk", t)
            fw = p.bone_world("foot_" + sd)
            heel = _xf(fw, (0, 0))
            world_x = heel[0] + step_speed * t
            rest_y = _xf(rig.pose().bone_world("foot_" + sd), (0, 0))[1]
            on = abs(heel[1] - rest_y) < 0.05                        # the ankle exactly at its standing height = on the ground
            if on and prev is not None and prev[2]:
                mx = max(mx, abs(world_x - prev[0]) / dt)
            prev = (world_x, heel[1], on)
            t += dt
        worst[sd] = round(mx / FPS, 3)                        # rig px per video frame
    return worst


def run(cid="hari", out_root=None, log=print):
    from engine2.rigby import animations as AN
    from engine2.rigby import face as FC
    from engine2.rigby import raster as RS
    from engine2 import videoqa
    rdir = os.path.join(ROOT, "assets", "character_rigs", cid)
    out = os.path.join(out_root or os.path.join(ROOT, "work", "rig_test"), cid)
    os.makedirs(out, exist_ok=True)
    cfg = json.load(open(os.path.join(rdir, "prep.json")))
    info = json.load(open(os.path.join(rdir, "layers.json")))
    CW, CH = info["size"]
    rig = RS.Rig(os.path.join(rdir, "export", f"{cid}.json"))
    ref = cv2.imread(os.path.join(ROOT, cfg["source"]), cv2.IMREAD_UNCHANGED)
    if ref is None:
        ref = cv2.imread(os.path.join(rdir, "reference.png"), cv2.IMREAD_UNCHANGED)
    skin = ref[cfg["face"]["skin_at"][1], cfg["face"]["skin_at"][0], :3]
    face = FC.Face(rig, cfg["face"], (CW, CH), skin)
    report = {"character": cid, "approved": False, "visual_approval": "WAITING FOR THE OWNER - a code check never approves art",
              "files": {}, "checks": {}, "problems": [], "known_limits": []}
    J = {k: (v[0] - CW / 2, CH - v[1]) for k, v in cfg["joints"].items() if not k.startswith("_")}

    # A / B: the drawing and the rig at rest
    a = ref[..., 3:] / 255.0
    plain = (ref[..., :3] * a + 236 * (1 - a)).astype(np.uint8)
    cv2.imwrite(os.path.join(out, "A_original_reference.png"), ref)
    rest = np.full((CH, CW, 3), 236, np.uint8)
    RS.draw(rig, rig.pose(), rest, 1.0, CW / 2, CH)
    cv2.imwrite(os.path.join(out, "B_clean_artwork.png"), rest)
    sh = np.zeros(ref.shape[:2], bool)
    diff = np.abs(rest.astype(int) - plain.astype(int)).max(axis=2)
    lay_union = np.zeros(ref.shape[:2], bool)
    for nm in info["order"]:
        lay_union |= cv2.imread(os.path.join(rdir, info["layers"][nm]["file"]), cv2.IMREAD_UNCHANGED)[..., 3] > 0
    core = cv2.erode((ref[..., 3] > 250).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    core &= lay_union
    bad = (diff > 60) & core
    report["checks"]["rest_pose_equals_drawing"] = {"pixels_differing": int(bad.sum()), "of": int(core.sum())}
    if bad.sum() > 0.005 * core.sum():                    # (below 0.5 %: resampling of thin ink lines, not a change)
        report["problems"].append(f"the rig at rest differs from the drawing in {int(bad.sum())} pixels")
    # C: layers
    import shutil
    shutil.copy(os.path.join(rdir, "diag_layers.png"), os.path.join(out, "C_layers.png"))
    # D: bones + joints
    S = 2
    big = cv2.resize(rest, None, fx=S, fy=S, interpolation=cv2.INTER_CUBIC)
    p0 = rig.pose()
    for b in rig.sk.bones:
        if b.name == "root":
            continue
        m = p0.bone_world(b.name)
        h0 = _xf(m, (0, 0))
        h1 = _xf(m, (b.length, 0))
        q0 = (int((h0[0] + CW / 2) * S), int((CH - h0[1]) * S))
        q1 = (int((h1[0] + CW / 2) * S), int((CH - h1[1]) * S))
        col = (0, 0, 255) if b.name.startswith("ik_") else (255, 60, 0)
        cv2.line(big, q0, q1, col, 3, cv2.LINE_AA)
        cv2.circle(big, q0, 8, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.circle(big, q0, 5, (0, 255, 255), -1, cv2.LINE_AA)
        cv2.putText(big, b.name, (q0[0] + 9, q0[1] - 6), 0, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(big, b.name, (q0[0] + 9, q0[1] - 6), 0, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(out, "D_rig_joints.png"), big)

    # E..H poses (each at a moment of its animation), sitting with a stool
    def still(anim, t, stool=False, blink=0.0, shape="X"):
        f = np.full((CH + 40, CW + 360, 3), 236, np.uint8)
        ox, oy = (CW + 360) / 2, CH + 20
        if stool:
            top_rig = J["hip_r"][1] - 112 - 26
            sy = oy - top_rig
            cx = ox + (J["hip_r"][0] - 62)
            cv2.fillConvexPoly(f, np.int32([[cx - 96, sy], [cx + 96, sy], [cx + 88, sy + 18], [cx - 88, sy + 18]]), (38, 64, 96), cv2.LINE_AA)
            g = oy - 45
            for dx in (-76, 76):
                cv2.line(f, (int(cx + dx), int(sy + 16)), (int(cx + dx * 1.12), int(g)), (28, 50, 78), 11, cv2.LINE_AA)
        p = rig.pose(anim, t) if anim else rig.pose()
        RS.draw(rig, p, f, 1.0, ox, oy)
        face.draw(f, p, 1.0, ox, oy, shape, blink)
        cv2.line(f, (0, int(oy - 45)), (f.shape[1], int(oy - 45)), (170, 170, 170), 1)
        return f, p
    poses = [("E_open_palms", "open_palms", 1.0, False, "B"), ("F_indicating_open_hand", "indicate", 1.2, False, "X"),
             ("G_talking", "talk", 1.35, False, "C"), ("G2_listening", "listen", 1.3, False, "X"), ("H_sitting_on_stool", "sit_talk", 0.6, True, "D")]
    setup_area = {s.name: int(_alpha(rig, rig.pose(), [s.name]).sum()) for s in rig.sk.slots}
    for fn, anim, t, stool, shp in poses:
        img, p = still(anim, t, stool, 0.0, shp)
        _label(img, f"{fn[2:]} ({anim} @ {t:.2f}s) - 100 %")
        cv2.imwrite(os.path.join(out, fn + ".png"), img)
        probs, m = qa_pose(rig, p, setup_area, fn)
        report["checks"][fn] = m
        report["problems"] += probs
    # I: walk cycle sheet
    names = [("contact (R)", 0.0), ("down", 0.06), ("passing", 0.29), ("up", 0.40), ("contact (L)", 0.5), ("down", 0.56),
             ("passing", 0.79), ("up", 0.90)]
    tiles = []
    for nm, u in names:
        f = np.full((CH - 40, 420, 3), 236, np.uint8)
        p = rig.pose("walk", u * AN.WALK_T)
        RS.draw(rig, p, f, 0.62, 210, CH - 70)
        gy = int(CH - 70 - 45 * 0.62)
        cv2.line(f, (0, gy), (420, gy), (150, 150, 150), 1)
        for sd in ("r", "l"):
            hx = _xf(p.bone_world("foot_" + sd), (0, 0))
            cv2.circle(f, (int(210 + hx[0] * 0.62), int(CH - 70 - hx[1] * 0.62)), 4, (0, 0, 255) if sd == "r" else (255, 0, 0), -1)
        _label(f, f"{nm}  t={u * AN.WALK_T:.2f}s", 26)
        tiles.append(f)
        probs, m = qa_pose(rig, p, setup_area, f"walk {nm} {u:.2f}")
        report["problems"] += probs
    sheet = np.vstack([np.hstack(tiles[:4]), np.hstack(tiles[4:])])
    cv2.imwrite(os.path.join(out, "I_walk_cycle.png"), sheet)
    speed = 2 * AN.STEP / (AN.DUTY * AN.WALK_T)
    slide = foot_slide(rig, speed, AN.WALK_T)
    report["checks"]["foot_slide_px_per_frame_at_rig_scale"] = slide
    if max(slide.values()) > 1.5:
        report["problems"].append(f"a planted foot slides {max(slide.values())} px per frame")
    # K: hands and feet close-ups (100 % and 300 %)
    rows = []
    for anim, t in ((None, 0), ("open_palms", 1.0), ("indicate", 1.2), ("walk", 0.0), ("walk", 0.29 * AN.WALK_T)):
        p = rig.pose(anim, t) if anim else rig.pose()
        f = np.full((CH + 200, CW + 400, 3), 236, np.uint8)
        RS.draw(rig, p, f, 1.0, (CW + 400) / 2, CH + 100)
        crops = []
        for b in ("hand_r", "hand_l", "foot_r", "foot_l"):
            c = _xf(p.bone_world(b), (35 if b.startswith("hand") else 30, 0))
            x, y = int((CW + 400) / 2 + c[0]), int(CH + 100 - c[1])
            r = 62
            cr = f[max(0, y - r):y + r, max(0, x - r):x + r]
            cr = cv2.copyMakeBorder(cr, 0, 2 * r - cr.shape[0], 0, 2 * r - cr.shape[1], cv2.BORDER_CONSTANT, value=(236, 236, 236))
            z3 = cv2.resize(cr, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            one = cv2.copyMakeBorder(cr, 0, z3.shape[0] - cr.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
            t_ = np.hstack([one, z3])
            _label(t_, f"{b} {anim or 'rest'}: 100 % | 300 %", 20)
            crops.append(t_)
        rows.append(np.hstack(crops))
    cv2.imwrite(os.path.join(out, "K_hands_feet_closeups.png"), np.vstack(rows))

    # J: the proof video
    stage = Stage("house_interior")
    voice = None
    vs = os.path.join(ROOT, "assets", "voice_samples")
    if os.path.isdir(vs):
        cands = sorted(f for f in os.listdir(vs) if f.endswith((".ogg", ".wav", ".mp3")))
        if cands:
            voice = os.path.join(out, "voice_cut.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.6", "-t", "3.2", "-i", os.path.join(vs, cands[-1]),
                            "-ac", "1", "-ar", "16000", voice])
    cues, how = FC.mouth_cues(voice, FPS, log) if voice else ([], "no voice")
    report["checks"]["lip_sync"] = how
    k = 0.52                                                # rig px -> world px (Hari ~475 world px tall)
    segs = [("idle", 2.0), ("talk", 3.2), ("walk", 3.3), ("indicate", 2.4), ("sit_down", 1.4), ("sit_talk", 2.6)]
    total = sum(d for _, d in segs)
    audio = os.path.join(out, "proof_audio.wav")
    if voice:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", "2.0", "-i", "anullsrc=r=16000:cl=mono", "-i", voice,
                        "-filter_complex", f"[0][1]concat=n=2:v=0:a=1,apad=whole_dur={total}", "-t", str(total), audio])
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", str(total), "-i", "anullsrc=r=16000:cl=mono", audio])
    vid = os.path.join(out, f"{cid}_proof_720p.mp4")
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                             "-i", "-", "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", vid], stdin=subprocess.PIPE)
    x0 = 700.0
    walk_v = speed * k                                      # world px / s, exactly the feet's speed on the ground
    walk_start = sum(d for _, d in segs[:2])
    walk_dur = segs[2][1]
    x_after = x0 + walk_v * walk_dur
    sole = 45.0
    heights = []
    crop_hits = 0
    for fi in range(int(total * FPS)):
        t = fi / FPS
        acc, seg, u = 0.0, "idle", 0.0
        for s, d in segs:
            if t < acc + d:
                seg, u = s, t - acc
                break
            acc += d
        x = x0
        if seg == "walk":
            x = x0 + walk_v * u
        elif seg in ("indicate", "sit_down", "sit_talk"):
            x = x_after
        # camera: full shot that follows the walk; medium shot for talking; full for sitting
        if seg == "talk":
            cx, cy, z = x0 + 60, stage.ground - 330, 2.35
        elif seg == "walk":
            cx, cy, z = x + 40, stage.ground - 245, 1.65
        elif seg == "indicate":
            cx, cy, z = x_after + 160, stage.ground - 245, 1.65
        elif seg in ("sit_down", "sit_talk"):
            cx, cy, z = x_after - 20, stage.ground - 225, 1.85
        else:
            cx, cy, z = x0 + 40, stage.ground - 245, 1.65
        img, pt = stage.frame(t, cx, cy, z)
        if seg in ("sit_down", "sit_talk"):
            top_w = stage.ground - (J["hip_r"][1] - 112 - 26 - sole) * k
            _stool(pt, x_after + (J["hip_r"][0] - 62) * k, stage.ground, top_w, k)
        scale, ox, oy = stage.to_screen_xf(x, k, sole)
        anim = {"idle": "idle", "talk": "talk", "walk": "walk", "indicate": "indicate", "sit_down": "sit_down", "sit_talk": "sit_talk"}[seg]
        p = rig.pose(anim, u, loop=seg not in ("sit_down",))
        alpha = RS.draw(rig, p, img, scale, ox, oy)
        shape = FC.shape_at(cues, t - 2.0) if seg == "talk" else ("B" if seg == "sit_talk" and int(u * 6) % 3 == 1 else "X")
        blink = 1.0 if (t % 3.3) < 0.11 else 0.0
        face.draw(img, p, scale, ox, oy, shape, blink)
        stage.finish(img, t)
        if img.dtype != np.uint8:
            img = np.clip(img, 0, 255).astype(np.uint8)
        ys, xs = np.nonzero(alpha > 0.3)
        if len(ys):
            heights.append((seg, (ys.max() - ys.min()) / H))
            medium = seg == "talk"                          # a medium shot frames the knees up (feet out on purpose)
            if xs.min() <= 0 or xs.max() >= W - 1 or (ys.max() >= H - 1 and not medium) or ys.min() <= 31:
                crop_hits += 1
        _mark(img)
        _label(img, f"Hari - {seg}" + ("  (mouth: " + shape + ")" if seg == "talk" else ""))
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()
    report["files"]["proof_video"] = vid
    report["checks"]["proof_video"] = videoqa.check(vid)
    hs = {}
    for s, h in heights:
        hs.setdefault(s, []).append(h)
    report["checks"]["character_height_share_of_frame"] = {s: [round(min(v), 2), round(max(v), 2)] for s, v in hs.items()}
    report["checks"]["frames_where_character_touches_frame_edge"] = crop_hits
    # slow walk with a ruler
    sv = os.path.join(out, f"{cid}_walk_slow.mp4")
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                             "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
                             "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart", sv],
                            stdin=subprocess.PIPE)
    sc = 0.62
    for fi in range(int(AN.WALK_T * 3 * 2 * FPS)):          # three cycles at half speed
        t = fi / FPS / 2.0
        f = np.full((H, W, 3), 236, np.uint8)
        xw = 120 + speed * sc * t
        gy = H - 60
        for gx in range(0, W, 40):
            cv2.line(f, (gx, gy), (gx, gy + 12), (150, 150, 150), 1)
        cv2.line(f, (0, gy), (W, gy), (120, 120, 120), 1)
        p = rig.pose("walk", t)
        RS.draw(rig, p, f, sc, xw, gy + 45 * sc)
        face.draw(f, p, sc, xw, gy + 45 * sc, "X", 0.0)
        _mark(f)
        _label(f, f"walk cycle at half speed - feet must stay still on the ruler while on the ground  t={t:.2f}s")
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    proc.wait()
    report["files"]["walk_slow"] = sv
    report["checks"]["walk_slow_video"] = videoqa.check(sv)
    report["known_limits"] = [
        "No index-finger hand exists in the artwork: 'pointing' is an open-hand indicating gesture. A real finger-point needs one new hand drawing (hand sheet), then approval.",
        "Mouth shapes and the blink are drawn by code on the face (the reference has one closed mouth and open eyes).",
        "Sitting is done by the rig (hips down onto a stool, knees forward). A full side-view sit or cross-legged sitting needs a complete new pose drawing.",
        "Only one view exists (three-quarter, facing right). Facing left is a mirror; a back view or a true profile needs new drawings.",
        "Expressions other than neutral (happy, afraid, angry...) need their own approved face drawings.",
    ]
    for c in ("proof_video", "walk_slow_video"):
        if not report["checks"][c]["pass"]:
            report["problems"] += [f"{c}: {x}" for x in report["checks"][c]["problems"]]
    if crop_hits > 0:
        report["problems"].append(f"the character touches the frame edge in {crop_hits} frames")
    report["technical_pass"] = not report["problems"]
    with open(os.path.join(out, "qa_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    return report


if __name__ == "__main__":
    r = run(*(sys.argv[1:2] or ["hari"]), *(sys.argv[2:3] or [None]))
    print(json.dumps({k: r[k] for k in ("technical_pass", "problems", "checks")}, ensure_ascii=False, indent=1, default=str)[:6000])
