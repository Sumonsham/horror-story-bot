"""CHARACTER SHEET (GitHub: mode = char_sheet) - ORIGINAL 2D character artwork for VISUAL APPROVAL, before anything else.

Why: a puppet cut from ONE three-quarter picture cannot show what the picture hides (the inner side of an arm, the
torso behind it, the saree under the pallu) and cannot give a true front or side view. The image model, given the
character's reference picture, reliably draws the SAME WHOLE CHARACTER again - so it is asked for complete drawings.

Per character (Hari, Saraswati, Kishori), ALWAYS with the ORIGINAL Cloudflare reference picture as the identity:
  front   a FRONT-facing A-pose (arms away from the body, open hands, legs apart, feet visible) -> also cut into parts
  side    a TRUE SIDE profile (checked: only one eye may be visible)
  stand / sit / talk / point   complete drawings of those poses
  walk    ONE picture with the FOUR frames of ONE walk cycle side by side (contact - passing - contact - passing):
          drawn together they share the canvas, the scale, the camera and the ground line; they are cut apart and
          checked (4 figures, the same height, the same ground) and placed on one canvas at the same scale.
= 7 pictures per character (plus at most 2 redraws of a rejected one).

Checks (they only throw out OBVIOUS failures - a person approves): one whole figure, nothing cut off, the costume /
skin / hair colours of the ORIGINAL. Then the front drawing is cut into its body parts and the parts are judged:
complete, nothing stretched, assembled again exactly, moving without gaps -> "2D cut-out suitable"; otherwise
"full-pose 2D animation" (complete drawings per pose - never a broken cut-out rig).
Output per character: ONE approval page (the original next to every new drawing, all labelled), every generated
picture as its own file, a walking preview video - Telegram + GitHub Actions Artifacts + the repo.
NOTHING is approved automatically: sheet.json says approved = false until the owner approves.
"""
import json
import os
import shutil
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import art_director as AD  # noqa: E402
import cutout_assets as CA  # noqa: E402

ROOT = os.path.join(HERE, "assets", "cartoon_parts")
OUT = os.path.join(HERE, "work", "char_sheet")
W_, H_ = 576, 1024
WALK_W, WALK_H = 1024, 576                                 # (a size already used with this Cloudflare model)

SAME = ("Exactly the SAME character as in the reference picture: the same face, the same hairstyle, the same facial "
        "hair (if the reference has no beard, draw NO beard; never add or remove a moustache or beard), the same age, "
        "the same clothes, colours, patterns and jewellery, the same body proportions")
WHOLE = ("the WHOLE body inside the picture with wide empty margins (the head and the feet well away from the "
         "edges), nothing held in the hands, no other objects")
DRAWINGS = [
    ("front", "seen straight from the FRONT, facing the viewer, standing in an A-pose: both arms held about 30 degrees "
              "away from the body with clear background between each arm and the body, open relaxed hands with all "
              "five fingers visible, legs slightly apart with a clear gap between them, both feet flat and fully visible", True),
    ("side", "seen exactly from the SIDE - a true side profile, like a silhouette from the side - facing RIGHT: only ONE "
             "eye, one ear and one arm visible, the nose and chin in outline, standing upright, arms relaxed by the sides", True),
    ("stand", "seen in three-quarter view turned to the RIGHT, standing relaxed, arms hanging naturally by the sides", True),
    ("sit", "seen in three-quarter view turned to the RIGHT, SITTING on a plain low wooden stool: back straight, thighs "
            "horizontal, knees bent, both feet flat on the floor, hands resting on the knees (the stool is the only "
            "object)", False),
    ("talk", "seen in three-quarter view turned to the RIGHT, standing and TALKING: the mouth open in mid-sentence, one "
             "hand raised to chest height in an explaining gesture", True),
    ("point", "seen in three-quarter view turned to the RIGHT, standing and POINTING: one arm stretched straight forward "
              "at shoulder height with the index finger pointing, the other arm relaxed", True),
]
WALK_PROMPT = ("an animation sprite sheet: FOUR frames of ONE continuous walk cycle of the SAME character side by side "
               "in a single row, evenly spaced, every frame the same size, the same camera, standing on the same "
               "ground line, seen exactly from the SIDE facing RIGHT. Frame 1: contact - the left leg forward with the "
               "heel on the ground, the right leg behind on its toes. Frame 2: passing - the left foot flat under the "
               "body, the right leg passing forward with the knee bent. Frame 3: contact - the RIGHT leg forward with "
               "the heel on the ground, the left leg behind. Frame 4: passing - the right foot flat under the body, the "
               "left leg passing forward with the knee bent. The arms swing opposite to the legs. The frames do not "
               "touch or overlap, the whole body of every frame is visible")
