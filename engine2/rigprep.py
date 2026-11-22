"""ASSET PREPARATION (engine 2, rig track) - one flattened ORIGINAL reference -> clean, separate, transparent layers.

A cartoon drawing is flat colour areas separated by black ink lines. This module separates the drawing ALONG ITS
OWN INK LINES (never along a guessed rectangle):

1. remove the background (the library's cut-out alpha) and the drawn ground shadow
2. flat-colour regions = connected areas between ink lines; a drawn line that stops short is finished by a
   hand-checked 'close' segment from the character's prep.json
3. each region goes to the part whose seed point lies in it; small leftovers go to the nearest part
4. every part keeps the ink line around it (a line between two parts is in BOTH, so each has a full outline)
5. trousers are split into pelvis + two legs along the drawn crotch line; the feet are what is below the hems
6. hidden-region reconstruction is deliberately small and honest: a strip of the part's OWN colour continues a
   part where the drawing shows it disappearing behind another part (far arm behind the torso, wrist inside the
   cuff, ankle inside the hem, neck under the jaw). Nothing else is invented. A pose that would reveal more than
   these strips needs a new complete drawing - the QA says so instead of guessing pixels.

Output: layers/<part>.png (full canvas, so they sit exactly as drawn), layers.json, a diagnostic sheet.
"""
import json
import os

import cv2
import numpy as np


def _label_regions(rgba, ink_value, closes):
    al = rgba[..., 3] > 127
    v = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2HSV)[..., 2]
    ink = (v < ink_value) & al
    cut = np.zeros(al.shape, np.uint8)
    for pts in closes:                                    # hand-checked polylines that finish a drawn line
        cv2.polylines(cut, [np.int32(pts)], False, 1, 2)
    ink = ink | (cut > 0)
    reg = (al & ~ink).astype(np.uint8)
    n, lab = cv2.connectedComponents(reg, connectivity=4)
    return al, ink, lab, cut > 0


def _poly_cut(shape, pts, w=2):
    m = np.zeros(shape, np.uint8)
    cv2.polylines(m, [np.int32(pts)], False, 1, w)
    return m > 0


def _comp_at(mask, pt):
    n, lab = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
    x, y = int(pt[0]), int(pt[1])
    if lab[y, x] == 0:                                     # the seed sits on a line: nearest component pixel
        ys, xs = np.nonzero(lab)
        i = np.argmin((xs - x) ** 2 + (ys - y) ** 2)
        x, y = xs[i], ys[i]
    return lab == lab[y, x]


