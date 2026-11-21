"""ENVIRONMENT ANIMATION - a living night: sky, moon, moving clouds, twinkling stars, a far tree line, trees whose
trunk, every branch and every leaf cluster move separately with the wind, swaying grass, a pond whose water ripples
and whose moon reflection shimmers, circular ripples, ground mist and moving fog, fireflies, blowing leaves, a
lantern / candle flame that flickers and lights its surroundings, rain and lightning when the scene asks for them.

Raster layers (sky, far land, near land + pond) are made once and moved by the camera with different parallax;
the pond is re-made every frame (real ripples, not a still picture); trees, grass and particles are vector shapes
drawn every frame through the camera. Everything is procedural: Python + NumPy + OpenCV, zero cost.
"""
import math

import cv2
import numpy as np

from cinematic_camera import WORLD_H, WORLD_W
from cartoon_rig import Painter, _shade

HORIZON = 545


def wind_at(t, storm=0.0):
    """wind strength 0..~2 with gusts"""
    return (0.55 + 0.35 * math.sin(t * 0.23) + 0.18 * math.sin(t * 1.13 + 1.0) + 0.1 * math.sin(t * 2.7)) * (1 + 1.6 * storm)


def _noise(rng, h, w, cells, blur):
    n = cv2.resize(rng.uniform(0, 1, cells).astype("float32"), (w, h), interpolation=cv2.INTER_CUBIC)
    n = cv2.GaussianBlur(n, (0, 0), blur)
    return (n - n.min()) / (n.max() - n.min() + 1e-6)


