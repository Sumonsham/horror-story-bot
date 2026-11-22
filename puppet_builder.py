"""PUPPET BUILDER - the whole 2.5D puppet is cut from ONE picture: the character's full-body A-pose reference.

Why (found in the real art_test of 21 Nov 2026): Cloudflare's image model, when it is given the reference picture,
very often draws the WHOLE character again instead of the one piece it was asked for - the "legs" of Taranath and
Kishori and the "skirt" of Saraswati were complete people, the "arms" of Kishori and Saraswati were short stubs.
Assembled, they gave second heads at the hips, giant arms and broken bodies. The full-body references themselves
were all clean: complete, in an A-pose, arms away from the body, margins all round.
So the puppet now comes from the reference alone - one picture = one identity, real proportions, every limb present:

  head        top -> neck (the body's own head; extra head drawings are only used when they match it)
  torso       neck -> pelvis, shoulders included (long hair / pallu / shawl move with it)
  arms        each arm is free of the body in an A-pose: upper arm (shoulder -> elbow), forearm + hand
  legs        split at the real gap between the legs (trousers, pyjama, dhoti); upper leg / lower leg + foot
  skirt       a saree / long dress / ghost's cloth: waist -> knee, knee -> hem (no legs; the cloth bends as one)
Every joint gets a ROUND overlap: both parts carry a full disc of their own pixels around the joint centre, so
when a limb turns, the disc turns into itself and no notch, gap or straight cut edge can show.
Measurements are checked against human proportions (child / adult); the assembled puppet is then validated in
seven poses by assembly_qa before it may be called ready.
"""
import cv2
import numpy as np

VERSION = 3
ARM_MIN = 0.24          # shoulder -> fingertips, of the height (the real references measure 0.31-0.37)


def _runs(row):
    d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0] - 1))


def _disc(shape, c, r):
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return (xx - c[0]) ** 2 + (yy - c[1]) ** 2 <= r * r


def separate(rgba):
    """the figure and the PROPS apart: (body mask, [prop masks], notes).
    A prop (a lantern on the floor, a bag, a stick lying by the feet) is never part of the body: in the real art test
    Taranath's lantern was joined to his foot only through the grey ground shadow and a few smoothed edge pixels.
    So: the ground shadow is taken away, thin bridges near the ground are broken, the body is the piece that holds
    the head; every other sizeable piece is a prop (kept as its own layer, at its own place)."""
    a = rgba[..., 3] > 127
    notes = []
    n, lab, st, _ = cv2.connectedComponentsWithStats(a.astype(np.uint8), 8)
    if n < 2:
        return a, [], notes
    big = 1 + int(np.argmax(st[1:, 4]))
    m_all = a
    ys = np.where((lab == big).any(axis=1))[0]
    top, bot = ys.min(), ys.max()
    H = bot - top + 1
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2HSV)
    yy = np.arange(a.shape[0])[:, None]
    shadow = m_all & (yy > bot - 0.07 * H) & (hsv[..., 1] < 28) & (hsv[..., 2] > 95) & (hsv[..., 2] < 215)
    m = m_all & ~shadow if shadow.sum() > 0.003 * (lab == big).sum() else m_all.copy()
    if shadow.sum() > 0.003 * (lab == big).sum():
        notes.append("the ground shadow under the feet was left out")
    low = yy > top + 0.70 * H                               # near the ground: break bridges a few pixels thin
    opened = cv2.morphologyEx((m & low).astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))).astype(bool)
    core = (m & ~low) | opened
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(core.astype(np.uint8), 8)
    if n2 < 2:
        return m, [], notes
    head_lab = None                                         # the body = the piece that holds the top of the figure
    for i in range(1, n2):
        if st2[i][1] <= top + 2:
            head_lab = i if head_lab is None or st2[i][4] > st2[head_lab][4] else head_lab
    if head_lab is None:
        head_lab = 1 + int(np.argmax(st2[1:, 4]))
    body_core = lab2 == head_lab
    props_core, rejoin = [], np.zeros(m.shape, bool)
    for i in range(1, n2):
        if i == head_lab:
            continue
        c_ = lab2 == i
        x_, y_, w_, h_, a_ = st2[i]
        # a body part cut off by the bridge-breaking (a leg under a kurta hem) has the BODY right above it; a prop
        # standing by the feet (the lantern) has empty space above it
        top_cols = c_[y_:y_ + max(2, int(0.2 * h_))].any(axis=0)
        band = body_core[max(0, y_ - int(0.035 * H)):y_]
        above = band.any(axis=0) if band.size else np.zeros(m.shape[1], bool)
        covered = (top_cols & above).sum() / max(1, top_cols.sum())
        if a_ > 0.004 * body_core.sum() and h_ > 0.035 * H and covered < 0.35:
            props_core.append(c_)
        else:
            rejoin |= c_
    body_core = body_core | rejoin
    k5 = np.ones((7, 7), np.uint8)
    any_prop = np.zeros(m.shape, bool)
    for pc in props_core:
        any_prop |= pc
    body = m & cv2.dilate(body_core.astype(np.uint8), k5).astype(bool) & ~any_prop
    n3, lab3, st3, _ = cv2.connectedComponentsWithStats(body.astype(np.uint8), 8)
    if n3 > 2:                                              # (keep the body in one piece)
        keep = 1 + int(np.argmax(st3[1:, 4]))
        body = lab3 == keep
    props = []
    for pc in props_core:
        pm = m & cv2.dilate(pc.astype(np.uint8), k5).astype(bool) & ~body
        props.append(pm)
        ys_, xs_ = np.where(pm)
        notes.append(f"a prop (an object, {int(np.ptp(ys_)) + 1}px high) was separated from the body - it is its own "
                     "layer, never part of the body")
    return body, props, notes


