"""POSE_FIRST_CHARACTER_PIPELINE - design the character FOR animation before anything is cut.

Character reference -> high-resolution master artwork -> complete pose drawings -> artwork validation ->
(owner looks) -> body-part separation -> hidden-region reconstruction -> layers -> rig -> animation -> visual QA ->
owner approval.

This module does the first three steps for ONE character (Hari first) and checks the results:
  * every pose is its OWN complete picture of the whole character (never several poses in one picture that is
    cropped afterwards), drawn from the ORIGINAL reference picture as the identity
  * size: 1280 x 1920 for a figure, 1024 x 1024 for a hand. Cloudflare's flux-2-klein-4b allows at most 1920 px per
    side (its documentation: width and height 256-1920), so 2048 x 3072 is NOT possible with this provider; a bigger
    master can be supplied by hand (inbox, below) and is then used instead
  * the reference picture is sent shrunk to fit inside 511 x 511 (the documentation: input images must be smaller
    than 512 x 512)
  * PROVIDER-INDEPENDENT: a picture the owner puts into assets/character_art/<id>/inbox/<pose>.png (any size, a
    transparent PNG or a plain light background) is used instead of generating that pose - no API call at all
  * resumable: a picture that passed is never drawn again; an HTTP 429 / free-limit stops the run cleanly; an attempt
    is counted only when a picture really came back; at most 2 attempts per pose per run and 4 in total
  * NOTHING is approved here: index.json says approved = false until the owner approves
"""
import json
import os
import shutil

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_W, FIG_H = 1280, 1920
HAND_W, HAND_H = 1024, 1024
MIN_FIG_H = 1450                    # px: a figure smaller than this is not a high-resolution master

LOOK = ("high-resolution character artwork made for 2D cut-out animation: crisp clean black outlines of even thickness, "
        "flat colours with the same soft cel shading as the reference, every finger, elbow, wrist, knee and ankle clearly "
        "drawn, the WHOLE body inside the picture with wide empty margins all round (nothing cut off), plain flat light "
        "grey background, no floor shadow, no other objects, no text, no watermark")
VIEW = "seen in three-quarter view turned to the RIGHT exactly like the reference picture"
LEFT_ARM = "the arm on the LEFT side of the picture (the character's right arm)"
RIGHT_ARM = "the arm on the RIGHT side of the picture (the character's left arm)"

