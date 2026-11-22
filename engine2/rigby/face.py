"""Mouth shapes (lip-sync) and blinks for a rigged character, drawn ON the character's own face and moving with
its head bone.

* Mouth timing: Rhubarb Lip Sync (MIT, github.com/DanielSWolf/rhubarb-lip-sync), recogniser 'phonetic' (language-
  independent - used for Bengali), shapes A-H + X. Without the Rhubarb binary the amplitude-based visemes of the
  existing lip_sync.py are used and the report says so.
* The shapes are small openings under the drawn moustache, in the drawing's own ink and colours; they are code-
  drawn (the reference has only a closed mouth). They are part of what the owner approves.
* Blink: the eyes (positions read off the drawing, prep.json "face") are covered with the skin colour and a lid line.
"""
import json
import os
import shutil
import subprocess

import cv2
import numpy as np

INK = (28, 24, 24)
INSIDE = (52, 34, 96)
TEETH = (238, 240, 244)
TONGUE = (112, 108, 214)
# Rhubarb shapes -> (width, height) as a share of the mouth width, teeth, tongue
SHAPES = {"X": None, "A": None, "B": (0.80, 0.20, True, False), "C": (0.86, 0.34, True, False), "D": (0.92, 0.52, False, True),
          "E": (0.62, 0.40, False, False), "F": (0.42, 0.26, False, False), "G": (0.74, 0.18, True, False), "H": (0.80, 0.36, False, True)}


def rhubarb_bin():
    for c in (os.environ.get("RHUBARB_BIN"), shutil.which("rhubarb")):
        if c and os.path.exists(c):
            return c
    return None


def mouth_cues(wav, fps, log=print):
    """[(t0, t1, shape)] for a voice file. Rhubarb when available (phonetic: language independent)."""
    rb = rhubarb_bin()
    if rb:
        out = wav + ".rhubarb.json"
        r = subprocess.run([rb, "-r", "phonetic", "-f", "json", "-q", wav, "-o", out], capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and os.path.exists(out):
            cues = json.load(open(out))["mouthCues"]
            return [(c["start"], c["end"], c["value"]) for c in cues], "rhubarb (phonetic)"
        log(f"  rhubarb failed: {r.stderr[-200:]}")
    import lip_sync
    vis = lip_sync.visemes(wav, fps)
    cues = []
    for i, (op, _) in enumerate(vis):
        sh = "X" if op < 0.08 else "B" if op < 0.3 else "C" if op < 0.55 else "D"
        cues.append((i / fps, (i + 1) / fps, sh))
    return cues, "amplitude (lip_sync.py fallback)"


def shape_at(cues, t):
    for a, b, s in cues:
        if a <= t < b:
            return s
    return "X"


def _xf(m, p):
    return m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5]


def _inv(m):
    a, b, c, d = m[0], m[2], m[1], m[3]
    det = a * d - b * c
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    tx, ty = m[4], m[5]
    return (ia, ic, ib, id_, -(ia * tx + ib * ty), -(ic * tx + id_ * ty))


class Face:
    def __init__(self, rig, face_cfg, size, skin_bgr):
        """face_cfg (prep.json 'face'): mouth [x,y,width], eyes [[x,y,rx,ry],...] in reference pixels"""
        self.rig = rig
        W, H = size
        self.to_rig = lambda p: (p[0] - W / 2.0, H - p[1])
        setup = rig.pose()
        self.inv0 = _inv(setup.bone_world("head"))
        self.cfg = face_cfg
        self.skin = tuple(int(v) for v in skin_bgr)

    def _head_pts(self, pose, pts):
        m1 = pose.bone_world("head")
        out = []
        for p in pts:
            q = _xf(self.inv0, self.to_rig(p))
            out.append(_xf(m1, q))
        return out

    def draw(self, frame, pose, scale, ox, oy, shape="X", blink=0.0):
        """draws on frame (screen = (x*scale+ox, oy-y*scale)), at 4x then reduced locally for clean small shapes"""
        def scr(p):
            return np.float32([p[0] * scale + ox, oy - p[1] * scale])
        mx, my, mw = self.cfg["mouth"]
        jobs = []
        if blink > 0.05:
            for ex, ey, rx, ry in self.cfg["eyes"]:
                c, r1, r2 = self._head_pts(pose, [(ex, ey), (ex + rx, ey), (ex, ey + ry)])
                jobs.append(("eye", scr(c), np.linalg.norm(scr(r1) - scr(c)), np.linalg.norm(scr(r2) - scr(c)), scr(r1) - scr(c)))
        spec = SHAPES.get(shape)
        if spec:
            c, r1 = self._head_pts(pose, [(mx, my), (mx + mw / 2.0, my)])
            jobs.append(("mouth", scr(c), np.linalg.norm(scr(r1) - scr(c)), spec, scr(r1) - scr(c)))
        for job in jobs:
            c = job[1]
            R = int(max(job[2], 4) * 2.2) + 6
            x0, y0 = int(c[0]) - R, int(c[1]) - R
            x1, y1 = x0 + 2 * R, y0 + 2 * R
            if x0 < 0 or y0 < 0 or x1 > frame.shape[1] or y1 > frame.shape[0]:
                continue
            Z = 4
            patch = cv2.resize(frame[y0:y1, x0:x1], None, fx=Z, fy=Z, interpolation=cv2.INTER_CUBIC)
            cc = ((c - [x0, y0]) * Z).astype(np.float32)
            ang = float(np.degrees(np.arctan2(job[-1][1], job[-1][0])))
            if job[0] == "eye":
                rx, ry = job[2] * Z, job[3] * Z
                k = min(1.0, blink)
                cv2.ellipse(patch, (int(cc[0]), int(cc[1])), (int(rx * 1.38), int(ry * 1.5)), ang, 0, 360, self.skin, -1, cv2.LINE_AA)
                if k < 0.95:                                # half-closed: the lower part of the eye still shows
                    pass
                lid_y = int(cc[1] + ry * 0.25)
                cv2.ellipse(patch, (int(cc[0]), lid_y), (int(rx * 1.0), int(ry * 0.45)), ang, 10, 170, INK, max(2, int(1.8 * Z)), cv2.LINE_AA)
            else:
                half = job[2] * Z
                w_, h_, teeth, tongue = job[3]
                ax = (int(half * w_), max(2, int(half * 2 * h_ / 2)))
                ctr = (int(cc[0]), int(cc[1] + ax[1] * 0.5))
                cv2.ellipse(patch, ctr, ax, ang, 0, 360, INSIDE, -1, cv2.LINE_AA)
                if teeth:
                    cv2.ellipse(patch, (ctr[0], ctr[1] - int(ax[1] * 0.55)), (int(ax[0] * 0.8), max(1, int(ax[1] * 0.42))), ang, 0, 180, TEETH, -1, cv2.LINE_AA)
                if tongue:
                    cv2.ellipse(patch, (ctr[0], ctr[1] + int(ax[1] * 0.45)), (int(ax[0] * 0.6), max(1, int(ax[1] * 0.45))), ang, 180, 360, TONGUE, -1, cv2.LINE_AA)
                cv2.ellipse(patch, ctr, ax, ang, 0, 360, INK, max(2, int(1.3 * Z)), cv2.LINE_AA)
            frame[y0:y1, x0:x1] = cv2.resize(patch, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