def clean_mask(rgba):
    """the figure only (no props, no ground shadow)"""
    body, _, notes = separate(rgba)
    return body, notes


def _central(runs, cx):
    if not runs:
        return None
    for r in runs:
        if r[0] - 2 <= cx <= r[1] + 2:
            return r
    return min(runs, key=lambda r: min(abs(r[0] - cx), abs(r[1] - cx)))


def _arm(m, gray, rows, side, cx, neck_y, top, bot, H, rgba=None):
    """one arm. Below the point where it leaves the body (a gap of background) it is its own shape; ABOVE it the upper
    arm lies against the body, so it is traced along the body's outer edge up to the shoulder, its inner edge
    following the drawn outline between arm and body. Returns the arm mask, the shoulder joint, the strip of the
    body that the upper arm covered (to be painted back on the torso) and the arm's width."""
    Hh, W = m.shape
    sgn = 1 if side == "far" else -1                        # far = the left of the picture: inwards is +x
    gap_y = None
    win = max(4, int(0.04 * H))
    for y in range(neck_y + int(0.03 * H), top + int(0.62 * H)):
        ok = 0
        for y2 in range(y, min(bot, y + win)):
            c2 = _central(rows[y2], cx)
            ok += bool(c2 and [r for r in rows[y2] if r != c2 and r[1] - r[0] >= 2 and (r[1] < c2[0] if side == "far" else r[0] > c2[1])])
        if ok >= 0.85 * win:
            gap_y = y
            break
    if gap_y is None:
        return None, f"{side} arm is not separate from the body anywhere (no A-pose in the reference)"
    lab_src = np.zeros(m.shape, np.uint8)
    for y in range(gap_y, bot + 1):
        c = _central(rows[y], cx)
        for r in rows[y]:
            if c is not None and r != c and (r[1] < c[0] if side == "far" else r[0] > c[1]):
                lab_src[y, r[0]:r[1] + 1] = 1
    n, lab, st, _ = cv2.connectedComponentsWithStats(lab_src, 8)
    cand = [i for i in range(1, n) if st[i][1] <= gap_y + win and st[i][4] > 150]
    if not cand:
        return None, f"{side} arm not found"
    low = lab == max(cand, key=lambda i: st[i][3] * 1000 + st[i][4])   # the longest piece hanging from that row
    ly = np.where(low.any(axis=1))[0]
    py_, px_ = np.where(low)                                  # the limb's true width: across its own axis (a slanting
    pts = np.stack([px_, py_], 1).astype(np.float32)        # arm is wider row by row than it really is)
    pts -= pts.mean(0)
    ev, evec = np.linalg.eigh(np.cov(pts.T)) if len(pts) > 10 else (np.array([1.0, 1.0]), np.eye(2))
    along = pts @ evec[:, 1]
    span = float(np.ptp(along)) if len(along) else 1.0
    upper = along <= along.min() + 0.45 * span if np.mean(py_[along <= along.min() + 0.1 * span]) < np.mean(py_) else \
        along >= along.max() - 0.45 * span                  # (the forearm, not the hand)
    aw = float(np.clip(upper.sum() / max(1.0, 0.45 * span) * 1.05, 0.03 * H, 0.075 * H))
    # the upper arm, row by row from the shoulder down to the gap
    sh_y = int(neck_y + 0.065 * H)                          # (below the collar: the shoulder line stays on the torso)
    am = low.copy()
    strip = np.zeros(m.shape, bool)
    inner_prev, outer_pts = None, []
    first_in = np.where(low[ly.min()])[0]
    gap_inner = float(first_in.max() if side == "far" else first_in.min())
    xs_inner = []
    for y in range(sh_y, gap_y):
        c = _central(rows[y], cx)
        if c is None:
            continue
        xo = c[0] if side == "far" else c[1]
        lo_, hi_ = xo + sgn * 0.6 * aw, xo + sgn * 1.3 * aw
        a_, b_ = int(min(lo_, hi_)), int(max(lo_, hi_))
        a_, b_ = max(0, a_), min(W - 1, b_)
        seg = gray[y, a_:b_ + 1].astype(np.float32) if b_ > a_ else None
        if seg is not None and len(seg) and seg.min() < 85:   # the drawn line between the arm and the body (the one
            want = xo + sgn * aw                              # nearest to where an arm of this width ends)
            score = seg + 1.2 * np.abs(np.arange(a_, b_ + 1) - want)
            xi = a_ + int(np.argmin(score))
        else:
            xi = int(xo + sgn * aw)
        xs_inner.append((y, xi, xo))
    if xs_inner:
        yv0 = np.array([t[0] for t in xs_inner])
        yv = np.arange(int(yv0.min()), int(yv0.max()) + 1)       # every row (a row the outline missed is filled in
        xi = np.interp(yv, yv0, [t[1] for t in xs_inner]).astype(np.float32)   # between its neighbours - no torn arm)
        xo = np.interp(yv, yv0, [t[2] for t in xs_inner]).astype(np.float32)
        k = max(3, (len(xi) // 6) * 2 + 1)
        xi = cv2.medianBlur(xi.reshape(-1, 1).astype(np.float32), 5).ravel() if len(xi) >= 5 else xi
        xi = np.convolve(np.pad(xi, k // 2, mode="edge"), np.ones(k) / k, mode="valid")[:len(yv)]
        # blend into the inner edge of the free part at the gap (no step)
        t = (yv - yv.min()) / max(1.0, float(yv.max() - yv.min()))
        xi = xi * (1 - t ** 3) + gap_inner * (t ** 3)
        for y, a_, o_ in zip(yv, xi, xo):
            x0, x1 = (int(o_), int(round(a_))) if side == "far" else (int(round(a_)), int(o_))
            if x1 > x0:
                am[y, x0:x1 + 1] |= m[y, x0:x1 + 1]
                s0, s1 = (int(round(a_)), int(round(a_ + 0.5 * aw))) if side == "far" else (int(round(a_ - 0.5 * aw)), int(round(a_)))
                strip[y, max(0, s0):min(W, s1 + 1)] = True
                strip[y, x0:x1 + 1] |= False
            outer_pts.append((o_, y))
    am = (cv2.morphologyEx(am.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 3), np.uint8)).astype(bool) & m) | am
    cover = np.zeros(m.shape, bool)
    skin = np.zeros(m.shape, bool)
    band = am & ~low
    if band.any() and rgba is not None:                      # is the upper arm COVERED in the drawing (a short sleeve,
        lab_img = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2LAB).astype(np.float32)   # a pallu, a shawl)? Its colours
        top_low = low & (np.arange(Hh)[:, None] <= ly.min() + 0.4 * (ly.max() - ly.min()))   # are then not those of
        ref_px = lab_img[top_low & (gray > 70)]                                           # the arm where it hangs free
        bmask = band & (gray > 70)
        if len(ref_px) > 30 and bmask.sum() > 50:
            ref_c = np.median(ref_px, axis=0)
            dist = np.linalg.norm(lab_img[bmask] - ref_c, axis=1)
            if (dist > 30).mean() > 0.35:
                cover = band                                 # the band is covered: its CLOTH stays on the torso ...
                own_ = np.zeros(m.shape, bool)               # ... but the arm's OWN skin / sleeve there goes with the arm
                own_[bmask] = dist <= 30
                skin = cv2.morphologyEx(own_.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    # the shoulder joint: inside the top of the arm    # the shoulder joint: inside the top of the arm
    # the shoulder joint: inside the top of the arm, about half an arm's width in from the outside
    if outer_pts:
        top_o = np.mean([p[0] for p in outer_pts[:max(1, len(outer_pts) // 6)]])
    else:
        top_o = float(np.where(low[ly.min()])[0].mean())
    J = (float(top_o + sgn * 0.5 * aw), float(sh_y + 0.45 * aw))
    if xs_inner:                                            # better: the MIDDLE of the upper arm at that height (half way
        jy = int(round(J[1]))                               # between its outside and the line against the body)
        if yv[0] <= jy <= yv[-1]:
            i_ = jy - int(yv[0])
            J = (float((xi[i_] + xo[i_]) / 2.0), float(jy))
    # the arm's axis: from the shoulder to the far end of the hand
    ay, ax = np.where(am)
    d = np.stack([ax, ay], 1).astype(np.float32) - np.array(J, np.float32)
    far = d[np.argmax((d ** 2).sum(1))]
    u = far / (np.linalg.norm(far) + 1e-6)
    if cover.any():                                         # (a covered arm: the torso keeps the cloth as drawn -
        strip[:] = False                                    # nothing has to be painted back behind it)
    return {"mask": am, "J": J, "u": u, "width": aw, "armpit": gap_y, "strip": strip & m, "cover": cover & ~skin,
            "skin": skin}, None


def build(rgba, plan=None):
    """-> (rig dict for cutout_rig, problems list, notes list). Problems mean the reference cannot make a puppet."""
    plan = plan or {}
    probs = []
    m, prop_masks, notes = separate(rgba)
    ys, xs = np.where(m)
    if len(ys) < 3000:
        return None, ["the figure is missing or too small"], notes
    top, bot, left, right = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    H = bot - top + 1
    Hh, Ww = m.shape
    if top < 0.015 * Hh or bot > Hh - 1 - 0.01 * Hh or left < 2 or right > Ww - 3:
        probs.append("the reference is cut by the picture edge (head, hands or feet missing)")
    rows = [(_runs(m[y]) if top <= y <= bot else []) for y in range(Hh)]
    gray = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2GRAY)
    widths = np.array([sum(b - a + 1 for a, b in r) for r in rows], np.float32)
    # ---- neck: the narrowest row below the face (8-30 % of the height)
    lo, hi = top + int(0.09 * H), top + int(0.30 * H)
    seg = widths[lo:hi].copy()
    seg[seg == 0] = 1e9
    neck_y = lo + int(np.argmin(cv2.GaussianBlur(seg.reshape(-1, 1), (1, 9), 0).ravel()))
    nr = _central(rows[neck_y], (left + right) / 2.0) or (left, right)
    cx = (nr[0] + nr[1]) / 2.0
    head_h = neck_y - top
    hf = plan.get("head_fraction", (0.10, 0.33))
    if not hf[0] <= head_h / H <= hf[1] + 0.02:
        probs.append(f"head is {head_h / H:.2f} of the height - not natural for this character")
    # ---- arms
    arms = {}
    for side in ("far", "near"):
        a, err = _arm(m, gray, rows, side, cx, neck_y, top, bot, H, rgba)
        if err:
            probs.append(err)
        else:
            arms[side] = a
    body = m.copy()
    arm_src = rgba
    skin_holes = np.zeros(m.shape, bool)
    for side_, a in arms.items():
        body &= ~(a["mask"] & ~a["cover"])                  # (a covered upper arm's CLOTH stays drawn on the torso ...)
        skin_holes |= a.get("skin", np.zeros(m.shape, bool))
        if a["cover"].any():                                 # ... and the arm itself, under it, gets its own colour
            if arm_src is rgba:                              # (skin or sleeve as where it hangs free), outlines kept
                arm_src = rgba.copy()
            low_px = rgba[..., :3][a["mask"] & ~a["cover"] & (gray > 70)]
            col = np.median(low_px, axis=0) if len(low_px) else np.array([150, 170, 200])
            fill = a["cover"] & (gray > 70)
            arm_src[..., :3][fill] = col.astype(np.uint8)
            edge = a["mask"] & ~cv2.erode(a["mask"].astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & a["cover"]
            arm_src[..., :3][edge] = (34, 30, 30)
            notes.append(f"the {side_} upper arm is covered by cloth in the drawing: the cloth stays with the body, "
                         "the arm under it is drawn in its own colour")
    # ---- pelvis / legs
    no_legs = bool(plan.get("no_legs", plan.get("archetype") in ("saree_woman", "long_dress", "ghost_flowing")))
    child = bool(plan.get("child"))
    nat_hip = top + int((0.56 if child else 0.52) * H)
    brows = [(_runs(body[y]) if top <= y <= bot else []) for y in range(Hh)]
    gap_top, gaps = None, []
    for y in range(bot - int(0.06 * H), top + int(0.40 * H), -1):  # up from the ankles: rows with two legs
        rr = [r for r in brows[y] if r[1] - r[0] >= 3]
        if len(rr) >= 2:
            rr = sorted(rr, key=lambda r: abs((r[0] + r[1]) / 2 - cx))[:2]
            rr.sort()
            g0, g1 = rr[0][1], rr[1][0]
            if g1 - g0 >= 2 and abs((g0 + g1) / 2 - cx) < 0.12 * H:
                gap_top = y
                gaps.append((g0 + g1) / 2.0)
                continue
        if gap_top is not None and y < gap_top - 3:
            break
    if no_legs:
        crotch = None
        hip_y = nat_hip
    elif gap_top is not None and top + 0.44 * H <= gap_top <= top + 0.62 * H:
        crotch = gap_top                                     # trousers: the legs part at the crotch
        hip_y = int(crotch - 0.035 * H)
    else:
        crotch = None                                        # a kurta / dhoti / lungi: the hip at its natural height
        hip_y = nat_hip
        if gap_top is None:
            notes.append("no gap between the legs - the cloth is split at the middle")
    sep = float(np.median(gaps[-12:])) if gaps else cx
    yy = np.arange(Hh)[:, None]
    XX = np.arange(Ww)[None, :]
    parts = {}

    def put(name, mask, pivot, end, src=None):
        ys_, xs_ = np.where(mask)
        if len(ys_) < 50:
            probs.append(f"part '{name}' is empty")
            return
        y0, y1, x0, x1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
        n_, lab_, st_, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        if n_ > 2:                                           # the part is ONE shape: loose fragments are dropped
            big_ = st_[1:, 4].max()
            mask = np.isin(lab_, [i for i in range(1, n_) if st_[i][4] >= 0.08 * big_])
            ys_, xs_ = np.where(mask)
            y0, y1, x0, x1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
        spr = (rgba if src is None else src)[y0:y1, x0:x1].copy()
        spr[..., 3] = np.where(mask[y0:y1, x0:x1], spr[..., 3], 0).astype(np.uint8)
        dx, dy = end[0] - pivot[0], end[1] - pivot[1]
        parts[name] = {"sprite": spr, "origin": (int(x0), int(y0)), "pivot": (float(pivot[0] - x0), float(pivot[1] - y0)),
                       "length": float(np.hypot(dx, dy)), "rest": float(np.degrees(np.arctan2(dx, dy)))}

    ov = max(3, int(0.02 * H))
    # head (above the neck, with a small overlap under the chin)
    put("head", m & (yy <= neck_y + ov), (cx, float(neck_y)), (cx, float(top)))
    # arms: upper arm and forearm(+hand), split at the elbow with round overlaps
    shoulders, arm_len = {}, {}
    for side, a in arms.items():
        am = a["mask"]
        J, u, aw = np.array(a["J"]), a["u"], a["width"]
        ay, ax = np.where(am)
        proj = (ax - J[0]) * u[0] + (ay - J[1]) * u[1]
        Lt = float(proj.max())
        te = 0.44 * Lt                                       # elbow (upper arm ~ forearm; the hand ~ 1/5 of the arm)
        tw = 0.80 * Lt                                       # wrist
        near_e = np.abs(proj - te) < 2.5
        E = (float(ax[near_e].mean()), float(ay[near_e].mean())) if near_e.any() else tuple(J + u * te)
        near_w = np.abs(proj - tw) < 2.5
        Wr = (float(ax[near_w].mean()), float(ay[near_w].mean())) if near_w.any() else tuple(J + u * tw)
        P = np.zeros(m.shape, np.float32)
        P[ay, ax] = proj
        re_ = 0.55 * aw
        rj = 0.62 * aw
        dE = _disc(m.shape, E, re_) & am
        # the shoulder end is rounded with the ARM's own pixels only (torso cloth - a pallu, a shawl - must never
        # travel with a raised arm)
        own = cv2.dilate(am.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & m
        ua = (am & (P <= te)) | dE | (_disc(m.shape, J, rj) & own)
        above = (np.arange(Hh)[:, None] < J[1])             # the top of the upper arm is ROUND about the shoulder joint:
        ua &= ~(above & ~_disc(m.shape, J, rj * 1.08))       # no square corner of outline that sticks out when it turns
        fa = (am & (P >= te)) | dE
        put(f"uarm_{side}", ua, J, E, src=arm_src)
        put(f"farm_{side}", fa, E, Wr, src=arm_src)
        shoulders[side] = (float(J[0]), float(J[1]))
        arm_len[side] = Lt / H
    # torso: neck -> pelvis (to the crotch for trousers; a little below the hip for a cloth)
    t_bot = (crotch + ov) if crotch is not None else (hip_y + 2 * ov)
    if no_legs:
        t_bot = hip_y + ov
    torso_mask = body & (yy >= neck_y - ov) & (yy <= t_bot)
    # (the shoulder discs of the arms are drawn over / under it - the torso keeps its own shoulders)
    hip_c = (float(sep if not no_legs else cx), float(hip_y))
    # where the upper arms lay against the body, the body's side is painted back (its own cloth colour, its own
    # outline), so a raised arm never leaves a hole or a straight cut in the torso
    strip = np.zeros(m.shape, bool)
    for a in arms.values():
        strip |= a["strip"]
    strip |= skin_holes                                     # (where the arm's own skin was under the cloth)
    strip &= (yy >= neck_y) & (yy <= t_bot)
    torso_src = rgba
    if strip.any():
        torso_src = rgba.copy()
        arm_all = np.zeros(m.shape, bool)
        for a in arms.values():
            arm_all |= a["mask"] & ~a["cover"]
        hole = cv2.dilate((strip | arm_all).astype(np.uint8), np.ones((3, 3), np.uint8))   # (painted from the CLOTH
        base_img = rgba[..., :3].copy()                                                      #  around, never the arm
        near_cloth = body & ~hole.astype(bool) & cv2.dilate(hole, np.ones((25, 25), np.uint8)).astype(bool) & (gray > 70)
        if near_cloth.any():                                                                 #  and never the empty
            base_img[~m] = np.median(rgba[..., :3][near_cloth], axis=0).astype(np.uint8)     #  background / outlines)
        lines_ = (gray < 70) & ~hole.astype(bool)
        if near_cloth.any():
            base_img[lines_ & cv2.dilate(hole, np.ones((9, 9), np.uint8)).astype(bool)] = np.median(rgba[..., :3][near_cloth], axis=0).astype(np.uint8)
        torso_src[..., :3] = cv2.inpaint(base_img, hole, 7, cv2.INPAINT_TELEA)
        torso_src[..., :3] = np.where(hole[..., None].astype(bool), torso_src[..., :3], rgba[..., :3])
        torso_mask = torso_mask | strip
        edge = torso_mask & ~cv2.erode(torso_mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        torso_src[edge & cv2.dilate(strip.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool), :3] = (34, 30, 30)
        torso_src[..., 3] = np.where(torso_mask, 255, torso_src[..., 3])
    put("torso", torso_mask, hip_c, (cx, float(neck_y)), src=torso_src)
    leg_hips, leg_len = {}, {}
    skirt_len = None
    meta_extra = {}
    if no_legs:
        # the saree / dress / ghost cloth: waist -> knee, knee -> hem, bending as one piece
        lower = body & (yy >= hip_y - ov)
        ly = np.where(lower.any(axis=1))[0]
        if len(ly) < 10:
            probs.append("the cloth below the waist is missing")
        else:
            hem = int(ly.max())
            knee = int(hip_y + 0.5 * (hem - hip_y))
            run_k = _central(_runs(lower[knee]), cx) or (cx - 10, cx + 10)
            kx = (run_k[0] + run_k[1]) / 2.0
            rk = 0.5 * (run_k[1] - run_k[0] + 1)
            dK = _disc(m.shape, (kx, knee), rk) & lower
            put("skirt_up", (lower & (yy <= knee)) | dK, (cx, float(hip_y)), (kx, float(knee)))
            put("skirt_lo", (lower & (yy >= knee)) | dK, (kx, float(knee)), (kx, float(hem)))
            skirt_len = float(hem - hip_y)
            meta_extra["waist"] = (cx, float(hip_y))
    else:
        lower = body & (yy >= hip_y)
        # below the point where the legs part, each leg is its own shape (a foot crossing the middle line stays with
        # its own leg); above it the cloth is split at the middle with an overlap
        split_y = gap_top if gap_top is not None else bot + 1
        sep_rows = np.full(Hh, np.nan, np.float32)           # the gap between the legs, row by row
        for y in range(split_y, bot + 1):
            rr = [r for r in _runs(lower[y]) if r[1] - r[0] >= 2]
            if len(rr) >= 2:
                rr = sorted(rr, key=lambda r: abs((r[0] + r[1]) / 2 - sep))[:2]
                rr.sort()
                if rr[1][0] - rr[0][1] >= 2:
                    sep_rows[y] = (rr[0][1] + rr[1][0]) / 2.0
        known = np.where(~np.isnan(sep_rows))[0]
        if len(known):
            sep_rows = np.interp(np.arange(Hh), known, sep_rows[known]).astype(np.float32)
        else:
            sep_rows[:] = sep
        sep_rows[:split_y] = sep
        SEP = sep_rows[:, None]
        for side, sel in (("far", XX < SEP + np.where(yy < split_y, ov if crotch is None else 0, 0)),
                          ("near", XX >= SEP - np.where(yy < split_y, ov if crotch is None else 0, 0))):
            gm = lower & sel
            if crotch is not None:                           # above the crotch the trousers are one: both halves overlap
                gm |= lower & (yy <= crotch + 1) & (np.abs(XX - sep) <= ov)
            gy, gx = np.where(gm)
            if len(gy) < 300:
                probs.append(f"{side} leg not found")
                continue
            g_bot = int(gy.max())
            ref_y = min(g_bot, (crotch if crotch is not None else hip_y) + int(0.06 * H))
            rr = _runs(gm[ref_y])
            hx = float(np.mean([(r[0] + r[1]) / 2.0 for r in rr])) if rr else float(gx.mean())
            ankle = int(g_bot - 0.045 * H)
            knee = int(hip_y + 0.5 * (ankle - hip_y))

            def colx(y, gm=gm, gx=gx):
                r = np.where(gm[min(max(y, 0), Hh - 1)])[0]
                return float(r.mean()) if len(r) else float(gx.mean())
            Hj = (hx, float(hip_y))
            K = (colx(knee), float(knee))
            A = (colx(ankle), float(ankle))
            kr = np.where(gm[knee])[0]
            rk = 0.5 * (np.ptp(kr) + 1) if len(kr) else 0.03 * H
            hr = np.where(gm[min(Hh - 1, hip_y + int(0.03 * H))])[0]
            rh = min(0.5 * (np.ptp(hr) + 1) if len(hr) else 0.04 * H, 0.07 * H)
            dK = _disc(m.shape, K, rk) & gm
            # the top of the thigh: a FULL round end as wide as the leg, in the leg's own cloth colour (it lies under
            # the torso - turning, a circle stays a circle: no corner swings out, no gap opens at the hip)
            top_rows = gm & (yy >= hip_y) & (yy <= hip_y + int(0.05 * H))
            wtop = top_rows.any(axis=0)
            rfull = float(min(0.5 * (wtop.sum() + 1), 0.10 * H)) if wtop.any() else rh
            hip_disc = _disc(m.shape, Hj, rfull)
            leg_src = rgba.copy()
            cpx = rgba[..., :3][top_rows & (gray > 70)]
            if len(cpx):
                fill_ = hip_disc & ~gm
                leg_src[..., :3][fill_] = np.median(cpx, axis=0).astype(np.uint8)
                leg_src[..., 3][fill_] = 255
            put(f"thigh_{side}", (gm & (yy <= knee)) | dK | hip_disc, Hj, K, src=leg_src)
            put(f"shin_{side}", (gm & (yy >= knee)) | dK, K, A)
            leg_hips[side] = Hj
            leg_len[side] = (A[1] - hip_y + 0.045 * H) / H
    # ---- something that is not the body (a lantern on the floor, a bag, a stick) touching a leg or an arm
    def _med_w(name):
        sp = parts.get(name)
        if not sp:
            return None
        a_ = sp["sprite"][..., 3] > 127
        w_ = [int(a_[y].sum()) for y in range(a_.shape[0]) if a_[y].any()]
        return float(np.median(w_)) if w_ else None
    for a_, b_, what in (("shin_near", "shin_far", "lower leg (something standing on the floor)"),
                         ("farm_near", "farm_far", "hand / forearm (something held)")):
        wa, wb = _med_w(a_), _med_w(b_)
        if wa and wb and max(wa, wb) > 1.6 * min(wa, wb):
            side = "near" if wa > wb else "far"
            probs.append(f"an object touches the {side} {what} - the reference must show the body alone")
    # ---- proportions (measured, never assumed)
    for side, L in arm_len.items():
        if not ARM_MIN <= L <= (0.50 if not child else 0.48):
            probs.append(f"{side} arm is {L:.2f} of the height - not a natural arm")
    for side, L in leg_len.items():
        if not (0.34 if not child else 0.30) <= L <= 0.58:
            probs.append(f"{side} leg is {L:.2f} of the height - not a natural leg")
    if skirt_len is not None and not 0.30 <= skirt_len / H <= 0.62:
        probs.append(f"the cloth below the waist is {skirt_len / H:.2f} of the height - unusual")
    if len(arms) == 2:
        sw = abs(arms["near"]["J"][0] - arms["far"]["J"][0]) / H
        if not 0.12 <= sw <= 0.40:
            probs.append(f"the shoulders are {sw:.2f} of the height apart - not natural")
    floats = bool(plan.get("floats"))
    under = [sd for sd, a in arms.items() if a["cover"].any()]     # an arm under a sleeve / pallu: behind the torso
    layers = ["hair_back"] + [f"uarm_{sd}" for sd in under] + \
        ["shin_far", "thigh_far", "shin_near", "thigh_near", "skirt_lo", "skirt_up", "torso"] + \
        [f"uarm_far" for _ in [0] if "far" not in under] + ["farm_far", "head"] + \
        [f"uarm_near" for _ in [0] if "near" not in under] + ["farm_near"]   # (an A-pose drawing: free arms are beside the body)
    rig = {"height_px": float(H), "top": float(top), "bottom": float(bot), "neck": (cx, float(neck_y)), "hip": hip_c,
           "shoulder_y": float(min([j[1] for j in shoulders.values()] or [neck_y + 0.07 * H])),
           "torso_len": float(np.hypot(cx - hip_c[0], neck_y - hip_c[1])), "head_h": float(head_h), "parts": parts,
           "shoulders": shoulders, "leg_hips": leg_hips, "arm_free": {s: s in arms for s in ("near", "far")},
           "no_legs": no_legs, "floats": floats, "layers": layers, "legs_under_torso": True, "method": "reference",
           "builder": VERSION, "head_fraction": round(head_h / H, 3), "crotch": crotch,
           "measures": {"arm": arm_len, "leg": leg_len, "skirt": (skirt_len / H) if skirt_len else None}}
    props = []                                              # every prop: its own layer, at its own place
    for i, pm in enumerate(prop_masks):
        ys_, xs_ = np.where(pm)
        y0, y1, x0, x1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
        spr = rgba[y0:y1, x0:x1].copy()
        spr[..., 3] = np.where(pm[y0:y1, x0:x1], spr[..., 3], 0).astype(np.uint8)
        on_ground = y1 >= bot - 0.04 * H
        props.append({"sprite": spr, "origin": (int(x0), int(y0)), "anchor": "ground" if on_ground else "free",
                      "offset_from_hip": (float(x0 - hip_c[0]), float(y0 - hip_c[1])), "size": (int(x1 - x0), int(y1 - y0))})
    rig["props"] = props
    if skirt_len is not None:
        rig["skirt_len"] = skirt_len
    rig.update(meta_extra)
    need = ["head", "torso", "uarm_near", "farm_near", "uarm_far", "farm_far"]
    need += ["skirt_up", "skirt_lo"] if no_legs else ["thigh_near", "shin_near", "thigh_far", "shin_far"]
    missing = [n for n in need if n not in parts]
    if missing:
        probs.append("missing body parts: " + ", ".join(missing))
    return rig, probs, notes