VIEWS = [n for n, _, _ in DRAWINGS] + ["walk"]
MAX_COLOUR_DE, MAX_SKIN_DE, MAX_HAIR_DE = 16.0, 18.0, 25.0


def _who(rec):
    d = rec.get("design") or {}
    return "a " + ("ghost " if d.get("ghost") else "") + ("woman" if d.get("sari") or d.get("robe") else "man")


def prompt_for(rec, view):
    look = str(rec.get("look", "")).strip().rstrip(".")
    d = rec.get("design") or {}
    ghost = (" " + AD.GHOST + ".") if d.get("ghost") else ""
    if view == "walk":
        return f"{AD.STYLE}. {SAME}. {WALK_PROMPT}. The character: {_who(rec)} - {look}.{ghost} {AD.STUDIO}."
    text = next(t for n, t, _ in DRAWINGS if n == view)
    alone = next(a for n, _, a in DRAWINGS if n == view)
    return (f"{AD.STYLE}. {SAME}. ONE single character, {text}, {WHOLE if alone else WHOLE.replace(', no other objects', '')}. "
            f"The character: {_who(rec)} - {look}.{ghost} {AD.STUDIO}.")


def _colours(rgba, ref_rgba):
    import consistency as C
    m, probs = {}, []
    m["colour_de"] = round(C.palette_de(C.palette(rgba), C.palette(ref_rgba)), 1)
    if m["colour_de"] > MAX_COLOUR_DE:
        probs.append(f"costume colours differ from the original (dE {m['colour_de']})")
    s1, s0 = C.skin_tone(rgba), C.skin_tone(ref_rgba)
    if s1 is not None and s0 is not None:
        m["skin_de"] = round(float(np.linalg.norm(s1 - s0)), 1)
        if m["skin_de"] > MAX_SKIN_DE:
            probs.append(f"skin tone differs from the original (dE {m['skin_de']})")
    h1, h0 = C.hair_tone(rgba), C.hair_tone(ref_rgba)
    if h1 is not None and h0 is not None:
        m["hair_de"] = round(float(np.linalg.norm(h1 - h0)), 1)
        if m["hair_de"] > MAX_HAIR_DE:
            probs.append(f"hair colour differs from the original (dE {m['hair_de']})")
    return m, probs


def _eyes_in_head(rgba):
    """the eyes the cartoon eye-finder sees in the head (the top ~22 % of the figure)"""
    ys = np.where((rgba[..., 3] > 127).any(axis=1))[0]
    if not len(ys):
        return []
    top, bot = ys.min(), ys.max()
    head = rgba[top:top + int(0.22 * (bot - top))].copy()
    return CA.cartoon_eyes(head) if head.size else []


def check_drawing(rgba, ref_rgba, view):
    """obvious failures only (a person must still approve): one whole figure, not cut off, same colours; a SIDE view
    must really be a profile (two eyes far apart = a front / three-quarter face, not a side view)"""
    import asset_qa as QA
    q = QA.reference(rgba)
    probs = list(q["problems"])
    if view == "sit":                                       # (the stool may stand apart from the body)
        probs = [p for p in probs if "more than one figure" not in p and "body shape" not in p]
    m, p2 = _colours(rgba, ref_rgba)
    probs += p2
    eyes = _eyes_in_head(rgba)
    m["eyes_seen"] = len(eyes)
    if view == "side" and len(eyes) >= 2:
        xs_ = np.where((rgba[..., 3] > 127).any(axis=0))[0]
        if abs(eyes[1][0] - eyes[0][0]) > 0.04 * max(1, np.ptp(xs_)):
            probs.append("not a true side view: two eyes are visible")
    return {"pass": not probs, "problems": probs, "metrics": m}


