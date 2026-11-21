"""CUT-OUT RIG - a 2.5D character made of the AI-drawn parts (cutout_assets.py), moved by the SAME skeleton,
poses and motions as the code-drawn rig (walk, run, sit, stand up, turn, look back, gestures, handshake, hug...).

Bone hierarchy: hip -> torso -> neck -> head;  torso -> shoulders -> upper arms -> forearms (+hands);
hip -> thighs -> shins (+feet). Every part is a transparent sprite rotated about its own joint (pivot), drawn
through the camera (so a close-up uses the sharp original, a wide shot a smaller mip level). Facing left = the
mirrored sprites. The head swaps between its front / three-quarter / profile drawings as it turns (the way
2.5D TV cartoons do), the frightened face is used when the character is scared.
Eyes blink and the mouth talks ON the AI face: the eyelids and mouth shapes are drawn at the face's own
landmarks with its own skin colour, driven by the real voice (lip_sync).
Same interface as cartoon_rig.Character: joints(st), foot_floor(st), draw(pt, st) -> joints, .d (design).
"""
import json
import math
import os

import cv2
import numpy as np

import cartoon_rig as R


class _Sprite:
    def __init__(self, rgba, pivot, rest):
        self.levels = {}
        self.base = (rgba, (float(pivot[0]), float(pivot[1])), float(rest))

    def get(self, mirror, scale):
        """(sprite, pivot, rest, factor): a pre-shrunk level when the sprite is drawn much smaller (no aliasing)"""
        lvl = 0
        while scale * (2 ** (lvl + 1)) <= 1.0 and lvl < 4:
            lvl += 1
        key = (mirror, lvl)
        if key not in self.levels:
            rgba, (px, py), rest = self.base
            if mirror:
                rgba = rgba[:, ::-1].copy()
                px = rgba.shape[1] - 1 - px
                rest = -rest
            f = 1.0
            for _ in range(lvl):
                rgba = cv2.pyrDown(rgba)
                f *= 0.5
            self.levels[key] = (rgba, (px * f, py * f), rest, f)
        return self.levels[key]


