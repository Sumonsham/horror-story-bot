"""ENGINE 2 - HYBRID 2D MVP (23 Nov 2026). Test modes only; production never reads this file.

What this module adds on top of the existing engine 2 pieces (library, rigby rig, posefirst, fullpose, videoqa):

1. RIG SAFETY (`rig_limits`, `anim_safety`, `clamp_arms`)
   The arm-lift test (engine2/rigby/armlift.py) proved Hari's flattened artwork breaks at the shoulder when an arm
   is lifted past its drawn angle (a hole at 30 degrees, a broken outline from 45, a pinched shoulder from 90).
   The rig's own animations lift the far arm to 56 degrees (talk), 80 degrees (indicate) and 53 degrees (sit_talk)
   - exactly the range that breaks. So every rig pose is now measured, and an arm that goes past its safe limit is
   eased back towards the drawing (`clamp_arms`). A movement that needs more than that is done with a complete pose
   drawing, or not at all.

2. HYBRID DECISION ENGINE (`decide`)
   Per action: A = skeletal rig (only inside the safe range), B = a complete illustrated pose, C = a static approved
   pose with small secondary motion, or MISSING (reported, never drawn broken). Every decision is written down with
   its reason, the asset used and whether that asset is owner-approved.

3. IDENTITY CHECK (`identity`)
   Several measurements instead of one colour threshold: colour per body region (hair, face/skin, shirt, trousers,
   feet) in Lab, hue-histogram correlation of the whole figure, the face crop's structure (normalised correlation),
   and the figure's proportions. The verdict is CONSISTENT / NEEDS_REVIEW / MISMATCH - never "approved".

4. COMPLETE POSES (`ComplexPose`)
   A pose-first picture (plain grey background) is cut out by a border flood-fill (no guessing inside the figure),
   scaled so its figure height equals the rig's figure height, and stood on the same ground line.

5. RENDER TEST (`render_test`) - a 60-second 1280x720 24 fps H.264/AAC video of Hari through the existing scene
   engine (location_library + environment_animation + cinematic_camera), the ten MVP actions, every frame marked
   'TEST - NOT APPROVED', plus a contact sheet, the decision table and a machine-readable report.
"""
import json
import math
import os
import subprocess

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1280, 720, 24
MARK = "TEST - NOT APPROVED - hybrid 2D MVP render test (nothing is published)"
SAFE_TOL = 10.0                      # degrees an arm may move past its drawn angle before the shoulder shows damage
ARM_BONES = {"r": ("upperarm_r", "forearm_r", "hand_r"), "l": ("upperarm_l", "forearm_l", "hand_l")}

# ------------------------------------------------------------------------------------------- 1. rig safety


def load_rig(cid="hari"):
    from engine2.rigby import raster as RS
    jp = os.path.join(ROOT, "assets", "character_rigs", cid, "export", f"{cid}.json")
    rig = RS.Rig(jp)
    rig.json_path = jp
    return rig


def _ang(m):
    return math.degrees(math.atan2(m[1], m[0]))


def arm_raise(p, side):
    """degrees the upper arm is lifted away from hanging straight down (screen space)"""
    w = _ang(p.bone_world(ARM_BONES[side][0]))
    return abs(((w + 90.0) + 180.0) % 360.0 - 180.0)


def rig_limits(rig, armlift_report=None):
    """per arm: the largest lift that does not damage the artwork.
    rest lift + SAFE_TOL, or (if the arm-lift test measured it) the last passing step before the first failure,
    whichever is larger."""
    p0 = rig.pose()
    out = {}
    for s in ("r", "l"):
        rest = arm_raise(p0, s)
        lim = rest + SAFE_TOL
        if armlift_report:
            steps = [x for x in armlift_report.get("arms", {}).get(s, []) if x.get("degrees", 0) > 0]
            last_ok = None
            for x in steps:
                if not x.get("pass"):
                    break
                last_ok = x["degrees"]
            if last_ok is not None:
                lim = max(lim, float(last_ok))
        out[s] = {"rest": round(rest, 1), "limit": round(lim, 1)}
    return out


def clamp_arms(rig, p, limits):
    """eases an arm back towards the drawing until it is inside its safe limit (upper arm and forearm together,
    same fraction); returns {side: fraction kept} for the arms that had to be eased"""
    eased = {}
    for s, (up, fo, _ha) in ARM_BONES.items():
        lim = limits[s]["limit"]
        if arm_raise(p, s) <= lim + 0.01:
            continue
        iu, jf = rig.sk.find_bone(up), rig.sk.find_bone(fo)
        su, sf = rig.sk.bones[iu].setup[2], rig.sk.bones[jf].setup[2]
        au, af = p.local[iu][2], p.local[jf][2]
        lo, hi = 0.0, 1.0
        for _ in range(14):                                    # binary search on the kept fraction of the movement
            mid = (lo + hi) / 2
            p.set_bone(iu, rotation=su + (au - su) * mid)
            p.set_bone(jf, rotation=sf + (af - sf) * mid)
            p.update_world()
            if arm_raise(p, s) <= lim:
                lo = mid
            else:
                hi = mid
        p.set_bone(iu, rotation=su + (au - su) * lo)
        p.set_bone(jf, rotation=sf + (af - sf) * lo)
        p.update_world()
        eased[s] = round(lo, 2)
    return eased


_FOOT = {}


def _foot_data(rig):
    """per foot: its rest angle to the ground and the rest position of its lowest corner (from the rig file)"""
    key = id(rig)
    if key in _FOOT:
        return _FOOT[key]
    p0 = rig.pose()
    out = {}
    att = {}
    try:                                                       # the foot pictures' rectangles (region attachments)
        jp = getattr(rig, "json_path", None) or os.path.join(ROOT, "assets", "character_rigs", "hari", "export", "hari.json")
        js = json.load(open(jp)) if os.path.exists(jp) else None
    except Exception:
        js = None
    for s in ("r", "l"):
        out[s] = {"rest_angle": _ang(p0.bone_world("foot_" + s)), "rect": None}
    if js:
        a = js["skins"][0]["attachments"]
        for s in ("r", "l"):
            r = list(a.get("foot_" + s, {}).values())[0] if a.get("foot_" + s) else None
            if r and r.get("type", "region") == "region":
                out[s]["rect"] = r
    for s in ("r", "l"):
        out[s]["rest_low"] = _foot_low(p0, s, out[s]["rect"])
    _FOOT[key] = out
    return out


def _foot_low(p, s, rect):
    """the lowest world y of a foot picture (its rectangle's corners); without the rectangle: the ankle"""
    m = p.bone_world("foot_" + s)
    if not rect:
        return m[5]
    cr, sr = math.cos(math.radians(rect.get("rotation", 0))), math.sin(math.radians(rect.get("rotation", 0)))
    w, h = rect["width"] / 2.0 * rect.get("scaleX", 1), rect["height"] / 2.0 * rect.get("scaleY", 1)
    ys = []
    for dx, dy in ((-w, -h), (w, -h), (w, h), (-w, h)):
        lx, ly = rect.get("x", 0) + dx * cr - dy * sr, rect.get("y", 0) + dx * sr + dy * cr
        ys.append(m[1] * lx + m[3] * ly + m[5])
    return min(ys)                                             # (y is up: the lowest point is the smallest y)


def fix_feet(rig, p):
    """WALK FOOT FIX (23 Nov 2026). The walk keys each foot's heel-toe roll LOCALLY (relative to the shin), so when the
    leg swings the foot's angle to the ground changed with the shin and the far foot's toe sank through the floor
    (up to 44 rig px). Here (1) each foot keeps its rest angle to the ground plus the keyed roll, and (2) a roll that
    would push the foot below its own ground lifts the ankle instead (the toe / heel is the pivot). Returns the lifts."""
    fd = _foot_data(rig)
    keyed = {}
    for s in ("r", "l"):
        i = rig.sk.find_bone("foot_" + s)
        keyed[s] = p.local[i][2] - rig.sk.bones[i].setup[2]        # the roll the animation wants
    lifts = {"r": 0.0, "l": 0.0}
    for _round in range(4):                                     # angle lock and ankle lift settle together
        for s in ("r", "l"):
            i = rig.sk.find_bone("foot_" + s)
            cur = _ang(p.bone_world("foot_" + s))
            target = fd[s]["rest_angle"] + keyed[s]
            p.set_bone(i, rotation=p.local[i][2] + ((target - cur + 180) % 360 - 180))
        p.update_world()
        moved = False
        for s in ("r", "l"):
            sink = fd[s]["rest_low"] - _foot_low(p, s, fd[s]["rect"])
            if sink > 0.2:
                j = rig.sk.find_bone("ik_foot_" + s)
                p.set_bone(j, y=p.local[j][1] + sink)
                lifts[s] += sink
                moved = True
        if not moved:
            break
        p.update_world()
    return {s: round(v, 1) for s, v in lifts.items() if v}


