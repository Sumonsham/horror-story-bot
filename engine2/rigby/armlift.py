"""ARM-LIFT VISUAL TEST - the arm of a rig is raised step by step (rest, 30, 45, 60, 90, 120 degrees, back to
rest) and every step is checked where cut-out rigs break: the shoulder and armpit, the elbow, the wrist.

Automatic checks per step (TECHNICAL only - the owner judges the look):
  holes      transparent pixels ENCLOSED by the character (a gap that shows the background)
  white      near-white pixels in the shoulder/armpit area that are not in the drawing at rest (white seams)
  outline    how much of the character's edge around the shoulder/armpit is still drawn ink; a cut edge without
             an outline lowers it
  joined     arm + hand + torso are one connected piece (no floating hand, no detached arm)
Output: a contact sheet (whole figure + 300 % zooms of shoulder/armpit, elbow, wrist), a slow-motion video and
armlift_report.json. Angles are measured from 'hanging straight down', outward (sideways, away from the body).
"""
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

STEPS = [0, 30, 45, 60, 90, 120, 0]
ARM = {"r": ("upperarm_r", "forearm_r", "hand_r", "arm_r", -1), "l": ("upperarm_l", "forearm_l", "hand_l", "arm_l", 1)}


def _ang(m):
    return math.degrees(math.atan2(m[1], m[0]))


def _xf(m, p):
    return m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5]


def pose_at(rig, side, raise_deg, bend=8.0):
    """the arm raised `raise_deg` sideways from hanging down (0 = the drawing's own rest angle is kept)"""
    up, fo, ha, _, out = ARM[side]
    p = rig.pose()
    if raise_deg <= 0:
        return p
    i = rig.sk.find_bone(up)
    world_now = _ang(p.bone_world(up))
    rest_raise = abs(((world_now + 90.0) + 180) % 360 - 180)             # how far the drawing's arm is already out
    target = -90.0 + out * max(raise_deg, rest_raise)
    delta = ((target - world_now) + 180) % 360 - 180
    loc = list(rig.sk.bones[i].setup)
    p.set_bone(i, rotation=loc[2] + delta)
    j = rig.sk.find_bone(fo)                                 # the elbow eases a little as the arm comes up
    lf = list(rig.sk.bones[j].setup)
    p.set_bone(j, rotation=lf[2] + out * bend * min(1.0, raise_deg / 90.0))
    p.update_world()
    return p


def _render(rig, p, scale, size):
    from engine2.rigby import raster as RS
    W, H = size
    f = np.full((H, W, 3), 236, np.uint8)
    a = RS.draw(rig, p, f, scale, W / 2, H - 40)
    return f, a


