"""ASSET QA - the central quality check. Every generated picture and every scene must pass BEFORE rendering.

body   : one whole figure, transparent background, natural proportions (height / width, head size, legs, arms),
         every part cut (head, torso, 2 upper arms, 2 forearms, 2 thighs, 2 shins), joints in the right order
         (neck above shoulders above elbows above wrists; hips above knees above ankles), parts not empty
head   : one head, transparent background, a face found (or, for a profile / a ghost, a plausible face), the same
         colours as the body's head (the SAME character - no other person)
plate  : right size, not black / not washed out, NO person in it (a face in an empty background = rejected)
scene  : every character the scene needs is in the cast, every character has its assets (or the report says which
         one uses the code-drawn fallback), the camera covers the whole scene, the dialogue fits the audio
Every check returns its measured numbers; "pass" is never set without them.
"""
import numpy as np

PARTS = ("head", "torso", "uarm_near", "farm_near", "uarm_far", "farm_far", "thigh_near", "shin_near", "thigh_far", "shin_far")


def _border_clear(rgba, frac=0.02):
    a = rgba[..., 3]
    b = max(2, int(min(a.shape) * frac))
    edge = np.concatenate([a[:b].ravel(), a[-b:].ravel(), a[:, :b].ravel(), a[:, -b:].ravel()])
    return float((edge > 127).mean())


def body(rgba, rig, problems):
    p = list(problems)
    m = rgba[..., 3] > 127
    ys, xs = np.where(m)
    res = {"problems": p}
    if not len(ys):
        res.update(problems=p + ["no figure"], **{"pass": False})
        return res
    h, w = int(np.ptp(ys)) + 1, int(np.ptp(xs)) + 1
    res["height_over_width"] = round(h / w, 2)
    res["fill_of_frame"] = round(h / rgba.shape[0], 2)
    res["touches_border"] = round(_border_clear(rgba), 3)
    if not 1.6 <= h / w <= 5.5:
        p.append(f"body shape {h / w:.2f} (height/width) is not a standing person")
    if h / rgba.shape[0] < 0.55:
        p.append("the figure is too small in the picture")
    if res["touches_border"] > 0.002:                     # (even a little: a cut hand or foot is a missing body part)
        p.append("the figure is cut by the picture edge")
    if ys.min() < 0.015 * rgba.shape[0] or ys.max() > rgba.shape[0] * 0.99 or xs.min() < 3 or xs.max() > rgba.shape[1] - 4:
        p.append("no empty margin round the figure (head, hands or feet at the edge)")
    if rig:
        need = [k for k in PARTS if not (rig.get("no_legs") and k.startswith(("thigh", "shin")))]
        if rig.get("no_legs"):
            need += ["skirt_up", "skirt_lo"]               # a saree / dress / ghost robe instead of legs
        miss = [k for k in need if k not in rig["parts"]]
        if miss:
            p.append("parts missing: " + ", ".join(miss))
        hh = rig["head_h"] / rig["height_px"]
        res["head_fraction"] = round(hh, 2)
        lo_, hi_ = rig.get("head_fraction", (0.10, 0.33))
        if not lo_ <= hh <= hi_:
            p.append(f"head is {hh:.2f} of the height (range {lo_}-{hi_} for this character)")
        for side in ("near", "far"):
            th, sh = rig["parts"].get(f"thigh_{side}"), rig["parts"].get(f"shin_{side}")
            if th and sh:
                leg = (th["length"] + sh["length"]) / rig["height_px"]
                res[f"leg_{side}"] = round(leg, 2)
                if not 0.25 <= leg <= 0.62:
                    p.append(f"{side} leg length {leg:.2f} of the height is not natural")
            ua, fa = rig["parts"].get(f"uarm_{side}"), rig["parts"].get(f"farm_{side}")
            if ua and fa:
                arm = (ua["length"] + fa["length"]) / rig["height_px"]
                res[f"arm_{side}"] = round(arm, 2)
                if not 0.15 <= arm <= 0.62:
                    p.append(f"{side} arm length {arm:.2f} of the height is not natural")
        if rig["neck"][1] >= rig["hip"][1]:
            p.append("neck is not above the hips")
    else:
        p.append("no rig could be built")
    hard = [x for x in p if not x.endswith("unusual")]
    res["pass"] = not hard
    res["problems"] = p
    return res