def split_walk(rgba):
    """the walk sprite sheet -> the 4 frames (left to right), each its own RGBA crop with its ground position;
    checks that they are 4 whole figures of the same height standing on the same ground line"""
    a = (rgba[..., 3] > 127).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(a, 8)
    big = sorted([i for i in range(1, n) if st[i][4] > 0.02 * a.sum()], key=lambda i: st[i][0])
    probs = []
    if len(big) != 4:
        return None, [f"{len(big)} figures in the walk picture instead of 4 separate frames"]
    frames, heights, grounds = [], [], []
    for i in big:
        x, y, w, h, _ = st[i]
        crop = rgba[y:y + h, x:x + w].copy()
        crop[..., 3] = np.where(lab[y:y + h, x:x + w] == i, crop[..., 3], 0)
        frames.append({"rgba": crop, "x": int(x), "y": int(y), "w": int(w), "h": int(h), "ground": int(y + h)})
        heights.append(h)
        grounds.append(y + h)
    H = float(np.median(heights))
    if (max(heights) - min(heights)) / H > 0.08:
        probs.append(f"the frames are not the same size (heights differ by {(max(heights) - min(heights)) / H * 100:.0f} %)")
    if (max(grounds) - min(grounds)) / H > 0.04:
        probs.append(f"the frames do not stand on the same ground line ({(max(grounds) - min(grounds)) / H * 100:.0f} % apart)")
    if min(st[i][1] for i in big) < 3 or max(st[i][1] + st[i][3] for i in big) > rgba.shape[0] - 3:
        probs.append("a frame is cut by the picture edge")
    return frames, probs