# (id, group, kind, the pose in words)
POSES = [
    ("master", "core", "figure", f"{VIEW}, standing in a RIGGING POSE: both arms held about 40 degrees away from the body with clear "
     "background between each arm and the body, elbows slightly bent, both hands open with all five fingers separated, the "
     "shoulders and armpits clearly visible, legs slightly apart with a clear gap between them, both feet flat and fully visible"),
    ("arm45", "core", "figure", f"{VIEW}, standing, the whole character from head to feet, {LEFT_ARM} raised sideways away from the body to 45 degrees (the hand at chest "
     "height, well away from the body), elbow almost straight, open hand; the other arm relaxed by the side; the armpit and the "
     "side of the shirt under the raised arm completely drawn"),
    ("arm90", "core", "figure", f"{VIEW}, standing, {LEFT_ARM} raised straight out sideways to shoulder height, horizontal, open hand "
     "palm down; the other arm relaxed by the side; the armpit and the side of the shirt under the raised arm completely drawn"),
    ("arm120", "core", "figure", f"{VIEW}, standing, {LEFT_ARM} raised high, about 120 degrees, the hand above the level of the head, "
     "open hand; the other arm relaxed by the side; the armpit, the shoulder and the sleeve completely drawn"),
    ("both_up", "core", "figure", f"{VIEW}, standing, BOTH arms raised high above the head, open hands, the armpits and the shirt "
     "under both arms completely drawn"),
    ("point_index", "core", "figure", f"{VIEW}, standing and POINTING: {RIGHT_ARM} stretched straight forward at shoulder height, "
     "the hand pointing with ONLY the index finger extended, the other three fingers curled into the palm and the thumb "
     "tucked; the other arm relaxed by the side"),
    ("relaxed", "arms", "figure", f"{VIEW}, standing relaxed, both arms hanging naturally a little away from the body, open hands"),
    ("arm_forward", "arms", "figure", f"{VIEW}, standing, {RIGHT_ARM} stretched straight forward at chest height, open hand, palm down"),
    ("both_open", "arms", "figure", f"{VIEW}, standing, both forearms raised in front of the body, both hands open with the palms "
     "up in an explaining gesture"),
    ("wave", "arms", "figure", f"{VIEW}, standing and WAVING: {RIGHT_ARM} raised with the elbow bent, the open hand beside the head, "
     "palm facing the viewer, fingers apart"),
    ("hand_chest", "arms", "figure", f"{VIEW}, standing, {LEFT_ARM} bent so that the hand rests flat on the chest, the other arm "
     "relaxed"),
    ("leg_left_up", "legs", "figure", f"{VIEW}, standing on one leg: the leg on the RIGHT side of the picture lifted with the knee "
     "bent forward, the foot off the ground; arms slightly out for balance"),
    ("leg_right_up", "legs", "figure", f"{VIEW}, standing on one leg: the leg on the LEFT side of the picture lifted with the knee "
     "bent forward, the foot off the ground; arms slightly out for balance"),
    ("step_left", "legs", "figure", f"{VIEW}, mid-step: the leg on the RIGHT side of the picture forward with the heel on the "
     "ground, the other leg behind on its toes, arms swinging opposite"),
    ("step_right", "legs", "figure", f"{VIEW}, mid-step: the leg on the LEFT side of the picture forward with the heel on the "
     "ground, the other leg behind on its toes, arms swinging opposite"),
    ("knees_bent", "legs", "figure", f"{VIEW}, standing with both knees bent in a half-crouch, back straight, arms relaxed"),
    ("sit_stool", "legs", "figure", f"{VIEW}, SITTING on a plain low wooden stool: thighs horizontal, knees bent, both feet flat on "
     "the floor, hands resting on the knees (the stool is the only object)"),
    ("stand_up", "legs", "figure", f"{VIEW}, getting up from a low wooden stool: leaning forward, hips just above the stool, hands "
     "pushing on the knees (the stool is the only object)"),
]
HANDS = [("relaxed", "a relaxed open hand, fingers gently curved"), ("open_palm", "an open hand, palm facing the viewer, all "
         "five fingers spread"), ("point", "a pointing hand: ONLY the index finger extended, the other fingers curled into the "
         "palm, the thumb tucked"), ("wave", "a waving hand, palm out, fingers apart, slightly tilted"), ("fist", "a closed "
         "fist"), ("hold", "a hand holding a small round object (a cup) from the side"), ("fear", "a hand raised in fear, fingers "
         "stiff and spread"), ("namaste", "two hands pressed together palm to palm in namaste")]
for _h, _t in HANDS:
    POSES.append((f"hand_{_h}", "hands", "hand", f"ONLY the hands, no body: {_t}; the hand(s) of the character in the reference "
                  "(the same skin colour and the same shirt cuff at the wrist), large in the picture, wrist and a little "
                  "of the sleeve cuff included, both the RIGHT hand and, separately beside it, the mirrored LEFT hand"))
GROUPS = ("core", "arms", "legs", "hands")
TILE_OUT, TILE_IN = 26.05, 5.37     # Cloudflare's published price of flux-2-klein-4b, neurons per 512x512 tile


