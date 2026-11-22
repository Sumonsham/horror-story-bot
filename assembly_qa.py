"""ASSEMBLY QA - the mandatory gate: a character is READY only when the ASSEMBLED puppet passes in every pose.

Checking the separate pictures is not enough (the real test of 21 Nov 2026: every piece "passed", the assembled
characters had second heads at the hips and giant arms). So the puppet itself is drawn, exactly as the video draws
it, in seven poses - standing front, three-quarter, side, seated (both legs), talking, pointing, walking - and each
drawing is measured:
  rebuild     drawn in the reference's own pose it must cover the reference (no part missing, none duplicated)
  one body    every pose is ONE connected figure (no floating hand, no detached leg, no torn cloth)
  joints      shoulders, elbows, hips and knees are solid in every pose (no gap or notch at a joint)
  framing     nothing is cut by the edge (head, hands, feet)
  anatomy     arm / leg / head proportions are human; no face inside a limb or the torso (a duplicated person)
  seated      hips above the knees, knees above the feet, both feet on the floor, seated height natural
  pointing    the pointing hand is at the end of a straight arm, attached
  walking     the feet are apart, both legs complete
A failure gives: status not ready, the exact problem per pose, and a picture with the failing poses marked.
"""
import json
import math
import os

import cv2
import numpy as np

import cartoon_rig as R
import cinematic_camera as cc

# (label, pose, facing, head yaw). A puppet cut from ONE three-quarter drawing has exactly two genuine views: the
# drawing itself (facing right) and its mirror (facing left). True FRONT and SIDE views are NOT drawn - they would
# need their own drawings of the same person - so they are not shown and are reported as NOT AVAILABLE.
POSES = [("three_q_right", "stand", 1.0, 1.0), ("three_q_left", "stand", -1.0, -1.0), ("seated", "sit_talk", 1.0, 1.0),
         ("talking", "stand", 1.0, 1.0), ("pointing", "stand_point", 1.0, 1.0), ("walking", "walk", 1.0, 1.0)]
GENUINE_VIEWS = {"three_quarter": True, "three_quarter_mirrored": True, "front": False, "side_profile": False, "back": False}
TW, TH = 360, 560
LIMITATIONS = [
    "ONLY two genuine views exist: the three-quarter drawing (facing right) and its mirror (facing left). There is NO "
    "true front view and NO true side (profile) view - a single three-quarter picture cannot make them; narrowing it "
    "is not a view and is no longer done. Genuine front / side views need their own drawings of the SAME person "
    "(the separate AI head drawings of the first version changed the face - beards that the character does not have).",
    "the face is the reference's own face in every direction; blinking and the mouth are drawn on it",
    "a seated pose needs a seat in the scene (bench, stool, log, chowki); without one a 2.5D character stays standing",
    "props are separate layers at their own place; the scene engine does not yet hand a prop to a character",
    "a saree / long dress / ghost cloth has no separate legs: walking, the cloth sways and the feet under its hem glide "
    "with it - there are no visible separate steps",
]


def _render(ch, pose, facing, yaw, mouth=(0.0, "rest"), t=1.0, bg=(0, 0, 0), zoom=1.55, floatpx=0.0, walk_phase=None):
    img = np.full((TH, TW, 3), bg, np.uint8)
    cam = cc.Camera(TW, TH)
    cam.set(960, 745, zoom)
    st = {"x": 960, "ground_y": 935, "facing": facing, "head_yaw": yaw, "pose": pose, "t": t, "mouth": mouth,
          "blink": 0.0, "float": floatpx}
    if walk_phase is not None:
        st["walk_phase"] = walk_phase
    j = ch.draw(R.Painter(img, cam), st)
    return img, j, cam


def _alpha(ch, pose, facing, yaw, **kw):
    """the drawn figure's coverage: drawn twice (on black and on white) - where they differ is background"""
    a_img, j, cam = _render(ch, pose, facing, yaw, bg=(0, 0, 0), **kw)
    b_img, _, _ = _render(ch, pose, facing, yaw, bg=(255, 255, 255), **kw)
    alpha = 1.0 - (b_img.astype(np.float32) - a_img.astype(np.float32)).mean(axis=2) / 255.0
    return np.clip(alpha, 0, 1), a_img, b_img, j, cam


def _pose(name):
    return R.walk_pose(1.1) if name == "walk" else dict(R.POSES[name])


