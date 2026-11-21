"""REFERENCE-BASED RECONSTRUCTION - a layered cut-out puppet built from SEPARATE pictures of the same character.

Why: cutting one finished picture into parts cannot work for an arm that crosses the chest - the chest under the
arm was never drawn. So the image provider draws, each with the full-body picture as its reference:
  the TORSO alone (no head, arms, legs), ONE ARM alone (shoulder to fingertips, hanging straight), the LEGS alone
  (waist down). Every piece is scaled to the full-body reference's own measurements (neck, shoulders, hips, leg
  and arm length), its joints are placed (shoulders at the torso's top corners, elbow / wrist / hips / knees /
  ankles along the piece), and every cut between two pieces gets ROUNDED, OVERLAPPING ends - no straight cut line
  ever shows and no gap opens when a joint bends. The far arm is the same arm mirrored and drawn behind the body.
Output: the same rig format as cutout_assets.auto_rig (so cutout_rig draws it unchanged), method = "rebuilt".
"""
import cv2
import numpy as np


def _main(rgba):
    """the biggest single object of a keyed picture, cropped (or None)"""
    m = (rgba[..., 3] > 127).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, a = st[i]
    if a < 1200:
        return None
    out = rgba[y:y + h, x:x + w].copy()
    keep = (lab[y:y + h, x:x + w] == i)
    keep = cv2.dilate(keep.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    out[..., 3] = (out[..., 3] * keep).astype(np.uint8)
    return out


def _scale(rgba, f):
    h, w = rgba.shape[:2]
    return cv2.resize(rgba, (max(2, int(round(w * f))), max(2, int(round(h * f)))), interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)


def _centre_x(alpha, y):
    r = np.where(alpha[int(np.clip(y, 0, alpha.shape[0] - 1))] > 127)[0]
    return float(r.mean()) if len(r) else alpha.shape[1] / 2.0


def _width(alpha, y):
    r = np.where(alpha[int(np.clip(y, 0, alpha.shape[0] - 1))] > 127)[0]
    return float(np.ptp(r) + 1) if len(r) else 0.0


def _round_split(rgba, y_cut, ov):
    """two pieces cut at y_cut, each with a ROUNDED end reaching ov px past the cut (overlap, no straight line)"""
    h, w = rgba.shape[:2]
    a = rgba[..., 3] > 127
    cx, half = _centre_x(rgba[..., 3], y_cut), max(4.0, _width(rgba[..., 3], y_cut) / 2.0)
    yy, xx = np.mgrid[0:h, 0:w]
    ell = ((xx - cx) / (half * 1.05)) ** 2 + ((yy - y_cut) / max(2.0, ov)) ** 2 <= 1.0
    upper = a & ((yy <= y_cut) | ell)
    lower = a & ((yy >= y_cut) | ell)
    up, lo = rgba.copy(), rgba.copy()
    up[..., 3] = np.where(upper, rgba[..., 3], 0)
    lo[..., 3] = np.where(lower, rgba[..., 3], 0)
    return up, lo


def _crop(rgba):
    ys, xs = np.where(rgba[..., 3] > 0)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return rgba[y0:y1, x0:x1].copy(), (x0, y0)


def _piece(rgba, pivot, end):
    spr, (ox, oy) = _crop(rgba)
    dx, dy = end[0] - pivot[0], end[1] - pivot[1]
    return {"sprite": spr, "pivot": (pivot[0] - ox, pivot[1] - oy), "length": float(np.hypot(dx, dy)),
            "rest": float(np.degrees(np.arctan2(dx, dy)))}


def measure(ref_rgba, ref_rig):
    """the reference's own measurements (from the cut rig of the full-body picture, or its silhouette)"""
    a = ref_rgba[..., 3] > 127
    ys, xs = np.where(a)
    top, bot = float(ys.min()), float(ys.max())
    H = bot - top
    if ref_rig:
        neck, hip = ref_rig["neck"], ref_rig["hip"]
    else:
        neck = (_centre_x(ref_rgba[..., 3], top + 0.2 * H), top + 0.2 * H)
        hip = (_centre_x(ref_rgba[..., 3], top + 0.52 * H), top + 0.52 * H)
    sh_y = int(neck[1] + 0.06 * H)
    row = (ref_rgba[..., 3][sh_y] > 127).astype(np.int8)            # the body's own width at the shoulders: the run
    d = np.diff(np.concatenate([[0], row, [0]]))                       # that holds the neck column (not the arms)
    runs = list(zip(np.where(d == 1)[0], np.where(d == -1)[0] - 1))
    run = min(runs, key=lambda r: 0 if r[0] <= neck[0] <= r[1] else min(abs(r[0] - neck[0]), abs(r[1] - neck[0]))) if runs else None
    return {"top": top, "bot": bot, "H": H, "neck": tuple(neck), "hip": tuple(hip), "shoulder_w": float(run[1] - run[0] + 1) if run else 0.0,
            "head_h": neck[1] - top}


def rebuild(ref_rgba, ref_rig, pieces, plan=None):
    """-> (rig, problems). Every piece is placed in the REFERENCE picture's coordinates.
    pieces: {"torso", "arm", and "legs" and/or "skirt", optional "pallu", "hair_back"} (keyed RGBA pictures)"""
    plan = plan or {"pieces": list(pieces), "layers": None, "floats": False, "head_fraction": (0.10, 0.33)}
    torso_rgba, arm_rgba = pieces["torso"], pieces["arm"]
    probs = []
    M = measure(ref_rgba, ref_rig)
    H = M["H"]
    parts = {}
    # ---- torso: neck at the top centre, hips at the bottom; scaled so neck->hip matches the reference
    t = _main(torso_rgba)
    if t is None:
        return None, ["torso picture empty"]
    th = t.shape[0]
    want = M["hip"][1] - M["neck"][1]
    if want < 0.2 * H:
        probs.append("reference neck / hip not plausible")
        want = 0.32 * H
    f = (want * 1.04) / th
    t = _scale(t, f)
    ta = t[..., 3]
    tn = (_centre_x(ta, 2), 0.0)
    thip = (_centre_x(ta, t.shape[0] - 3), float(t.shape[0] - 1) / 1.04)
    shy = 0.13 * t.shape[0]
    r = np.where(ta[int(shy)] > 127)[0]
    sw = float(np.ptp(r) + 1) if len(r) else t.shape[1] * 0.8
    if M["shoulder_w"] and not 0.5 <= sw / M["shoulder_w"] <= 2.3:   # (long hair over the shoulders widens the reference)
        probs.append(f"torso shoulders {sw / M['shoulder_w']:.2f} x the reference - proportions differ")
    sh_far = (float(r.min()) + 0.18 * sw if len(r) else 0.2 * t.shape[1], shy)
    sh_near = (float(r.max()) - 0.18 * sw if len(r) else 0.8 * t.shape[1], shy)
    ox, oy = M["neck"][0] - tn[0], M["neck"][1] - tn[1]              # torso placed with its neck on the reference neck
    parts["torso"] = {"sprite": t, "pivot": thip, "length": float(np.hypot(tn[0] - thip[0], tn[1] - thip[1])),
                      "rest": float(np.degrees(np.arctan2(tn[0] - thip[0], tn[1] - thip[1])))}
    hip_c = (thip[0] + ox, thip[1] + oy)
    neck = (tn[0] + ox, tn[1] + oy)
    shoulders = {"far": (sh_far[0] + ox, sh_far[1] + oy), "near": (sh_near[0] + ox, sh_near[1] + oy)}
    # ---- arm: shoulder -> fingertips straight down; the length of a natural cartoon arm (0.40 of the height)
    a_ = _main(arm_rgba)
    if a_ is None:
        return None, probs + ["arm picture empty"]
    if a_.shape[0] < 2.2 * a_.shape[1]:
        probs.append("the arm is not drawn straight / alone")
    a_ = _scale(a_, 0.40 * H / a_.shape[0])
    ah = a_.shape[0]
    aa = a_[..., 3]
    sh_p = (_centre_x(aa, 0.04 * ah), 0.04 * ah)
    el_y, wr_y = 0.46 * ah, 0.80 * ah
    el_p, wr_p = (_centre_x(aa, el_y), el_y), (_centre_x(aa, wr_y), wr_y)
    up, lo = _round_split(a_, el_y, 0.035 * ah)
    top_cap = np.mgrid[0:ah, 0:a_.shape[1]]                          # the shoulder end is rounded too (a sleeve top)
    ell = ((top_cap[1] - sh_p[0]) / max(4.0, _width(aa, 0.08 * ah) / 2)) ** 2 + ((top_cap[0] - 0.08 * ah) / (0.08 * ah)) ** 2 <= 1
    up[..., 3] = np.where((top_cap[0] >= 0.08 * ah) | ell, up[..., 3], 0)
    for side in ("near", "far"):
        shade = 1.0 if side == "near" else 0.8                       # the far arm: the same arm, mirrored, in shadow
        u_, l_ = up.copy(), lo.copy()
        if side == "far":
            u_[..., :3] = (u_[..., :3] * shade).astype(np.uint8)
            l_[..., :3] = (l_[..., :3] * shade).astype(np.uint8)
        parts[f"uarm_{side}"] = _piece(u_, sh_p, el_p)
        parts[f"farm_{side}"] = _piece(l_, el_p, wr_p)
    leg_hips = {}
    extra = {}
    if "skirt" in pieces:                                   # ---- a saree / long dress / ghost robe: ONE cloth in two
        sk = _main(pieces["skirt"])                         # layers (waist->knee, knee->hem) that bend with the legs
        if sk is None:
            return None, probs + ["skirt picture empty"]
        want_s = M["bot"] - hip_c[1] + 0.05 * H
        sk = _scale(sk, want_s / sk.shape[0])
        sh_, sw_ = sk.shape[:2]
        waist = (_centre_x(sk[..., 3], 3), 0.0)
        knee_y = 0.5 * sh_
        up, lo = _round_split(sk, knee_y, 0.04 * sh_)
        kp = (_centre_x(sk[..., 3], knee_y), knee_y)
        hem = (_centre_x(sk[..., 3], sh_ - 3), float(sh_ - 1))
        parts["skirt_up"] = _piece(up, waist, kp)
        parts["skirt_lo"] = _piece(lo, kp, hem)
        extra.update(skirt_len=float(want_s - 0.05 * H), waist=(hip_c[0], hip_c[1] - 0.05 * H))
    if "pallu" in pieces:                                   # ---- the saree's loose end, hanging from the far shoulder
        pl = _main(pieces["pallu"])
        if pl is not None:
            pl = _scale(pl, 0.45 * H / pl.shape[0])
            top = (_centre_x(pl[..., 3], 3), 0.0)
            parts["pallu"] = _piece(pl, top, (_centre_x(pl[..., 3], pl.shape[0] - 3), float(pl.shape[0] - 1)))
            extra["pallu_anchor"] = (shoulders["far"][0], shoulders["far"][1] - 0.02 * H)
        else:
            probs.append("pallu picture empty")
    if "hair_back" in pieces:                               # ---- long hair behind the back (sways with the head)
        hb = _main(pieces["hair_back"])
        if hb is not None:
            hb = _scale(hb, 2.3 * M["head_h"] / hb.shape[0])
            top = (_centre_x(hb[..., 3], 3), 0.0)
            parts["hair_back"] = _piece(hb, top, (_centre_x(hb[..., 3], hb.shape[0] - 3), float(hb.shape[0] - 1)))
            extra["hair_anchor"] = (M["neck"][0], M["top"] + 0.22 * M["head_h"])
        else:
            probs.append("back-hair picture empty")
    if "legs" not in pieces:                                # (no legs piece: a saree / dress / floating ghost)
        g = None
    else:
        g = _main(pieces["legs"])
        if g is None:
            return None, probs + ["legs picture empty"]
    if g is not None:
        pass
    else:
        rig = _finish(M, H, neck, hip_c, shoulders, leg_hips, parts, extra, plan, ref_rgba, ref_rig)
        return rig, probs
    # ---- legs: waist at the reference hips, the two legs split at their gap, rounded knees
    want_l = M["bot"] - M["hip"][1] + 0.06 * H
    g = _scale(g, want_l / g.shape[0])
    gh, gw = g.shape[:2]
    ga = g[..., 3] > 127
    sep, found = gw / 2.0, False
    for y in range(int(gh * 0.95), int(gh * 0.25), -1):              # the gap between the legs, from the feet up
        rr = []
        d = np.diff(np.concatenate([[0], ga[y].astype(np.int8), [0]]))
        for x0, x1 in zip(np.where(d == 1)[0], np.where(d == -1)[0] - 1):
            if x1 - x0 > 3:
                rr.append((x0, x1))
        if len(rr) >= 2:
            sep, found = (rr[0][1] + rr[1][0]) / 2.0, True
            gap_top = y
        elif found:
            break
    if not found:
        probs.append("no gap between the legs in the legs picture - split at the middle - unusual")
        gap_top = int(0.5 * gh)
    waist = (_centre_x(g[..., 3], 3), 0.0)
    gox, goy = hip_c[0] - waist[0], hip_c[1] - 0.06 * H - waist[1]
    XX = np.arange(gw)[None, :]
    ov = 6
    for side, sel in (("far", XX < sep + ov), ("near", XX >= sep - ov)):
        leg = g.copy()
        leg[..., 3] = np.where(sel & ga, g[..., 3], 0)
        la = leg[..., 3]
        ys_ = np.where((la > 127).any(axis=1))[0]
        lb = float(ys_.max())
        hip_y = 0.07 * gh
        hip_p = (_centre_x(la, max(hip_y, min(gap_top, 0.2 * gh))), hip_y)
        knee_y = hip_p[1] + 0.48 * (lb - hip_p[1])
        ank_y = lb - 0.06 * H
        knee_p, ank_p = (_centre_x(la, knee_y), knee_y), (_centre_x(la, ank_y), ank_y)
        th_, sh_ = _round_split(leg, knee_y, 0.03 * gh)
        parts[f"thigh_{side}"] = _piece(th_, hip_p, knee_p)
        parts[f"shin_{side}"] = _piece(sh_, knee_p, ank_p)
        leg_hips[side] = (hip_p[0] + gox, hip_p[1] + goy)
    rig = _finish(M, H, neck, hip_c, shoulders, leg_hips, parts, extra, plan, ref_rgba, ref_rig)
    return rig, probs


def _finish(M, H, neck, hip_c, shoulders, leg_hips, parts, extra, plan, ref_rgba, ref_rig):
    if ref_rig and "head" in ref_rig["parts"]:            # the reference's head (the head drawings replace it in use)
        parts["head"] = ref_rig["parts"]["head"]
    else:
        hm = ref_rgba.copy()
        hm[int(M["neck"][1]) + 4:, :, 3] = 0
        parts["head"] = _piece(hm, M["neck"], (M["neck"][0], M["top"]))
    rig = {"height_px": H, "top": M["top"], "bottom": M["bot"], "neck": neck, "hip": hip_c, "shoulder_y": shoulders["near"][1],
           "torso_len": float(np.hypot(neck[0] - hip_c[0], neck[1] - hip_c[1])), "head_h": M["head_h"], "parts": parts,
           "shoulders": shoulders, "leg_hips": leg_hips, "arm_free": {"near": True, "far": True},
           "method": "rebuilt", "legs_under_torso": True, "no_legs": not leg_hips, "layers": plan.get("layers"),
           "floats": bool(plan.get("floats")), "head_fraction": list(plan.get("head_fraction", (0.10, 0.33)))}
    rig.update(extra)
    return rig