def _premul(rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    return rgba[..., :3].astype(np.float32) * a, a


class CutoutCharacter:
    def __init__(self, cid, design, folder, scale=1.0):
        self.id, self.d, self.scale = cid, design, scale
        self.h = design.get("height", 1.0)
        meta = json.load(open(os.path.join(folder, "rig.json")))
        self.meta = meta
        self.parts = {}
        for name, p in meta["parts"].items():
            img = cv2.imread(os.path.join(folder, p["file"]), cv2.IMREAD_UNCHANGED)
            if img is not None and img.shape[2] == 4:
                self.parts[name] = (_Sprite(img, p["pivot"], p["rest"]), p["length"])
        self.heads = {}
        for view in ("front", "three_q", "profile", "scared"):
            f = os.path.join(folder, f"head_{view}.png")
            if os.path.exists(f):
                img = cv2.imread(f, cv2.IMREAD_UNCHANGED)
                marks = json.load(open(os.path.join(folder, f"head_{view}.json")))
                ys = np.where((img[..., 3] > 127).any(axis=1))[0]
                hv_h = max(10.0, marks["neck"][1] - ys.min())
                self.heads[view] = (_Sprite(img, marks["neck"], 180.0), marks, hv_h)
        self.Hpx = meta["height_px"]
        need = ["head", "torso", "uarm_near", "farm_near", "uarm_far", "farm_far"]
        need += ["skirt_up", "skirt_lo"] if meta.get("no_legs") else ["thigh_near", "shin_near", "thigh_far", "shin_far"]
        self.complete = all(k in self.parts for k in need)       # (a saree / dress / ghost has the cloth, not legs)

    # -------------------------------------------------------------- skeleton (same pose angles as cartoon_rig)
    def _s(self):
        return 372.0 * self.scale * self.h / self.Hpx          # world px per picture px

    def _pose(self, p):
        """an arm that could not be cut out cleanly moves only near its drawn position (never leaves a ghost arm)"""
        p = dict(p)
        for side, sfx in (("near", "n"), ("far", "f")):
            if not self.meta.get("arm_free", {}).get(side, True):
                for seg_ in ("uarm", "farm"):
                    part = self.parts.get(f"{seg_}_{side}")
                    if part:
                        rest = part[0].base[2]
                        p[f"{seg_}_{sfx}"] = max(rest - 20.0, min(rest + 20.0, p.get(f"{seg_}_{sfx}", rest)))
        return p

    def joints(self, st):
        st = dict(st, pose=self._pose(st["pose"]))
        s = self._s()
        k = self.scale * self.h
        f = st["facing"]
        fu = st.get("facing_upper", f)
        fw = 1 if f >= 0 else -1
        sq, squ = max(0.45, abs(f)), max(0.45, abs(fu))
        p = st["pose"]
        meta = self.meta
        if meta.get("no_legs"):                            # a saree / dress / ghost: the cloth's length is the leg
            half = meta.get("skirt_len", 0.45 * self.Hpx) * s * 0.5
            L = lambda n: (self.parts[n][1] * s if n in self.parts else (half if n.startswith(("thigh", "shin")) else 60.0 * k))
        else:
            L = lambda n: self.parts[n][1] * s if n in self.parts else 60.0 * k
        leg = L("thigh_near") + L("shin_near")
        x0, gy = st["x"], st["ground_y"]
        hip = (x0, gy - p["hip"] / 147.0 * leg)
        lean = math.radians(p.get("torso", 0.0) + p.get("chest", 0.0) * 0.5)
        hx, hy = meta["hip"]
        nx, ny = meta["neck"]
        T = math.hypot(nx - hx, ny - hy) * s
        neck = (hip[0] + math.sin(lean) * T * fw * squ, hip[1] - math.cos(lean) * T)

        def rot(dx, dy, ang):                               # rotate a picture offset by the torso lean (rig sense)
            c, s_ = math.cos(ang), math.sin(ang)
            return dx * c - dy * s_, dx * s_ + dy * c

        def from_neck(pt_img):
            dx, dy = (pt_img[0] - nx) * s, (pt_img[1] - ny) * s
            rx, ry = rot(dx, dy, lean)
            return (neck[0] + rx * fw * squ, neck[1] + ry)

        j_extra = {}
        for name in ("pallu_anchor", "hair_anchor", "waist"):
            if name in meta:
                j_extra[name] = from_neck(meta[name])
        sh = meta.get("shoulders", {})
        sh_n = from_neck(sh["near"]) if "near" in sh else (neck[0] + 6 * k * fw, neck[1] + 12 * k)
        sh_f = from_neck(sh["far"]) if "far" in sh else (neck[0] - 6 * k * fw, neck[1] + 12 * k)
        lh = meta.get("leg_hips", {})

        def hipj(side):
            if side in lh:
                return (hip[0] + (lh[side][0] - hx) * s * fw * sq, hip[1] + (lh[side][1] - hy) * s)
            return (hip[0] + (4 if side == "near" else -4) * k * fw, hip[1])

        def seg(a, ang, ln, sqf):
            r = math.radians(ang)
            return (a[0] + math.sin(r) * ln * fw * (sqf if abs(ang) < 120 else 1), a[1] + math.cos(r) * ln)
        hn, hf = hipj("near"), hipj("far")
        kn_n = seg(hn, p["thigh_n"], L("thigh_near"), sq)
        ft_n = seg(kn_n, p["shin_n"], L("shin_near"), sq)
        kn_f = seg(hf, p["thigh_f"], L("thigh_far"), sq)
        ft_f = seg(kn_f, p["shin_f"], L("shin_far"), sq)
        el_n = seg(sh_n, p["uarm_n"], L("uarm_near"), squ)
        hd_n = seg(el_n, p["farm_n"], L("farm_near"), squ)
        el_f = seg(sh_f, p["uarm_f"], L("uarm_far"), squ)
        hd_f = seg(el_f, p["farm_f"], L("farm_far"), squ)
        pitch = st.get("head_pitch", 0.0)
        head_ang = math.radians(math.degrees(lean) * 0.6 + pitch * 0.6)
        hh = meta["head_h"] * s
        head = (neck[0] + math.sin(head_ang) * hh * 0.55 * fw, neck[1] - math.cos(head_ang) * hh * 0.55)
        return {"hip": hip, "neck": neck, "sh_n": sh_n, "sh_f": sh_f, "kn_n": kn_n, "ft_n": ft_n, "kn_f": kn_f, "ft_f": ft_f,
                "el_n": el_n, "hd_n": hd_n, "el_f": el_f, "hd_f": hd_f, "head": head, "k": k, "fw": fw, "squash": sq,
                "sq_u": squ, "hip_n": hn, "hip_f": hf, "lean": lean, "head_ang": head_ang, "s": s, **j_extra}

    def foot_floor(self, st):
        j = self.joints(st)
        low = max(j["ft_n"][1], j["ft_f"][1])
        return st["ground_y"] - low - 4 * j["k"]

    # -------------------------------------------------------------- drawing
    def _blit(self, pt, name_or_sprite, P, ang_pose, fw, sqx, s_world, mirror_rest=True):
        spr = name_or_sprite
        cam = pt.cam
        screen_scale = s_world * cam.s
        rgba, (px, py), rest, f = spr.get(fw < 0, screen_scale)
        sc = s_world / f                                     # world px per (shrunk) sprite px
        delta = math.radians(fw * ang_pose - rest) if mirror_rest else math.radians(ang_pose)
        c, s_ = math.cos(delta), math.sin(delta)

        def to_world(qx, qy):
            dx, dy = (qx - px) * sc, (qy - py) * sc
            wx, wy = c * dx + s_ * dy, -s_ * dx + c * dy
            return P[0] + wx * sqx, P[1] + wy
        src = np.float32([[px, py], [px + 10, py], [px, py + 10]])
        dst = np.float32([cam.to_screen(*to_world(*q)) for q in src])
        M = cv2.getAffineTransform(src, dst)
        h, w = rgba.shape[:2]
        corners = np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], np.float32) @ M.T
        x0, y0 = np.floor(corners.min(axis=0)).astype(int)
        x1, y1 = np.ceil(corners.max(axis=0)).astype(int)
        H_, W_ = pt.img.shape[:2]
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W_, x1), min(H_, y1)
        if x1 <= x0 or y1 <= y0:
            return
        M2 = M.copy()
        M2[:, 2] -= (x0, y0)
        warped = cv2.warpAffine(rgba, M2, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        col, a = _premul(warped)
        roi = pt.img[y0:y1, x0:x1].astype(np.float32)
        pt.img[y0:y1, x0:x1] = np.clip(roi * (1 - a) + col * pt.light, 0, 255).astype(np.uint8)

    def draw(self, pt, st):
        st = dict(st)
        if st.get("planted", True):
            st["ground_y"] = st["ground_y"] + self.foot_floor(st)
        st["ground_y"] -= st.get("float", 0.0)
        j = self.joints(st)
        self.last_joints = j
        fw, sq, squ, s = j["fw"], j["squash"], j["sq_u"], j["s"]
        p = self._pose(st["pose"])
        lean_deg = math.degrees(j["lean"])

        def part(name, P, ang, sqx):
            if name in self.parts:
                self._blit(pt, self.parts[name][0], P, ang, fw, sqx, s)
        part("uarm_far", j["sh_f"], p["uarm_f"], squ)     # every part turns by its pose angle about its own joint
        part("farm_far", j["el_f"], p["farm_f"], squ)
        layers = self.meta.get("layers")
        if not layers:                                     # (older cut rigs: the simple order)
            layers = ["uarm_far", "farm_far", "shin_far", "thigh_far", "shin_near", "thigh_near", "torso", "head",
                      "uarm_near", "farm_near"] if self.meta.get("legs_under_torso") else \
                ["uarm_far", "farm_far", "shin_far", "thigh_far", "torso", "shin_near", "thigh_near", "head", "uarm_near", "farm_near"]
        t = st.get("t", 0.0)
        ghost = self.d.get("ghost") or self.meta.get("floats")
        th_avg = (p["thigh_n"] + p["thigh_f"]) / 2.0
        sn_avg = (p["shin_n"] + p["shin_f"]) / 2.0
        flutter = (4.0 * math.sin(t * 1.7) + 2.0 * math.sin(t * 3.1)) if ghost else 0.0
        up_ang = th_avg * 0.7 + flutter * 0.5             # the cloth follows the legs, softly - it never splits
        lo_ang = sn_avg * 0.6 + th_avg * 0.12 + flutter
        no_legs = self.meta.get("no_legs")
        for L_ in layers:
            if L_ in ("shin_far", "thigh_far", "shin_near", "thigh_near"):
                if no_legs:
                    continue
                sd = "n" if L_.endswith("near") else "f"
                base = j["kn_" + sd] if L_.startswith("shin") else j["hip_" + sd]
                part(L_, base, p[("shin_" if L_.startswith("shin") else "thigh_") + sd], sq)
            elif L_ in ("uarm_far", "farm_far", "uarm_near", "farm_near"):
                sd = "n" if L_.endswith("near") else "f"
                base = j["sh_" + sd] if L_.startswith("uarm") else j["el_" + sd]
                part(L_, base, p[("uarm_" if L_.startswith("uarm") else "farm_") + sd], squ)
            elif L_ == "torso":
                part("torso", j["hip"], 180.0 - lean_deg, squ)
            elif L_ == "head":
                self._head(pt, st, j)
            elif L_ == "skirt_up" and "skirt_up" in self.parts:
                w_ = j.get("waist", j["hip"])
                part("skirt_up", w_, up_ang, sq)
            elif L_ == "skirt_lo" and "skirt_lo" in self.parts:
                w_ = j.get("waist", j["hip"])
                ln = self.parts["skirt_up"][1] * s
                r_ = math.radians(up_ang)
                kp = (w_[0] + math.sin(r_) * ln * fw * sq, w_[1] + math.cos(r_) * ln)
                part("skirt_lo", kp, lo_ang, sq)
                if abs(up_ang - lo_ang) > 12:                  # a bent knee (sitting): the cloth stays ONE piece - the
                    spr_ = self.parts["skirt_up"][0].base[0]   # bend is filled with the cloth's own colour, no notch
                    if not hasattr(self, "_skirt_col"):
                        px_ = spr_[..., :3][spr_[..., 3] > 200]
                        self._skirt_col = tuple(int(v) for v in np.median(px_, axis=0)) if len(px_) else (80, 80, 80)
                    wid = np.where(spr_[-max(2, spr_.shape[0] // 10)][..., 3] > 127)[0]
                    rad = (np.ptp(wid) + 1) * s * 0.52 if len(wid) else 30 * j["k"]
                    ink0 = pt.ink
                    pt.ink = None
                    pt.circle(kp, rad, self._skirt_col)
                    pt.ink = ink0
            elif L_ == "pallu" and "pallu" in self.parts and "pallu_anchor" in j:
                part("pallu", j["pallu_anchor"], -lean_deg * 0.4 + 2.5 * math.sin(t * 1.1), 1.0)
            elif L_ == "hair_back" and "hair_back" in self.parts and "hair_anchor" in j:
                part("hair_back", j["hair_anchor"], -math.degrees(j["head_ang"]) * 0.6 + 3.0 * math.sin(t * 1.3 + 0.5), 1.0)
        return j

    def _view(self, st):
        yaw = st.get("head_yaw", st["facing"])
        a = abs(yaw)
        scared = st.get("brows") in ("fear", "surprise") and "scared" in self.heads
        if a < 0.35 and "front" in self.heads:
            v = "front"
        elif a > 0.8 and "profile" in self.heads:
            v = "profile"
        else:
            v = "scared" if scared else ("three_q" if "three_q" in self.heads else next(iter(self.heads), None))
        return v, (1 if yaw >= 0 else -1)

    def _head(self, pt, st, j):
        s = j["s"]
        ang = 180.0 - math.degrees(j["head_ang"])
        v, side = self._view(st) if self.heads else (None, j["fw"])
        if v is None:                                       # no separate head drawings: the body's own head part
            if "head" in self.parts:
                self._blit(pt, self.parts["head"][0], j["neck"], ang, j["fw"], 1.0, s)
            return
        spr, marks, hv_h = self.heads[v]
        s_h = self.meta["head_h"] * s / hv_h * 1.05            # the head drawing scaled to the body's head size
        self._blit(pt, spr, j["neck"], ang, side, 1.0, s_h)
        # blinking + talking ON the drawn face (its own landmarks and skin colour)
        rgba, (px, py), rest, f = spr.get(side < 0, 1.0)
        W = spr.base[0].shape[1]
        delta = math.radians(side * ang - (-180.0 if side < 0 else 180.0))
        c, s_ = math.cos(delta), math.sin(delta)
        npx, npy = spr.base[1]

        def lm(q):
            qx = q[0] if side > 0 else W - 1 - q[0]
            pxx = npx if side > 0 else W - 1 - npx
            dx, dy = (qx - pxx) * s_h, (q[1] - npy) * s_h
            return j["neck"][0] + c * dx + s_ * dy, j["neck"][1] - s_ * dx + c * dy
        skin = tuple(int(v_) for v_ in marks["skin"])
        fwid = marks["face_w"] * s_h
        blink = st.get("blink", 0.0) if not self.d.get("glow_eyes") else 0.0
        ink0 = pt.ink
        pt.ink = None
        if blink > 0.05:
            for e in marks["eyes"]:
                ex, ey = lm(e)
                pt.ellipse((ex, ey - fwid * 0.03 * (1 - blink)), fwid * 0.11, fwid * 0.075 * blink + 0.5, 0, skin)
                pt.line((ex - fwid * 0.1, ey + fwid * 0.03 * blink), (ex + fwid * 0.1, ey + fwid * 0.03 * blink), (30, 26, 30), max(1.0, fwid * 0.018))
        op, shape = st.get("mouth", (0.0, "rest"))
        if op > 0.12:
            mx, my = lm(marks["mouth"])
            w = {"A": 0.13, "E": 0.16, "O": 0.09, "M": 0.12}.get(shape, 0.12) * fwid
            hgt = {"A": 0.11, "E": 0.055, "O": 0.1, "M": 0.0}.get(shape, 0.05) * fwid * op
            pt.ellipse((mx, my), w * 1.25, max(hgt, fwid * 0.03) * 1.2 + fwid * 0.02, 0, skin)     # cover the drawn mouth
            if hgt > 0.8:
                pt.ellipse((mx, my + hgt * 0.15), w, hgt, 0, (40, 30, 70))
                if shape in ("A", "E"):
                    pt.ellipse((mx, my - hgt * 0.5), w * 0.75, max(0.6, hgt * 0.2), 0, (225, 228, 232))
            pt.line((mx - w * 1.05, my - hgt * 0.95), (mx + w * 1.05, my - hgt * 0.95), (60, 50, 90), max(1.0, fwid * 0.015))
        pt.ink = ink0


def load(cid, design, registry_root, key, scale=1.0, log=print):
    """the cut-out character if its assets are ready and complete; None (-> the code rig) otherwise"""
    folder = os.path.join(registry_root, key)
    if not os.path.exists(os.path.join(folder, "rig.json")):
        return None
    try:
        ch = CutoutCharacter(cid, design, folder, scale)
        return ch if ch.complete else None
    except Exception as e:
        log(f"  cut-out '{cid}' could not be loaded ({str(e)[:100]}) - code rig")
        return None