def safe_pose(rig, anim, t, limits, loop=True):
    p = rig.pose(anim, t, loop=loop) if anim else rig.pose()
    if anim == "walk":
        fix_feet(rig, p)
    eased = clamp_arms(rig, p, limits)
    return p, eased


def anim_safety(rig, limits, samples=25):
    """per rig animation: the largest arm lift and whether the animation stays inside the safe range"""
    out = {}
    for a, d in rig.durations.items():
        mx = {"r": 0.0, "l": 0.0}
        for t in np.linspace(0, d, samples):
            p = rig.pose(a, t)
            for s in mx:
                mx[s] = max(mx[s], arm_raise(p, s))
        over = {s: round(mx[s] - limits[s]["limit"], 1) for s in mx if mx[s] > limits[s]["limit"]}
        out[a] = {"max_lift": {s: round(v, 1) for s, v in mx.items()}, "safe": not over, "over_limit_by": over}
    return out


# ------------------------------------------------------------------------------------------- 2. decisions

# MVP actions: what each one needs. 'rig' = rig animation name (used only if safe, else clamped if 'clamp_ok'),
# 'poses' = complete pose drawings that do it (first found wins), 'static' = a still drawing is an honest stand-in.
MVP_ACTIONS = [
    ("neutral", {"rig": "idle", "clamp_ok": True, "poses": ["stand", "master"], "static": True}),
    ("talking", {"rig": "talk", "clamp_ok": True, "poses": ["talk"], "static": False, "mouth": True}),
    ("pointing", {"rig": None, "poses": ["point_index", "point"], "static": False}),
    ("one_arm_raised", {"rig": None, "poses": ["arm90", "arm120", "arm45"], "static": False}),
    ("both_arms_raised", {"rig": None, "poses": ["both_up"], "static": False}),
    ("sitting", {"rig": "sit_talk", "clamp_ok": True, "poses": ["sit"], "static": False, "seat": True}),
    ("walking", {"rig": "walk", "clamp_ok": True, "poses": ["walk1", "walk2", "walk3", "walk4"], "all_poses": True}),
    ("listening", {"rig": "listen", "clamp_ok": True, "poses": ["listen"], "static": False}),
    ("scared", {"rig": None, "poses": ["fear", "scared"], "static": False, "expression": "afraid"}),
    ("scene_transition", {"camera": True}),
]


def pose_inventory(cid="hari"):
    """complete pose drawings that exist for a character: {pose: {"file", "status", "approved", "source"}}
    status = what the automatic check said (passed / failed); approved only from the owner's APPROVALS.json"""
    from engine2 import library as L
    inv = {}
    pf = os.path.join(ROOT, "assets", "character_art", cid, "pose_first")
    idx = {}
    try:
        idx = json.load(open(os.path.join(pf, "index.json"), encoding="utf-8"))
    except Exception:
        pass
    appr = (L.approvals().get(cid) or {}) if hasattr(L, "approvals") else {}
    pose_appr = appr.get("pose_first") or {}
    for pid, rec in (idx.get("poses") or idx or {}).items():
        if not isinstance(rec, dict) or pid.startswith("_"):
            continue
        f = os.path.join(pf, f"{pid}.png")
        ok = bool((rec.get("qa") or {}).get("pass")) if "qa" in rec else \
            str(rec.get("status", "")).lower() in ("generated", "passed", "ok")
        if not os.path.exists(f):                       # a failed pose keeps only its provider originals
            orig = sorted(x for x in os.listdir(os.path.join(pf, "originals")) if x.startswith(pid + "_attempt")) \
                if os.path.isdir(os.path.join(pf, "originals")) else []
            if not orig:
                continue
            f = os.path.join(pf, "originals", orig[-1])
            ok = False
        st = pose_appr.get(pid, {}).get("status") if isinstance(pose_appr.get(pid), dict) else pose_appr.get(pid)
        inv[pid] = {"file": f, "status": "passed" if ok else "failed", "approved": st == "USER_APPROVED",
                    "rejected_by_owner": st == "REJECTED", "source": "pose_first"}
    for pid in ("master", "arm45", "arm90", "arm120", "both_up", "point_index"):
        if pid not in inv and os.path.exists(os.path.join(pf, f"{pid}.png")):
            inv[pid] = {"file": os.path.join(pf, f"{pid}.png"), "status": "passed", "approved": False,
                        "rejected_by_owner": False, "source": "pose_first"}
    inbox = os.path.join(ROOT, "assets", "character_art", cid, "inbox")       # the owner's own drawings win
    if os.path.isdir(inbox):
        for fn in os.listdir(inbox):
            if fn.lower().endswith(".png"):
                pid = os.path.splitext(fn)[0]
                st = pose_appr.get(pid, {}).get("status") if isinstance(pose_appr.get(pid), dict) else pose_appr.get(pid)
                inv[pid] = {"file": os.path.join(inbox, fn), "status": "passed", "approved": st == "USER_APPROVED",
                            "rejected_by_owner": st == "REJECTED", "source": "owner_inbox"}
    return inv


def decide(safety, inventory, production=False):
    """the hybrid decision per MVP action. production=True: only owner-approved complete poses count, and the rig
    counts only if the rig itself is owner-approved (it is not, today)."""
    from engine2 import library as L
    rig_ok = (not production) or ((L.approvals().get("hari") or {}).get("rig", {}) or {}).get("status") == "USER_APPROVED"
    usable = {k: v for k, v in inventory.items() if not v.get("rejected_by_owner")
              and (v["approved"] if production else v["status"] == "passed")}
    rows = []
    for action, need in MVP_ACTIONS:
        row = {"action": action}
        if need.get("camera"):
            row.update(method="camera", asset="scene engine (cross-fade, camera move)", approved=True,
                       reason="no character asset needed")
            rows.append(row)
            continue
        poses = need.get("poses") or []
        have = [p for p in poses if p in usable]
        if need.get("all_poses") and len(have) == len(poses):
            row.update(method="B_complete_pose", asset=have, approved=all(usable[p]["approved"] for p in have),
                       reason="a full drawn cycle exists")
        elif need.get("rig") and rig_ok and safety.get(need["rig"], {}).get("safe"):
            row.update(method="A_rig", asset=f"rig:{need['rig']}", approved=False,
                       reason="inside the arm-lift safe range")
        elif have and not need.get("all_poses"):
            p = have[0]
            row.update(method="B_complete_pose", asset=p, approved=usable[p]["approved"],
                       reason="a complex arm/hand position: drawn, not deformed")
        elif need.get("rig") and rig_ok and need.get("clamp_ok"):
            s = safety.get(need["rig"], {})
            row.update(method="A_rig_safe_range", asset=f"rig:{need['rig']} (arms eased to the safe limit)",
                       approved=False, reason=f"the full animation lifts an arm past the safe limit by "
                                              f"{s.get('over_limit_by')} degrees - the arm is eased back, the rest "
                                              f"(legs, head, mouth) moves as animated")
        elif need.get("static") and any(p in usable for p in ("stand", "master")):
            p = "stand" if "stand" in usable else "master"
            row.update(method="C_static_pose", asset=p, approved=usable[p]["approved"],
                       reason="no motion asset - a still drawing with breathing only")
        else:
            missing = [p for p in poses if p not in inventory] or poses
            failed = [p for p in poses if p in inventory and p not in usable]
            row.update(method="MISSING", asset=None, approved=False,
                       reason=("drawing failed its check / not approved: " + ", ".join(failed)) if failed else
                       ("no drawing exists: " + ", ".join(missing))
                       + ("; also needs an approved face expression drawing" if need.get("expression") else ""))
        if need.get("expression") and row["method"] != "MISSING":
            row["reason"] += "; the face stays neutral (no expression drawings exist)"
        rows.append(row)
    return rows


# ------------------------------------------------------------------------------------------- 3. identity


