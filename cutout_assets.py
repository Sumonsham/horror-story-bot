"""CUT-OUT ASSETS - the 2.5D character parts and background plates, made once, checked, kept for ever.

For every character of a story (from the character designer's record):
  1. body.png      one full-body picture (3/4 view, arms and legs apart) from the image provider (Cloudflare)
  2. heads         front / three-quarter / profile / scared heads, made WITH the body picture as reference
  3. background removed (plain grey studio) -> transparent PNGs
  4. AUTO-RIG: the body is cut into head, torso, upper arms, forearms (+hands), thighs, shins (+feet); every
     joint (neck, shoulders, elbows, wrists, hips, knees, ankles) is found from the shape; rest angles measured
  5. face landmarks (eyes, mouth, skin colour) of every head -> blinking + lip-sync are drawn on the real face
  6. QUALITY CHECK (asset_qa.py) on every picture; a failed picture is made again (new seed, max retries) - a
     picture that passed is never replaced by a worse one
Background plates: one EMPTY illustrated background per place (pond, road, jungle ...), checked (no people in it),
kept and reused.

The provider's free limit: the moment it says the limit is used up, generation PAUSES - everything finished stays,
the rest is written down as "pending" and is made by the next run. Nothing is retried in a loop, nothing paid.
Registry: assets/cartoon_parts/index.json (+ history.jsonl); every file is written atomically (tmp -> rename).
"""
import hashlib
import io
import json
import os
import time

import cv2
import numpy as np

import art_director as AD
import asset_qa as QA

BODY_W, BODY_H = 576, 1024
HEAD_W = 512
PLATE_W, PLATE_H = 1024, 576
VIEWS = ("three_q", "front", "profile", "scared")


class Paused(Exception):
    """the provider's free limit is used up: stop making pictures for this run (progress is kept)"""


def _is_limit(e):
    s = str(e).lower()
    return any(k in s for k in ("4006", "allocation", "quota", "neurons", "429", "rate limit", "used up"))


def char_key(rec):
    """the same name + the same look = the same character, for ever"""
    return hashlib.sha1(f"{str(rec.get('name', '')).strip().lower()}|{str(rec.get('look', '')).strip()}".encode()).hexdigest()[:12]


def _atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.replace(tmp, path)


def _png(arr):
    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        raise RuntimeError("png encode failed")
    return buf.tobytes()


def _decode(raw):
    arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("the provider returned no readable picture")
    return arr


# ====================================================================== background removal
def key_out(bgr, tol=34.0):
    """plain studio background -> alpha: the colour of the border is the background; only the big figure stays"""
    a = bgr.astype(np.float32)
    border = np.concatenate([a[:5].reshape(-1, 3), a[-5:].reshape(-1, 3), a[:, :5].reshape(-1, 3), a[:, -5:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    alpha = np.clip((dist - tol * 0.55) / (tol * 0.7), 0, 1)
    m = (alpha > 0.5).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        keep = (lab == big).astype(np.uint8)
        holes = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))   # fill small holes inside
        alpha = np.maximum(alpha * cv2.dilate(keep, np.ones((5, 5), np.uint8)), holes * (alpha > 0.15))
    alpha = cv2.GaussianBlur(alpha.astype(np.float32), (0, 0), 0.8)
    return np.dstack([bgr, (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])


# ====================================================================== AUTO-RIG: body -> parts + joints
def _runs(row):
    """[(x0, x1)] of the filled runs of one mask row"""
    d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0] - 1))


