"""CONSISTENCY - the separately generated pieces must be the SAME character as the full-body reference.

Measured (never assumed), each against the matching region of the reference picture:
  clothing colours   dominant colours (k-means, Lab) of the piece vs the region it must match  (mean delta-E)
  fabric pattern     edge density (prints, checks, borders) of the piece vs its region            (ratio)
  skin tone          median skin colour of a hand / face vs the reference face                    (delta-E)
  hair               hair colour of every head drawing (and the back-hair piece) vs the reference  (delta-E)
  face identity      the head drawings among themselves: skin, hair, eye spacing / face width      (delta-E, ratio)
  proportions/joints checked by cutout_rebuild + asset_qa (shoulders, hips, arm and leg lengths)
A piece that fails is REJECTED and made again from the reference (never silently accepted).
"""
import cv2
import numpy as np

REGION = {"torso": "torso", "arm": "torso", "legs": "lower", "skirt": "lower", "pallu": "torso", "hair_back": "head"}
MAX_COLOUR_DE = 26.0
MAX_SKIN_DE = 22.0
MAX_HAIR_DE = 28.0


def _px(rgba, mask=None):
    a = rgba[..., 3] > 200
    if mask is not None:
        a &= mask
    return rgba[..., :3][a]


def _lab(bgr_px):
    if not len(bgr_px):
        return np.zeros((0, 3), np.float32)
    return cv2.cvtColor(bgr_px.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32) * \
        np.array([100 / 255.0, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)


def palette(rgba, mask=None, k=3):
    """the dominant colours (Lab) and their shares, outlines (very dark) left out"""
    px = _px(rgba, mask)
    px = px[px.max(axis=1) > 45]
    if len(px) < 50:
        return []
    if len(px) > 6000:
        px = px[np.random.default_rng(1).choice(len(px), 6000, replace=False)]
    lab = _lab(px)
    k = min(k, len(lab))
    _, lab_, cen = cv2.kmeans(lab, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5), 2, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lab_.ravel(), minlength=k) / len(lab_)
    return [(cen[i], float(share[i])) for i in range(k) if share[i] > 0.08]


def palette_de(a, b):
    """how far a's main colours are from the nearest of b's (weighted mean delta-E)"""
    if not a or not b:
        return 99.0
    tot = 0.0
    for c, w in a:
        tot += w * min(float(np.linalg.norm(c - c2)) for c2, _ in b)
    return tot / sum(w for _, w in a)