def _tiles(w, h):
    return -(-w // 512) * -(-h // 512)


def size_of(pose_id):
    kind = next(k for p, _, k, _ in POSES if p == pose_id)
    return (HAND_W, HAND_H) if kind == "hand" else (FIG_W, FIG_H)


SIX = ["master", "arm45", "arm90", "arm120", "both_up", "point_index"]   # the owner's first step: these six only


def selected(pose_set):
    """'core' (default) / 'arms' / 'legs' / 'hands' / 'all', or comma-separated pose ids"""
    s = (pose_set or "core").strip().lower()
    if s == "all":
        return [p for p, *_ in POSES]
    if s in GROUPS:
        return [p for p, g, *_ in POSES if g == s]
    ids = [x.strip() for x in s.split(",") if x.strip()]
    bad = [x for x in ids if x not in [p for p, *_ in POSES]]
    if bad:
        raise ValueError("unknown pose(s): " + ", ".join(bad))
    return ids


def estimate(pose_ids):
    """by Cloudflare's PUBLISHED price, assuming whole 512x512 tiles (the price page does not say how a part tile is
    counted); today's remaining allocation is NOT known to this program"""
    per = {p: round(_tiles(*size_of(p)) * TILE_OUT + 1 * TILE_IN, 1) for p in pose_ids}
    total = round(sum(per.values()))
    return {"pictures": len(pose_ids), "neurons_each": per, "neurons_if_all_pass_first_time": total,
            "neurons_if_every_picture_needs_a_second_try": total * 2, "daily_free_neurons": 10000,
            "note": "published price per 512x512 tile, whole tiles assumed; the neurons already used today (the daily "
                    "story pictures use the same account) are only on the Cloudflare dashboard. Free allocation resets "
                    "at 00:00 UTC (5:30 AM India time)."}


class _Stop(Exception):
    """the image provider refused or failed: the run stops (no substitute picture of any kind)"""


class Store:
    def __init__(self, cid, root=None):
        self.cid = cid
        self.dir = os.path.join(root or os.path.join(HERE, "assets", "character_art"), cid)
        self.poses = os.path.join(self.dir, "pose_first")
        self.inbox = os.path.join(self.dir, "inbox")
        self.rejected = os.path.join(self.poses, "rejected")
        self.originals = os.path.join(self.poses, "originals")
        for d in (self.poses, self.inbox, self.rejected, self.originals):
            os.makedirs(d, exist_ok=True)
        self.idx_f = os.path.join(self.poses, "index.json")
        self.idx = json.load(open(self.idx_f)) if os.path.exists(self.idx_f) else {}
        self.idx["_approved"] = False                       # (only the owner approves - never this program)
        self.idx.setdefault("_how_to_approve", "Look at every picture at 100 %. Write your decision in "
                            "assets/character_library/APPROVALS.json - this program never approves anything.")

    def save(self):
        tmp = self.idx_f + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.idx, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.idx_f)

    def status(self, pose_id):
        r = self.idx.get(pose_id) or {}
        if r.get("status") == "passed" and os.path.exists(os.path.join(self.poses, f"{pose_id}.png")):
            return "generated"
        return "failed" if r.get("status") == "failed" else "pending"


def small_reference(ref_rgba, path):
    """the identity picture for the model: the ORIGINAL reference on its grey studio colour, shrunk to fit inside
    511 x 511 (the model's documented input limit), JPEG"""
    a = ref_rgba[..., 3:] / 255.0
    bg = np.full(ref_rgba.shape[:2] + (3,), 180, np.float32)
    img = (ref_rgba[..., :3] * a + bg * (1 - a)).astype(np.uint8)
    s = 511.0 / max(img.shape[:2])
    img = cv2.resize(img, (max(1, int(img.shape[1] * s)), max(1, int(img.shape[0] * s))), interpolation=cv2.INTER_AREA)
    cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return path


def prompt_for(rec, pose_id):
    import art_director as AD
    text = next(t for p, _, _, t in POSES if p == pose_id)
    look = str(rec.get("look", "")).strip().rstrip(".")
    same = ("Exactly the SAME character as in the reference picture: the same face, the same hairstyle, the same moustache, "
            "the same skin colour, the same body proportions, the same clothes, colours and footwear, the same outline "
            "thickness and the same cartoon style")
    return f"{AD.STYLE}. {same}. {LOOK}. ONE single character, {text}. The character: a man - {look}. {AD.STUDIO}."[:1990]