def auto_rig(rgba):
    """find the joints of a standing 3/4-view figure (facing right) and cut it into parts.
    Returns (rig dict, problems list). Every part: sprite RGBA + its pivot + its rest angle (rig convention:
    0 deg = straight down, positive = towards the facing side)."""
    probs = []
    m = rgba[..., 3] > 127
    ys, xs = np.where(m)
    if len(ys) < 2000:
        return None, ["the figure is missing or too small"]
    top, bot, left, right = ys.min(), ys.max(), xs.min(), xs.max()
    H = bot - top + 1
    rows = [(_runs(m[y]) if top <= y <= bot else []) for y in range(m.shape[0])]
    widths = np.array([sum(b - a + 1 for a, b in r) for r in rows], np.float32)
    # neck: the narrowest row between the chin and the shoulders (8-30 % of the height)
    lo, hi = top + int(0.08 * H), top + int(0.30 * H)
    seg = widths[lo:hi].copy()
    seg[seg == 0] = 1e9
    neck_y = lo + int(np.argmin(cv2.GaussianBlur(seg.reshape(-1, 1), (1, 9), 0).ravel()))
    nr = max(rows[neck_y], key=lambda r: r[1] - r[0]) if rows[neck_y] else (left, right)
    neck_x = (nr[0] + nr[1]) / 2.0
    head_h = neck_y - top
    if not (0.09 * H <= head_h <= 0.32 * H):
        probs.append(f"head height {head_h / H:.2f} of the body - unusual")
    # crotch: going up from the knees, the first row where the two legs join into one
    y = bot - 2                                        # the top of the block of rows (from the feet up) with 2 legs
    while y > top + int(0.38 * H) and len([r for r in rows[y] if r[1] - r[0] > 3]) >= 2:
        y -= 1
    found = y if bot - y > 0.08 * H else None
    if found is None or found > top + 0.56 * H:        # thighs hidden by a kurta / dhoti / saree: natural hip height
        crotch_y = top + int(0.52 * H)
        probs.append("the hips are under the clothes - hip joint at the natural height - unusual")
    else:
        crotch_y = found
    sep_row = (found + 3) if found is not None else None
    # torso core columns at the waist (the run that holds the neck column)
    waist_y = int(neck_y + 0.55 * (crotch_y - neck_y))
    core = min(rows[waist_y], key=lambda r: abs((r[0] + r[1]) / 2 - neck_x)) if rows[waist_y] else (int(neck_x - 20), int(neck_x + 20))
    tx0, tx1 = core
    shoulder_y = int(neck_y + 0.07 * H)
    # arms: pixels outside the torso core between the shoulders and the hand tips
    arms = {}
    for side, sel in (("far", lambda X: X < tx0 - 2), ("near", lambda X: X > tx1 + 2)):
        am = np.zeros_like(m)
        yy = np.arange(m.shape[0])[:, None]
        XX = np.arange(m.shape[1])[None, :]
        band = (yy >= shoulder_y) & (yy <= bot) & sel(XX) & m
        n, lab, st, _ = cv2.connectedComponentsWithStats(band.astype(np.uint8), 8)
        best = None
        for i in range(1, n):
            x_, y_, w_, h_, a_ = st[i]
            if y_ <= shoulder_y + 0.30 * H and h_ > 0.12 * H and a_ > 400:
                if best is None or a_ > st[best][4]:
                    best = i
        if best is None:
            probs.append(f"{side} arm not separate from the body")
            continue
        am = lab == best
        ay, ax = np.where(am)
        a_top, a_bot = ay.min(), ay.max()
        rows_w = [np.ptp(np.where(am[y])[0]) + 1 for y in range(a_top, a_bot + 1) if am[y].any()]
        wid = int(np.median(rows_w)) if rows_w else 12
        topx = float(np.where(am[a_top])[0].mean())
        if a_top > shoulder_y + 0.03 * H:                # the upper arm lies over / behind the chest: follow the
            cy_ = [y for y in range(a_top, a_top + max(4, int(0.5 * (a_bot - a_top)))) if am[y].any()]   # cartoon
            cx_ = [float(np.where(am[y])[0].mean()) for y in cy_]                                     # outlines
            k_, b_ = np.polyfit(cy_, cx_, 1) if len(cy_) > 3 else (0.0, topx)
            sy = float(shoulder_y + 0.02 * H)
            sx = float(np.clip(k_ * sy + b_, tx0 - wid, tx1 + wid))
            sh = (sx, sy)
            cap = np.zeros(m.shape, np.uint8)            # the arm's path from the shoulder down to its visible part
            cv2.line(cap, (int(sx), int(sy)), (int(topx), int(a_top)), 1, max(8, int(1.35 * wid)))
            cap = cap.astype(bool)
            gray = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2GRAY)
            lines = (gray < 70) & m
            n2, lab2, st2, _ = cv2.connectedComponentsWithStats((m & ~lines).astype(np.uint8), 4)
            tot = int(m.sum())
            grow = np.zeros_like(m)
            for i in range(1, n2):                       # regions enclosed by outlines that lie along the arm's path
                reg_ = lab2 == i
                ar = st2[i][4]
                if ar < 0.12 * tot and (reg_ & cap).sum() >= 0.6 * ar:
                    grow |= reg_
            grow |= cv2.dilate(grow.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & lines & cv2.dilate(
                cap.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
            am = am | grow
            a_top = int(np.where(am.any(axis=1))[0].min())
            if a_top > shoulder_y + 0.12 * H:
                probs.append(f"{side} arm crosses the body and its outline cannot be followed - it cannot be cut out cleanly")
        else:
            sh = (topx, float(a_top + 0.04 * H))
        elbow_y = int(a_top + 0.47 * (a_bot - a_top))
        wrist_y = int(a_bot - 0.11 * (a_bot - a_top))
        def cx(y):
            r = np.where(am[y])[0]
            return float(r.mean()) if len(r) else sh[0]
        arms[side] = {"mask": am, "shoulder": sh, "elbow": (cx(elbow_y), float(elbow_y)), "wrist": (cx(wrist_y), float(wrist_y)),
                      "top": a_top, "bot": a_bot}
    # legs: everything below the hips (minus the arms), split at the gap between the legs
    legs = {}
    lm = m.copy()
    lm[:crotch_y + 1] = False
    for a_ in arms.values():
        lm &= ~a_["mask"]
    rr = [r for r in rows[sep_row] if r[1] - r[0] > 3] if sep_row is not None and sep_row <= bot else []
    if len(rr) >= 2:
        rr = sorted(rr)[:2]
        sep = (rr[0][1] + rr[1][0]) / 2.0
    else:
        xs_l = np.where(lm)[1]
        sep = float(np.median(xs_l)) if len(xs_l) else neck_x
        probs.append("no gap between the legs - split at the middle - unusual")
    XX = np.arange(m.shape[1])[None, :]
    cloth_ov = 0 if len(rr) >= 2 else 7                # one cloth: the halves overlap a little (no gap ever shows)
    for side, gm in (("far", lm & (XX < sep + cloth_ov)), ("near", lm & (XX >= sep - cloth_ov))):
        gy, gx = np.where(gm)
        if len(gy) < 300:
            probs.append(f"{side} leg not found")
            continue
        g_bot = gy.max()
        knee_y = int(crotch_y + 0.5 * (g_bot - crotch_y))
        ankle_y = int(g_bot - 0.045 * H)

        def lx(y, gm=gm, gx=gx):
            r = np.where(gm[min(max(y, 0), gm.shape[0] - 1)])[0]
            return float(r.mean()) if len(r) else float(gx.mean())
        cloth = len(rr) < 2                              # one cloth (saree / dhoti / robe): both halves turn about
        hipx = sep if cloth else lx(crotch_y + 4)        # the SAME point - standing, they join exactly
        legs[side] = {"mask": gm, "hip": (hipx, float(crotch_y)), "knee": (lx(knee_y), float(knee_y)),
                      "ankle": (lx(ankle_y), float(ankle_y)), "bot": g_bot, "cloth": cloth}
    # parts (sprites with pivots), overlapping a little at the joints so no gap opens when they rotate
    ov = int(0.025 * H)
    full = rgba
    parts = {}

    def cut(mask, pivot, end, name, src=None):
        ys_, xs_ = np.where(mask)
        if len(ys_) < 50:
            probs.append(f"part '{name}' empty")
            return
        y0, y1, x0, x1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
        spr = (full if src is None else src)[y0:y1, x0:x1].copy()
        spr[..., 3] = (spr[..., 3] * mask[y0:y1, x0:x1]).astype(np.uint8)
        dx, dy = end[0] - pivot[0], end[1] - pivot[1]
        parts[name] = {"sprite": spr, "pivot": (pivot[0] - x0, pivot[1] - y0), "length": float(np.hypot(dx, dy)),
                       "rest": float(np.degrees(np.arctan2(dx, dy)))}
    yy = np.arange(m.shape[0])[:, None]
    head_mask = m & (yy <= neck_y + ov)
    arm_any = np.zeros_like(m)
    for a_ in arms.values():
        arm_any |= a_["mask"]
    leg_any = np.zeros_like(m)
    for g in legs.values():
        leg_any |= g["mask"]
    torso_rows = m & (yy >= neck_y - ov) & (yy <= crotch_y + 2 * ov)
    torso_mask = torso_rows.copy()                     # the torso keeps its full outline ...
    over = torso_rows & arm_any & (np.arange(m.shape[1])[None, :] >= tx0 - 2) & (np.arange(m.shape[1])[None, :] <= tx1 + 2)
    torso_src = full.copy()                            # ... but where an arm crossed in front of the chest, the chest
    if over.any():                                     # is painted back from the cloth around it (no ghost arm left)
        torso_src[..., :3] = cv2.inpaint(full[..., :3], cv2.dilate(over.astype(np.uint8), np.ones((5, 5), np.uint8)), 6,
                                         cv2.INPAINT_TELEA)
    torso_mask &= ~(arm_any & ~((np.arange(m.shape[1])[None, :] >= tx0 - 2) & (np.arange(m.shape[1])[None, :] <= tx1 + 2)))
    hip_c = ((legs["far"]["hip"][0] + legs["near"]["hip"][0]) / 2 if len(legs) == 2 else neck_x, float(crotch_y))
    cut(head_mask, (neck_x, float(neck_y)), (neck_x, float(top)), "head")
    cut(torso_mask, hip_c, (neck_x, float(neck_y)), "torso", src=torso_src)
    for side, a_ in arms.items():
        am = a_["mask"]
        ey = a_["elbow"][1]
        cut(am & (yy <= ey + ov), a_["shoulder"], a_["elbow"], f"uarm_{side}")
        cut(am & (yy >= ey - ov), a_["elbow"], a_["wrist"], f"farm_{side}")
    for side, g in legs.items():
        gm = g["mask"] | (m & (yy >= crotch_y - ov) & (yy <= crotch_y + ov) & ~arm_any
                          & (np.abs(np.arange(m.shape[1])[None, :] - g["hip"][0]) < (tx1 - tx0) * 0.35))
        ky = g["knee"][1]
        cut(gm & (yy <= ky + ov), g["hip"], g["knee"], f"thigh_{side}")
        cut(gm & (yy >= ky - ov), g["knee"], g["ankle"], f"shin_{side}")
    rig = {"height_px": float(H), "top": float(top), "bottom": float(bot), "neck": (neck_x, float(neck_y)), "hip": hip_c,
           "shoulder_y": float(shoulder_y), "torso_len": float(np.hypot(neck_x - hip_c[0], neck_y - hip_c[1])),
           "head_h": float(head_h), "parts": parts,
           "shoulders": {s: a_["shoulder"] for s, a_ in arms.items()},
           "leg_hips": {s: g["hip"] for s, g in legs.items()},
           "arm_free": {s: bool(f"uarm_{s}" in parts and f"farm_{s}" in parts and
                                (parts[f"uarm_{s}"]["length"] + parts[f"farm_{s}"]["length"]) / H >= 0.28) for s in ("near", "far")}}
    for s_, free in rig["arm_free"].items():
        if not free and f"uarm_{s_}" in parts:
            probs.append(f"{s_} arm is partly drawn over the body - it moves only a little (no ghost arm) - unusual")
    return rig, probs


# ====================================================================== face landmarks on a head picture
def cartoon_eyes(rgba):
    """cartoon eyes: white blobs (the sclera) with a dark pupil inside, in the upper-middle of the head"""
    m = rgba[..., 3] > 127
    ys, xs = np.where(m)
    if not len(ys):
        return []
    top, bot = ys.min(), ys.max()
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2HSV)
    white = ((hsv[..., 2] > 195) & (hsv[..., 1] < 45) & m).astype(np.uint8)
    yy = np.arange(m.shape[0])[:, None]
    white &= ((yy > top + 0.2 * (bot - top)) & (yy < top + 0.7 * (bot - top))).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(white, 8)
    hh = bot - top
    eyes = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if not (0.0004 * hh * hh < a < 0.03 * hh * hh) or w > 3.5 * h or h > 3 * w:
            continue
        box = rgba[y:y + h, x:x + w, :3]
        dark = (cv2.cvtColor(box, cv2.COLOR_BGR2GRAY) < 70).mean() if box.size else 0
        grown = cv2.dilate((lab == i).astype(np.uint8), np.ones((5, 5), np.uint8))
        ring = rgba[..., :3][grown.astype(bool) & ~(lab == i)]
        if dark > 0.02 or (len(ring) and (ring.mean(axis=1) < 70).mean() > 0.15):      # a pupil / an outlined eye
            eyes.append((float(cen[i][0]), float(cen[i][1]), float(a)))
    eyes = sorted(eyes, key=lambda e: -e[2])[:2]
    return sorted([(e[0], e[1]) for e in eyes])


def face_marks(rgba, view):
    """eyes / mouth / skin of a head sprite: OpenCV face finder first, the head's own shape otherwise"""
    m = rgba[..., 3] > 127
    ys, xs = np.where(m)
    top, bot, left, right = ys.min(), ys.max(), xs.min(), xs.max()
    hh = bot - top
    neck_y = top + int(0.80 * hh)
    box = None
    try:
        import animate
        f = animate.find_faces(cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2RGB))
        if f:
            b = max(f, key=lambda x: x["box"][2])["box"]
            box = [int(v) for v in b]
    except Exception:
        box = None
    hw = right - left
    ce = cartoon_eyes(rgba) if not box else []
    if not box and ce:                                  # the cartoon eye-finder found the eyes
        ex_ = [e[0] for e in ce]
        ey_ = float(np.mean([e[1] for e in ce]))
        span = (max(ex_) - min(ex_)) if len(ce) == 2 else 0.22 * hw
        cxm = float(np.mean(ex_)) + (0.08 * hw if len(ce) == 1 else 0.0)
        eyes = [(e[0], e[1]) for e in ce]
        mouth = (cxm, ey_ + 1.05 * max(span, 0.18 * hw))
        fw = max(span * 2.3, 0.45 * hw)
        box = [0, 0, 0, 0]                              # (found - by the cartoon finder)
    elif box:
        x, y, w, h = box
        eyes = [(x + 0.32 * w, y + 0.42 * h), (x + 0.68 * w, y + 0.42 * h)]
        mouth = (x + 0.5 * w, y + 0.78 * h)
        fw = w
    else:                                               # no face found: proportions of a cartoon head
        shift = {"front": 0.5, "three_q": 0.58, "scared": 0.58, "profile": 0.72}.get(view, 0.55)
        cxh = left + shift * hw
        eyes = ([(cxh - 0.16 * hw, top + 0.45 * hh), (cxh + 0.16 * hw, top + 0.45 * hh)] if view == "front" else
                [(cxh + 0.05 * hw, top + 0.45 * hh)] + ([] if view == "profile" else [(cxh - 0.2 * hw, top + 0.45 * hh)]))
        mouth = (cxh + (0.12 * hw if view == "profile" else 0.03 * hw), top + 0.66 * hh)
        fw = 0.62 * hw
    if view == "profile" and len(eyes) > 1:
        eyes = eyes[1:]
    cx_, cy_ = int(mouth[0] - 0.18 * fw), int(mouth[1] - 0.12 * fw)
    patch = rgba[max(0, cy_ - 6):cy_ + 6, max(0, cx_ - 6):cx_ + 6]
    px = patch[patch[..., 3] > 200][:, :3] if patch.size else np.zeros((0, 3))
    skin = tuple(int(v) for v in (np.median(px, axis=0) if len(px) else (110, 150, 196)))
    return {"eyes": [tuple(map(float, e)) for e in eyes], "mouth": tuple(map(float, mouth)), "face_w": float(fw),
            "skin": skin, "found_face": bool(box), "neck": (float((left + right) / 2), float(bot))}