class Environment:
    def __init__(self, spec, seed=7):
        self.spec = spec
        self.rng = np.random.default_rng(seed)
        self.moon = spec.get("moon", (1430, 175))
        self.pond = spec.get("pond")                       # (cx, cy, rx, ry) or None
        self.loc = spec.get("location", "pond")            # V1.1: the place (location_library.py)
        self.lightning = spec.get("lightning", [])
        self._build_rasters()
        self.trees = [Tree(t["x"], t["y"], t["h"], t.get("seed", i * 13 + 5), t.get("depth", 5), t.get("scale", 1.0),
                           t.get("bare", False)) for i, t in enumerate(spec.get("trees", []))]
        self.grass = [(float(self.rng.uniform(0, WORLD_W)), float(self.rng.uniform(spec.get("grass_y", 1000), WORLD_H + 20)),
                       float(self.rng.uniform(18, 46)), float(self.rng.uniform(0, 6.28))) for _ in range(spec.get("grass", 420))]
        self.bank_grass = [(float(self.rng.uniform(0, WORLD_W)), float(self.rng.uniform(HORIZON + 50, 980)),
                            float(self.rng.uniform(8, 20)), float(self.rng.uniform(0, 6.28))) for _ in range(spec.get("bank_grass", 260))]
        if self.pond:
            cx, cy, rx, ry = self.pond
            self.bank_grass = [g for g in self.bank_grass if ((g[0] - cx) / rx) ** 2 + ((g[1] - cy) / ry) ** 2 > 1.15]
        import location_library
        self.grass = [g for g in self.grass if location_library.grass_ok(self.loc, g[0], g[1])]
        self.bank_grass = [g for g in self.bank_grass if location_library.grass_ok(self.loc, g[0], g[1])]
        self.flies = [(float(self.rng.uniform(300, 1700)), float(self.rng.uniform(560, 950)), float(self.rng.uniform(0, 6.28)))
                      for _ in range(spec.get("fireflies", 18))]
        self.leaves = [(float(self.rng.uniform(-200, WORLD_W)), float(self.rng.uniform(150, 900)), float(self.rng.uniform(0, 6.28)))
                       for _ in range(spec.get("falling_leaves", 10))]
        self.fog = _noise(self.rng, 300, WORLD_W * 2, (6, 26), 22)
        self.mist = _noise(self.rng, 220, WORLD_W * 2, (5, 30), 18)
        for arr in (self.fog, self.mist):                  # soft top and bottom edges (no hard band)
            prof = np.sin(np.linspace(0, math.pi, arr.shape[0])) ** 2
            arr *= prof[:, None].astype("float32")
        cl = np.zeros((160, 520), "float32")              # one soft cloud, made once
        cv2.ellipse(cl, (260, 80), (210, 46), 0, 0, 360, 1.0, -1)
        cv2.ellipse(cl, (190, 70), (110, 40), 0, 0, 360, 1.0, -1)
        cv2.ellipse(cl, (330, 66), (120, 44), 0, 0, 360, 1.0, -1)
        self.cloud = cv2.GaussianBlur(cl, (0, 0), 18) * 0.6
        self.ripples = spec.get("ripples", [])            # [(t, x, y)] - a stone / fish: circular ripples
        self.rain = spec.get("rain", 0.0)
        self.lightning = spec.get("lightning", [])

    # ------------------------------------------------------------------ rasters made once
    def _build_rasters(self):
        W, H = WORLD_W, WORLD_H
        rng = self.rng
        y = np.linspace(0, 1, H)[:, None, None]
        sky = (np.array([46, 22, 12], "float32") * (1 - y) + np.array([92, 58, 36], "float32") * y) * np.ones((1, W, 1), "float32")
        mx, my = self.moon
        yy, xx = np.mgrid[0:H, 0:W].astype("float32")
        d = np.sqrt((xx - mx) ** 2 + (yy - my) ** 2)
        sky += (np.exp(-d / 260.0) * 70)[..., None] * np.array([0.95, 0.95, 0.85], "float32")
        sky = np.clip(sky, 0, 255).astype(np.uint8)
        cv2.circle(sky, (mx, my), 46, (210, 236, 242), -1, cv2.LINE_AA)
        cv2.circle(sky, (mx + 10, my - 8), 9, (190, 214, 222), -1, cv2.LINE_AA)
        cv2.circle(sky, (mx - 14, my + 12), 6, (192, 216, 224), -1, cv2.LINE_AA)
        self.stars = [(int(rng.uniform(0, W)), int(rng.uniform(0, HORIZON - 40)), float(rng.uniform(0, 6.28))) for _ in range(140)]
        self.sky = sky
        far = np.zeros((H, W, 4), np.uint8)
        pts = [(0, HORIZON + 20)]
        x = 0
        while x < W + 40:
            pts.append((x, HORIZON - int(rng.uniform(25, 95)) + int(18 * math.sin(x / 140.0))))
            x += int(rng.uniform(14, 34))
        pts += [(W, HORIZON + 40), (0, HORIZON + 40)]
        cv2.fillPoly(far, [np.array(pts, np.int32)], (34, 30, 22, 255), cv2.LINE_AA)
        cv2.rectangle(far, (0, HORIZON + 30), (W, HORIZON + 60), (30, 34, 28, 255), -1)
        self.far = far
        land = np.zeros((H, W, 4), np.uint8)
        g = np.linspace(0, 1, H - HORIZON)[:, None, None]
        ground = (np.array([30, 40, 34], "float32") * (1 - g) + np.array([22, 32, 30], "float32") * g) * np.ones((1, W, 1), "float32")
        ground += (rng.standard_normal(ground.shape[:2]) * 3.0)[..., None]
        land[HORIZON + 40:, :, :3] = np.clip(ground[40:], 0, 255).astype(np.uint8)
        land[HORIZON + 40:, :, 3] = 255
        for a in (HORIZON + 40,):
            land[a:a + 12, :, 3] = np.linspace(0, 255, 12).astype(np.uint8)[:, None]
        self.land = land
        import location_library                            # V1.1: the place paints itself onto the base layers
        location_library.paint(self)
        sky, far = self.sky, self.far
        if self.pond:                                      # what the water reflects: the sky and the far trees, upside down
            cx, cy, rx, ry = self.pond
            top = int(cy - ry)
            comp = sky.astype("float32")
            a = far[..., 3:4] / 255.0
            comp = comp * (1 - a) + far[..., :3] * a
            band = comp[max(0, top - 2 * ry):top][::-1]
            self.reflect = cv2.resize(band, (W, 2 * ry), interpolation=cv2.INTER_LINEAR)
            m = np.zeros((H, W), "float32")
            cv2.ellipse(m, (cx, cy), (rx, ry), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
            self.pond_mask = cv2.GaussianBlur(m, (0, 0), 3)[top:top + 2 * ry, :, None]

    # ------------------------------------------------------------------ the pond, every frame
    def pond_frame(self, t, wind):
        cx, cy, rx, ry = self.pond
        H2 = 2 * ry
        yy, xx = np.mgrid[0:H2, 0:WORLD_W].astype("float32")
        depth = yy / H2                                    # 0 far edge .. 1 near edge
        amp = (1.5 + 3.5 * depth) * (0.6 + 0.5 * wind)
        dx = amp * np.sin(yy * 0.35 - t * 2.3 + np.sin(xx * 0.01 + t * 0.4) * 2.0)
        dy = 0.8 * amp * np.sin(xx * 0.045 + t * 1.7)
        for (tr, px, py) in self.ripples:                  # circular ripples from a point
            age = t - tr
            if 0 <= age < 4.0:
                r = np.sqrt(((xx - px) / 1.0) ** 2 + ((yy - (py - cy + ry)) * (rx / ry)) ** 2)
                w = np.exp(-((r - age * 85) ** 2) / 260.0) * (1 - age / 4.0)
                dy += 6.0 * w * np.sin(r * 0.25)
        water = cv2.remap(self.reflect, xx + dx, yy + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        water = water * (0.45 + 0.2 * (1 - depth[..., None])) + np.array([40, 22, 10], "float32") * 0.5
        mx = self.moon[0]                                  # the moon's broken, shimmering path on the water
        rng = np.random.default_rng(int(t * 8) + 3)
        for k in range(26):
            yk = int(H2 * (k / 26.0) ** 0.9)
            wk = int(6 + 34 * (k / 26.0) * (0.6 + 0.4 * math.sin(t * 3 + k)))
            xk = int(mx + 18 * math.sin(t * 1.3 + k * 0.7) + rng.uniform(-6, 6))
            if rng.uniform() < 0.82:
                cv2.ellipse(water, (xk, yk), (wk, 2), 0, 0, 360, (205, 228, 236), -1, cv2.LINE_AA)
        for (tr, px, py) in self.ripples:                  # the ring lines themselves
            age = t - tr
            if 0 <= age < 4.0:
                for kk in range(3):
                    rr = age * 85 - kk * 26
                    if rr > 4:
                        cv2.ellipse(water, (int(px), int(py - cy + ry)), (int(rr), int(rr * ry / rx)), 0, 0, 360,
                                    (150, 160, 160), 1, cv2.LINE_AA)
        return water, int(cy - ry)

    # ------------------------------------------------------------------ compositing the raster layers
    def background(self, cam, t, wind, out):
        W, H = cam.W, cam.H
        sky = self.sky.copy()
        for (sx, sy, ph) in self.stars:                    # twinkling
            b = 150 + 100 * (0.5 + 0.5 * math.sin(t * 2.2 + ph))
            sky[sy, sx] = (b, b, b)
        frame = cv2.warpAffine(sky, cam.matrix(self.spec.get("sky_parallax", 0.2)), (W, H),
                               borderMode=cv2.BORDER_REFLECT).astype("float32")   # a room wall moves with the floor
        clouds = self.spec.get("clouds", 3)
        for k in range(clouds):                            # slow clouds crossing the sky (and the moon)
            x = (k * 700 + t * (10 + 4 * k)) % (WORLD_W + 900) - 450
            yk = 120 + 90 * k
            M = cam.matrix(0.2)
            sx, sy = M[0, 0] * x + M[0, 1] * yk + M[0, 2], M[1, 0] * x + M[1, 1] * yk + M[1, 2]
            sc = M[0, 0] * (1.0 + 0.15 * k)
            cw, chh = max(4, int(520 * sc)), max(4, int(160 * sc))
            m = cv2.resize(self.cloud, (cw, chh))
            self._blend(frame, m, int(sx - cw / 2), int(sy - chh / 2), np.array([70, 58, 52], "float32"), 1.0)
        far = cv2.warpAffine(self.far, cam.matrix(0.5), (W, H))
        a = far[..., 3:4].astype("float32") / 255.0
        frame = frame * (1 - a) + far[..., :3] * a
        land = self.land.copy()
        if self.pond:
            water, top = self.pond_frame(t, wind)
            region = land[top:top + water.shape[0]]
            mk = self.pond_mask
            region[..., :3] = (region[..., :3] * (1 - mk) + water * mk).astype(np.uint8)
            region[..., 3] = np.maximum(region[..., 3], (mk[..., 0] * 255).astype(np.uint8))
        lw = cv2.warpAffine(land, cam.matrix(1.0), (W, H))
        a = lw[..., 3:4].astype("float32") / 255.0
        frame = frame * (1 - a) + lw[..., :3] * a
        if cam.z > 2.0:                                    # a close-up: the far background goes soft (depth of field)
            frame = cv2.GaussianBlur(frame, (0, 0), min(6.0, (cam.z - 2.0) * 2.2))
        return frame

    # ------------------------------------------------------------------ vector layers
    def draw_location(self, pt, t, wind, state=None):
        """the place's own moving things (street lamp, door, window rain, pyre fire, bulb, bats...); light points"""
        import location_library
        return location_library.draw(self, pt, t, wind, state or {})

    def draw_trees(self, pt, t, wind, which=None):
        for i, tr in enumerate(self.trees):
            if which is None or i in which:
                tr.draw(pt, t, wind)

    def draw_bank_grass(self, pt, t, wind):
        for (x, y, h, ph) in self.bank_grass:
            sw = (3 + 5 * wind) * math.sin(t * 1.9 + ph + x * 0.01)
            pt.line((x, y), (x + sw, y - h), (40, 62, 46), 1.6)

    def draw_foreground(self, pt, t, wind):
        for (x, y, h, ph) in self.grass:
            sw = (6 + 12 * wind) * math.sin(t * 2.1 + ph + x * 0.006)
            pt.line((x, y), (x + sw * 0.5, y - h * 0.5), (18, 34, 24), 3.2)
            pt.line((x + sw * 0.5, y - h * 0.5), (x + sw, y - h), (20, 40, 28), 2.0)

    def draw_lantern(self, pt, x, y, t):
        """a hurricane lantern; returns the flicker (0.75..1.1) for the light it throws"""
        fl = 0.92 + 0.08 * math.sin(t * 23) * math.sin(t * 7.1) + 0.05 * math.sin(t * 41)
        pt.poly([(x - 16, y), (x + 16, y), (x + 13, y - 10), (x - 13, y - 10)], (30, 34, 40))
        pt.ellipse((x, y - 32), 15, 22, 0, (120, 170, 210))
        flame_h = 13 * fl + 2 * math.sin(t * 31)
        pt.ellipse((x + math.sin(t * 9) * 1.5, y - 30), 5, flame_h, 0, (90, 200, 255))
        pt.ellipse((x, y - 28), 2.5, flame_h * 0.5, 0, (220, 250, 255))
        pt.line((x - 18, y - 56), (x + 18, y - 56), (30, 34, 40), 3)
        pt.line((x - 14, y - 10), (x - 14, y - 54), (40, 44, 52), 2.5)
        pt.line((x + 14, y - 10), (x + 14, y - 54), (40, 44, 52), 2.5)
        return fl

    def particles(self, pt, t, wind):
        for (x, y, ph) in self.flies:                     # fireflies
            px = x + 40 * math.sin(t * 0.5 + ph) + 20 * math.sin(t * 1.3 + ph * 2)
            py = y + 25 * math.sin(t * 0.7 + ph * 1.5)
            on = 0.5 + 0.5 * math.sin(t * 2.5 + ph * 3)
            if on > 0.35:
                pt.circle((px, py), 3.2, (int(120 * on), int(255 * on), int(220 * on)))
        for (x, y, ph) in self.leaves:                    # leaves blowing across
            px = (x + t * (60 + 80 * wind)) % (WORLD_W + 300) - 150
            py = y + (t * 35) % 500 + 30 * math.sin(t * 2 + ph)
            pt.ellipse((px, py), 7, 3, math.degrees(t * 3 + ph), (30, 70, 90))

    def atmosphere(self, frame, cam, t, wind, light_points):
        """fog, ground mist over the water, the lantern's light, moonlight grade - in screen space"""
        H, W = frame.shape[:2]
        off = int((t * 14 * (0.5 + wind)) % WORLD_W)
        fog = self.fog[:, off:off + WORLD_W]
        x0, y0 = cam.to_screen(0, 380)
        x1, y1 = cam.to_screen(WORLD_W, 680)
        fogk = 0.42 * self.spec.get("fog", 1.0)
        if y1 > 0 and y0 < H and fogk > 0:
            f_ = cv2.resize(fog, (max(2, int(x1 - x0)), max(2, int(y1 - y0))))
            self._blend(frame, f_, int(x0), int(y0), np.array([62, 58, 52], "float32"), min(0.8, fogk))
        if self.pond:
            cx, cy, rx, ry = self.pond
            off2 = int((t * 22) % WORLD_W)
            mist = self.mist[:, off2:off2 + WORLD_W]
            x0, y0 = cam.to_screen(0, cy - ry - 40)
            x1, y1 = cam.to_screen(WORLD_W, cy + ry * 0.4)
            if y1 > 0 and y0 < H:
                m_ = cv2.resize(mist, (max(2, int(x1 - x0)), max(2, int(y1 - y0))))
                self._blend(frame, m_, int(x0), int(y0), np.array([84, 80, 74], "float32"), 0.5)
        for (lx, ly, rad, col, k) in light_points:         # warm light pools (lantern, candle, torch)
            sx, sy = cam.to_screen(lx, ly)
            r = rad * cam.s
            x0, y0, x1, y1 = int(max(0, sx - r)), int(max(0, sy - r)), int(min(W, sx + r)), int(min(H, sy + r))
            if x1 > x0 and y1 > y0:
                yy, xx = np.mgrid[y0:y1, x0:x1].astype("float32")
                g = np.clip(1 - np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2) / r, 0, 1) ** 2 * k
                frame[y0:y1, x0:x1] += g[..., None] * np.array(col, "float32")
        import location_library
        frame = location_library.atmosphere(self, frame, cam, t, wind)
        lk = self.spec.get("lightning_k", 0.65)
        for lt in self.lightning:
            d = t - lt
            if 0 <= d < 0.08 or 0.16 <= d < 0.22:
                frame[:] = frame * (1 - lk) + np.array([255, 245, 235], "float32") * lk
        if self.rain:
            rng = np.random.default_rng(int(t * 30))
            for _ in range(int(380 * self.rain)):
                x, y = rng.uniform(0, W), rng.uniform(0, H)
                cv2.line(frame, (int(x), int(y)), (int(x - 4), int(y + 22)), (150, 150, 150), 1, cv2.LINE_AA)
        return frame

    @staticmethod
    def _blend(frame, m, x0, y0, col, k):
        H, W = frame.shape[:2]
        h, w = m.shape
        fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
        if fx1 <= fx0 or fy1 <= fy0:
            return
        sub = m[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0][..., None] * k
        frame[fy0:fy1, fx0:fx1] = frame[fy0:fy1, fx0:fx1] * (1 - sub) + col * sub


class Tree:
    """a tree with a real hierarchy: trunk -> branches -> twigs -> leaf clusters; each part sways on its own"""

    def __init__(self, x, y, h, seed=1, depth=5, scale=1.0, bare=False):
        rng = np.random.default_rng(seed)
        self.bare = bare                                  # a dead, leafless tree (cremation ground, ruins)
        self.x, self.y = x, y
        self.parts = []                                   # (parent, rel_angle, length, width, depth, phase)
        self.leaves = []                                  # (part, dx, dy, r, phase, shade)

        def grow(parent, ang, ln, wd, dp):
            idx = len(self.parts)
            self.parts.append((parent, ang, ln, wd, dp, float(rng.uniform(0, 6.28))))
            if dp >= depth or ln < 22:
                for _ in range(int(rng.integers(2, 5))):
                    self.leaves.append((idx, float(rng.uniform(-30, 30)), float(rng.uniform(-30, 20)),
                                        float(rng.uniform(22, 40)) * scale, float(rng.uniform(0, 6.28)), float(rng.uniform(0.8, 1.15))))
                return
            n = int(rng.integers(2, 4))
            for k in range(n):
                a = (k - (n - 1) / 2) * float(rng.uniform(22, 38)) + float(rng.uniform(-10, 10))
                grow(idx, a, ln * float(rng.uniform(0.62, 0.78)), wd * 0.62, dp + 1)

        grow(-1, float(rng.uniform(-4, 4)), h * 0.36, 34 * scale, 0)

    def draw(self, pt, t, wind):
        pos, angs = [], []
        for (parent, rel, ln, wd, dp, ph) in self.parts:
            sway = wind * (0.6 + dp * dp * 0.55) * math.sin(t * (1.1 + dp * 0.35) + ph) + wind * dp * 1.4
            if parent < 0:
                base, ang = (self.x, self.y), rel + sway * 0.3
            else:
                base, ang = pos[parent][1], angs[parent] + rel + sway
            r = math.radians(ang)
            end = (base[0] + math.sin(r) * ln, base[1] - math.cos(r) * ln)
            pos.append((base, end))
            angs.append(ang)
            pt.line(base, end, (24, 30, 38) if dp < 2 else (28, 36, 42), max(1.5, wd))
        for (pi, dx, dy, r, ph, sh) in ([] if self.bare else self.leaves):      # leaf clusters flutter on their own
            ex, ey = pos[pi][1]
            fl = (2.0 + 4.0 * wind) * math.sin(t * 3.2 + ph)
            pt.ellipse((ex + dx + fl, ey + dy + fl * 0.4), r, r * 0.72, ph * 30, _shade((34, 58, 30), sh))
            pt.ellipse((ex + dx + fl + r * 0.25, ey + dy + fl * 0.4 - r * 0.2), r * 0.55, r * 0.38, ph * 30, _shade((60, 92, 64), sh))