def prepare(ref_rgba, cfg, out_dir):
    os.makedirs(os.path.join(out_dir, "layers"), exist_ok=True)
    H, W = ref_rgba.shape[:2]
    al, ink, lab, cutline = _label_regions(ref_rgba, cfg.get("ink_value", 90), cfg.get("close", []))
    seeds = cfg["seeds"]
    owner = np.zeros((H, W), np.int32)                     # 0 = nobody
    names = []

    def own(name, mask):
        if name not in names:
            names.append(name)
        owner[mask & (owner == 0)] = names.index(name) + 1

    for name, pts in seeds.items():
        for p in pts:
            x, y = int(p[0]), int(p[1])
            k = lab[y, x]
            if k == 0:                                     # the seed is on a line: the nearest region within 8 px
                win = lab[max(0, y - 8):y + 9, max(0, x - 8):x + 9]
                ys, xs = np.nonzero(win)
                if len(ys):
                    i = np.argmin((ys - min(8, y)) ** 2 + (xs - min(8, x)) ** 2)
                    k = win[ys[i], xs[i]]
            if k:
                own(name, lab == k)
    # leftover flat regions (buttons, folds, fingers...) -> the nearest owned part
    shadow_i = names.index("shadow") + 1 if "shadow" in names else -1
    sh_seed = owner == shadow_i
    owner[sh_seed] = 0                                     # (the shadow never takes leftovers: toes are not shadow)
    left = (lab > 0) & (owner == 0) & ~sh_seed
    if left.any():
        dist, idx = cv2.distanceTransformWithLabels((owner == 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(owner > 0)
        lut = np.zeros(idx.max() + 1, np.int32)
        lut[idx[ys, xs]] = owner[ys, xs]
        owner[left] = lut[idx[left]]
    owner[sh_seed] = shadow_i
    flat = {n: owner == names.index(n) + 1 for n in names if n != "shadow"}
    shadow = owner == shadow_i
    shadow = cv2.dilate(shadow.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    # trousers -> pelvis + two legs (along the drawn crotch line), feet = below the hems
    pc = cfg.get("pants")
    if pc and "pants" in flat:
        P = flat.pop("pants")
        yy = np.mgrid[0:H, 0:W][0]
        if not pc.get("no_pelvis"):                         # (a separate pelvis piece; without it each leg reaches
            flat["pelvis"] = P & (yy <= pc["pelvis_bottom"])   # the waistband and bends at the hip as one mesh)
        legs = P & (yy >= pc["legs_top"]) & ~_poly_cut((H, W), pc["split"])
        for nm, sp in pc["leg_seeds"].items():
            flat[nm] = _comp_at(legs, sp)
    fc = cfg.get("feet")
    if fc:
        yy = np.mgrid[0:H, 0:W][0]
        used = np.zeros((H, W), bool)
        for m in flat.values():
            used |= m
        below = al & ~shadow & (yy >= fc["top"]) & ~used
        lg = [n for n in (cfg.get("pants") or {}).get("leg_seeds", {}) if n in flat]
        if lg:                                               # the trouser's own outline is not the foot's
            legm = np.zeros((H, W), bool)
            for n in lg:
                legm |= flat[n]
            dleg = cv2.distanceTransform((~legm).astype(np.uint8), cv2.DIST_L2, 5)
            below &= ~(ink & (dleg <= 5))
        below = cv2.morphologyEx(below.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
        hsv = cv2.cvtColor(ref_rgba[..., :3], cv2.COLOR_BGR2HSV)
        cloth = below & (hsv[..., 1] < 45) & (hsv[..., 2] > 85) & (hsv[..., 2] < 185)   # trouser cloth below a hem
        cloth = cv2.morphologyEx(cloth.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        legs_ = [n for n in (pc or {}).get("leg_seeds", {}) if n in flat]
        if legs_ and cloth.any():                            # (a turned-up hem is the trouser's, not the foot's)
            dl = {n: cv2.distanceTransform((~flat[n]).astype(np.uint8), cv2.DIST_L2, 5) for n in legs_}
            near = np.argmin(np.stack([dl[n] for n in legs_]), axis=0)
            for i_, n in enumerate(legs_):
                flat[n] = flat[n] | (cloth & (near == i_) & (dl[n] < 25))
            below = below & ~cloth
            legm2 = np.zeros((H, W), bool)
            for n in legs_:
                legm2 |= flat[n]
            dleg2 = cv2.distanceTransform((~legm2).astype(np.uint8), cv2.DIST_L2, 5)
            below &= ~(ink & (dleg2 <= 5))
        for nm, sp in fc["seeds"].items():
            flat[nm] = _comp_at(below, sp)
    # ink: a line belongs to the part it borders; a line BETWEEN two parts belongs to both (each part gets a full
    # outline). A line that only borders another part (a trouser side next to the foot) is not taken.
    inkpx = (ink | cutline) & al & ~shadow
    dist = {}
    for nm, m in flat.items():
        dist[nm] = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 5)
    dmin = np.min(np.stack(list(dist.values())), axis=0)
    layers = {}
    for nm, m in flat.items():
        layers[nm] = m | (inkpx & (dist[nm] <= 7.0) & (dist[nm] <= dmin + 2.5))
    # a line where one part passes BEHIND another belongs only to the front part
    for back, front, owner in (cfg.get("line_owner") or {}).get("pairs", []):
        if back in layers and front in layers:
            loser = back if owner == front else front
            other = front if loser == back else back
            shared = layers[loser] & layers[other] & inkpx
            layers[loser] &= ~shared | flat[loser]
    # a part that sits UNDER another (foot under the trouser, hand under the cuff) does not carry that part's lines
    for nm, cover in cfg.get("clip_under", {}).items():
        if nm in layers and cover in flat:
            layers[nm] &= ~(cv2.dilate(flat[cover].astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) | flat[nm]
            layers[nm] &= ~(inkpx & (dist[cover] < dist[nm]))
            layers[nm] &= ~(cv2.dilate(layers[cover].astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) | (flat[nm] & ~ink)
            layers[nm] &= dist[nm] <= 4.0                  # (and no soft fringe of the covering part's outline)
    # a leg's top (hidden under the pelvis) keeps only the cloth INSIDE the pelvis outline: when the thigh swings,
    # no second outline appears beside the hip
    pcfg = cfg.get("pants")
    if pcfg and "pelvis" in flat:
        yy = np.mgrid[0:H, 0:W][0]
        inner = cv2.erode(flat["pelvis"].astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        top = yy < pcfg["pelvis_bottom"] - pcfg.get("pelvis_feather", 0) - 3
        for nm in pcfg["leg_seeds"]:
            if nm in layers:                             # (cloth only - its outline there is the pelvis's)
                layers[nm] &= ~top | (inner | (flat[nm] & ~inkpx))
    # big ink areas nobody has yet (hair): to the nearest part (head)
    taken = np.zeros((H, W), bool)
    for m in layers.values():
        taken |= m
    rest = inkpx & ~taken
    if rest.any():
        ids = {nm: i + 1 for i, nm in enumerate(layers)}
        lab2 = np.zeros((H, W), np.int32)
        for nm, m in layers.items():
            lab2[m & (lab2 == 0)] = ids[nm]
        dist, idx = cv2.distanceTransformWithLabels((lab2 == 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(lab2 > 0)
        lut = np.zeros(idx.max() + 1, np.int32)
        lut[idx[ys, xs]] = lab2[ys, xs]
        got = lut[idx[rest]]
        inv = {v: k for k, v in ids.items()}
        ry, rx = np.nonzero(rest)
        for g in np.unique(got):
            sel = got == g
            layers[inv[g]][ry[sel], rx[sel]] = True
    # a drawn pixel that no part took (on a split line, an anti-aliased edge): to every part within 3 px, so the
    # assembled layers show exactly the drawing
    taken = np.zeros((H, W), bool)
    for m in layers.values():
        taken |= m
    lost0 = al & ~shadow & ~taken
    for nm in list(layers):
        d = cv2.distanceTransform((~layers[nm]).astype(np.uint8), cv2.DIST_L2, 3)
        layers[nm] |= lost0 & (d <= 3.0)
    # hidden continuations (own colour, under the covering part)
    notes = []
    for e in cfg.get("extend", []):
        nm, under = e["part"], e["under"]
        if nm not in layers or under not in layers:
            continue
        m = flat[nm]
        col = np.median(ref_rgba[..., :3][m & ~ink], axis=0) if (m & ~ink).any() else np.array([128, 128, 128])
        dx, dy = e["dir"]
        nrm = max(1e-6, (dx * dx + dy * dy) ** 0.5)
        ext = np.zeros((H, W), bool)
        src = (flat[nm] & ~ink).astype(np.uint8)          # the part's colour area (its ink lines are not swept)
        for s in range(1, int(e["px"]) + 1):
            M = np.float32([[1, 0, dx / nrm * s], [0, 1, dy / nrm * s]])
            ext |= cv2.warpAffine(src, M, (W, H)) > 0
        if "y" in e:
            yy = np.mgrid[0:H, 0:W][0]
            ext &= (yy >= e["y"][0]) & (yy <= e["y"][1])
        ext &= (cv2.erode(layers[under].astype(np.uint8), np.ones((9, 9), np.uint8)) > 0) & ~layers[nm]   # only well INSIDE the covering part
        layers[nm] = layers[nm] | ext
        flat.setdefault("_ext_" + nm, ext)
        notes.append({"part": nm, "under": under, "pixels": int(ext.sum()), "colour": [int(c) for c in col], "why": e.get("why", "")})
        layers[nm + "__ext"] = ext
        layers[nm + "__col"] = col
    for nm in list(layers):                              # stray specks (a few pixels cut off by a line) are dropped
        if nm.endswith("__ext") or nm.endswith("__col") or nm not in cfg["order"]:
            continue
        n_, lab_, st_, _ = cv2.connectedComponentsWithStats(layers[nm].astype(np.uint8), connectivity=8)
        if n_ > 2:
            big_ = 1 + int(np.argmax(st_[1:, 4]))
            for k_ in range(1, n_):
                if k_ != big_ and st_[k_, 4] < 40:
                    layers[nm][lab_ == k_] = False
    out = {}
    for nm in cfg["order"]:
        if nm not in layers:
            continue
        m = layers[nm]
        img = np.zeros((H, W, 4), np.uint8)
        img[..., :3] = ref_rgba[..., :3]
        a = ref_rgba[..., 3].copy()
        img[..., 3] = np.where(m, a, 0)
        pf = (cfg.get("pants") or {}).get("pelvis_feather")
        if nm == "pelvis" and pf:                          # the pelvis fades into the thighs (no hard cut line)
            yy = np.arange(H)[:, None]
            b = cfg["pants"]["pelvis_bottom"]
            ramp = np.clip((b - yy) / float(pf), 0.0, 1.0)
            img[..., 3] = (img[..., 3] * ramp).astype(np.uint8)
        ext = layers.get(nm + "__ext")
        if ext is not None and ext.any():
            img[ext, :3] = layers[nm + "__col"]
            img[ext, 3] = 255
        # soft 1 px edge where a part was cut through a flat area (never a hard staircase)
        f = os.path.join(out_dir, "layers", f"{nm}.png")
        cv2.imwrite(f, img)
        ys, xs = np.nonzero(img[..., 3] > 0)
        out[nm] = {"file": f"layers/{nm}.png", "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
                   "pixels": int((img[..., 3] > 0).sum())}
    # coverage check: every visible pixel of the character is in at least one layer (no lost artwork)
    cover = np.zeros((H, W), bool)
    for nm in out:
        cover |= cv2.imread(os.path.join(out_dir, out[nm]["file"]), cv2.IMREAD_UNCHANGED)[..., 3] > 0
    lost = al & ~cover & ~shadow
    info = {"character": cfg.get("character"), "size": [W, H], "order": [n for n in cfg["order"] if n in out], "layers": out,
            "hidden_continuations": notes, "lost_pixels": int(lost.sum()), "shadow_removed_pixels": int((shadow & al).sum()),
            "joints": cfg.get("joints", {}), "weights": {k: v for k, v in cfg.get("weights", {}).items() if not k.startswith("_")}}
    with open(os.path.join(out_dir, "layers.json"), "w") as f:
        json.dump(info, f, indent=1)
    cv2.imwrite(os.path.join(out_dir, "lost_pixels.png"), (lost * 255).astype(np.uint8))
    return info


COLOURS = {"head": (255, 0, 255), "neck": (180, 0, 180), "torso": (0, 200, 255), "pelvis": (0, 140, 200), "arm_r": (0, 0, 255),
           "hand_r": (0, 128, 255), "arm_l": (255, 0, 0), "hand_l": (255, 128, 0), "leg_r": (0, 220, 0), "foot_r": (0, 120, 0),
           "leg_l": (220, 220, 0), "foot_l": (140, 140, 0)}


def diagnostic(out_dir, ref_rgba, scale=2):
    """part boundaries + joint markers on the reference, enlarged; and every layer alone on a checkerboard"""
    info = json.load(open(os.path.join(out_dir, "layers.json")))
    H, W = ref_rgba.shape[:2]
    a = ref_rgba[..., 3:] / 255.0
    base = (ref_rgba[..., :3] * a + 236 * (1 - a)).astype(np.uint8)
    big = cv2.resize(base, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    for nm in info["order"]:
        m = cv2.imread(os.path.join(out_dir, info["layers"][nm]["file"]), cv2.IMREAD_UNCHANGED)[..., 3] > 0
        m = cv2.resize(m.astype(np.uint8), None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(big, cs, -1, COLOURS.get(nm, (0, 0, 0)), 2)
    for jn, p in info.get("joints", {}).items():
        if jn.startswith("_"):
            continue
        q = (int(p[0] * scale), int(p[1] * scale))
        cv2.circle(big, q, 7, (0, 0, 0), 2)
        cv2.circle(big, q, 4, (0, 255, 255), -1)
        cv2.putText(big, jn, (q[0] + 8, q[1] - 6), 0, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(big, jn, (q[0] + 8, q[1] - 6), 0, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(out_dir, "diag_parts_joints.png"), big)
    tiles = []
    for nm in info["order"]:
        L = cv2.imread(os.path.join(out_dir, info["layers"][nm]["file"]), cv2.IMREAD_UNCHANGED)
        x0, y0, x1, y1 = info["layers"][nm]["bbox"]
        c = L[max(0, y0 - 6):y1 + 7, max(0, x0 - 6):x1 + 7]
        chk = np.indices(c.shape[:2]).sum(0) // 8 % 2
        bg = np.where(chk[..., None] == 0, 200, 255).astype(np.uint8).repeat(3, 2)
        al = c[..., 3:] / 255.0
        t = (c[..., :3] * al + bg * (1 - al)).astype(np.uint8)
        hh = 300
        t = cv2.resize(t, (max(1, int(t.shape[1] * hh / t.shape[0])), hh), interpolation=cv2.INTER_AREA)
        t = cv2.copyMakeBorder(t, 24, 4, 4, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(t, nm, (4, 17), 0, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
        tiles.append(t)
    rows, row, wsum = [], [], 0
    for t in tiles:
        if wsum + t.shape[1] > 1600 and row:
            rows.append(row)
            row, wsum = [], 0
        row.append(t)
        wsum += t.shape[1]
    if row:
        rows.append(row)
    Wm = max(sum(t.shape[1] for t in r) for r in rows)
    sheet = np.vstack([cv2.copyMakeBorder(np.hstack(r), 0, 0, 0, Wm - sum(t.shape[1] for t in r), cv2.BORDER_CONSTANT, value=(255, 255, 255)) for r in rows])
    cv2.imwrite(os.path.join(out_dir, "diag_layers.png"), sheet)