# ====================================================================== registry
class Registry:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.index_path = os.path.join(root, "index.json")
        try:
            self.index = json.load(open(self.index_path, encoding="utf-8"))
        except Exception:
            self.index = {"characters": {}, "plates": {}}

    def save(self):
        _atomic(self.index_path, json.dumps(self.index, ensure_ascii=False, indent=1))

    def history(self, ev):
        with open(os.path.join(self.root, "history.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ev, t=time.strftime("%Y-%m-%d %H:%M:%S")), ensure_ascii=False) + "\n")

    def char_dir(self, key):
        d = os.path.join(self.root, key)
        os.makedirs(d, exist_ok=True)
        return d

    def ready(self, key):
        r = self.index["characters"].get(key)
        return bool(r and r.get("status") == "ready")


# ====================================================================== making the assets
class Maker:
    """image_fn(prompt, ref_path, seed, w, h) -> picture bytes (raises on failure; a limit error PAUSES)"""

    def __init__(self, registry, image_fn, log=print, retries=2, budget=30):
        self.reg, self.image_fn, self.log, self.retries, self.budget = registry, image_fn, log, retries, budget
        self.made = 0
        self.paused = False

    def _pic(self, prompt, ref, seed, w, h):
        if self.paused:
            raise Paused("already paused")
        if self.made >= self.budget:
            self.paused = True
            raise Paused(f"this run's picture budget ({self.budget}) is used - the rest comes next run")
        try:
            raw = self.image_fn(prompt, ref, seed, w, h)
        except Exception as e:
            if _is_limit(e):
                self.paused = True
                raise Paused(str(e)[:120])
            raise
        self.made += 1
        return _decode(raw)

    PART_SIZE = {"torso": (576, 640), "arm": (384, 1024), "legs": (576, 768), "skirt": (576, 896), "pallu": (384, 896),
                 "hair_back": (448, 768)}

    def _try(self, idx, rec, name, prompt, ref, seed, w, h, check, log_name):
        """one picture with its check and limited retries; returns the keyed RGBA that passed, or None"""
        for att in range(self.retries + 1):
            idx["attempts"][name] = idx["attempts"].get(name, 0) + 1
            img = self._pic(prompt, ref, seed + 101 * att, w, h)
            rgba = key_out(img)
            qa = check(rgba)
            idx["qa"][name] = qa
            self.reg.history({"char": rec.get("name"), "asset": name, "attempt": att + 1, "pass": qa["pass"], "problems": qa["problems"]})
            if qa["pass"]:
                return img, rgba
            self.log(f"    {rec.get('name')}: {log_name} failed the check ({'; '.join(qa['problems'][:2])})"
                     + (" - again" if att < self.retries else ""))
        return None, None

    def character(self, rec):
        """make (or finish) one character: the full-body REFERENCE, the separate torso / arm / legs pieces, the heads;
        then the puppet is REBUILT from the pieces (or, if a piece failed, cut from the reference as before)"""
        key = char_key(rec)
        idx = self.reg.index["characters"].setdefault(key, {"name": rec.get("name"), "look": rec.get("look", "")[:600],
                                                            "ghost": bool((rec.get("design") or {}).get("ghost")),
                                                            "status": "pending", "files": {}, "qa": {}, "attempts": {}})
        if idx.get("status") == "ready":
            return idx
        if idx.get("status") == "failed" and idx["attempts"].get("body", 0) >= 6:
            idx["note"] = "6 pictures failed the check - this character stays code-drawn until its look is changed"
            return idx                                     # never waste the free limit on the same failure every day
        d = self.reg.char_dir(key)
        seed0 = int(key[:6], 16) % 100000
        try:
            if "body" not in idx["files"]:                 # 1) the full-body reference
                img, rgba = self._try(idx, rec, "body", AD.character_prompt(rec), None, seed0, BODY_W, BODY_H, QA.reference,
                                      "full-body picture")
                if rgba is None:
                    idx["status"] = "failed"
                    return idx
                _atomic(os.path.join(d, "body.png"), _png(rgba))
                _atomic(os.path.join(d, "body_src.png"), _png(img))
                idx["files"]["body"] = "body.png"
            ref = os.path.join(d, "body_src.png")
            body_rgba = cv2.imread(os.path.join(d, "body.png"), cv2.IMREAD_UNCHANGED)
            import asset_plan
            import consistency
            import cutout_rebuild as RB
            plan = asset_plan.plan(rec.get("design") or {})  # THIS character's pieces (saree, ghost, child ...)
            idx["plan"] = {k: plan[k] for k in ("archetype", "pieces", "child", "floats")}
            cut_rig, cut_probs = auto_rig(body_rgba)
            M = RB.measure(body_rgba, cut_rig)
            for part in plan["pieces"]:                    # 2) the separate pieces, each from the reference
                if part in idx["files"] or idx["attempts"].get(part, 0) >= 6:
                    continue
                w, h = self.PART_SIZE[part]
                img, rgba = self._try(idx, rec, part, AD.part_prompt(rec, part), ref, seed0 + 7 + len(part), w, h,
                                      lambda x, p_=part: QA.part(x, p_, body_rgba, M, wide=plan["wide_sleeves"], ghost=idx["ghost"]),
                                      f"{part} piece")
                if rgba is not None:
                    _atomic(os.path.join(d, f"piece_{part}.png"), _png(rgba))
                    idx["files"][part] = f"piece_{part}.png"
            for view in VIEWS:                             # 3) the heads, made from the reference
                if view in idx["files"] or idx["attempts"].get(view, 0) >= 6:
                    continue
                master = cv2.imread(os.path.join(d, "head_three_q.png"), cv2.IMREAD_UNCHANGED) if "three_q" in idx["files"] else None
                mm = json.load(open(os.path.join(d, "head_three_q.json"))) if master is not None else None

                def hcheck(x, v=view, master=master, mm=mm):
                    mk = face_marks(x, v) if (x[..., 3] > 127).sum() > 1500 else None
                    q = QA.head(x, mk, body_rgba, v, ghost=idx["ghost"])
                    if mk is not None:                     # the same face: skin, hair, colours vs the master head
                        c = consistency.check_head(x, body_rgba, M, master if v != "three_q" else None, mk, mm, ghost=idx["ghost"])
                        q["consistency"] = c["metrics"]
                        q["problems"] = q["problems"] + c["problems"]
                        q["pass"] = q["pass"] and not c["problems"]
                    q["_marks"] = mk
                    return q
                img, rgba = self._try(idx, rec, view, AD.head_prompt(rec, view), ref, seed0 + 13 + len(view), HEAD_W, HEAD_W,
                                      hcheck, f"{view} head")
                if rgba is not None:
                    marks = idx["qa"][view].pop("_marks", None)
                    _atomic(os.path.join(d, f"head_{view}.png"), _png(rgba))
                    _atomic(os.path.join(d, f"head_{view}.json"), json.dumps(marks))
                    idx["files"][view] = f"head_{view}.png"
                else:
                    idx["qa"].get(view, {}).pop("_marks", None)
            # 4) the puppet: rebuilt from the pieces, else cut from the reference
            rig, method = None, None
            if all(p in idx["files"] for p in plan["pieces"]):
                pieces = {p: cv2.imread(os.path.join(d, idx["files"][p]), cv2.IMREAD_UNCHANGED) for p in plan["pieces"]}
                r_, probs = RB.rebuild(body_rgba, cut_rig, pieces, plan)
                qa = QA.body(body_rgba, r_, probs)
                idx["qa"]["rig_rebuilt"] = qa
                if qa["pass"]:
                    rig, method = r_, "rebuilt"
            if rig is None:
                qa = QA.body(body_rgba, cut_rig, cut_probs)
                idx["qa"]["rig_cut"] = qa
                if qa["pass"]:
                    rig, method = cut_rig, "cut"
            if rig is not None:
                rig["method"] = method
                self._save_rig(d, rig)
                idx["rig_method"] = method
            have = [v for v in VIEWS if v in idx["files"]]
            if rig is not None and ("three_q" in have or "front" in have):
                idx["status"] = "ready"
            elif rig is None and all(p in idx["attempts"] for p in plan["pieces"]):
                idx["status"] = "failed"
            else:
                idx["status"] = "partial"
        except Paused as e:
            idx["status"] = "pending" if "body" not in idx["files"] else "partial"
            idx["paused"] = str(e)
            self.log(f"    picture making PAUSED ({str(e)[:80]}) - {rec.get('name')} is kept as '{idx['status']}', "
                     f"the next run continues")
        finally:
            self.reg.save()
        return idx

    @staticmethod
    def _save_rig(d, rig):
        meta = {k: v for k, v in rig.items() if k != "parts"}
        meta["parts"] = {}
        for name, p in rig["parts"].items():
            _atomic(os.path.join(d, f"part_{name}.png"), _png(p["sprite"]))
            meta["parts"][name] = {"file": f"part_{name}.png", "pivot": list(p["pivot"]), "length": p["length"], "rest": p["rest"]}
        _atomic(os.path.join(d, "rig.json"), json.dumps(meta, indent=1))

    def plate(self, loc, weather=None):
        """one EMPTY illustrated background per place (reused for ever)"""
        key = loc + ("_rain" if (weather or {}).get("rain") else "")
        rec = self.reg.index["plates"].setdefault(key, {"status": "pending", "attempts": 0})
        if rec.get("status") == "ready":
            return rec
        try:
            for att in range(self.retries + 1):
                rec["attempts"] += 1
                img = self._pic(AD.plate_prompt(loc, weather), None, 7000 + 31 * att + len(key), PLATE_W, PLATE_H)
                qa = QA.plate(img)
                self.reg.history({"plate": key, "attempt": att + 1, "pass": qa["pass"], "problems": qa["problems"]})
                rec["qa"] = qa
                if qa["pass"]:
                    _atomic(os.path.join(self.reg.root, f"plate_{key}.png"), _png(img))
                    rec.update(status="ready", file=f"plate_{key}.png")
                    break
            else:
                rec["status"] = "failed"
        except Paused as e:
            rec["paused"] = str(e)
        finally:
            self.reg.save()
        return rec


def ensure_cast(records, registry, image_fn, log=print, budget=30, places=()):
    """every character of the story (+ the places' plates): make what is missing. Returns a report."""
    mk = Maker(registry, image_fn, log=log, budget=budget)
    rep = {"characters": {}, "plates": {}, "paused": False, "made": 0}
    for rec in records:
        r = mk.character(rec)
        rep["characters"][rec.get("name")] = {"key": char_key(rec), "status": r["status"],
                                              "problems": [p for q in r.get("qa", {}).values() for p in q.get("problems", [])][:6]}
        if mk.paused:
            break
    for loc, w in places:
        if mk.paused:
            break
        r = mk.plate(loc, w)
        rep["plates"][loc] = r.get("status")
    for rec in records:                                    # what was not reached is reported, never hidden
        rep["characters"].setdefault(rec.get("name"), {"key": char_key(rec), "status": registry.index["characters"].get(
            char_key(rec), {}).get("status", "pending"), "problems": ["not reached this run (paused)"]})
    rep["paused"], rep["made"] = mk.paused, mk.made
    return rep