WALK_PHASE = 1.1


def _components(mask, min_frac=0.0004):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    tot = max(1, int(mask.sum()))
    return [i for i in range(1, n) if st[i][4] >= min_frac * tot], st


def _rest_pose(ch):
    """every part at the angle it has in the reference drawing"""
    p = dict(R.POSES["stand"])
    import cutout_rig as CR_
    arms_ = () if CR_.meta_ref(ch.meta) else (("uarm_n", "uarm_near"), ("farm_n", "farm_near"), ("uarm_f", "uarm_far"),
                                              ("farm_f", "farm_far"))   # (a reference puppet: 'stand' = arms as drawn)
    for k, part in arms_ + (("thigh_n", "thigh_near"), ("shin_n", "shin_near"), ("thigh_f", "thigh_far"), ("shin_f", "shin_far")):
        if part in ch.parts:
            p[k] = ch.parts[part][0].base[2]
    p["torso"] = 0.0
    p["chest"] = 0.0
    return p


def _crop(mask):
    ys, xs = np.where(mask)
    if not len(ys):
        return None
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def rebuild_iou(ch, ref_mask):
    """the puppet drawn in the reference's own pose vs the reference's outline (both cropped, same size)"""
    al, _, _, _, _ = _alpha(ch, _rest_pose(ch), 1.0, 1.0)
    a = _crop(al > 0.5)
    b = _crop(ref_mask)
    if a is None or b is None:
        return 0.0
    b = cv2.resize(b.astype(np.uint8), (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
    return float((a & b).sum() / max(1, (a | b).sum()))


def _faces_in_parts(ch):
    """a face (two eyes) inside an arm, a leg or the torso = another person drawn into the piece"""
    from cutout_assets import cartoon_eyes
    bad = []
    skin = np.array(ch.heads["ref"][1]["skin"], np.float32) if "ref" in ch.heads else None
    for name, (spr, _) in ch.parts.items():
        if name == "head":
            continue
        rgba = spr.base[0]
        if rgba.shape[0] < 30 or rgba.shape[1] < 30:
            continue
        eyes = cartoon_eyes(rgba)
        if len(eyes) >= 2 and skin is not None:            # two eyes WITH face skin around them (white cloth and a
            (x0, y0), (x1, y1) = eyes                      # lantern's glass also have white blobs with dark edges)
            span = max(6.0, abs(x1 - x0))
            box = rgba[int(max(0, min(y0, y1) - 0.2 * span)):int(max(y0, y1) + 0.9 * span),
                       int(max(0, min(x0, x1) - 0.3 * span)):int(max(x0, x1) + 0.3 * span)]
            px = box[box[..., 3] > 200][:, :3].astype(np.float32) if box.size else np.zeros((0, 3), np.float32)
            if len(px) and (np.linalg.norm(px - skin, axis=1) < 40).mean() > 0.30:
                bad.append(name)
    return bad


def _gray_on_grey(rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    g = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32)[..., None]
    return (g * a + 128.0 * (1 - a))[..., 0].astype(np.uint8)


def _heads_in_parts(ch):
    """the character's OWN head found again inside a limb / the torso (at any size) = a duplicated person"""
    if "head" not in ch.parts:
        return []
    head = ch.parts["head"][0].base[0]
    hg = _gray_on_grey(head)
    out = []
    for name, (spr, _) in ch.parts.items():
        if name == "head":
            continue
        pg = _gray_on_grey(spr.base[0])
        best = 0.0
        for sc in (1.0, 0.75, 0.55, 0.4, 0.3, 0.22):
            t = cv2.resize(hg, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
            if t.shape[0] < 14 or t.shape[1] < 14 or t.shape[0] > pg.shape[0] or t.shape[1] > pg.shape[1]:
                continue
            if t.std() < 8:
                continue
            r = cv2.matchTemplate(pg, t, cv2.TM_CCOEFF_NORMED)
            best = max(best, float(r.max()))
        if best > 0.67:                                      # (clean real characters: <= 0.63; a glued-on copy: 0.71+)
            out.append((name, round(best, 2)))
    return out


class _FixedCam:
    """a camera whose screen = the REFERENCE picture's own pixel grid (for the part-by-part fidelity check)"""

    def __init__(self, ox, oy, k):
        self.ox, self.oy, self.s, self.rot = ox, oy, k, 0.0

    def to_screen(self, x, y):
        return ((x - self.ox) * self.s, (y - self.oy) * self.s)


def _alpha_cam(ch, st, cam, shape):
    a_img = np.zeros(shape + (3,), np.uint8)
    b_img = np.full(shape + (3,), 255, np.uint8)
    ch.draw(R.Painter(a_img, cam), dict(st))
    ch.draw(R.Painter(b_img, cam), dict(st))
    return np.clip(1.0 - (b_img.astype(np.float32) - a_img.astype(np.float32)).mean(axis=2) / 255.0, 0, 1), b_img


def fidelity(ch, ref_rgba, out_dir=None):
    """EVERY part, drawn alone by the renderer in the reference's own pose, must lie exactly where - and be exactly
    as big as - the piece it was cut from: overlap, position (centre) and size per part, and the joints' positions.
    (Proportions are therefore the reference's own, not just 'seven pictures were drawn'.)"""
    Hh, Ww = ref_rgba.shape[:2]
    meta = ch.meta
    st = {"x": 960, "ground_y": 935, "facing": 1.0, "head_yaw": 1.0, "pose": _rest_pose(ch), "t": 0.0,
          "mouth": (0.0, "rest"), "blink": 0.0}
    gy = st["ground_y"] + ch.foot_floor(st)
    st = dict(st, ground_y=gy, planted=False)
    j = ch.joints(st)
    s = j["s"]
    hx, hy = meta["hip"]
    cam = _FixedCam(j["hip"][0] - hx * s, j["hip"][1] - hy * s, 1.0 / s)   # screen pixel = reference pixel
    H = meta["height_px"]
    out, probs = {}, []
    over = np.zeros((Hh, Ww, 3), np.uint8)
    for name, p in meta["parts"].items():
        if name not in ch.parts:
            continue
        spr = ch.parts[name][0].base[0]
        ox, oy = p.get("origin", (0, 0))
        exp = np.zeros((Hh, Ww), bool)
        hh_, ww_ = spr.shape[:2]
        y1, x1 = min(Hh, oy + hh_), min(Ww, ox + ww_)
        exp[oy:y1, ox:x1] = spr[:y1 - oy, :x1 - ox, 3] > 127
        al, _ = _alpha_cam(ch, dict(st, only={name}), cam, (Hh, Ww))
        got = al > 0.5
        inter, uni = (exp & got).sum(), (exp | got).sum()
        iou = float(inter / max(1, uni))
        ey, ex = np.where(exp)
        gy_, gx_ = np.where(got)
        if len(gy_) and len(ey):
            dc = math.hypot(gx_.mean() - ex.mean(), gy_.mean() - ey.mean()) / H
            ar = got.sum() / max(1, exp.sum())
        else:
            dc, ar = 1.0, 0.0
        out[name] = {"overlap": round(iou, 3), "centre_shift": round(dc, 4), "size_ratio": round(float(ar), 3)}
        if iou < 0.90 or dc > 0.01 or not 0.93 <= ar <= 1.07:
            probs.append(f"part '{name}' is not where / as big as in the reference (overlap {iou:.2f}, moved "
                         f"{dc * 100:.1f} % of the height, size x{ar:.2f})")
        over[exp & ~got] = (0, 0, 255)                     # red: in the reference, not drawn
        over[got & ~exp] = (255, 0, 0)                     # blue: drawn, not in the reference
        over[got & exp] = np.maximum(over[got & exp], (70, 160, 70))
    # the joints, where the drawing has them
    want = {"neck": meta["neck"]}
    for sd, sfx in (("near", "n"), ("far", "f")):
        if sd in meta.get("shoulders", {}):
            want["sh_" + sfx] = meta["shoulders"][sd]
        if sd in meta.get("leg_hips", {}):
            want["hip_" + sfx] = meta["leg_hips"][sd]
        for part_, key in ((f"farm_{sd}", "el_" + sfx), (f"shin_{sd}", "kn_" + sfx)):
            if part_ in meta["parts"]:
                pp = meta["parts"][part_]
                want[key] = (pp["origin"][0] + pp["pivot"][0], pp["origin"][1] + pp["pivot"][1])
    jerr = {}
    for k, ref_pt in want.items():
        if k in j:
            x, y = cam.to_screen(*j[k])
            jerr[k] = round(math.hypot(x - ref_pt[0], y - ref_pt[1]) / H, 4)
            if jerr[k] > 0.01:
                probs.append(f"joint '{k}' is {jerr[k] * 100:.1f} % of the height away from where the drawing has it")
    res = {"pass": not probs, "problems": probs, "parts": out, "joint_error": jerr,
           "proportions": {k: v for k, v in (meta.get("measures") or {}).items()},
           "head_fraction": meta.get("head_fraction")}
    if out_dir:
        cv2.putText(over, "green = part exactly where the reference has it, red = missing, blue = extra", (8, 24), 0, 0.5,
                    (255, 255, 255), 1)
        cv2.imwrite(os.path.join(out_dir, "assembly_fidelity.png"), over)
    return res


def walk_cycle(ch, out_dir=None, n=16):
    """a whole walk cycle (two steps), moving forward by the puppet's own step length: the two legs must take turns,
    one foot is always ON the ground, the lifted foot rises only a little, the standing foot does not slide, the hips
    do not jump - and every frame is one connected figure"""
    probs = []
    if ch.meta.get("no_legs"):
        step = ch.step_length("walk")
    else:
        step = ch.step_length("walk")
    Hw = ch.Hpx * ch._s()
    rows, lead, lifts, hips = [], [], [], []
    prev_stance, slip, travel = None, 0.0, 0.0
    prev_x = None
    frames = []
    for i in range(n + 1):
        ph = 2 * math.pi * i / n
        x = 960 + step * ph / math.pi
        st = {"x": x, "ground_y": 935, "facing": 1.0, "head_yaw": 0.6, "pose": R.walk_pose(ph), "t": i / n,
              "walk_phase": ph}                            # (exactly as the renderer hands it over)
        gy = st["ground_y"] + ch.foot_floor(st)
        j = ch.joints(dict(st, ground_y=gy))
        fn, ff = j["ft_n"], j["ft_f"]
        ground = max(fn[1], ff[1])
        stance = "n" if fn[1] >= ff[1] else "f"
        lifts.append((ground - min(fn[1], ff[1])) / Hw)
        hips.append(j["hip"][1])
        lead.append(1 if fn[0] > ff[0] else -1)
        foot = fn if stance == "n" else ff
        if prev_stance == stance and prev_x is not None:
            slip += abs(foot[0] - prev_x)
        if i > 0:
            travel += step / (n / 2)
        prev_stance, prev_x = stance, foot[0]
        if i % 2 == 0 and i < n:
            frames.append((st, gy))
    if ch.meta.get("no_legs"):                             # a saree / long dress: the feet are under the cloth - they
        slip = 0.0                                          # glide with it (see LIMITATIONS); it must stay on the ground
    if not ch.meta.get("no_legs"):
        if not (1 in lead and -1 in lead):
            probs.append("the legs do not take turns (one leg always in front)")
        if max(lifts) > 0.10:
            probs.append(f"a foot rises {max(lifts) * 100:.0f} % of the height off the ground - not a walk")
    bob = (max(hips) - min(hips)) / Hw
    if bob > 0.05:
        probs.append(f"the hips jump {bob * 100:.0f} % of the height while walking")
    slip_r = slip / max(1.0, travel)
    if slip_r > 0.15:
        probs.append(f"the standing foot slides {slip_r * 100:.0f} % of the distance walked")
    strip = []
    for st, gy in frames:
        img_a = np.zeros((TH, TW, 3), np.uint8)
        img_b = np.full((TH, TW, 3), 255, np.uint8)
        cam = cc.Camera(TW, TH)
        cam.set(st["x"], 745, 1.55)
        ch.draw(R.Painter(img_a, cam), dict(st))
        ch.draw(R.Painter(img_b, cam), dict(st))
        al = 1.0 - (img_b.astype(np.float32) - img_a.astype(np.float32)).mean(axis=2) / 255.0
        comps, _ = _components(al > 0.5)
        if len(comps) != 1:
            probs.append(f"walk frame at {st['t']:.2f}: {len(comps)} separate pieces")
        tile = img_b.copy()
        tile[al < 0.02] = (58, 66, 54)
        gys = int(cam.to_screen(0, gy)[1])
        cv2.line(tile, (0, gys), (TW, gys), (120, 200, 255), 1)
        strip.append(tile)
    res = {"pass": not probs, "problems": sorted(set(probs)), "max_foot_lift": round(max(lifts), 3),
           "hip_bob": round(bob, 3), "foot_slide": round(slip_r, 3), "legs_take_turns": bool(1 in lead and -1 in lead),
           "step_length_world": round(step, 1)}
    if out_dir and strip:
        cv2.imwrite(os.path.join(out_dir, "assembly_walk_cycle.png"), np.hstack(strip))
    return res


def _seat_and_render(ch, pp, facing, yaw, mouth):
    """the seated pose ON a seat (a plain bench drawn under the hips for the picture; the checks use the figure only)"""
    al, img_b, img_a, j, cam = _alpha(ch, pp, facing, yaw, mouth=mouth)
    Hw = ch.Hpx * j["s"]
    hip = j["hip"]
    floor = max(j["ft_n"][1], j["ft_f"][1])
    seat_y = hip[1] + 0.02 * Hw
    fw = j["fw"]
    xa, xb = hip[0] - fw * 0.16 * Hw, hip[0] + fw * 0.12 * Hw
    img = np.full((TH, TW, 3), (58, 66, 54), np.uint8)
    pt = R.Painter(img, cam)
    pt.poly([(min(xa, xb), seat_y), (max(xa, xb), seat_y), (max(xa, xb), seat_y + 0.035 * Hw), (min(xa, xb), seat_y + 0.035 * Hw)],
            (40, 62, 86))
    for xl in (min(xa, xb) + 0.02 * Hw, max(xa, xb) - 0.02 * Hw):
        pt.line((xl, seat_y + 0.03 * Hw), (xl, floor), (30, 46, 64), 0.022 * Hw)
    st = {"x": 960, "ground_y": 935, "facing": facing, "head_yaw": yaw, "pose": pp, "t": 1.0, "mouth": mouth, "blink": 0.0}
    ch.draw(R.Painter(img, cam), st)
    return al, img, j, cam, {"seat_y": seat_y, "floor": floor, "Hw": Hw}


def _identity(ch, ref_rgba, img_b, al, j, cam, facing):
    """the face and the costume in THIS pose vs the ORIGINAL reference picture (never vs another pose):
    face = normalised correlation of the drawn head with the reference's head (same size, same side);
    costume = main colours of the drawn body vs the reference body (delta-E)"""
    import consistency
    meta = ch.meta
    top, neck = meta["top"], meta["neck"]
    hx0 = int(max(0, neck[0] - 0.6 * meta["head_h"]))
    hx1 = int(neck[0] + 0.6 * meta["head_h"])
    ref_head = ref_rgba[int(top):int(neck[1]), hx0:hx1]
    k = j["s"] * cam.s
    nx, ny = cam.to_screen(*j["neck"])
    w_, h_ = int((hx1 - hx0) * k), int((neck[1] - top) * k)
    if facing >= 0:
        x0 = int(nx - (neck[0] - hx0) * k)
    else:
        x0 = int(nx - (hx1 - neck[0]) * k)
        ref_head = ref_head[:, ::-1]
    y0 = int(ny - h_)
    got = img_b[max(0, y0):y0 + h_, max(0, x0):x0 + w_]
    out = {}
    if got.size and ref_head.size and got.shape[0] > 10 and got.shape[1] > 10:
        rh = cv2.resize(ref_head, (got.shape[1], got.shape[0]), interpolation=cv2.INTER_AREA)
        a = rh[..., 3] > 127
        g1 = cv2.cvtColor(rh[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32)[a]
        g2 = cv2.cvtColor(got, cv2.COLOR_BGR2GRAY).astype(np.float32)[a]
        if len(g1) > 50 and g1.std() > 1 and g2.std() > 1:
            out["face_match"] = round(float(np.corrcoef(g1, g2)[0, 1]), 3)
    body = np.dstack([img_b, ((al > 0.5) * 255).astype(np.uint8)])
    out["costume_colour_de"] = round(consistency.palette_de(consistency.palette(body), consistency.palette(ref_rgba)), 1)
    return out


def face_match(ch, ref_rgba, st):
    """the FACE in this pose vs the ORIGINAL reference's face, at the reference's own size: only the head is drawn
    (screen grid = the reference's pixels, the neck at the reference's neck), the reference head is turned by the
    same head angle (and mirrored when facing left), then compared pixel by pixel (correlation of brightness).
    Same face -> close to 1; another face / another hairstyle / a beard that is not there -> clearly lower."""
    meta = ch.meta
    Hh, Ww = ref_rgba.shape[:2]
    j = ch.joints(dict(st))
    s = j["s"]
    nx, ny = meta["neck"]
    fw = 1 if st["facing"] >= 0 else -1
    cam = _FixedCam(j["neck"][0] - (nx if fw > 0 else (Ww - 1 - nx)) * s, j["neck"][1] - ny * s, 1.0 / s)
    st2 = dict(st, only={"head"}, planted=False, ground_y=st["ground_y"])
    a = np.zeros((Hh, Ww, 3), np.uint8)
    b = np.full((Hh, Ww, 3), 255, np.uint8)
    # draw with the SAME joints (no planting shift): the neck lands on the reference neck
    ch.draw(R.Painter(a, cam), dict(st2))
    ch.draw(R.Painter(b, cam), dict(st2))
    al = 1.0 - (b.astype(np.float32) - a.astype(np.float32)).mean(axis=2) / 255.0
    ref = ref_rgba if fw > 0 else ref_rgba[:, ::-1]
    nxx = nx if fw > 0 else Ww - 1 - nx
    head_ang = -math.degrees(j["head_ang"]) * fw
    M = cv2.getRotationMatrix2D((nxx, ny), head_ang, 1.0)
    rr = cv2.warpAffine(ref, M, (Ww, Hh), flags=cv2.INTER_LINEAR, borderValue=0)
    m = (rr[..., 3] > 200) & (al > 0.95)
    yy = np.arange(Hh)[:, None]
    m &= yy < ny - 0.05 * meta["head_h"]                 # the head above the neck
    if m.sum() < 200:
        return None
    g1 = cv2.cvtColor(rr[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32)[m]
    g2 = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)[m]
    cover = float(m.sum() / max(1, ((rr[..., 3] > 200) & (yy < ny - 0.05 * meta["head_h"])).sum()))
    return round(float(np.corrcoef(g1, g2)[0, 1]), 3), round(cover, 3)


def check(ch, ref_rgba, build_probs=(), plan=None, out_dir=None):
    """-> {pass, problems, poses, fidelity, walk_cycle, props, limitations, metrics}.
    In out_dir: assembly.jpg (all 7 poses), assembly_<pose>.png (each pose), assembly_fidelity.png,
    assembly_walk_cycle.png and assembly.json (the full report)."""
    import puppet_builder as PB
    plan = plan or {}
    problems = list(build_probs)
    metrics = {}
    ref_mask, _ = PB.clean_mask(ref_rgba)
    iou = rebuild_iou(ch, ref_mask)
    metrics["rebuild_iou"] = round(iou, 3)
    if iou < 0.88:
        problems.append(f"assembled in the reference pose it does not match the drawing (overlap {iou:.2f} < 0.88): "
                        "a part is missing, misplaced or duplicated")
    fid = fidelity(ch, ref_rgba, out_dir) if ch.meta.get("method") == "reference" else {"pass": True, "problems": []}
    problems += [f"fidelity: {p}" for p in fid["problems"]]
    faces = _faces_in_parts(ch)
    if faces:
        problems.append("a face appears inside " + ", ".join(faces) + " (a duplicated person)")
    dup = _heads_in_parts(ch)
    metrics["head_found_in_parts"] = dup
    if dup:
        problems.append("the character's own head appears again inside " + ", ".join(n for n, _ in dup) +
                        " (a duplicated person drawn into a body part)")
    wc = walk_cycle(ch, out_dir)
    problems += [f"walk cycle: {p}" for p in wc["problems"]]
    no_legs = bool(ch.meta.get("no_legs"))
    ghost = bool(ch.d.get("ghost") or ch.meta.get("floats"))
    poses, tiles = {}, []
    stand_h = None
    for label, pname, facing, yaw in POSES:
        pp = _pose(pname)
        mouth = (0.85, "A") if label in ("talking", "seated") else (0.0, "rest")
        seat = None
        if label == "seated":
            if ghost:                                      # a ghost never sits (it floats)
                poses[label] = {"pass": True, "problems": [], "note": "a ghost does not sit - not drawn"}
                tile = np.full((TH, TW, 3), (58, 66, 54), np.uint8)
                cv2.putText(tile, "ghost: never sits", (40, TH // 2), 0, 0.7, (255, 255, 255), 2)
                tiles.append(tile)
                continue
            al, img_b, j, cam, seat = _seat_and_render(ch, pp, facing, yaw, mouth)
        else:
            al, img_b, _, j, cam = _alpha(ch, pp, facing, yaw, mouth=mouth, floatpx=12.0 if ghost else 0.0,
                                          walk_phase=WALK_PHASE if pname == "walk" else None)
        m = al > 0.5
        pr = []
        comps, st = _components(m)
        if len(comps) != 1:
            pr.append(f"{len(comps)} separate pieces (a floating or detached part)")
        ys, xs = np.where(m)
        if len(ys):
            if ys.min() <= 1 or xs.min() <= 1 or xs.max() >= TW - 2 or ys.max() >= TH - 2:
                pr.append("cut by the frame")
            hgt = ys.max() - ys.min()
            if label == "three_q_right":
                stand_h = hgt
        else:
            pr.append("nothing drawn")
            hgt = 0
        s_ = j["s"] * cam.s
        rad = max(2.0, 0.006 * ch.Hpx * s_)

        def solid(pt_w):
            x, y = cam.to_screen(*pt_w)
            x, y = int(round(x)), int(round(y))
            if not (0 <= x < TW and 0 <= y < TH):
                return False
            d = np.zeros(m.shape, np.uint8)
            cv2.circle(d, (x, y), int(rad), 1, -1)
            v = al[d.astype(bool)]
            if not len(v):
                return False
            return bool((v < 0.5).sum() == 0 and v.mean() > 0.93)   # a real hole (see-through pixels), not edge smoothing
        joints = ["sh_n", "el_n", "sh_f", "el_f"] + ([] if no_legs else ["hip_n", "kn_n", "hip_f", "kn_f"])
        weak = [k for k in joints if k in j and not solid(j[k])]
        if weak:
            pr.append("a gap at the joint(s) " + ", ".join(weak))
        sc = lambda P: cam.to_screen(*P)
        if seat:                                           # hips ON the seat, thighs forward, knees, feet on the floor
            Hs = seat["Hw"] * cam.s
            hipx, hipy = sc(j["hip"])
            fl = sc((0, seat["floor"]))[1]
            sit_h = (fl - hipy) / Hs
            metrics["seat_height"] = round(sit_h, 3)
            if not 0.18 <= sit_h <= 0.36:
                pr.append(f"the hips are {sit_h:.2f} of the height above the floor - not a seat height")
            for sd in ("n", "f"):
                kx, ky = sc(j["kn_" + sd])
                fx_, fy_ = sc(j["ft_" + sd])
                fwd = (kx - hipx) * j["fw"] / Hs
                if not -0.02 <= (ky - hipy) / Hs <= 0.16:
                    pr.append(f"knee ({sd}) is not at the level of the lap")
                if fwd < 0.02:
                    pr.append(f"knee ({sd}) is not in front of the hips")
                if (fy_ - ky) / Hs < 0.14:
                    pr.append(f"lower leg ({sd}) does not reach down to the floor")
                if abs(fx_ - kx) / Hs > 0.12:
                    pr.append(f"foot ({sd}) is not under its knee")
                if abs(fy_ - fl) / Hs > 0.02:
                    pr.append(f"foot ({sd}) is off the floor")
            if stand_h:
                ratio = hgt / stand_h
                metrics["seated_height"] = round(ratio, 2)
                if not 0.62 <= ratio <= 0.87:
                    pr.append(f"seated height {ratio:.2f} of standing - not a natural seat")
        if label == "pointing":
            sh, hd = sc(j["sh_n"]), sc(j["hd_n"])
            arm = (ch.parts["uarm_near"][1] + ch.parts["farm_near"][1]) * s_ if "uarm_near" in ch.parts else 1.0
            reach = math.hypot(hd[0] - sh[0], hd[1] - sh[1]) / max(1.0, arm)
            metrics["pointing_reach"] = round(reach, 2)
            if reach < 0.8:
                pr.append(f"the pointing arm is bent or short (reach {reach:.2f})")
        if label == "walking" and not no_legs:
            fx = abs(sc(j["ft_n"])[0] - sc(j["ft_f"])[0]) / max(1.0, ch.Hpx * s_)
            if fx < 0.10:
                pr.append("the feet are not apart while walking")
        idt = _identity(ch, ref_rgba, img_b, al, j, cam, facing)
        idt.pop("face_match", None)
        st_f = {"x": 960, "ground_y": 935, "facing": facing, "head_yaw": yaw, "pose": pp, "t": 1.0, "mouth": mouth,
                "blink": 0.0}
        if pname == "walk":
            st_f["walk_phase"] = WALK_PHASE
        fm = face_match(ch, ref_rgba, st_f)
        if fm is None:
            pr.append("the face could not be compared with the reference")
        else:
            idt["face_match"], idt["face_covered"] = fm
            need = 0.85 if mouth[0] > 0.1 else 0.95       # (a talking mouth changes a few pixels)
            if fm[0] < need or fm[1] < 0.9:
                pr.append(f"the face is not the reference's face (match {fm[0]:.2f}, covered {fm[1]:.2f})")
        if idt["costume_colour_de"] > 12:
            pr.append(f"the costume colours differ from the reference (dE {idt['costume_colour_de']})")
        note = None
        poses[label] = {"pass": not pr, "problems": pr, "identity": idt}
        tile = img_b.copy()
        if not seat:
            tile[al < 0.02] = (58, 66, 54)
        if label == "three_q_right" and ch.meta.get("props"):      # props: their own layer, beside the body (not part of it)
            for pr_ in ch.meta["props"]:
                spr = cv2.imread(os.path.join(ch.folder, pr_["file"]), cv2.IMREAD_UNCHANGED) if hasattr(ch, "folder") else None
                if spr is None:
                    continue
                k = j["s"] * cam.s
                small = cv2.resize(spr, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
                ox_, oy_ = pr_["offset_from_hip"]
                X, Y = cam.to_screen(j["hip"][0] + ox_ * j["s"] * j["fw"], j["hip"][1] + oy_ * j["s"])
                X, Y = int(X), int(Y)
                h_, w_ = small.shape[:2]
                if 0 <= X and 0 <= Y and X + w_ <= TW and Y + h_ <= TH:
                    a_ = small[..., 3:4] / 255.0
                    tile[Y:Y + h_, X:X + w_] = (tile[Y:Y + h_, X:X + w_] * (1 - a_) + small[..., :3] * a_).astype(np.uint8)
                    cv2.rectangle(tile, (X, Y), (X + w_, Y + h_), (0, 200, 255), 1)
                    cv2.putText(tile, "prop (own layer)", (max(0, X - 30), max(12, Y - 4)), 0, 0.35, (0, 200, 255), 1)
        col = (90, 200, 90) if not pr else (40, 40, 230)
        cv2.rectangle(tile, (0, 0), (TW - 1, TH - 1), col, 4)
        cv2.putText(tile, label + ("*" if note else ""), (8, 22), 0, 0.6, (255, 255, 255), 2)
        if note:
            cv2.putText(tile, "* " + note[:46], (8, 40), 0, 0.33, (200, 220, 255), 1)
        for i_, p_ in enumerate(pr[:3]):
            cv2.putText(tile, p_[:44], (8, TH - 50 + 16 * i_), 0, 0.38, (80, 80, 255), 1)
        tiles.append(tile)
        if out_dir:
            cv2.imwrite(os.path.join(out_dir, f"assembly_{label}.png"), tile)
    for label, r in poses.items():
        problems += [f"{label}: {p}" for p in r["problems"]]
    res = {"pass": not problems, "problems": problems, "poses": poses, "metrics": metrics, "fidelity": fid,
           "walk_cycle": wc, "props": [{k: v for k, v in p.items()} for p in ch.meta.get("props") or []],
           "genuine_views": GENUINE_VIEWS, "usable_for": "three-quarter views only (right and mirrored left)",
           "limitations": LIMITATIONS}
    if out_dir:
        sheet = np.hstack(tiles)
        cv2.putText(sheet, "PASS (3/4 only)" if res["pass"] else "FAIL", (TW * len(tiles) - 260, 40), 0, 1.0,
                    (90, 220, 90) if res["pass"] else (60, 60, 240), 3)
        cv2.imwrite(os.path.join(out_dir, "assembly.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
        with open(os.path.join(out_dir, "assembly.json"), "w") as f:
            json.dump(res, f, indent=1, default=float)
    return res