def normalise_walk(frames, canvas=(720, 400)):
    """the 4 frames on ONE canvas each: the SAME scale (as drawn together) and the SAME ground line"""
    Hc, Wc = canvas
    hmax = max(f["h"] for f in frames)
    sc = 0.86 * Hc / hmax
    out = []
    for f in frames:
        sm = cv2.resize(f["rgba"], None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        c = np.zeros((Hc, Wc, 4), np.uint8)
        gy = int(0.95 * Hc)
        y0 = gy - sm.shape[0]
        x0 = (Wc - sm.shape[1]) // 2
        c[max(0, y0):y0 + sm.shape[0], max(0, x0):x0 + sm.shape[1]] = sm[max(0, -y0):, max(0, -x0):][:Hc - max(0, y0), :Wc - max(0, x0)]
        out.append(c)
    return out


class _Budget:
    def __init__(self, image_fn, budget):
        self.fn, self.left, self.made, self.paused, self.blocker = image_fn, budget, 0, False, None

    def __call__(self, prompt, ref, seed, w=W_, h=H_):
        if self.paused or self.left <= 0:
            self.paused = True
            raise CA.Paused("picture budget / free limit")
        try:
            raw = self.fn(prompt, ref, seed, w, h)
        except Exception as e:
            if CA._is_limit(e):
                self.paused = True
                self.blocker = str(e)[:200]
                raise CA.Paused(str(e)[:120])
            raise
        self.left -= 1
        self.made += 1
        return CA._decode(raw)


def make_drawings(rec, key, pic, log=print, retries=2):
    """every drawing of one character (only the missing ones) - ALWAYS from the ORIGINAL reference picture"""
    d = os.path.join(ROOT, key, "sheet")
    os.makedirs(d, exist_ok=True)
    idx_f = os.path.join(d, "sheet.json")
    idx = json.load(open(idx_f)) if os.path.exists(idx_f) else {}
    idx["_approved"] = False                                # (only the owner approves - never this program)
    orig_src = os.path.join(ROOT, key, "body_src.png")
    orig = cv2.imread(os.path.join(ROOT, key, "body.png"), cv2.IMREAD_UNCHANGED)
    if orig is None or not os.path.exists(orig_src):
        return {"_error": "no original reference picture for this character"}
    seed0 = int(key[:6], 16) % 100000
    try:
        for i, view in enumerate(VIEWS):
            r = idx.get(view, {})
            if r.get("status") == "passed" or r.get("attempts", 0) >= 6:
                continue
            for att in range(retries + 1):
                r["attempts"] = r.get("attempts", 0) + 1
                seed = seed0 + 131 * i + 977 * r["attempts"]
                if view == "walk":
                    img = pic(prompt_for(rec, view), orig_src, seed, WALK_W, WALK_H)
                    rgba = CA.key_out(img, keep_all=True)          # (all four frames)
                    frames, probs = split_walk(rgba)
                    m = {}
                    if frames:
                        cm, p2 = _colours(rgba, orig)
                        m.update(cm)
                        probs += p2
                    q = {"pass": not probs, "problems": probs, "metrics": m}
                else:
                    img = pic(prompt_for(rec, view), orig_src, seed)
                    rgba = CA.key_out(img, keep_all=(view == "sit"))  # (the stool stays with the sitter)
                    q = check_drawing(rgba, orig, view)
                r["qa"] = q
                if q["pass"]:
                    cv2.imwrite(os.path.join(d, f"{view}.png"), rgba)
                    cv2.imwrite(os.path.join(d, f"{view}_src.png"), img)
                    if view == "walk":
                        for k, fr in enumerate(normalise_walk(frames), 1):
                            cv2.imwrite(os.path.join(d, f"walk{k}.png"), fr)
                    r.update(status="passed", file=f"{view}.png")
                    break
                cv2.imwrite(os.path.join(d, f"rejected_{view}_{r['attempts']}.png"), img)
                r["status"] = "failed"
                log(f"    {rec['name']} {view}: rejected ({'; '.join(q['problems'][:2])})")
            idx[view] = r
    except CA.Paused:
        pass
    finally:
        with open(idx_f, "w") as f:
            json.dump(idx, f, indent=1)
    return idx


# ----------------------------------------------------------------------------------- the body parts + the verdict
PART_NAMES = {"head": "head + neck", "torso": "torso (shoulders-pelvis)", "uarm_far": "RIGHT upper arm",
              "farm_far": "RIGHT forearm + hand", "uarm_near": "LEFT upper arm", "farm_near": "LEFT forearm + hand",
              "thigh_far": "RIGHT thigh", "shin_far": "RIGHT lower leg + foot", "thigh_near": "LEFT thigh",
              "shin_near": "LEFT lower leg + foot", "skirt_up": "cloth: waist -> knee", "skirt_lo": "cloth: knee -> feet"}


def parts_from_front(rec, key, log=print):
    """the FRONT A-pose drawing cut into its body parts, then judged as a 2D cut-out:
    the cut must succeed with no problem, every part must lie exactly where (and be exactly as big as) it is in the
    drawing - nothing stretched -, and the assembled puppet must pass the whole assembled check (one body in every
    pose, no gap at a joint, natural seat and walk, the same face). Anything less -> full-pose 2D animation."""
    import asset_plan
    import assembly_qa as AQ
    import cartoon_rig as R
    import cutout_rig as CR
    import puppet_builder as PB
    d = os.path.join(ROOT, key, "sheet")
    f = os.path.join(d, "front.png")
    out = {"problems": [], "notes": [], "parts": {}, "assembled": None, "fidelity": None, "gate": None,
           "verdict": "not decided - the front drawing is not made yet"}
    if not os.path.exists(f):
        return out
    rgba = cv2.imread(f, cv2.IMREAD_UNCHANGED)
    plan = asset_plan.plan(rec.get("design") or {})
    rig, probs, notes = PB.build(rgba, plan)
    out.update(problems=list(probs), notes=notes)
    if rig is None:
        out["verdict"] = "FULL-POSE 2D ANIMATION (the front drawing could not be cut into parts)"
        return out
    pd = os.path.join(d, "parts")
    shutil.rmtree(pd, ignore_errors=True)
    os.makedirs(pd, exist_ok=True)
    CA.Maker._save_rig(pd, rig)
    CA.save_ref_head(pd, rig)
    for n, p in rig["parts"].items():
        out["parts"][n] = p["sprite"]
    try:
        ch = CR.CutoutCharacter(rec["name"], rec.get("design") or {}, pd)
        fid = AQ.fidelity(ch, rgba, pd)
        out["fidelity"] = {"pass": fid["pass"], "problems": fid["problems"][:4]}
        gate = AQ.check(ch, rgba, probs, plan, out_dir=pd)
        out["gate"] = {"pass": gate["pass"], "problems": gate["problems"][:6]}
        meta = ch.meta
        st = {"x": 960, "ground_y": 935, "facing": 1.0, "head_yaw": 1.0, "pose": AQ._rest_pose(ch), "t": 0.0,
              "mouth": (0, "rest"), "blink": 0}
        gy = st["ground_y"] + ch.foot_floor(st)
        st = dict(st, ground_y=gy, planted=False)
        j = ch.joints(st)
        s = j["s"]
        hx, hy = meta["hip"]
        cam = AQ._FixedCam(j["hip"][0] - hx * s, j["hip"][1] - hy * s, 1.0 / s)
        img = np.full(rgba.shape[:2] + (3,), 236, np.uint8)
        ch.draw(R.Painter(img, cam), dict(st))
        out["assembled"] = img
    except Exception as e:
        out["problems"].append(f"assembling failed: {type(e).__name__}: {str(e)[:100]}")
    ok = not out["problems"] and (out["fidelity"] or {}).get("pass") and (out["gate"] or {}).get("pass")
    out["verdict"] = ("2D CUT-OUT SUITABLE (automatic suggestion - your eyes decide)" if ok else
                      "FULL-POSE 2D ANIMATION (the cut-out did not pass: " +
                      "; ".join((out["problems"] + (out["fidelity"] or {}).get("problems", []) +
                                 (out["gate"] or {}).get("problems", []))[:2]) + ")")
    return out


# ----------------------------------------------------------------------------------------------- the approval page
def _comp(rgba, bg=(236, 236, 236)):
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    return (rgba[..., :3] * a + np.array(bg, np.float32) * (1 - a)).astype(np.uint8)


def _fit(img, h, w=None):
    out = cv2.resize(img, (max(1, int(img.shape[1] * h / img.shape[0])), h), interpolation=cv2.INTER_AREA)
    if w and out.shape[1] < w:
        out = np.pad(out, ((0, 0), ((w - out.shape[1]) // 2, w - out.shape[1] - (w - out.shape[1]) // 2), (0, 0)),
                     constant_values=236)
    elif w and out.shape[1] > w:
        out = cv2.resize(img, (w, max(1, int(img.shape[0] * w / img.shape[1]))), interpolation=cv2.INTER_AREA)
        out = np.pad(out, (((h - out.shape[0]) // 2, h - out.shape[0] - (h - out.shape[0]) // 2), (0, 0), (0, 0)),
                     constant_values=236)
    return out


def _tile(img, title, sub="", ok=True, h=420, w=250):
    t = _fit(img, h, w)
    t = np.pad(t, ((44, 8), (4, 4), (0, 0)), constant_values=255)
    cv2.putText(t, title, (8, 20), 0, 0.52, (20, 20, 20), 1, cv2.LINE_AA)
    if sub:
        cv2.putText(t, sub[:44], (8, 38), 0, 0.37, (60, 60, 60), 1, cv2.LINE_AA)
    cv2.rectangle(t, (1, 1), (t.shape[1] - 2, t.shape[0] - 2), (60, 170, 60) if ok else (40, 40, 220), 2)
    return t


def _row(tiles, width):
    r = np.hstack(tiles) if tiles else np.full((10, width, 3), 255, np.uint8)
    if r.shape[1] < width:
        r = np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0)), constant_values=255)
    return r[:, :width]


def approval_page(rec, key, idx, parts, path):
    d = os.path.join(ROOT, key, "sheet")
    orig = _comp(cv2.imread(os.path.join(ROOT, key, "body.png"), cv2.IMREAD_UNCHANGED))
    ORIG = _tile(orig, "ORIGINAL reference", "the identity for every drawing")

    def view_tile(v, title):
        r = idx.get(v, {})
        f = os.path.join(d, f"{v}.png")
        if r.get("status") == "passed" and os.path.exists(f):
            m = r.get("qa", {}).get("metrics", {})
            return _tile(_comp(cv2.imread(f, cv2.IMREAD_UNCHANGED)), title,
                         f"colour dE {m.get('colour_de')} skin {m.get('skin_de')} hair {m.get('hair_de')}")
        rej = sorted(x for x in os.listdir(d) if x.startswith(f"rejected_{v}_")) if os.path.isdir(d) else []
        if rej:
            return _tile(cv2.imread(os.path.join(d, rej[-1])), title + " - REJECTED",
                         "; ".join((r.get("qa") or {}).get("problems", [])[:1]), ok=False)
        return _tile(np.full((420, 250, 3), 210, np.uint8), title, "not made yet" + (" (paused)" if r else ""), ok=False)
    rows = [ORIG, view_tile("front", "NEW front A-pose"), view_tile("side", "NEW true side view")]
    if parts and parts.get("assembled") is not None:
        fp = parts.get("fidelity") or {}
        rows.append(_tile(parts["assembled"], "parts ASSEMBLED again", "every part exactly in place" if fp.get("pass")
                          else ("; ".join(fp.get("problems", [])[:1]) or "-"), ok=bool(fp.get("pass"))))
    r1 = rows
    r2 = [ORIG, view_tile("stand", "NEW standing (3/4)"), view_tile("sit", "NEW sitting"), view_tile("talk", "NEW talking"),
          view_tile("point", "NEW pointing")]
    # the walk: the four frames on the same canvas, the ground line drawn through all of them
    wr = idx.get("walk", {})
    frames = [cv2.imread(os.path.join(d, f"walk{k}.png"), cv2.IMREAD_UNCHANGED) for k in range(1, 5)]
    if wr.get("status") == "passed" and all(f is not None for f in frames):
        r3 = [ORIG]
        for k, f in enumerate(frames, 1):
            t = _tile(_comp(f), f"NEW walk {k}/4: {['contact L', 'passing', 'contact R', 'passing'][k - 1]}",
                      "one cycle, same scale + ground", h=420, w=250)
            gy = 44 + int(0.95 * 420)
            cv2.line(t, (4, gy), (t.shape[1] - 4, gy), (40, 120, 220), 1)
            r3.append(t)
    else:
        r3 = [ORIG, view_tile("walk", "NEW walk cycle (4 frames)")]
    WIDTH = max(sum(x.shape[1] for x in r) for r in (r1, r2, r3))
    head = np.full((120, WIDTH, 3), 255, np.uint8)
    cv2.putText(head, f"{rec['name']} - ORIGINAL 2D CHARACTER SHEET FOR VISUAL APPROVAL (NOT approved until you say so)",
                (10, 32), 0, 0.8, (10, 10, 10), 2, cv2.LINE_AA)
    cv2.putText(head, "Every row starts with the ORIGINAL reference. green = passed the automatic checks (whole figure, "
                      "nothing cut off, same colours); red = rejected / missing.", (10, 64), 0, 0.48, (40, 40, 40), 1, cv2.LINE_AA)
    verdict = (parts or {}).get("verdict", "not decided")
    cv2.putText(head, "SUGGESTION: " + verdict[:150], (10, 98), 0, 0.5,
                (30, 130, 30) if verdict.startswith("2D CUT-OUT") else (30, 30, 190), 1, cv2.LINE_AA)
    out_rows = [head, _row(r1, WIDTH), _row(r2, WIDTH), _row(r3, WIDTH)]
    if parts and parts.get("parts"):                         # the separated body parts, each with its name
        cells = [_tile(_comp(parts["parts"][n]), PART_NAMES[n], f"{parts['parts'][n].shape[1]}x{parts['parts'][n].shape[0]} px, as drawn",
                       True, h=200, w=170)
                 for n in ("head", "torso", "uarm_far", "farm_far", "uarm_near", "farm_near", "thigh_far", "shin_far",
                           "thigh_near", "shin_near", "skirt_up", "skirt_lo") if n in parts["parts"]]
        title = np.full((60, WIDTH, 3), 255, np.uint8)
        cv2.putText(title, "the FRONT drawing cut into its body parts - at their drawn size, nothing stretched "
                           "(LEFT / RIGHT = the character's own)" + ("   PROBLEMS: " + "; ".join(parts["problems"][:2])
                                                                    if parts["problems"] else ""),
                    (10, 38), 0, 0.5, (10, 10, 10) if not parts["problems"] else (30, 30, 200), 1, cv2.LINE_AA)
        out_rows.append(title)
        per = max(1, WIDTH // 178)
        for i in range(0, len(cells), per):
            out_rows.append(_row(cells[i:i + per], WIDTH))
    page = np.vstack(out_rows)
    cv2.imwrite(path, page, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path


def walk_video(key, path, fps=6, seconds=4):
    """the four walking frames in a loop, moving forward - to SEE the walk (the frames keep their common scale)"""
    d = os.path.join(ROOT, key, "sheet")
    frames = [cv2.imread(os.path.join(d, f"walk{i}.png"), cv2.IMREAD_UNCHANGED) for i in range(1, 5)]
    if any(f is None for f in frames):
        return None
    H, W = 540, 960
    tmp = path + ".tmp"
    os.makedirs(tmp, exist_ok=True)
    n = fps * seconds
    sc = 470.0 / frames[0].shape[0]
    for k in range(n):
        sm = cv2.resize(frames[k % 4], None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        canvas = np.full((H, W, 3), (205, 214, 200), np.uint8)
        x = int(20 + (W - sm.shape[1] - 40) * k / n)
        y = 515 - sm.shape[0] + int((1 - 0.95) * sm.shape[0])
        cv2.line(canvas, (0, 515 - int(0.0)), (W, 515), (120, 130, 110), 2)
        a = sm[..., 3:4] / 255.0
        y0, y1 = max(0, y), min(H, y + sm.shape[0])
        roi = canvas[y0:y1, x:x + sm.shape[1]]
        part = sm[y0 - y:y1 - y, :roi.shape[1]]
        aa = a[y0 - y:y1 - y, :roi.shape[1]]
        roi[...] = (roi * (1 - aa) + part[..., :3] * aa).astype(np.uint8)
        cv2.imwrite(os.path.join(tmp, f"{k:04d}.png"), canvas)
    os.system(f"ffmpeg -y -loglevel error -framerate {fps} -i '{tmp}/%04d.png' -pix_fmt yuv420p -movflags +faststart '{path}'")
    shutil.rmtree(tmp, ignore_errors=True)
    return path if os.path.exists(path) else None


def cast():
    """the three characters of this step: Hari (an ordinary man), Saraswati (a saree woman), Kishori (kurta, pyjama)"""
    import art_test
    import character_designer as CD
    import story_test as ST
    people = [dict(c, design=CD.design(c)[0]) for c in art_test.PLAN_CAST if c["id"] in ("hari", "saraswati")]
    people += [c for c in ST.designed_cast(None, lambda *a: None) if c["id"] == "kishori"]
    return [{"id": c["id"], "name": c["name"], "look": c["look"], "design": c["design"]} for c in people]


def run(image_fn, log=print, budget=45):
    os.makedirs(OUT, exist_ok=True)
    pic = _Budget(image_fn, budget)
    report = {"characters": {}, "made": 0, "paused": False, "pages": [], "videos": [], "zips": [], "approved": False}
    for rec in cast():
        key = CA.char_key({"name": rec["name"], "look": rec["look"]})
        sj = os.path.join(ROOT, key, "sheet", "sheet.json")
        idx = make_drawings(rec, key, pic, log=log) if not pic.paused else (json.load(open(sj)) if os.path.exists(sj) else {})
        parts = parts_from_front(rec, key, log)
        page = approval_page(rec, key, idx, parts, os.path.join(OUT, f"{rec['name']}_sheet.jpg"))
        vid = walk_video(key, os.path.join(OUT, f"{rec['name']}_walk.mp4"))
        cd = os.path.join(OUT, rec["name"])                 # every generated picture as its own file (artifacts)
        shutil.rmtree(cd, ignore_errors=True)
        src_d = os.path.join(ROOT, key, "sheet")
        if os.path.isdir(src_d):
            shutil.copytree(src_d, cd)
        shutil.copy(os.path.join(ROOT, key, "body_src.png"), os.path.join(cd, "ORIGINAL_reference.png")) \
            if os.path.isdir(cd) and os.path.exists(os.path.join(ROOT, key, "body_src.png")) else None
        z = shutil.make_archive(os.path.join(OUT, f"{rec['name']}_pictures"), "zip", cd) if os.path.isdir(cd) else None
        report["characters"][rec["name"]] = {
            "drawings": {v: {"status": r.get("status"), "attempts": r.get("attempts"),
                             "problems": (r.get("qa") or {}).get("problems"), "metrics": (r.get("qa") or {}).get("metrics")}
                         for v, r in idx.items() if not v.startswith("_")},
            "parts_problems": (parts or {}).get("problems"), "parts_fidelity": (parts or {}).get("fidelity"),
            "cutout_gate": (parts or {}).get("gate"), "suggestion": (parts or {}).get("verdict"), "approved": False}
        report["pages"].append(page)
        if vid:
            report["videos"].append(vid)
        if z:
            report["zips"].append(z)
    report["made"], report["paused"], report["blocker"] = pic.made, pic.paused, pic.blocker
    with open(os.path.join(OUT, "char_sheet_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    keep = os.path.join(ROOT, "_char_sheet")                # kept in the repo too (to be examined later)
    os.makedirs(keep, exist_ok=True)
    for p in report["pages"] + report["videos"] + [os.path.join(OUT, "char_sheet_report.json")]:
        if p and os.path.exists(p):
            shutil.copy(p, os.path.join(keep, os.path.basename(p)))
    return report