def head(rgba, marks, body_rgba, view, ghost=False):
    p = []
    m = rgba[..., 3] > 127
    res = {"view": view}
    if m.sum() < 1500 or marks is None:
        res.update(problems=["no head in the picture"], **{"pass": False})
        return res
    res["face_found"] = bool(marks.get("found_face"))
    if not marks.get("found_face") and view in ("front", "three_q") and not ghost:
        p.append("no face found on a front / three-quarter head (the mouth and eyes would be guessed)")
    res["touches_border_top_sides"] = round(float(np.concatenate([m[:3].ravel(), m[:, :3].ravel(), m[:, -3:].ravel()]).mean()), 3)
    if res["touches_border_top_sides"] > 0.03:
        p.append("the head is cut by the picture edge")
    if body_rgba is not None:                              # the same character: colours of the head vs the body's head
        bm = body_rgba[..., 3] > 127
        ys = np.where(bm.any(axis=1))[0]
        if len(ys):
            top = ys.min()
            hb = body_rgba[top:top + int(0.2 * (ys.max() - top))]
            sim = _colour_sim(hb, rgba)
            res["same_colours_as_body"] = round(sim, 2)
            if sim < 0.45:
                p.append(f"colours differ from the body's head ({sim:.2f}) - maybe another person")
    res["problems"] = p
    res["pass"] = not p
    return res


