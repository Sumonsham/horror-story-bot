"""METHOD B - COMPLETE-POSE 2D ANIMATION: the character is drawn from its own complete drawings (one per pose),
never from rotated / stretched pieces. Same interface as the code rig and the cut-out rig (joints, foot_floor, draw),
so the existing renderer draws it unchanged.

  standing / idle     the 'stand' drawing; breathing = a very small vertical scale (0.5 %) from the feet
  talking             the 'stand' (or 'talk' while gesturing) drawing + the mouth drawn on ITS face from the real audio
  pointing            the 'point' drawing        sitting  the 'sit' drawing (only with a seat - asset_qa.seat_rule)
  walking             the 4 walk drawings of ONE cycle, chosen by the walk phase; the body moves by the measured step
  blinking            eyelids drawn on the drawing's own eyes (its own skin colour)
The drawing's feet stand on the ground line; the size is fixed by the character's height (no scale jumps between
drawings: every drawing is scaled by ITS OWN figure height to the same world height).
"""
import math
import os

import cv2
import numpy as np

VIEW_FOR = {"stand": "stand", "talk": "talk", "point": "point", "sit": "sit", "front": "front", "side": "side"}


class _Pose:
    def __init__(self, path):
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None or img.ndim < 3 or img.shape[2] != 4:
            raise ValueError(f"not an RGBA drawing: {path}")
        a = img[..., 3] > 127
        ys, xs = np.where(a)
        self.img = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy()
        self.h, self.w = self.img.shape[:2]
        self.levels = {}
        self.marks = None
        try:                                                # the face of THIS drawing (for mouth + blink)
            import cutout_assets as CA
            head = self.img[:max(10, int(0.25 * self.h))]
            self.marks = CA.face_marks(head, "three_q") if (head[..., 3] > 127).sum() > 400 else None
        except Exception:
            self.marks = None

    def scaled(self, k, mirror):
        key = (round(k, 3), mirror)
        if key not in self.levels:
            im = self.img[:, ::-1] if mirror else self.img
            self.levels = {key: cv2.resize(im, (max(1, int(self.w * k)), max(1, int(self.h * k))),
                                           interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)}
        return self.levels[key]