def _figure_mask(rgba):
    m = rgba[..., 3] > 127
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    return m, n, st


def limbs_clear(rgba):
    """master pose: arms away from the body and legs apart - many rows must cross 3+ separate pieces (arm | torso |
    arm) in the arm band and 2 (leg | leg) in the leg band"""
    m = rgba[..., 3] > 127
    ys = np.where(m.any(axis=1))[0]
    if not len(ys):
        return 0.0, 0.0
    top, h = ys.min(), np.ptp(ys) + 1

    def runs(row):
        r = row.astype(np.int8)
        return int(((r[1:] == 1) & (r[:-1] == 0)).sum() + r[0])
    arm = [runs(m[y]) >= 3 for y in range(int(top + 0.30 * h), int(top + 0.48 * h))]
    leg = [runs(m[y]) >= 2 for y in range(int(top + 0.70 * h), int(top + 0.92 * h))]
    return float(np.mean(arm)) if arm else 0.0, float(np.mean(leg)) if leg else 0.0


def check(rgba, ref_rgba, pose_id):
    """OBVIOUS failures only - the owner still has to look: one whole figure (or hands), not cut by the edge, big
    enough to be a high-resolution master, the original's colours, the eyes in the head, the master's limbs clear"""
    import char_sheet
    probs, m = [], {}
    mask, n, st = _figure_mask(rgba)
    ys, xs = np.where(mask)
    if len(ys) < 5000:
        return {"pass": False, "problems": ["nothing drawn"], "metrics": {}}
    H, W = mask.shape
    m["figure_px_height"] = int(np.ptp(ys)) + 1
    if ys.min() <= 3 or xs.min() <= 3 or ys.max() >= H - 4 or xs.max() >= W - 4:
        probs.append("cut by the picture edge (no margin)")
    kind = next(k for p, _, k, _ in POSES if p == pose_id)
    big = sorted(st[1:, cv2.CC_STAT_AREA], reverse=True)
    if kind == "figure":
        allow_two = pose_id in ("sit_stool", "stand_up")
        if len(big) > 1 and big[1] > 0.08 * big[0] and not allow_two:
            probs.append("more than one figure / object in the picture")
        if m["figure_px_height"] < MIN_FIG_H:
            probs.append(f"the figure is only {m['figure_px_height']} px tall (a high-resolution master needs {MIN_FIG_H}+)")
        cm, p2 = char_sheet._colours(rgba, ref_rgba)
        m.update(cm)
        probs += p2
        m["eyes_seen"] = len(char_sheet._eyes_in_head(rgba))
        if m["eyes_seen"] == 0:
            probs.append("no eyes found in the head (face missing or changed)")
        if pose_id == "master":
            a, l_ = limbs_clear(rgba)
            m["arms_clear_rows"], m["legs_apart_rows"] = round(a, 2), round(l_, 2)
            if a < 0.5:
                probs.append("the arms touch the body (a rigging master needs background between arms and torso)")
            if l_ < 0.5:
                probs.append("the legs are not apart")
    return {"pass": not probs, "problems": probs, "metrics": m}