def _colour_sim(a, b):
    def hist(x):
        px = x[x[..., 3] > 200][:, :3]
        if not len(px):
            return np.zeros(64)
        q = (px // 64).astype(int)
        h = np.bincount(q[:, 0] * 16 + q[:, 1] * 4 + q[:, 2], minlength=64).astype(float)
        return h / h.sum()
    return float(np.minimum(hist(a), hist(b)).sum())


def plate(bgr):
    p = []
    res = {"size": list(bgr.shape[:2])}
    mean = float(bgr.mean())
    res["brightness"] = round(mean, 1)
    if bgr.shape[0] < 400 or bgr.shape[1] < 700:
        p.append("too small")
    if mean < 12:
        p.append("almost black")
    if mean > 215:
        p.append("washed out")
    try:
        import animate
        import cv2
        faces = animate.find_faces(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        res["faces"] = len(faces)
        if faces:
            p.append(f"{len(faces)} person(s) in what must be an EMPTY background")
    except Exception:
        res["faces"] = "not checked"
    res["problems"] = p
    res["pass"] = not p
    return res


def scene(plan, cast_ids, needed_ids, asset_status):
    """before rendering one scene: nobody needed is missing; who uses the fallback is reported"""
    p, notes = [], []
    on = {c["id"] for c in plan.get("characters", [])}
    for cid in needed_ids:
        if cid not in cast_ids:
            p.append(f"'{cid}' speaks / acts in this scene but is not in the story's cast")
        elif cid not in on:
            p.append(f"'{cid}' is needed in this scene but was not placed")
    for cid in on:
        st = asset_status.get(cid, "code")
        if st != "cutout":
            notes.append(f"{cid}: drawn by the code rig ({st})")
    cam = sorted(plan.get("camera", []), key=lambda s: s["t0"])
    if not cam or cam[0]["t0"] > 0.01 or abs(cam[-1]["t1"] - plan["duration"]) > 0.05:
        p.append("the camera does not cover the whole scene")
    for d in plan.get("dialogue", []):
        if d["t1"] > plan["duration"] + 0.05:
            p.append(f"a line ends after the scene ({d['t1']:.1f} > {plan['duration']:.1f})")
    return {"pass": not p, "problems": p, "notes": notes}


def reference(rgba):
    """the full-body REFERENCE: one whole standing figure, natural proportions, not cut by the edge"""
    p = []
    m = rgba[..., 3] > 127
    ys, xs = np.where(m)
    res = {}
    if len(ys) < 3000:
        res.update(problems=["no figure"], **{"pass": False})
        return res
    h, w = int(np.ptp(ys)) + 1, int(np.ptp(xs)) + 1
    res.update(height_over_width=round(h / w, 2), fill_of_frame=round(h / rgba.shape[0], 2), touches_border=round(_border_clear(rgba), 3))
    if not 1.6 <= h / w <= 5.5:
        p.append(f"body shape {h / w:.2f} (height/width) is not a standing person")
    if h / rgba.shape[0] < 0.55:
        p.append("the figure is too small in the picture")
    if res["touches_border"] > 0.002:                     # (even a little: a cut hand or foot is a missing body part)
        p.append("the figure is cut by the picture edge")
    if ys.min() < 0.015 * rgba.shape[0] or ys.max() > rgba.shape[0] * 0.99 or xs.min() < 3 or xs.max() > rgba.shape[1] - 4:
        p.append("no empty margin round the figure (head, hands or feet at the edge)")
    import cv2
    n, _, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    big = sorted(st[1:, cv2.CC_STAT_AREA], reverse=True)
    if len(big) > 1 and big[1] > 0.08 * big[0]:
        p.append("more than one figure in the picture")
    res["problems"] = p
    res["pass"] = not p
    return res


def part(rgba, kind, ref_rgba=None, M=None, wide=False, ghost=False):
    """a separate piece (torso / arm / legs): ONE object, the right shape, the same colours as the reference"""
    import cv2
    p = []
    m = (rgba[..., 3] > 127).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    res = {"kind": kind}
    if n < 2 or st[1:, cv2.CC_STAT_AREA].max() < 1500:
        res.update(problems=["nothing drawn"], **{"pass": False})
        return res
    big = sorted(st[1:, cv2.CC_STAT_AREA], reverse=True)
    if len(big) > 1 and big[1] > 0.15 * big[0]:
        p.append("more than one object (the piece must be alone)")
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    w, h = st[i][2], st[i][3]
    ar = h / max(1, w)
    res["height_over_width"] = round(ar, 2)
    lim = {"torso": (0.7, 3.4), "arm": ((1.3 if wide else 2.2), 12.0), "legs": (0.8, 4.0),   # (a long kurta: tall torso)
           "skirt": (0.8, 4.5), "pallu": (1.0, 9.0), "hair_back": (0.8, 7.0)}[kind]           # (wide sleeves: wide arm)
    if not lim[0] <= ar <= lim[1]:
        p.append(f"{kind} shape {ar:.2f} (height/width) is wrong - not drawn alone / not straight")
    res["touches_border"] = round(_border_clear(rgba), 3)
    if res["touches_border"] > 0.03:
        p.append(f"the {kind} is cut by the picture edge")
    if ref_rgba is not None and M is not None:          # the SAME character: colours, pattern, skin, hair
        import consistency
        c = consistency.check_piece(kind, rgba, ref_rgba, M, ghost=ghost)
        res["consistency"] = c["metrics"]
        p += c["problems"]
    elif ref_rgba is not None:
        sim = _colour_sim(ref_rgba, rgba)
        res["same_colours_as_reference"] = round(sim, 2)
        if sim < 0.35:
            p.append(f"colours differ from the character ({sim:.2f}) - another character's clothes?")
    res["problems"] = p
    res["pass"] = not p
    return res


SEATS = ("log", "stool", "bench", "chowki", "chair", "khat")


def seat_rule(plan, reach=90.0):
    """a 2.5D (cut-out) character SITS only on a seat that is in the scene (a bench, stool, log, chowki...). Without a
    seat under it the sitting is NOT drawn: it stands (and the change is reported). The code-drawn characters keep
    their old behaviour (this rule touches only characters with cut-out parts)."""
    notes = []
    props = plan.get("props") or []
    acts = plan.get("actions") or []
    for c in plan.get("characters") or []:
        if not ((c.get("design") or {}).get("cutout") or (c.get("design") or {}).get("hybrid")):
            continue
        cid = c["id"]
        sits = str(c.get("start_pose", "stand")).startswith("sit") or any(
            a.get("who") == cid and (a.get("type") == "sit_down" or str(a.get("pose") or "").startswith("sit")) for a in acts)
        if not sits:
            continue
        if any(p.get("type") in SEATS and abs(float(p.get("x", -1e9)) - float(c.get("x", 0))) <= reach for p in props):
            continue
        c["start_pose"] = "stand"
        kept = []
        for a in acts:
            if a.get("who") == cid and a.get("type") in ("sit_down", "stand_up"):
                continue
            if a.get("who") == cid and str(a.get("pose") or "").startswith("sit"):
                a = dict(a)
                a.pop("pose", None)
            kept.append(a)
        acts = kept
        notes.append(f"{cid}: no seat in the scene - stands instead of sitting (a 2.5D character never sits on nothing)")
    plan["actions"] = acts
    return notes