class FullPoseCharacter:
    def __init__(self, cid, design, files, scale=1.0, watermark=None):
        """files: {view: path} with stand (required), talk, point, sit, walk1..4 (optional)"""
        self.id, self.d, self.scale = cid, design, scale
        self.h = design.get("height", 1.0)
        self.poses = {v: _Pose(p) for v, p in files.items() if p and os.path.exists(p)}
        if "stand" not in self.poses:
            raise ValueError("a complete-pose character needs at least its standing drawing")
        self.walk = [self.poses[f"walk{k}"] for k in range(1, 5) if f"walk{k}" in self.poses]
        self.watermark = watermark
        self.complete = True

    def available(self):
        return sorted(self.poses)

    def world_h(self):
        return 372.0 * self.scale * self.h                 # the same world height as the other rigs

    def step_length(self, kind="walk"):
        """the distance of one step: the spread of the feet in the contact drawings (measured, not guessed)"""
        if len(self.walk) < 4:
            return 0.35 * self.world_h()
        spreads = []
        for p in (self.walk[0], self.walk[2]):
            a = p.img[int(0.9 * p.h):, :, 3] > 127
            xs = np.where(a.any(axis=0))[0]
            if len(xs):
                spreads.append((xs.max() - xs.min()) / p.h)
        s = (np.mean(spreads) if spreads else 0.3) * self.world_h() * 0.8
        return s * (1.6 if kind == "run" else 1.0)

    def _choose(self, st):
        p = st.get("pose") or {}
        if st.get("walk_phase") is not None and len(self.walk) == 4:
            i = int((st["walk_phase"] % (2 * math.pi)) / (math.pi / 2)) % 4
            return self.walk[i], f"walk{i + 1}"
        if p.get("hip", 147) < 120 and "sit" in self.poses:
            return self.poses["sit"], "sit"
        if max(p.get("uarm_n", 0), p.get("uarm_f", 0)) > 60 and "point" in self.poses:
            return self.poses["point"], "point"
        if st.get("gesture") and "talk" in self.poses:
            return self.poses["talk"], "talk"
        return self.poses["stand"], "stand"

    def joints(self, st):
        pose, name = self._choose(st)
        k = self.world_h() / pose.h
        if name == "sit":
            k *= 0.85                                       # (a seated drawing is shorter: the seated figure height)
        breath = 1.0 + (0.005 * math.sin(st.get("t", 0.0) * 2 * math.pi / 3.6) if name in ("stand", "talk") else 0.0)
        W, H = pose.w * k, pose.h * k * breath
        x, gy = st["x"], st["ground_y"]
        fw = 1 if st.get("facing", 1.0) >= 0 else -1
        top = gy - H
        jj = {"k": self.scale * self.h, "fw": fw, "s": k, "head": (x + 0.05 * W * fw, top + 0.12 * H),
              "neck": (x, top + 0.2 * H), "hip": (x, top + 0.52 * H), "hd_n": (x + 0.35 * W * fw, top + 0.5 * H),
              "hd_f": (x - 0.35 * W * fw, top + 0.5 * H), "sh_n": (x + 0.15 * W * fw, top + 0.24 * H),
              "sh_f": (x - 0.15 * W * fw, top + 0.24 * H), "el_n": (x + 0.25 * W * fw, top + 0.38 * H),
              "el_f": (x - 0.25 * W * fw, top + 0.38 * H), "kn_n": (x + 0.06 * W * fw, top + 0.75 * H),
              "kn_f": (x - 0.06 * W * fw, top + 0.75 * H), "ft_n": (x + 0.1 * W * fw, gy - 4 * self.scale * self.h),
              "ft_f": (x - 0.1 * W * fw, gy - 4 * self.scale * self.h), "_pose": name, "_box": (x - W / 2, top, W, H)}
        return jj

    def foot_floor(self, st):
        return 0.0                                          # the drawing's feet are on the ground line by construction

    def draw(self, pt, st):
        st = dict(st)
        st["ground_y"] = st["ground_y"] - st.get("float", 0.0)
        j = self.joints(st)
        pose, name = self._choose(st)
        cam = pt.cam
        x0, y0, W, H = j["_box"]
        sx0, sy0 = cam.to_screen(x0, y0)
        sx1, sy1 = cam.to_screen(x0 + W, y0 + H)
        w_, h_ = int(round(sx1 - sx0)), int(round(sy1 - sy0))
        if w_ < 2 or h_ < 2:
            return j
        spr = pose.scaled(w_ / pose.w, j["fw"] < 0)
        spr = cv2.resize(spr, (w_, h_), interpolation=cv2.INTER_AREA) if spr.shape[:2] != (h_, w_) else spr
        X, Y = int(round(sx0)), int(round(sy0))
        img = pt.img
        Hh, Ww = img.shape[:2]
        xa, ya, xb, yb = max(0, X), max(0, Y), min(Ww, X + w_), min(Hh, Y + h_)
        if xb <= xa or yb <= ya:
            return j
        part = spr[ya - Y:yb - Y, xa - X:xb - X].astype(np.float32)
        a = part[..., 3:4] / 255.0 * st.get("alpha", 1.0)
        roi = img[ya:yb, xa:xb].astype(np.float32)
        img[ya:yb, xa:xb] = np.clip(roi * (1 - a) + part[..., :3] * pt.light * a, 0, 255).astype(np.uint8)
        self._face(pt, st, pose, (X, Y, w_, h_), j["fw"])
        return j

    def _face(self, pt, st, pose, box, fw):
        """mouth (from the real audio) and blinking, drawn on THIS drawing's own face with its own skin colour"""
        mk = pose.marks
        if not mk or not mk.get("found_face"):
            return
        X, Y, w_, h_ = box
        k = w_ / pose.w

        def to(q):
            qx = q[0] if fw > 0 else pose.w - 1 - q[0]
            return int(X + qx * k), int(Y + q[1] * k)
        skin = tuple(int(v) for v in mk["skin"])
        fwid = mk["face_w"] * k
        blink = st.get("blink", 0.0)
        if blink > 0.05:
            for e in mk["eyes"]:
                ex, ey = to(e)
                cv2.ellipse(pt.img, (ex, ey), (max(1, int(fwid * 0.11)), max(1, int(fwid * 0.075 * blink))), 0, 0, 360, skin, -1, cv2.LINE_AA)
                cv2.line(pt.img, (int(ex - fwid * 0.1), ey), (int(ex + fwid * 0.1), ey), (30, 26, 30), max(1, int(fwid * 0.02)), cv2.LINE_AA)
        op, shape = st.get("mouth", (0.0, "rest"))
        if op > 0.12:
            mx, my = to(mk["mouth"])
            w = {"A": 0.13, "E": 0.16, "O": 0.09, "M": 0.12}.get(shape, 0.12) * fwid
            hgt = {"A": 0.11, "E": 0.055, "O": 0.1, "M": 0.0}.get(shape, 0.05) * fwid * op
            cv2.ellipse(pt.img, (mx, my), (max(1, int(w * 1.25)), max(1, int(max(hgt, fwid * 0.03) * 1.2 + fwid * 0.02))), 0, 0, 360, skin, -1, cv2.LINE_AA)
            if hgt > 0.8:
                cv2.ellipse(pt.img, (mx, int(my + hgt * 0.15)), (max(1, int(w)), max(1, int(hgt))), 0, 0, 360, (40, 30, 70), -1, cv2.LINE_AA)