def _checks(img, alpha, rest_white, rest_ink, centre, r, rig, p, side):
    up, fo, ha, slot, _ = ARM[side]
    m = alpha > 0.5
    inv = (~m).astype(np.uint8)
    ff = inv.copy()
    h, w = ff.shape
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 2)
    holes = (ff == 1)
    n, lab, st, _ = cv2.connectedComponentsWithStats(holes.astype(np.uint8), connectivity=4)
    hole_px = int(sum(v for v in st[1:, 4] if v >= 4))
    yy, xx = np.mgrid[0:h, 0:w]
    roi = (xx - centre[0]) ** 2 + (yy - centre[1]) ** 2 < r * r
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white = m & roi & (hsv[..., 2] > 243) & (hsv[..., 1] < 28)
    edge = m & ~(cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & roi
    dark = cv2.erode((hsv[..., 2] < 110).astype(np.uint8), np.ones((1, 1), np.uint8)) > 0
    near_dark = cv2.dilate(dark.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    ink_ratio = float((edge & near_dark).sum()) / max(1, int(edge.sum()))
    return {"holes_px": hole_px, "white_px": int(white.sum()), "white_extra_px": max(0, int(white.sum()) - rest_white),
            "outline_ratio": round(ink_ratio, 3), "outline_drop": round(max(0.0, rest_ink - ink_ratio), 3)}, holes, white


def arm_widths(rig, p, side, S=1.0):
    """the sleeve's width across the upper arm at 15 %, 30 % and 50 % of its length (a stretched / pinched
    shoulder shows as a narrower arm near the shoulder)"""
    from engine2.rigby import raster as RS
    up, fo, ha, slot, _ = ARM[side]
    W, H = 1400, 1400
    f = np.zeros((H, W, 3), np.uint8)
    a = RS.draw(rig, p, f, S, W / 2, H - 100, only={slot}) > 0.5
    m = p.bone_world(up)
    L = rig.sk.bones[rig.sk.find_bone(up)].length
    ang = math.atan2(m[1], m[0])
    nx, ny = -math.sin(ang), math.cos(ang)
    out = []
    for frac in (0.15, 0.30, 0.50):
        cx, cy = _xf(m, (L * frac, 0))
        run_, best = 0, 0                                    # the longest run of the sleeve across the arm
        for k in range(-140, 141):
            x = int(round(W / 2 + (cx + nx * k) * S))
            y = int(round(H - 100 - (cy + ny * k) * S))
            if 0 <= x < W and 0 <= y < H and a[y, x]:
                run_ += 1
                best = max(best, run_)
            else:
                run_ = 0
        out.append(best)
    return out


def visible_root_ratio(rig, p, side, S=1.0):
    """where the arm comes out from the body: its VISIBLE width (not covered by the torso) at the first point along
    the upper arm where it is seen, divided by the forearm's width. A pinched, stretched shoulder gives a small
    ratio (a real arm is at least about as wide at the shoulder as at the forearm)."""
    from engine2.rigby import raster as RS
    up, fo, ha, slot, _ = ARM[side]
    W, H = 1400, 1400
    f = np.zeros((H, W, 3), np.uint8)
    arm = RS.draw(rig, p, f, S, W / 2, H - 100, only={slot}) > 0.5
    f[:] = 0
    tor = RS.draw(rig, p, f, S, W / 2, H - 100, only={"torso", "neck", "head"}) > 0.5
    vis = arm & ~tor

    def width(mask, m, L, frac):
        ang = math.atan2(m[1], m[0])
        nx, ny = -math.sin(ang), math.cos(ang)
        cx, cy = _xf(m, (L * frac, 0))
        run_, best = 0, 0
        for k in range(-140, 141):
            x = int(round(W / 2 + (cx + nx * k) * S))
            y = int(round(H - 100 - (cy + ny * k) * S))
            if 0 <= x < W and 0 <= y < H and mask[y, x]:
                run_ += 1
                best = max(best, run_)
            else:
                run_ = 0
        return best
    mu, mf = p.bone_world(up), p.bone_world(fo)
    Lu = rig.sk.bones[rig.sk.find_bone(up)].length
    Lf = rig.sk.bones[rig.sk.find_bone(fo)].length
    ref = max(1, width(arm, mf, Lf, 0.5))
    for k in range(4, 60):
        w = width(vis, mu, Lu, k / 100.0)
        if w >= 3:
            return round(w / ref, 2), k
    return 1.0, None


def run(rig_json, out_dir, label="current rig", log=print):
    from engine2.rigby import raster as RS
    rig = RS.Rig(rig_json)
    os.makedirs(out_dir, exist_ok=True)
    S, size = 0.9, (1100, 1000)
    report = {"rig": rig_json, "label": label, "steps": STEPS, "arms": {}, "pass": True}
    sheets = []
    for side in ("r", "l"):
        up, fo, ha, slot, out = ARM[side]
        p0 = rig.pose()
        img0, a0 = _render(rig, p0, S, size)
        sh0 = _xf(p0.bone_world(up), (0, 0))
        c0 = (int(size[0] / 2 + sh0[0] * S), int(size[1] - 40 - sh0[1] * S))
        hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)
        r = int(95 * S)
        yy, xx = np.mgrid[0:size[1], 0:size[0]]
        roi0 = (xx - c0[0]) ** 2 + (yy - c0[1]) ** 2 < r * r
        m0 = a0 > 0.5
        rest_white = int((m0 & roi0 & (hsv0[..., 2] > 243) & (hsv0[..., 1] < 28)).sum())
        e0 = m0 & ~(cv2.erode(m0.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & roi0
        nd0 = cv2.dilate((hsv0[..., 2] < 110).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        rest_ink = float((e0 & nd0).sum()) / max(1, int(e0.sum()))
        w0 = arm_widths(rig, p0, side)
        rows, res = [], []
        for k, deg in enumerate(STEPS):
            p = pose_at(rig, side, deg)
            img, a = _render(rig, p, S, size)
            sh = _xf(p.bone_world(up), (0, 0))
            el = _xf(p.bone_world(fo), (0, 0))
            wr = _xf(p.bone_world(ha), (0, 0))
            to = lambda q: (int(size[0] / 2 + q[0] * S), int(size[1] - 40 - q[1] * S))
            c = to(sh)
            m, holes, white = _checks(img, a, rest_white, rest_ink, c, r, rig, p, side)
            from engine2.rigby.proof import _pieces
            m["arm_hand_torso_pieces"] = _pieces(rig, p, [slot, ha, "torso"])
            wd = arm_widths(rig, p, side)
            m["upper_arm_width_vs_drawing"] = [round(a_ / max(1, b_), 2) for a_, b_ in zip(wd, w0)]
            rr, at = visible_root_ratio(rig, p, side)
            r0 = visible_root_ratio(rig, p0, side)[0]
            m["visible_shoulder_width_vs_forearm"] = rr
            probs = []
            if rr < min(0.75, 0.8 * r0) or (deg >= 60 and rr < 0.6):   # (a raised arm shows its shoulder)
                probs.append(f"the arm comes out of the body pinched (visible width {rr:.0%} of the forearm, drawing {r0:.0%})")
            if min(m["upper_arm_width_vs_drawing"]) < 0.72:
                probs.append(f"the upper arm is pinched / stretched near the shoulder (width {min(m['upper_arm_width_vs_drawing']):.0%} of the drawing)")
            if m["holes_px"] > 0:
                probs.append(f"{m['holes_px']} px of transparent hole inside the figure")
            if m["white_extra_px"] > 25:
                probs.append(f"{m['white_extra_px']} px of white seam at the shoulder / armpit")
            if m["outline_drop"] > 0.12:
                probs.append(f"the outline around the shoulder / armpit is broken ({m['outline_ratio']:.0%} ink, rest {rest_ink:.0%})")
            if m["arm_hand_torso_pieces"] != 1:
                probs.append("the arm / hand is not joined to the body")
            res.append({"degrees": deg, "metrics": m, "problems": probs, "pass": not probs})
            if probs:
                report["pass"] = False
            # tiles: whole figure (problems marked) + 300 % zooms
            vis = img.copy()
            vis[holes] = (255, 0, 255)
            vis[white] = (0, 0, 255)
            cv2.circle(vis, c, r, (0, 200, 255), 1, cv2.LINE_AA)
            whole = cv2.resize(vis, (330, 300), interpolation=cv2.INTER_AREA)
            cv2.putText(whole, f"{deg} deg" + ("  OK" if not probs else "  FAIL"), (6, 22), 0, 0.65,
                        (0, 140, 0) if not probs else (0, 0, 220), 2, cv2.LINE_AA)
            zooms = []
            for nm, q in (("shoulder/armpit", sh), ("elbow", el), ("wrist", wr)):
                x, y = to(q)
                z = 50
                cr = img[max(0, y - z):y + z, max(0, x - z):x + z]
                cr = cv2.copyMakeBorder(cr, 0, 2 * z - cr.shape[0], 0, 2 * z - cr.shape[1], cv2.BORDER_CONSTANT, value=(236, 236, 236))
                zz = cv2.resize(cr, (300, 300), interpolation=cv2.INTER_CUBIC)
                cv2.putText(zz, nm + " 300%", (5, 18), 0, 0.5, (0, 0, 0), 2, cv2.LINE_AA)
                cv2.putText(zz, nm + " 300%", (5, 18), 0, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                zooms.append(zz)
            row = np.hstack([whole] + zooms)
            cv2.putText(row, "; ".join(probs)[:150], (6, 292), 0, 0.42, (0, 0, 200), 1, cv2.LINE_AA)
            rows.append(cv2.copyMakeBorder(row, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=(255, 255, 255)))
        sheet = np.vstack(rows)
        title = np.full((44, sheet.shape[1], 3), 255, np.uint8)
        cv2.putText(title, f"ARM-LIFT TEST - {label} - {'near (screen-left)' if side == 'r' else 'far (screen-right)'} arm "
                    "- magenta = hole, red = white seam", (8, 28), 0, 0.62, (0, 0, 0), 1, cv2.LINE_AA)
        sheet = np.vstack([title, sheet])
        fn = os.path.join(out_dir, f"armlift_{side}_sheet.png")
        cv2.imwrite(fn, sheet)
        sheets.append(fn)
        report["arms"][side] = res
    # slow motion: rest -> 120 -> rest, both arms in turn, 8 s each
    vid = os.path.join(out_dir, "armlift_slow.mp4")
    W, H, FPS = 1280, 720, 24
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                             "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-map", "0:v", "-map", "1:a",
                             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                             "-movflags", "+faststart", vid], stdin=subprocess.PIPE)
    for side in ("r", "l"):
        for fi in range(8 * FPS):
            u = fi / (8 * FPS)
            deg = 120 * (0.5 - 0.5 * math.cos(2 * math.pi * u))
            p = pose_at(rig, side, deg)
            f = np.full((H, W, 3), 236, np.uint8)
            RS.draw(rig, p, f, 0.68, W / 2, H - 20)
            cv2.rectangle(f, (0, 0), (W, 30), (20, 20, 20), -1)
            cv2.putText(f, f"PREVIEW - NOT APPROVED - arm-lift test ({label}) - {deg:5.1f} deg", (10, 21), 0, 0.56, (80, 200, 255), 1, cv2.LINE_AA)
            proc.stdin.write(f.tobytes())
    proc.stdin.close()
    proc.wait()
    report["files"] = {"sheets": sheets, "video": vid}
    with open(os.path.join(out_dir, "armlift_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    return report


if __name__ == "__main__":
    r = run(sys.argv[1], sys.argv[2], *(sys.argv[3:4] or ["current rig"]))
    for s, res in r["arms"].items():
        print(s, [(x["degrees"], "OK" if x["pass"] else x["problems"]) for x in res])