def edge_density(rgba, mask=None):
    g = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2GRAY)
    a = rgba[..., 3] > 200
    if mask is not None:
        a &= mask
    inner = cv2.erode(a.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    if inner.sum() < 200:
        return 0.0
    e = cv2.Canny(g, 60, 140) > 0
    return float(e[inner].mean())


def skin_tone(rgba, mask=None):
    px = _px(rgba, mask)
    if not len(px):
        return None
    hsv = cv2.cvtColor(px.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    sel = (hsv[:, 0] >= 5) & (hsv[:, 0] <= 25) & (hsv[:, 1] >= 40) & (hsv[:, 1] <= 170) & (hsv[:, 2] >= 70)   # (not red cloth)
    if sel.sum() < 30:
        return None
    return np.median(_lab(px[sel]), axis=0)


def hair_tone(head_rgba):
    a = head_rgba[..., 3] > 200
    ys = np.where(a.any(axis=1))[0]
    if not len(ys):
        return None
    top = ys.min()
    band = np.zeros_like(a)
    band[top:top + max(4, int(0.18 * (ys.max() - top)))] = True
    px = _px(head_rgba, band)
    return np.median(_lab(px), axis=0) if len(px) > 20 else None


def regions(ref_rgba, M):
    """masks of the reference: head (top -> neck), torso (neck -> hips, the body's own width), lower (hips -> feet)"""
    h, w = ref_rgba.shape[:2]
    yy = np.arange(h)[:, None]
    a = ref_rgba[..., 3] > 127
    nx = M["neck"][0]
    half = max(10.0, M.get("shoulder_w", 0.3 * w) / 2.0)
    core = np.abs(np.arange(w)[None, :] - nx) <= half
    return {"head": a & (yy < M["neck"][1]), "torso": a & (yy >= M["neck"][1]) & (yy <= M["hip"][1]) & core,
            "lower": a & (yy > M["hip"][1])}


def check_piece(kind, piece, ref_rgba, M, ghost=False):
    """one piece against its region of the reference -> {metrics, problems}"""
    reg = regions(ref_rgba, M)[REGION.get(kind, "torso")]
    out, probs = {}, []
    if kind == "hair_back":
        ht, hp = hair_tone(ref_rgba), np.median(_lab(_px(piece)), axis=0) if len(_px(piece)) else None
        if ht is not None and hp is not None:
            out["hair_de"] = round(float(np.linalg.norm(ht - hp)), 1)
            if out["hair_de"] > MAX_HAIR_DE:
                probs.append(f"hair colour differs from the character's hair (dE {out['hair_de']})")
        return {"metrics": out, "problems": probs}
    de = palette_de(palette(piece), palette(ref_rgba, reg))
    out["colour_de"] = round(de, 1)
    if de > MAX_COLOUR_DE:
        probs.append(f"clothing colours differ from the reference (dE {de:.1f} > {MAX_COLOUR_DE})")
    ep, er = edge_density(piece), edge_density(ref_rgba, reg)
    out["pattern_ratio"] = round((ep + 0.004) / (er + 0.004), 2)
    if kind in ("torso", "legs", "skirt") and er > 0.02 and not 0.35 <= out["pattern_ratio"] <= 2.8:   # (a sleeve may be plain)
        probs.append(f"fabric pattern differs (detail {out['pattern_ratio']}x the reference)")
    if kind == "arm" and not ghost:                       # the hand's skin = the face's skin
        s1, s0 = skin_tone(piece), skin_tone(ref_rgba, regions(ref_rgba, M)["head"])
        if s1 is not None and s0 is not None:
            out["skin_de"] = round(float(np.linalg.norm(s1 - s0)), 1)
            if out["skin_de"] > MAX_SKIN_DE:
                probs.append(f"skin tone of the hand differs from the face (dE {out['skin_de']})")
    return {"metrics": out, "problems": probs}


def check_head(head, ref_rgba, M, master=None, marks=None, master_marks=None, ghost=False):
    """a head drawing vs the reference head (skin, hair) and vs the master three-quarter head (identity)"""
    reg = regions(ref_rgba, M)["head"]
    out, probs = {}, []
    s1, s0 = skin_tone(head), skin_tone(ref_rgba, reg)
    if s1 is not None and s0 is not None and not ghost:    # (a ghost's pale / glowing skin is meant to differ)
        out["skin_de"] = round(float(np.linalg.norm(s1 - s0)), 1)
        if out["skin_de"] > MAX_SKIN_DE:
            probs.append(f"skin tone differs from the character (dE {out['skin_de']})")
    hb, hr = hair_tone(head), hair_tone(ref_rgba)
    if hb is not None and hr is not None:
        out["hair_de"] = round(float(np.linalg.norm(hb - hr)), 1)
        if out["hair_de"] > MAX_HAIR_DE:
            probs.append(f"hair differs from the character (dE {out['hair_de']})")
    if master is not None:
        de = palette_de(palette(head), palette(master))
        out["identity_colour_de"] = round(de, 1)
        if de > MAX_COLOUR_DE:
            probs.append(f"not the same face as the three-quarter head (colours dE {de:.1f})")
        if marks and master_marks and len(marks.get("eyes", [])) == 2 and len(master_marks.get("eyes", [])) == 2:
            r1 = abs(marks["eyes"][1][0] - marks["eyes"][0][0]) / max(1.0, marks["face_w"])
            r0 = abs(master_marks["eyes"][1][0] - master_marks["eyes"][0][0]) / max(1.0, master_marks["face_w"])
            out["eye_spacing_ratio"] = round(r1 / max(0.01, r0), 2)
    return {"metrics": out, "problems": probs}