def _read_any(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None, None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4 and (img[..., 3] < 250).mean() > 0.02:
        return img, img[..., :3]                            # already transparent
    import cutout_assets as CA
    bgr = img[..., :3]
    return CA.key_out(bgr, keep_all=True), bgr


def make(rec, ref_rgba, pic, pose_ids, store, log=print, on_saved=None, per_run=2, total=4):
    """the MISSING poses of one character: inbox picture first, otherwise the image model (pic). Never redraws a
    passed pose. pic(prompt, ref_path, seed, w, h) -> raw bytes; it raises CA.Paused at the free limit."""
    import cutout_assets as CA
    ref_small = small_reference(ref_rgba, os.path.join(store.poses, "_reference_input_511.jpg"))
    seed0 = sum(ord(c) for c in store.cid) * 7919 % 100000
    made = 0
    try:
        for i, pid in enumerate(pose_ids):
            r = store.idx.get(pid) or {}
            out = os.path.join(store.poses, f"{pid}.png")
            inbox = next((os.path.join(store.inbox, f) for f in sorted(os.listdir(store.inbox))
                          if os.path.splitext(f)[0] == pid), None)
            if store.status(pid) == "generated" and not inbox:
                continue
            if inbox:                                       # the owner's own artwork: used as given, checked
                rgba, src = _read_any(inbox)
                q = check(rgba, ref_rgba, pid) if rgba is not None else {"pass": False, "problems": ["unreadable"], "metrics": {}}
                if os.path.exists(out):                     # an older version is kept, never overwritten silently
                    shutil.move(out, os.path.join(store.rejected, f"{pid}_replaced_{len(os.listdir(store.rejected))}.png"))
                cv2.imwrite(out, rgba)
                cv2.imwrite(os.path.join(store.poses, f"{pid}_src.png"), src)
                store.idx[pid] = {"status": "passed" if q["pass"] else "failed", "source": "owner-supplied (inbox)",
                                  "file": f"{pid}.png", "qa": q, "size": list(rgba.shape[1::-1])}
                if not q["pass"]:
                    store.idx[pid]["status"] = "passed"     # the owner's own picture is kept; the problems are shown
                    store.idx[pid]["owner_supplied_with_problems"] = q["problems"]
                shutil.move(inbox, os.path.join(store.poses, f"_used_inbox_{os.path.basename(inbox)}"))
                store.save()
                continue
            if r.get("attempts", 0) >= total:
                continue
            w, h = size_of(pid)
            for att in range(per_run):
                if r.get("attempts", 0) >= total:
                    break
                seed = seed0 + 131 * i + 977 * (r.get("attempts", 0) + 1)
                prompt = prompt_for(rec, pid)
                try:
                    raw = pic(prompt, ref_small, seed, w, h)
                except Exception as e:                      # HTTP 429 / any API error: STOP, keep the exact error
                    store.idx["_stopped_by_error"] = {"pose": pid, "error": f"{type(e).__name__}: {e}"[:600]}
                    store.save()
                    raise _Stop(str(e))
                r["attempts"] = r.get("attempts", 0) + 1     # (counted only now: a picture came back)
                made += 1
                n = r["attempts"]
                ext = ".png" if raw[:4] == b"\x89PNG" else ".jpg" if raw[:2] == b"\xff\xd8" else ".bin"
                orig_name = f"{pid}_attempt{n}_ORIGINAL{ext}"   # the provider's file, byte for byte, full size
                with open(os.path.join(store.originals, orig_name), "wb") as fh:
                    fh.write(raw)
                img = CA._decode(raw)
                rgba = CA.key_out(img, keep_all=pid in ("sit_stool", "stand_up") or pid.startswith("hand_"))
                q = check(rgba, ref_rgba, pid)
                r.update(qa=q, prompt=prompt, seed=seed, size_asked=[w, h], size_returned=[int(img.shape[1]), int(img.shape[0])],
                         provider="cloudflare", model="flux-2-klein-4b", original_file=f"originals/{orig_name}",
                         reference_input="the ORIGINAL reference, shrunk to fit 511x511", kind="NEWLY GENERATED - NOT APPROVED")
                r.setdefault("all_attempts", []).append({"attempt": n, "file": f"originals/{orig_name}", "automatic_check": q})
                if q["pass"]:
                    cv2.imwrite(out, rgba)                  # (transparent copy, same size as the original)
                    r.update(status="passed", file=f"{pid}.png")
                    store.idx[pid] = r
                    store.save()
                    if on_saved:
                        on_saved(pid)
                    break
                r["status"] = "failed"
                store.idx[pid] = r
                store.save()
                log(f"    {pid}: automatic check failed ({'; '.join(q['problems'][:2])}) - the picture is kept in originals/")
            store.idx[pid] = r
            store.save()
    except (CA.Paused, _Stop) as e:
        store.idx["_paused"] = str(e)[:600]
    finally:
        store.save()
    return made


def sheet(rec, ref_rgba, store, pose_ids, path):
    """ONE page: the ORIGINAL next to every pose (status written under each); at 100 % every picture is also its
    own file in pose_first/"""
    tiles = []

    def tile(img_bgr, title, sub, ok):
        h, w = 520, 350
        t = np.full((h, w, 3), 255, np.uint8)
        if img_bgr is not None:
            s = min((w - 10) / img_bgr.shape[1], (h - 70) / img_bgr.shape[0])
            im = cv2.resize(img_bgr, (max(1, int(img_bgr.shape[1] * s)), max(1, int(img_bgr.shape[0] * s))), interpolation=cv2.INTER_AREA)
            y0, x0 = 30, (w - im.shape[1]) // 2
            t[y0:y0 + im.shape[0], x0:x0 + im.shape[1]] = im
        cv2.putText(t, title, (6, 20), 0, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(t, sub[:48], (6, h - 26), 0, 0.42, (0, 120, 0) if ok else (0, 0, 200), 1, cv2.LINE_AA)
        cv2.putText(t, sub[48:96], (6, h - 10), 0, 0.42, (0, 120, 0) if ok else (0, 0, 200), 1, cv2.LINE_AA)
        return cv2.copyMakeBorder(t, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=(200, 200, 200))
    a = ref_rgba[..., 3:] / 255.0
    tiles.append(tile((ref_rgba[..., :3] * a + 236 * (1 - a)).astype(np.uint8), "ORIGINAL reference", "identity source", True))
    for pid in pose_ids:
        st = store.status(pid)
        f = os.path.join(store.poses, f"{pid}.png")
        img = None
        if os.path.exists(f):
            rg = cv2.imread(f, cv2.IMREAD_UNCHANGED)
            aa = rg[..., 3:] / 255.0
            img = (rg[..., :3] * aa + 236 * (1 - aa)).astype(np.uint8)
        r = store.idx.get(pid) or {}
        sub = {"generated": "generated - NOT approved", "failed": "failed: " + "; ".join((r.get("qa") or {}).get("problems", [])[:2]),
               "pending": "pending (not drawn yet)"}[st]
        if r.get("owner_supplied_with_problems"):
            sub = "owner file - check: " + "; ".join(r["owner_supplied_with_problems"][:1])
        tiles.append(tile(img, pid, sub, st == "generated"))
    per_row = 5
    rows = []
    for k in range(0, len(tiles), per_row):
        row = tiles[k:k + per_row]
        while len(row) < per_row:
            row.append(np.full_like(tiles[0], 255))
        rows.append(np.hstack(row))
    page = np.vstack(rows)
    head = np.full((50, page.shape[1], 3), 255, np.uint8)
    cv2.putText(head, f"{rec['name']} - POSE-FIRST artwork (complete pictures, not cut) - NOTHING is approved until you approve",
                (10, 32), 0, 0.7, (0, 0, 0), 1, cv2.LINE_AA)
    page = np.vstack([head, page])
    cv2.imwrite(path, page, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path


def armlift_from_poses(store, out_dir):
    """the arm-lift test on COMPLETE drawings: master (rest) -> arm45 -> arm90 -> arm120 -> both_up, each with
    300 % zooms of the raised side's shoulder / armpit, and the same image checks (holes inside the figure, white
    seams, broken outline). Only drawings that exist are shown; missing steps are listed."""
    steps = [("rest (master)", "master"), ("45 deg", "arm45"), ("90 deg", "arm90"), ("120 deg", "arm120"), ("both up", "both_up")]
    rows, res = [], []
    for label, pid in steps:
        f = os.path.join(store.poses, f"{pid}.png")
        if store.status(pid) != "generated":
            res.append({"step": label, "pose": pid, "status": "MISSING - not generated yet"})
            continue
        rg = cv2.imread(f, cv2.IMREAD_UNCHANGED)
        al = rg[..., 3] > 127
        a = rg[..., 3:] / 255.0
        img = (rg[..., :3] * a + 236 * (1 - a)).astype(np.uint8)
        inv = (~al).astype(np.uint8)
        mk = np.zeros((inv.shape[0] + 2, inv.shape[1] + 2), np.uint8)
        ff = inv.copy()
        cv2.floodFill(ff, mk, (0, 0), 2)
        holes = ff == 1
        n, lab, st, _ = cv2.connectedComponentsWithStats(holes.astype(np.uint8), 4)
        hole_px = int(sum(v for v in st[1:, 4] if v >= 30))      # (small closed gaps, e.g. between fingers, are art)
        ys, xs = np.where(al)
        top, bot, left, right = ys.min(), ys.max(), xs.min(), xs.max()
        hh = bot - top
        # the raised arm is on the LEFT of the picture: shoulder / armpit zone = left half, 12-45 % of the height
        y0, y1 = int(top + 0.12 * hh), int(top + 0.45 * hh)
        x0, x1 = left, int((left + right) / 2)
        zone = img[y0:y1, x0:x1]
        edge = al & ~(cv2.erode(al.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        near_dark = cv2.dilate((hsv[..., 2] < 110).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        z = np.zeros_like(al)
        z[y0:y1, x0:x1] = True
        ink = float((edge & near_dark & z).sum()) / max(1, int((edge & z).sum()))
        probs = []
        if hole_px:
            probs.append(f"{hole_px} px of hole inside the figure")
        if ink < 0.85:
            probs.append(f"outline around the shoulder / armpit only {ink:.0%} drawn")
        res.append({"step": label, "pose": pid, "holes_px": hole_px, "outline_ratio": round(ink, 3), "problems": probs,
                    "automatic_check": "pass" if not probs else "fail"})
        whole = cv2.resize(img, (int(img.shape[1] * 420 / img.shape[0]), 420), interpolation=cv2.INTER_AREA)
        zz = cv2.resize(zone, (int(zone.shape[1] * 420 / max(1, zone.shape[0])), 420), interpolation=cv2.INTER_CUBIC)
        sc = 420 / max(1, zone.shape[0])
        row = np.hstack([whole, zz])
        cv2.putText(row, f"{label}: " + ("automatic check OK" if not probs else "; ".join(probs)), (6, 22), 0, 0.6,
                    (0, 130, 0) if not probs else (0, 0, 210), 2, cv2.LINE_AA)
        cv2.putText(row, f"zoom {sc / (420 / img.shape[0]):.0f}x of the shoulder / armpit zone", (whole.shape[1] + 6, 412), 0, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        rows.append(row)
    os.makedirs(out_dir, exist_ok=True)
    path = None
    if rows:
        W = max(r.shape[1] for r in rows)
        rows = [cv2.copyMakeBorder(r, 2, 2, 2, W - r.shape[1] + 2, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for r in rows]
        path = os.path.join(out_dir, "armlift_complete_poses.png")
        cv2.imwrite(path, np.vstack(rows))
    rep = {"steps": res, "sheet": path, "note": "complete drawings: an arm above 60 degrees uses these pictures, not the rig"}
    with open(os.path.join(out_dir, "armlift_complete_poses.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    return rep


# ----------------------------------------------------------------------------------------------- owner's sheets
def _plain(rgba):
    a = rgba[..., 3:] / 255.0
    return (rgba[..., :3] * a + 236 * (1 - a)).astype(np.uint8)


LABELS = {"master": "1 MASTER A-pose", "arm45": "2 right arm 45 deg", "arm90": "3 right arm 90 deg",
          "arm120": "4 right arm 120 deg", "both_up": "5 both arms raised", "point_index": "6 index-finger pointing"}


def latest_original(store, pid):
    r = store.idx.get(pid) or {}
    f = r.get("original_file")
    if f and os.path.exists(os.path.join(store.poses, f)):
        return os.path.join(store.poses, f), r
    return None, r


def contact_sheet(store, path, ids=SIX):
    """the six NEW pictures exactly as generated (each scaled only for this page; the files stay full size),
    every one labelled: what it is, NEWLY GENERATED, its size, the automatic check, NOT APPROVED"""
    tiles = []
    for pid in ids:
        f, r = latest_original(store, pid)
        t = np.full((760, 520, 3), 255, np.uint8)
        if f:
            img = cv2.imread(f, cv2.IMREAD_COLOR)
            s_ = min(500 / img.shape[1], 640 / img.shape[0])
            im = cv2.resize(img, (int(img.shape[1] * s_), int(img.shape[0] * s_)), interpolation=cv2.INTER_AREA)
            t[50:50 + im.shape[0], (520 - im.shape[1]) // 2:(520 - im.shape[1]) // 2 + im.shape[1]] = im
            chk = "automatic check: passed" if r.get("status") == "passed" else \
                "automatic check FAILED: " + "; ".join((r.get("qa") or {}).get("problems", [])[:1])
            sub = [f"NEWLY GENERATED - {img.shape[1]}x{img.shape[0]} - attempt {r.get('attempts')}", chk[:70], "NOT APPROVED"]
        else:
            cv2.putText(t, "NOT GENERATED", (150, 380), 0, 0.9, (0, 0, 200), 2, cv2.LINE_AA)
            sub = ["no picture - see the report for the exact error", "", ""]
        cv2.putText(t, LABELS.get(pid, pid), (8, 32), 0, 0.85, (0, 0, 0), 2, cv2.LINE_AA)
        for k, line in enumerate(sub):
            cv2.putText(t, line, (8, 712 + 18 * k), 0, 0.45, (0, 0, 180) if "FAIL" in line or "NOT" in line else (0, 110, 0), 1, cv2.LINE_AA)
        tiles.append(cv2.copyMakeBorder(t, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=(190, 190, 190)))
    page = np.vstack([np.hstack(tiles[:3]), np.hstack(tiles[3:6])])
    head = np.full((56, page.shape[1], 3), 255, np.uint8)
    cv2.putText(head, "HARI - NEWLY GENERATED pose-first artwork (Cloudflare flux-2-klein-4b, from the original reference) - NOT APPROVED",
                (10, 36), 0, 0.7, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(path, np.vstack([head, page]), [cv2.IMWRITE_JPEG_QUALITY, 92])
    return path


def comparison_sheet(store, ref_rgba, path, ids=SIX):
    """OLD artwork (the original reference) on the left, each NEW picture beside it, the same display height"""
    old = _plain(ref_rgba)
    rows = []
    for pid in ids:
        f, r = latest_original(store, pid)
        H = 620

        def fit(img):
            s_ = H / img.shape[0]
            return cv2.resize(img, (int(img.shape[1] * s_), H), interpolation=cv2.INTER_AREA)
        a = fit(old)
        b = fit(cv2.imread(f, cv2.IMREAD_COLOR)) if f else np.full((H, 413, 3), 255, np.uint8)
        la = np.full((40, a.shape[1], 3), 255, np.uint8)
        lb = np.full((40, b.shape[1], 3), 255, np.uint8)
        cv2.putText(la, f"OLD artwork (original reference) {ref_rgba.shape[1]}x{ref_rgba.shape[0]}", (4, 26), 0, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(lb, f"NEW: {LABELS.get(pid, pid)}" + (" - NOT GENERATED" if not f else " - NOT APPROVED"), (4, 26), 0, 0.55,
                    (0, 0, 180), 1, cv2.LINE_AA)
        row = np.hstack([np.vstack([la, a]), np.full((H + 40, 12, 3), 200, np.uint8), np.vstack([lb, b])])
        rows.append(row)
    Wm = max(r.shape[1] for r in rows)
    rows = [cv2.copyMakeBorder(r, 4, 4, 4, Wm - r.shape[1] + 4, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for r in rows]
    cv2.imwrite(path, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path