def figure_rgba(img):
    """a pose-first picture on a plain background -> RGBA, by flood-filling the background from the border only
    (nothing inside the figure is guessed). Accepts RGBA (kept) or BGR."""
    if img.ndim == 3 and img.shape[2] == 4 and (img[..., 3] < 250).mean() > 0.05:
        return _no_ground_shadow(img)
    bgr = img[..., :3].copy()
    h, w = bgr.shape[:2]
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.int16)
    border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    bg = np.median(border, axis=0)
    dist = np.abs(lab - bg).sum(axis=2)
    cand = (dist < 26).astype(np.uint8)                        # near the background colour
    sat = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[..., 1]
    grey = ((sat < 22) & (np.abs(lab[..., 0] - bg[0]) < 60)).astype(np.uint8)   # the soft grey ground shadow
    mask = np.zeros((h + 2, w + 2), np.uint8)
    fill = np.where(cand | grey, 255, 0).astype(np.uint8)
    seeds = [(x, 0) for x in range(0, w, 16)] + [(x, h - 1) for x in range(0, w, 16)] + \
            [(0, y) for y in range(0, h, 16)] + [(w - 1, y) for y in range(0, h, 16)]
    out = np.zeros((h, w), np.uint8)
    for sx, sy in seeds:
        if fill[sy, sx] and not out[sy, sx]:
            m = np.zeros((h + 2, w + 2), np.uint8)
            cv2.floodFill(fill.copy(), m, (sx, sy), 128, loDiff=0, upDiff=0, flags=4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
            out |= m[1:-1, 1:-1]
    alpha = np.where(out > 0, 0, 255).astype(np.uint8)
    # keep only the largest connected figure (no stray specks), soften the edge by one pixel
    n, lab_cc, stats, _ = cv2.connectedComponentsWithStats((alpha > 0).astype(np.uint8), 8)
    if n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        alpha = np.where(lab_cc == big, 255, 0).astype(np.uint8)
        holes = (alpha == 0).astype(np.uint8)                   # background-coloured areas INSIDE the figure stay
        nh, hl, hs, _ = cv2.connectedComponentsWithStats(holes, 4)
        for i in range(1, nh):
            x, y, ww, hh, a = hs[i]
            if x > 0 and y > 0 and x + ww < w and y + hh < h:
                alpha[hl == i] = 255
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    return _no_ground_shadow(np.dstack([bgr, alpha]))


def _no_ground_shadow(rgba):
    """the soft grey ellipse under the feet is not part of the character: low-saturation pixels close to the
    background's lightness, in the lowest 12 % of the figure, connected to the transparent background, are made
    transparent (the dark sandals and the grey trousers are far darker and stay)"""
    rgba = rgba.copy()
    a = rgba[..., 3]
    clear = a < 30
    if clear.sum() < 100:
        return rgba
    bg = np.median(rgba[..., :3][clear].reshape(-1, 3), axis=0) if (rgba[..., :3][clear] > 0).any() else None
    b = _bbox(a)
    if b is None:
        return rgba
    x0, y0, x1, y1 = b
    band0 = y1 - int(0.12 * (y1 - y0))
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2HSV)
    L = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2LAB)[..., 0].astype(np.int16)
    bgL = int(cv2.cvtColor(np.uint8([[bg]]), cv2.COLOR_BGR2LAB)[0, 0, 0]) if bg is not None and bg.max() > 0 else 180
    cand = (hsv[..., 1] < 24) & (np.abs(L - bgL) < 45) & (a > 0)
    cand[:band0] = False
    if not cand.any():
        return rgba
    n, lab_cc = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
    touch = cv2.dilate(clear.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    for i in range(1, n):
        m = lab_cc == i
        if (m & touch).any():
            a[m] = 0
    rgba[..., 3] = a
    return rgba


def _bbox(a):
    ys, xs = np.where(a > 127)
    return (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) if len(ys) else None


REGIONS = {"hair": (0.00, 0.06), "face": (0.07, 0.15), "shirt": (0.22, 0.45), "trousers": (0.58, 0.82), "feet": (0.92, 1.0)}


def _region_lab(rgba, frac):
    a = rgba[..., 3]
    b = _bbox(a)
    if b is None:
        return None
    x0, y0, x1, y1 = b
    hh = y1 - y0
    ya, yb = y0 + int(frac[0] * hh), y0 + max(int(frac[1] * hh), int(frac[0] * hh) + 2)
    sub = rgba[ya:yb, x0:x1]
    m = sub[..., 3] > 200
    if m.sum() < 30:
        return None
    lab = cv2.cvtColor(sub[..., :3], cv2.COLOR_BGR2LAB)[m].astype(np.float32)
    # the region's main colour: the median of its non-ink pixels (ink = very dark outlines)
    lab = lab[lab[:, 0] > 60] if (lab[:, 0] > 60).sum() > 20 else lab
    return np.median(lab, axis=0)


def _de(a, b):
    return float(np.linalg.norm((a - b) * np.array([100 / 255.0, 1, 1]))) if a is not None and b is not None else None


def identity(ref_rgba, cand_rgba):
    """several independent measurements; verdict CONSISTENT / NEEDS_REVIEW / MISMATCH (never 'approved')"""
    r, c = figure_rgba(ref_rgba), figure_rgba(cand_rgba)
    out = {"regions_dE": {}, "notes": []}
    for name, fr in REGIONS.items():
        out["regions_dE"][name] = None if _de(_region_lab(r, fr), _region_lab(c, fr)) is None else \
            round(_de(_region_lab(r, fr), _region_lab(c, fr)), 1)

    def hue_hist(x):
        m = (x[..., 3] > 200).astype(np.uint8)
        hsv = cv2.cvtColor(x[..., :3], cv2.COLOR_BGR2HSV)
        hh = cv2.calcHist([hsv], [0, 1], m, [24, 8], [0, 180, 0, 256])
        return cv2.normalize(hh, None).flatten()
    out["hue_hist_correlation"] = round(float(cv2.compareHist(hue_hist(r), hue_hist(c), cv2.HISTCMP_CORREL)), 3)
    br, bc = _bbox(r[..., 3]), _bbox(c[..., 3])
    if br and bc:
        def face(x, b):
            x0, y0, x1, y1 = b
            hh = y1 - y0
            g = cv2.cvtColor(x[y0:y0 + int(0.17 * hh), x0:x1, :3], cv2.COLOR_BGR2GRAY)
            a = x[y0:y0 + int(0.17 * hh), x0:x1, 3]
            ys, xs = np.where(a > 200)
            if not len(ys):
                return None
            g = g[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            return cv2.resize(g, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
        fr_, fc_ = face(r, br), face(c, bc)
        if fr_ is not None and fc_ is not None:
            a_, b_ = fr_ - fr_.mean(), fc_ - fc_.mean()
            out["face_structure_ncc"] = round(float((a_ * b_).sum() / (np.sqrt((a_ ** 2).sum() * (b_ ** 2).sum()) + 1e-6)), 3)
        out["head_to_height_ratio"] = None
    de = [v for v in out["regions_dE"].values() if v is not None]
    worst = max(de) if de else 99
    bad = [k for k, v in out["regions_dE"].items() if v is not None and v > 30]
    hue = out["hue_hist_correlation"]
    if not bad and hue > 0.75:
        out["verdict"] = "CONSISTENT"
    elif len(bad) >= 2 or (hue < 0.3 and bad):
        out["verdict"] = "MISMATCH"
    else:
        out["verdict"] = "NEEDS_REVIEW"
    ncc = out.get("face_structure_ncc")
    if ncc is not None and ncc < 0.5 and out["verdict"] == "CONSISTENT":
        out["verdict"] = "NEEDS_REVIEW"
        out["notes"].append(f"the face region looks different (structure {ncc}) - a hand in front of the face, "
                            "or a changed face: look at it")
    if bad:
        out["notes"].append("colour differs in: " + ", ".join(bad))
    if hue < 0.45:
        out["notes"].append(f"overall colour mix differs (hue correlation {hue})")
        if out["verdict"] == "CONSISTENT":
            out["verdict"] = "NEEDS_REVIEW"
    out["worst_region_dE"] = round(worst, 1)
    out["note"] = "an automatic comparison - only the owner's eyes approve a character"
    return out


# ------------------------------------------------------------------------------------------- 4. complete poses


class ComplexPose:
    """a complete pose drawing standing on the scene's ground at the rig's BODY height (head top to soles - a raised
    hand does not count), its feet centred where the rig's feet are, colours brought to the reference's own colours
    (harmonize: a shift per colour group, the drawing's shading kept; nothing redrawn)"""

    def __init__(self, path, world_h, ref=None):
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"cannot read {path}")
        rgba = figure_rgba(img)
        self.colour = None
        if ref is not None:
            rgba, self.colour = harmonize(rgba, figure_rgba(ref))
        b = _bbox(rgba[..., 3])
        self.img = rgba[b[1]:b[3], b[0]:b[2]].copy()
        self.m = body_metrics(self.img[..., 3])
        self.world_h = world_h
        self.path = path

    def place(self, cam, wx, ground):
        s = cam.s * self.world_h / self.m["height"]
        sx, sy = cam.to_screen(wx, ground)
        x0 = int(round(sx - self.m["foot_cx"] * s))
        y0 = int(round(sy - self.m["bottom"] * s))
        return s, x0, y0

    def feet(self, cam, wx, ground):
        s, x0, y0 = self.place(cam, wx, ground)
        return [(x0 + (a + b) / 2 * s, y0 + y * s, (b - a) / 2 * s, 1.0) for a, b, y in self.m["feet"]]

    def draw(self, frame, cam, wx, ground, t=0.0, breathe=True):
        s, x0, y0 = self.place(cam, wx, ground)
        k = 1.0 + (0.004 * math.sin(2 * math.pi * t / 3.4) if breathe else 0.0)   # breathing from the feet
        w, h = max(1, int(round(self.img.shape[1] * s))), max(1, int(round(self.img.shape[0] * s * k)))
        im = cv2.resize(self.img, (w, h), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        y_sole = y0 + self.m["bottom"] * s
        return _paste(frame, im, x0, int(round(y_sole - self.m["bottom"] * s * k)))


def body_metrics(alpha):
    """head top (in the body's central band - a raised hand is not the head), soles, body height, the feet's centre
    and each foot's span on the ground. alpha: 2D mask (0-255 or bool)"""
    a = np.asarray(alpha) > (127 if np.asarray(alpha).dtype != bool else 0)
    ys, xs = np.where(a)
    bottom, top_any = int(ys.max()), int(ys.min())
    hh = bottom - top_any
    mid_rows = a[top_any + int(0.45 * hh):top_any + int(0.6 * hh)]
    cx = float(np.where(mid_rows)[1].mean()) if mid_rows.any() else float(xs.mean())
    band = a[:, max(0, int(cx - 0.07 * hh)):int(cx + 0.07 * hh)]
    top = int(np.where(band.any(axis=1))[0].min())
    foot_rows = a[bottom - max(3, int(0.035 * hh)):bottom + 1]
    fx = np.where(foot_rows.any(axis=0))[0]
    feet = []
    if len(fx):                                               # runs of columns = the feet on the ground
        start = prev = fx[0]
        for x in list(fx[1:]) + [None]:
            if x is None or x > prev + 3:
                feet.append((int(start), int(prev), bottom))
                start = x
            if x is not None:
                prev = x
    foot_cx = float(np.mean([(a_ + b_) / 2 for a_, b_, _ in feet])) if feet else cx
    return {"top": top, "bottom": bottom, "height": float(bottom - top), "foot_cx": foot_cx, "feet": feet,
            "centre_x": cx}


def harmonize(rgba, ref_rgba, regions=("hair", "face", "shirt", "trousers", "feet")):
    """per body region: the drawing's main colour group (pixels within dE 22 of the region's median, anywhere on the
    figure) is shifted to the reference's colour of that region. Ink lines, shading steps and every shape stay.
    Returns (new rgba, {"region": [dE before, dE after]})"""
    out = rgba.copy()
    lab = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2LAB).astype(np.float32)
    a = rgba[..., 3] > 200
    rep = {}
    taken = np.zeros(a.shape, bool)
    for name in regions:
        c, r = _region_lab(rgba, REGIONS[name]), _region_lab(ref_rgba, REGIONS[name])
        if c is None or r is None:
            continue
        before = _de(c, r)
        if before < 3.0:
            rep[name] = [round(before, 1), round(before, 1)]
            continue
        group = a & ~taken & (np.linalg.norm(lab - c, axis=2) < 22) & (lab[..., 0] > 60)
        if group.sum() < 50:
            continue
        lab[group] += (r - c)
        taken |= group
        rep[name] = [round(before, 1), None]
    lab = np.clip(lab, 0, 255).astype(np.uint8)
    out[..., :3] = np.where(taken[..., None], cv2.cvtColor(lab, cv2.COLOR_LAB2BGR), rgba[..., :3])
    for name in list(rep):
        if rep[name][1] is None:
            rep[name][1] = round(_de(_region_lab(out, REGIONS[name]), _region_lab(ref_rgba, REGIONS[name])), 1)
    return out, rep


def contact_shadow(img, feet, lights=None):
    """a small soft shadow under each foot that touches the ground (not one big oval): width of the foot, flattened,
    darker in the middle; a lifted foot casts a smaller, lighter one. Its strength follows the scene: the brighter the
    floor around the feet, the darker (more visible) the shadow."""
    if not feet:
        return img
    H_, W_ = img.shape[:2]
    xs = [f[0] for f in feet]
    ys = [f[1] for f in feet]
    x0, x1 = int(max(0, min(xs) - 80)), int(min(W_, max(xs) + 80))
    y0, y1 = int(max(0, min(ys) - 20)), int(min(H_, max(ys) + 24))
    if x1 <= x0 or y1 <= y0:
        return img
    floor = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2LAB)[..., 0].mean() / 255.0
    strength = float(np.clip(0.25 + 0.45 * floor, 0.22, 0.6))
    sh = np.zeros((H_, W_), np.float32)
    for cx, cy, hw, on in feet:
        if on <= 0.05:
            continue
        rx, ry = max(4.0, hw * (1.15 if on > 0.9 else 0.8)), max(2.5, hw * 0.2)
        cv2.ellipse(sh, (int(cx), int(cy + ry * 0.35)), (int(rx), int(ry)), 0, 0, 360, float(on), -1, cv2.LINE_AA)
    sh = cv2.GaussianBlur(sh, (0, 0), max(2.0, float(np.mean([f[2] for f in feet])) * 0.16))
    k = 1.0 - strength * np.clip(sh, 0, 1)[..., None]
    img[:] = np.clip(img.astype(np.float32) * k, 0, 255).astype(np.uint8)
    return img


def _foot_corners(p, s, rect):
    m = p.bone_world("foot_" + s)
    cr, sr = math.cos(math.radians(rect.get("rotation", 0))), math.sin(math.radians(rect.get("rotation", 0)))
    w, h = rect["width"] / 2.0 * rect.get("scaleX", 1), rect["height"] / 2.0 * rect.get("scaleY", 1)
    pts = []
    for dx, dy in ((-w, -h), (w, -h), (w, h), (-w, h)):
        lx, ly = rect.get("x", 0) + dx * cr - dy * sr, rect.get("y", 0) + dx * sr + dy * cr
        pts.append((m[0] * lx + m[2] * ly + m[4], m[1] * lx + m[3] * ly + m[5]))
    return pts


def rig_feet(rig, p, s, ox, oy, ground_y=None):
    """each rig foot's contact on screen: (centre x of the sole, the sole's own ground y, half width, contact 0..1).
    Every foot has its OWN ground line (in the three-quarter view the far foot stands higher); a foot on its line
    casts a full shadow, a lifted foot a fading one."""
    fd = _foot_data(rig)
    out = []
    for side in ("r", "l"):
        rect = fd[side]["rect"]
        if not rect:
            m = p.bone_world("foot_" + side)
            out.append((ox + m[4] * s, oy - fd[side]["rest_low"] * s, 12 * s, 1.0))
            continue
        pts = _foot_corners(p, side, rect)
        low = min(y for _x, y in pts)
        near = [x for x, y in pts if y < low + 0.35 * rect["height"]]   # the corners along the sole
        xs = [x for x, _y in pts]
        x_mid = (min(near) + max(near)) / 2 if near else (min(xs) + max(xs)) / 2
        hw = max(6.0, (max(xs) - min(xs)) / 2 * 0.62) * s
        lift = max(0.0, low - fd[side]["rest_low"])                    # rig px above its own ground
        on = float(np.clip(1.0 - lift / 40.0, 0.0, 1.0))
        out.append((ox + x_mid * s, oy - fd[side]["rest_low"] * s, hw, on))
    return out


def seat_from_pose(rig, limits, anim="sit_talk", t=0.6):
    """(seat top in rig px above the rig origin, seat centre x in rig px) under the thighs of the sitting pose"""
    from engine2.rigby import raster as RS
    p, _e = safe_pose(rig, anim, t, limits)
    f = np.zeros((1400, 1000, 3), np.uint8)
    legs = RS.draw(rig, p, f, 1.0, 500, 1250, only={"leg_r", "leg_l"}) > 0.4
    tops = []
    xs_all = []
    for side in ("r", "l"):
        hip, knee = p.bone_world("thigh_" + side), p.bone_world("shin_" + side)
        hx, hy = 500 + hip[4], 1250 - hip[5]
        kx, ky = 500 + knee[4], 1250 - knee[5]
        x_a, x_b = sorted((hx + 0.15 * (kx - hx), hx + 0.7 * (kx - hx)))
        for c in range(int(x_a), int(x_b) + 1):
            col = np.where(legs[:int(max(hy, ky) + 45), c])[0]
            if len(col):
                tops.append(col.max())
                xs_all.append(c)
    if not tops:
        return 112.0, 0.0
    seat_row = float(np.median(tops)) + 1.0                     # the seat touches the underside of the thighs
    return 1250.0 - seat_row, float(np.median(xs_all)) - 500.0


def production_gate(rows, needed):
    """production may use an action only if its decision is an owner-approved asset (or the camera). Returns the
    list of blocked actions with reasons - empty = allowed."""
    dec = {r["action"]: r for r in rows}
    blocked = []
    for a in needed:
        r = dec.get(a)
        if r is None:
            blocked.append((a, "unknown action"))
        elif r["method"] == "MISSING":
            blocked.append((a, "BLOCKED - " + r["reason"]))
        elif r["method"] != "camera" and not r.get("approved"):
            blocked.append((a, "BLOCKED - asset not approved by the owner: " + str(r["asset"])))
    return blocked


def _paste(frame, im, x0, y0):
    H_, W_ = frame.shape[:2]
    x1, y1 = x0 + im.shape[1], y0 + im.shape[0]
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(W_, x1), min(H_, y1)
    if cx0 >= cx1 or cy0 >= cy1:
        return np.zeros((H_, W_), np.float32)
    sub = im[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    a = sub[..., 3:4].astype(np.float32) / 255.0
    roi = frame[cy0:cy1, cx0:cx1].astype(np.float32)
    frame[cy0:cy1, cx0:cx1] = np.clip(roi * (1 - a) + sub[..., :3] * a, 0, 255).astype(np.uint8)
    full = np.zeros((H_, W_), np.float32)
    full[cy0:cy1, cx0:cx1] = a[..., 0]
    return full


# ------------------------------------------------------------------------------------------- 5. render test


def _label(img, txt, y=None, scale=0.62):
    y = y or img.shape[0] - 14
    cv2.putText(img, txt, (12, y), 0, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, txt, (12, y), 0, scale, (255, 255, 255), 1, cv2.LINE_AA)


def _mark(img):
    cv2.rectangle(img, (0, 0), (img.shape[1], 30), (20, 20, 20), -1)
    cv2.putText(img, MARK, (10, 21), 0, 0.56, (80, 200, 255), 1, cv2.LINE_AA)


def _atmos(env_, img, cam, t, lights):
    """the scene engine's fog / dust / light flicker (it works on a float frame)"""
    f = img.astype(np.float32)
    try:
        env_.atmosphere(f, cam, t, 0.0, lights)
    except Exception:
        return img
    return np.clip(f, 0, 255).astype(np.uint8)


def _voice(out_dir, secs):
    vs = os.path.join(ROOT, "assets", "voice_samples")
    if not os.path.isdir(vs):
        return None
    cands = sorted(f for f in os.listdir(vs) if f.endswith((".ogg", ".wav", ".mp3")))
    if not cands:
        return None
    v = os.path.join(out_dir, "voice_cut.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.6", "-t", str(secs), "-i", os.path.join(vs, cands[-1]),
                    "-ac", "1", "-ar", "16000", v])
    return v if os.path.exists(v) else None


def lipsync_info(how):
    """what the mouth movement really is - never claimed as Bengali phoneme alignment"""
    from engine2.rigby import face as FC
    rb = FC.rhubarb_bin()
    info = {"method": how, "rhubarb_binary": rb, "rhubarb_version": None}
    if rb:
        try:
            info["rhubarb_version"] = subprocess.run([rb, "--version"], capture_output=True, text=True,
                                                     timeout=30).stdout.strip()[:80]
        except Exception as e:
            info["rhubarb_version"] = f"could not run: {str(e)[:60]}"
    if "rhubarb" in str(how).lower():
        info["what_it_is"] = ("Rhubarb's language-independent phonetic recogniser: mouth shapes A-H/X from the sound "
                              "classes it hears. It is NOT a Bengali phoneme model; shapes are approximate.")
    else:
        info["what_it_is"] = ("AMPLITUDE: the mouth opens with the loudness of the voice. This is NOT phoneme or "
                              "viseme synchronisation.")
    return info


SCRIPT = [   # (action, seconds, location) - the ten MVP items; a MISSING action is left out (its time goes to the rest)
    ("neutral", 5.5, "house_interior"), ("talking", 8.0, "house_interior"), ("listening", 5.5, "house_interior"),
    ("pointing", 6.0, "house_interior"), ("one_arm_raised", 5.5, "house_interior"),
    ("both_arms_raised", 4.5, "house_interior"), ("scene_transition", 2.0, None), ("walking", 7.0, "road"),
    ("sitting", 7.0, "road"), ("scared", 5.0, "road"), ("neutral", 4.0, "road")]


def timeline(rows, script=None, total=60.0):
    """the video's timeline: MISSING actions are taken OUT (never shown as if done), the rest stretched to `total`"""
    dec = {r["action"]: r for r in rows}
    script = script or SCRIPT
    keep = [s for s in script if s[0] == "scene_transition" or dec.get(s[0], {}).get("method") != "MISSING"]
    left = [s[0] for s in script if s not in keep]
    fixed = sum(d for a, d, _ in keep if a == "scene_transition")
    flex = sum(d for a, d, _ in keep if a != "scene_transition")
    k = (total - fixed) / flex if flex else 1.0
    return [(a, (d if a == "scene_transition" else d * k), loc) for a, d, loc in keep], left


def render_test(cid="hari", out_root=None, log=print, preview=False, script=None, total=60.0, overlay=False):
    """the 60-second test video. overlay=False (default): CLEAN frames - no label, no watermark, no debug text (the
    'NOT APPROVED' status is in the file name, the report and the contact sheet). preview=True: 640x360, 12 fps."""
    import cinematic_camera as cc
    import location_library
    from environment_animation import Environment
    from engine2 import videoqa
    from engine2.rigby import armlift as AL
    from engine2.rigby import face as FC
    from engine2.rigby import raster as RS
    import cartoon_rig as CRg
    out = os.path.join(out_root or os.path.join(ROOT, "work", "render_test"), cid)
    os.makedirs(out, exist_ok=True)
    rdir = os.path.join(ROOT, "assets", "character_rigs", cid)
    rig = load_rig(cid)
    cfg = json.load(open(os.path.join(rdir, "prep.json")))
    info = json.load(open(os.path.join(rdir, "layers.json")))
    CW, CH = info["size"]
    ref = cv2.imread(os.path.join(ROOT, cfg["source"]), cv2.IMREAD_UNCHANGED)
    skin = ref[cfg["face"]["skin_at"][1], cfg["face"]["skin_at"][0], :3]
    face = FC.Face(rig, cfg["face"], (CW, CH), skin)
    report = {"character": cid, "approved": False, "human_visual_approval": "REQUIRED - nothing here is approved",
              "files": {}, "checks": {}, "problems": [], "limits": []}

    al_dir = os.path.join(out, "armlift")
    try:
        al = AL.run(os.path.join(rdir, "export", f"{cid}.json"), al_dir, log=lambda *a: None)
    except Exception as e:
        al = None
        report["problems"].append(f"arm-lift test could not run: {str(e)[:120]}")
    limits = rig_limits(rig, al)
    safety = anim_safety(rig, limits)
    inv = pose_inventory(cid)
    rows = decide(safety, inv)
    report["checks"]["rig_limits_degrees"] = limits
    report["checks"]["rig_animation_safety"] = safety
    report["checks"]["pose_inventory"] = {k: {x: v[x] for x in ("status", "approved", "source")} for k, v in inv.items()}
    report["decisions"] = rows
    report["production_gate"] = production_gate(rows, [a for a, _ in MVP_ACTIONS])
    dec = {r["action"]: r for r in rows}
    report["checks"]["waist_exposure"] = waist_exposure(rig)
    if report["checks"]["waist_exposure"]["max_px"] > 5:
        report["problems"].append(f"walk: a leg's hidden top shows at the waist ({report['checks']['waist_exposure']['max_px']} px)")

    ids = {}
    for pid, rec in inv.items():
        try:
            ids[pid] = identity(ref, cv2.imread(rec["file"], cv2.IMREAD_UNCHANGED))
        except Exception as e:
            ids[pid] = {"verdict": "ERROR", "error": str(e)[:100]}
    report["checks"]["identity_original_drawings"] = ids

    # one world scale for everything: the rig's BODY height (head top to soles) in world px
    k = 0.52
    union = np.zeros((CH, CW), np.uint8)
    for nm in info["order"]:
        union = np.maximum(union, cv2.imread(os.path.join(rdir, info["layers"][nm]["file"]), cv2.IMREAD_UNCHANGED)[..., 3])
    rest_m = body_metrics(union)
    world_h = rest_m["height"] * k
    sole = 45.0
    complete = {}
    for r in rows:
        if r["method"] in ("B_complete_pose", "C_static_pose") and isinstance(r["asset"], str):
            complete[r["action"]] = ComplexPose(inv[r["asset"]]["file"], world_h, ref)
    report["checks"]["colour_harmonised"] = {a_: {"asset": dec[a_]["asset"], "region_dE_before_after": cp.colour}
                                             for a_, cp in complete.items()}
    report["checks"]["identity_after_harmonise"] = {a_: identity(ref, cp.img) for a_, cp in complete.items()}

    vw, vh, fps = (640, 360, 12) if preview else (W, H, FPS)
    tl, left_out = timeline(rows, script, total)
    report["timeline"] = [{"action": a, "seconds": round(d, 2), "location": loc} for a, d, loc in tl]
    report["missing_actions"] = left_out
    total = sum(d for _, d, _ in tl)
    talk_start = 0.0
    for a, d, _l in tl:
        if a == "talking":
            break
        talk_start += d
    voice = _voice(out, 7.2)
    cues, how = FC.mouth_cues(voice, FPS, log) if voice else ([], "no voice sample")
    report["checks"]["lip_sync"] = lipsync_info(how)
    if "rhubarb" not in str(how).lower():
        report["limits"].append("lip-sync is AMPLITUDE-driven in this run (Rhubarb not available): the mouth opens "
                                "with loudness - NOT Bengali phoneme / viseme alignment")
    else:
        report["limits"].append("lip-sync uses Rhubarb's language-independent phonetic mode - approximate, NOT a "
                                "Bengali phoneme model")
    audio = os.path.join(out, "render_test_audio.wav")
    if voice and any(a == "talking" for a, _, _ in tl):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", str(talk_start + 0.4), "-i",
                        "anullsrc=r=16000:cl=mono", "-i", voice, "-filter_complex",
                        f"[0][1]concat=n=2:v=0:a=1,apad=whole_dur={total}", "-t", str(total), audio])
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", str(total), "-i",
                        "anullsrc=r=16000:cl=mono", audio])
    vid = os.path.join(out, f"{cid}_render_test_{'preview' if preview else '720p'}_NOT_APPROVED.mp4")
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                             "-r", str(fps), "-i", "-", "-i", audio, "-map", "0:v", "-map", "1:a",
                             "-vf", f"scale={vw}:{vh}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                             vid], stdin=subprocess.PIPE)
    stages = {}

    def stage(loc):
        if loc not in stages:
            stages[loc] = (Environment(location_library.spec_for(loc)), cc.Camera(W, H))
        return stages[loc]
    ground = 935.0
    x0 = 700.0
    speed = 2 * 78.0 / (0.60 * 1.1) * k
    # the scene is 1920 world px wide and the full shot shows ~1160 of it: a walk can cover at most ~800 px at the
    # feet's own speed - a longer walk is shortened (its time goes to the next scene), so he never leaves the set
    cap = 800.0 / speed
    for i_, (a_, d_, l_) in enumerate(tl):
        if a_ == "walking" and d_ > cap:
            extra_ = d_ - cap
            tl[i_] = (a_, cap, l_)
            j_ = next((j for j in range(i_ + 1, len(tl)) if tl[j][0] != "scene_transition"), None)
            if j_ is not None:
                tl[j_] = (tl[j_][0], tl[j_][1] + extra_, tl[j_][2])
    report["timeline"] = [{"action": a, "seconds": round(d, 2), "location": loc} for a, d, loc in tl]
    walk_dur = next((d for a, d, _ in tl if a == "walking"), 0.0)
    walk_x0 = 560.0
    J = {kk: (v[0] - CW / 2, CH - v[1]) for kk, v in cfg["joints"].items() if not kk.startswith("_")}
    # the seat: its top is put exactly under the THIGHS of the sitting pose (measured on the pose: the lowest leg
    # pixels between the hip and the knee), its centre between hip and knee, its legs down to the ground
    seat_rig, seat_x_rig = seat_from_pose(rig, limits)
    report["checks"]["seat_from_pose_rig_px"] = {"top_above_sole_line": round(seat_rig, 1), "centre_x": round(seat_x_rig, 1)}
    used, metrics, eased_frames, keyframes = {}, {}, 0, []
    prev_frame = None
    t0 = 0.0
    shadow_pair = None
    for idx_, (action, dur, loc) in enumerate(tl):
        n = int(round(dur * fps))
        d = dec.get(action, {"method": "camera"})
        for fi in range(n):
            u = fi / fps
            t = t0 + u
            if action == "scene_transition":
                a = fi / max(1, n - 1)
                nxt = tl[idx_ + 1][2] if idx_ + 1 < len(tl) else loc
                env_, cam = stage(nxt or "road")
                cam.set(x0 + 40, ground - 245, 1.65)
                img = env_.background(cam, t, 0.0, None)
                img = np.clip(img, 0, 255).astype(np.uint8) if img.dtype != np.uint8 else img
                pt = CRg.Painter(img, cam)
                lights = list(env_.draw_location(pt, t, 0.0, None) or [])
                img = _atmos(env_, img, cam, t, lights)
                frame = cv2.addWeighted(prev_frame, 1 - a, img, a, 0) if prev_frame is not None else img
                if fi == n - 1:
                    prev_frame = None
                if overlay:
                    _mark(frame)
                proc.stdin.write(frame.tobytes())
                used["camera"] = used.get("camera", 0) + 1
                continue
            env_, cam = stage(loc)
            wx = x0
            if action == "walking":                         # across the set, the camera following
                wx = walk_x0 + speed * u
            elif loc == "road" and walk_dur:
                wx = walk_x0 + speed * walk_dur
            cam.set(wx + 40, ground - 245, 1.65)               # ONE framing for every action: the same full shot
            img = env_.background(cam, t, 0.0, None)
            img = np.clip(img, 0, 255).astype(np.uint8) if img.dtype != np.uint8 else img
            pt = CRg.Painter(img, cam)
            lights = list(env_.draw_location(pt, t, 0.0, None) or [])
            meth = d["method"]
            s_ = cam.s * k
            sx0, sy0 = cam.to_screen(wx, ground)
            gy = sy0
            if meth.startswith("A_rig"):
                anim = d["asset"].split(":", 1)[1].split(" ")[0]
                seat = None
                if action == "sitting":
                    anim = "sit_down" if u < 1.4 else "sit_talk"
                    p, eased = safe_pose(rig, anim, u if u < 1.4 else u - 1.4, limits, loop=anim != "sit_down")
                    seat = (wx + seat_x_rig * k, ground - (seat_rig - sole) * k)
                else:
                    p, eased = safe_pose(rig, anim, u, limits)
                eased_frames += bool(eased)
                feet = rig_feet(rig, p, s_, sx0, sy0 + sole * s_, gy)
                if seat:                                       # the stool stands on the ground, its shadow too
                    stx, sty = seat
                    contact_shadow(img, [(cam.to_screen(stx, ground)[0], gy, 92 * s_, 1.0)])
                    pt.poly([(stx - 96 * k, sty), (stx + 96 * k, sty), (stx + 88 * k, sty + 18 * k),
                             (stx - 88 * k, sty + 18 * k)], (38, 64, 96))
                    for dx in (-76, 76):
                        pt.line((stx + dx * k, sty + 14 * k), (stx + dx * 1.12 * k, ground), (28, 50, 78), 10 * k)
                ns = img.copy() if (action == "neutral" and fi == n // 2 and shadow_pair is None) else None
                contact_shadow(img, feet)
                alpha = RS.draw(rig, p, img, s_, sx0, sy0 + sole * s_)
                shape = FC.shape_at(cues, t - talk_start - 0.4) if action == "talking" else "X"
                blink = 1.0 if (t % 3.3) < 0.11 else 0.0
                face.draw(img, p, s_, sx0, sy0 + sole * s_, shape, blink)
                if ns is not None:                             # the same frame without the contact shadows
                    RS.draw(rig, p, ns, s_, sx0, sy0 + sole * s_)
                    face.draw(ns, p, s_, sx0, sy0 + sole * s_, shape, blink)
                    shadow_pair = (ns, img.copy(), (int(sx0), int(gy)))
            else:
                cp = complete[action]
                contact_shadow(img, cp.feet(cam, wx, ground))
                alpha = cp.draw(img, cam, wx, ground, t)
            img = _atmos(env_, img, cam, t, lights)
            if fi < 6 and prev_frame is not None and idx_ > 0 and tl[idx_ - 1][2] == loc:
                img = cv2.addWeighted(prev_frame, 1 - (fi + 1) / 7.0, img, (fi + 1) / 7.0, 0)   # no hard pose jump
            used[meth] = used.get(meth, 0) + 1
            if fi >= 6 and alpha is not None and (alpha > 0.3).any():
                bm = body_metrics(alpha > 0.3)
                mm = metrics.setdefault(action, {"height": [], "sole_off": [], "edge": 0})
                mm["height"].append(bm["height"] / H)
                mm["sole_off"].append(bm["bottom"] - gy)
                xs_ = np.where((alpha > 0.3).any(axis=0))[0]
                mm["edge"] += int(xs_.min() <= 1 or xs_.max() >= W - 2)
            if fi == n // 2:
                keyframes.append((action, d["method"], d.get("asset"), img.copy()))
            prev_frame = img.copy()
            if overlay:
                _mark(img)
                _label(img, f"{action}: {meth}"[:96], scale=0.5)
            proc.stdin.write(img.tobytes())
        t0 += dur
    proc.stdin.close()
    proc.wait()
    report["files"]["video"] = vid
    q = videoqa.check(vid, W=vw, H=vh, fps=fps)
    report["checks"]["video_qa"] = q
    if not q["pass"]:
        report["problems"] += [f"video: {x}" for x in q["problems"]]
    # scale + ground consistency (sitting is shorter on purpose and is checked for ground only)
    sc = {a_: {"body_height_share": [round(min(v["height"]), 3), round(max(v["height"]), 3)],
               "sole_vs_ground_px": [int(min(v["sole_off"])), int(max(v["sole_off"]))]} for a_, v in metrics.items()}
    report["checks"]["scale_and_ground"] = sc
    if "neutral" in metrics:
        base = float(np.median(metrics["neutral"]["height"]))
        for a_, v in metrics.items():
            if a_ in ("sitting",):
                continue
            dev = max(abs(min(v["height"]) - base), abs(max(v["height"]) - base)) / base
            sc[a_]["height_vs_neutral_pct"] = round(100 * dev, 1)
            if dev > (0.04 if a_ != "walking" else 0.06):
                report["problems"].append(f"{a_}: body height differs from neutral by {100 * dev:.1f} %")
    for a_, v in metrics.items():
        sc[a_]["frames_touching_frame_edge"] = v["edge"]
        if v["edge"]:
            report["problems"].append(f"{a_}: the character touches the frame edge in {v['edge']} frames")
        if a_ == "sitting":
            continue
        if max(abs(x) for x in v["sole_off"]) > 4 and a_ != "walking":
            report["problems"].append(f"{a_}: the soles are {max(v['sole_off'], key=abs)} px off the ground")
    report["checks"]["frames_by_method"] = used
    report["checks"]["frames_with_arms_eased"] = eased_frames
    report["checks"]["overlay_in_video"] = bool(overlay)
    # contact sheet (labels ONLY here), with the left-out actions as their own tiles
    tiles = []
    for a_, m_, asset_, im in keyframes:
        tl_ = cv2.resize(im, (426, 240))
        _label(tl_, f"{a_} | {m_} | {asset_}"[:58], 22, 0.42)
        _label(tl_, "NOT APPROVED", 232, 0.42)
        tiles.append(tl_)
    for a_ in left_out:
        tl_ = np.full((240, 426, 3), 40, np.uint8)
        cv2.rectangle(tl_, (8, 8), (418, 232), (0, 0, 200), 3)
        _label(tl_, f"{a_}: MISSING / BLOCKED", 110, 0.6)
        _label(tl_, dec[a_]["reason"][:56], 150, 0.4)
        _label(tl_, "not in the video, not usable in production", 180, 0.4)
        tiles.append(tl_)
    while len(tiles) % 3:
        tiles.append(np.full((240, 426, 3), 30, np.uint8))
    sheet = np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)])
    sp = os.path.join(out, "render_test_contact_sheet.jpg")
    cv2.imwrite(sp, sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    report["files"]["contact_sheet"] = sp
    if isinstance(shadow_pair, tuple):                          # the same frame without / with the contact shadows
        a_, b_, (fx_, fy_) = shadow_pair
        crop = lambda im: im[max(0, fy_ - 150):min(H, fy_ + 40), max(0, fx_ - 160):min(W, fx_ + 160)]
        za, zb = (cv2.resize(crop(x), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC) for x in (a_, b_))
        pair = np.hstack([za, zb])
        _label(pair, "without contact shadow (200 %)", 24, 0.6)
        cv2.putText(pair, "with contact shadow", (za.shape[1] + 12, 24), 0, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(os.path.join(out, "ground_shadow_comparison.jpg"), pair, [cv2.IMWRITE_JPEG_QUALITY, 92])
        report["files"]["ground_shadow_comparison"] = os.path.join(out, "ground_shadow_comparison.jpg")
    report["files"]["armlift"] = al_dir
    report["not_approved_assets_used"] = sorted({str(dec[a_]["asset"]) for a_, _d, _l in tl if a_ in dec
                                                 and dec[a_]["method"] not in ("camera", "MISSING")})
    missing_rep = [{"action": a_, "status": "BLOCKED", "reason": dec[a_]["reason"],
                    "in_video": False, "production": "blocked until an owner-approved drawing exists"} for a_ in left_out]
    with open(os.path.join(out, "missing_pose_report.json"), "w", encoding="utf-8") as f:
        json.dump(missing_rep, f, ensure_ascii=False, indent=1)
    report["files"]["missing_pose_report"] = os.path.join(out, "missing_pose_report.json")
    report["technical_pass"] = not report["problems"]
    report["limits"] += [
        "complete pose drawings have no mouth / blink yet (their face marks are not prepared)",
        "no expression drawings exist: every face is neutral",
        "the rig's own talk / indicate / sit_talk lift the far arm past the safe limit; those arms are eased back",
    ]
    with open(os.path.join(out, "render_test_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    return report


def scale_sheet(cid="hari", out_root=None):
    """every available pose at ONE world scale on a plain floor, with the head line and the ground line"""
    from engine2.rigby import raster as RS
    rdir = os.path.join(ROOT, "assets", "character_rigs", cid)
    rig = RS.Rig(os.path.join(rdir, "export", f"{cid}.json"))
    info = json.load(open(os.path.join(rdir, "layers.json")))
    cfg = json.load(open(os.path.join(rdir, "prep.json")))
    ref = cv2.imread(os.path.join(ROOT, cfg["source"]), cv2.IMREAD_UNCHANGED)
    CW, CH = info["size"]
    union = np.zeros((CH, CW), np.uint8)
    for nm in info["order"]:
        union = np.maximum(union, cv2.imread(os.path.join(rdir, info["layers"][nm]["file"]), cv2.IMREAD_UNCHANGED)[..., 3])
    body = body_metrics(union)["height"]
    lim = rig_limits(rig)
    tiles, rows = [], []
    Ht, Wt, ground = 760, 400, 700
    s = 600.0 / body                                             # body height 600 px in every tile

    class _Cam:                                                  # a plain camera: world = screen
        def __init__(self):
            self.s = 1.0

        def to_screen(self, x, y):
            return x, y
    for name, anim in (("neutral", "idle"), ("talking", "talk"), ("listening", "listen"), ("walking", "walk")):
        f = np.full((Ht, Wt, 3), 236, np.uint8)
        p, _e = safe_pose(rig, anim, 0.3, lim)
        a = RS.draw(rig, p, f, s, Wt / 2, ground + 45 * s) > 0.3
        bm = body_metrics(a)
        rows.append((name, "rig", bm["height"], bm["bottom"]))
        tiles.append((name + " (rig)", f, bm))
    inv = pose_inventory(cid)
    for name, pid in (("pointing", "point_index"), ("one_arm_raised", "arm90"), ("one_arm_45", "arm45"),
                      ("both_arms_raised*", "both_up"), ("master*", "master")):
        if pid not in inv:
            continue
        cp = ComplexPose(inv[pid]["file"], 600.0, ref)
        f = np.full((Ht, Wt, 3), 236, np.uint8)
        a = cp.draw(f, _Cam(), Wt / 2, ground, breathe=False) > 0.3
        bm = body_metrics(a)
        rows.append((name, pid, bm["height"], bm["bottom"]))
        tiles.append((name + f" ({pid}{', FAILED check' if inv[pid]['status'] != 'passed' else ''})", f, bm))
    out_tiles = []
    for title, f, bm in tiles:
        cv2.line(f, (0, bm["top"]), (Wt, bm["top"]), (0, 0, 255), 1)
        cv2.line(f, (0, ground), (Wt, ground), (255, 0, 0), 1)
        _label(f, title[:40], 22, 0.45)
        _label(f, f"body {bm['height']:.0f}px  sole {bm['bottom']}", Ht - 12, 0.45)
        out_tiles.append(f)
    sheet = np.hstack(out_tiles)
    out = os.path.join(out_root or os.path.join(ROOT, "work", "render_test"), cid)
    os.makedirs(out, exist_ok=True)
    sp = os.path.join(out, "character_scale_comparison.jpg")
    cv2.imwrite(sp, sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return sp, rows


def walk_closeup_sheet(cid="hari", out_root=None):
    """the waist through the walk cycle at 300 %: before the hip-cap fix (originals kept) and now"""
    import shutil
    import tempfile
    from engine2.rigby import raster as RS
    rdir = os.path.join(ROOT, "assets", "character_rigs", cid)
    bk = os.path.join(rdir, "originals_before_hipcap", f"{cid}.png")
    rigs = [("now", RS.Rig(os.path.join(rdir, "export", f"{cid}.json")))]
    if os.path.exists(bk):
        tmp = tempfile.mkdtemp(prefix="hipcap_before_")
        for fn in os.listdir(os.path.join(rdir, "export")):
            shutil.copy(os.path.join(rdir, "export", fn), tmp)
        shutil.copy(bk, os.path.join(tmp, f"{cid}.png"))
        rigs.insert(0, ("before", RS.Rig(os.path.join(tmp, f"{cid}.json"))))
    rows = []
    for label, rig in rigs:
        tiles = []
        for u in (0.0, 0.06, 0.18, 0.25, 0.29, 0.5, 0.79):
            p = rig.pose("walk", u * rig.durations["walk"])
            f = np.full((1400, 1000, 3), 236, np.uint8)
            RS.draw(rig, p, f, 1.0, 500, 1250)
            z = cv2.resize(f[780:920, 360:520], None, fx=2.4, fy=2.4, interpolation=cv2.INTER_CUBIC)
            _label(z, f"{label} t={u:.2f}", 22, 0.5)
            tiles.append(z)
        rows.append(np.hstack(tiles))
    sheet = np.vstack(rows)
    out = os.path.join(out_root or os.path.join(ROOT, "work", "render_test"), cid)
    os.makedirs(out, exist_ok=True)
    sp = os.path.join(out, "walking_waist_closeups.jpg")
    cv2.imwrite(sp, sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return sp


# ------------------------------------------------------------------------------------------- engine audit / asset QA


def engine_audit():
    """a machine-readable snapshot of engine 2: what exists, what is approved, what each MVP action would use"""
    from engine2 import library as L
    from engine2.rigby import raster as RS
    out = {"flag_HYBRID_2D_MODE": os.environ.get("HYBRID_2D_MODE", "") or "OFF (unset)", "characters": {}}
    for cid in ("hari", "saraswati", "kishori"):
        c = {"rig": os.path.exists(os.path.join(ROOT, "assets", "character_rigs", cid, "export", f"{cid}.json")),
             "library": os.path.exists(os.path.join(ROOT, "assets", "character_library", cid, "manifest.json")),
             "owner_decision": L.approvals().get(cid)}
        c["complete_poses"] = {k: {x: v[x] for x in ("status", "approved", "source")} for k, v in pose_inventory(cid).items()}
        if c["rig"]:
            rig = RS.Rig(os.path.join(ROOT, "assets", "character_rigs", cid, "export", f"{cid}.json"))
            lim = rig_limits(rig)
            saf = anim_safety(rig, lim)
            c["rig_limits"] = lim
            c["rig_animation_safety"] = saf
            c["decisions_preview"] = decide(saf, pose_inventory(cid))
            c["decisions_production"] = decide(saf, pose_inventory(cid), production=True)
        out["characters"][cid] = c
    return out


def closeup_points(rgba):
    """where to look closely: every hand (skin-coloured pieces other than the face) and both shoulders / armpits
    (where the arm leaves the torso), found on THIS drawing - no fixed positions"""
    a = rgba[..., 3] > 127
    b = _bbox(rgba[..., 3])
    if b is None:
        return {}
    x0, y0, x1, y1 = b
    hh = y1 - y0
    lab = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2LAB).astype(np.int16)
    face = lab[y0 + int(0.08 * hh):y0 + int(0.14 * hh), x0:x1][a[y0 + int(0.08 * hh):y0 + int(0.14 * hh), x0:x1]]
    pts = {}
    if len(face):
        skin = np.median(face[(face[:, 1] > 135)] if (face[:, 1] > 135).sum() > 20 else face, axis=0)
        m = (np.abs(lab - skin).sum(axis=2) < 34) & a
        m[:y0 + int(0.17 * hh)] = False                          # below the head: hands only
        n, _l, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        big = sorted(range(1, n), key=lambda i: -st[i, cv2.CC_STAT_AREA])[:3]
        for k_, i in enumerate(big):
            if st[i, cv2.CC_STAT_AREA] > 0.0015 * a.sum():
                pts[f"skin_part_{k_ + 1}"] = (int(cen[i][0]), int(cen[i][1]))
        m2 = (np.abs(lab - skin).sum(axis=2) < 34) & a
        m2[y0 + int(0.17 * hh):] = False
        m2[:y0] = False
        n, _l, st, cen = cv2.connectedComponentsWithStats(m2.astype(np.uint8), 8)
        for i in range(1, n):                                    # a hand raised above / at the head
            if st[i, cv2.CC_STAT_AREA] > 0.0015 * a.sum() and abs(cen[i][0] - (x0 + x1) / 2) > 0.18 * (x1 - x0):
                pts[f"skin_part_top_{i}"] = (int(cen[i][0]), int(cen[i][1]))
    y = y0 + int(0.27 * hh)                                       # armpits: the gaps next to the torso on this row
    row = a[y, x0:x1]
    runs, on, st_ = [], False, 0
    for x, v in enumerate(row):
        if v and not on:
            on, st_ = True, x
        elif not v and on:
            on = False
            runs.append((st_, x))
    if on:
        runs.append((st_, len(row)))
    if runs:
        mid = (x1 - x0) / 2
        torso = min(runs, key=lambda r: abs((r[0] + r[1]) / 2 - mid))
        pts["shoulder_left"] = (x0 + torso[0], y)
        pts["shoulder_right"] = (x0 + torso[1], y)
    return pts


def asset_qa(cid="hari", out_root=None):
    """identity + figure checks of every complete pose, a cut-out preview of each, and a 200 % / 400 % close-up sheet"""
    out = os.path.join(out_root or os.path.join(ROOT, "work", "asset_qa"), cid)
    os.makedirs(out, exist_ok=True)
    from engine2 import library as L
    ref_path = os.path.join(ROOT, "assets", "character_library", cid, "v1", "reference", "original.png")
    ref = cv2.imread(ref_path, cv2.IMREAD_UNCHANGED)
    rep = {"character": cid, "reference": ref_path, "approved": False, "poses": {}}
    tiles = []
    for pid, rec in pose_inventory(cid).items():
        img = cv2.imread(rec["file"], cv2.IMREAD_UNCHANGED)
        rgba = figure_rgba(img)
        r = {"status": rec["status"], "approved": rec["approved"]}
        r["identity"] = identity(ref, img) if ref is not None else {"verdict": "NO_REFERENCE"}
        a = rgba[..., 3]
        n, _l, st, _c = cv2.connectedComponentsWithStats((a > 127).astype(np.uint8), 8)
        r["figure_pieces"] = int(n - 1)
        b = _bbox(a)
        r["figure_height_px"] = int(b[3] - b[1]) if b else 0
        r["touches_edge"] = bool(b and (b[0] <= 1 or b[1] <= 1 or b[2] >= a.shape[1] - 1 or b[3] >= a.shape[0] - 1))
        rep["poses"][pid] = r
        cut = np.full(img.shape[:2] + (3,), (40, 200, 60), np.uint8)       # green behind: holes / halos show
        al = a[..., None] / 255.0
        cut = (cut * (1 - al) + rgba[..., :3] * al).astype(np.uint8)
        t1 = cv2.resize(cut, (300, int(300 * cut.shape[0] / cut.shape[1])))
        _label(t1, f"{pid}: {r['identity']['verdict']}", 24, 0.5)
        tiles.append(t1)
        if b:                                                    # hand + shoulder close-ups at 200 % and 400 %
            crops = []
            for nm, (cx, cy) in closeup_points(rgba).items():
                cr = cut[max(0, cy - 90):cy + 90, max(0, cx - 90):cx + 90]
                if cr.size:
                    z2 = cv2.resize(cr, (360, 360), interpolation=cv2.INTER_CUBIC)
                    z4 = cv2.resize(cr[45:135, 45:135], (360, 360), interpolation=cv2.INTER_CUBIC) if cr.shape[0] >= 135 and cr.shape[1] >= 135 else z2
                    t_ = np.hstack([z2, z4])
                    _label(t_, f"{pid} {nm} 200% | 400%", 22, 0.5)
                    crops.append(t_)
            if crops:
                cv2.imwrite(os.path.join(out, f"closeups_{pid}.jpg"), np.vstack(crops), [cv2.IMWRITE_JPEG_QUALITY, 90])
    if tiles:
        hmax = max(t.shape[0] for t in tiles)
        tiles = [cv2.copyMakeBorder(t, 0, hmax - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30)) for t in tiles]
        cv2.imwrite(os.path.join(out, "cutout_sheet.jpg"), np.hstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 90])
    rep["note"] = "automatic checks only - nothing is approved by them"
    with open(os.path.join(out, "asset_qa_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1, default=str)
    return rep


# ------------------------------------------------------------------------------------------- walk waist check


def waist_exposure(rig, phases=24, scale=1.0):
    """per walk phase: leg pixels that show ABOVE the pelvis' lower edge outside the body (the hidden top of a leg
    swinging out = the 'black sliver at the waist'). Returns {"max_px", "per_phase", "worst_phase"}."""
    from engine2.rigby import raster as RS
    legs = {"leg_r", "leg_l", "foot_r", "foot_l"}
    others = {s.name for s in rig.sk.slots} - legs
    W_, H_, ox, oy = 1000, 1400, 500, 1250
    per = []
    for k in range(phases):
        t = rig.durations["walk"] * k / phases
        p = rig.pose("walk", t)
        f = np.zeros((H_, W_, 3), np.uint8)
        a_all = RS.draw(rig, p, f.copy(), scale, ox, oy) > 0.35
        a_no = RS.draw(rig, p, f.copy(), scale, ox, oy, only=others) > 0.35
        a_pel = RS.draw(rig, p, f.copy(), scale, ox, oy, only={"pelvis"}) > 0.9
        rows = np.where(a_pel.any(axis=1))[0]
        if not len(rows):
            per.append(0)
            continue
        edge = rows.max() - 12                                 # the pelvis' lower edge (above its soft fade)
        leg_only = a_all & ~a_no
        leg_only[edge:] = False
        per.append(int(leg_only.sum()))
    worst = int(np.argmax(per))
    return {"max_px": max(per), "per_phase": per, "worst_phase": worst,
            "worst_t": round(rig.durations["walk"] * worst / phases, 3)}
