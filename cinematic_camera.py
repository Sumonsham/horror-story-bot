"""CINEMATIC CAMERA - world (1920x1080 stage) -> screen, with shots that follow the story.

Shots: wide (establishing), two_shot, medium, ots (over the shoulder), close_up, extreme_close_up, reaction,
follow (tracking a walking character), reveal (pan from one place to another), push_in, pull_out, tilt,
plus a dutch angle and a controlled shake as options of any shot. Between shots: a cut (default) or an eased move.
Works for 16:9 and 9:16 outputs (the same world, a different window).
"""
import math

WORLD_W, WORLD_H = 1920, 1080


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


class Camera:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.base = max(W / WORLD_W, H / WORLD_H)
        self.set(WORLD_W / 2, WORLD_H / 2, 1.0)

    def set(self, cx, cy, z, rot=0.0, shake=(0.0, 0.0)):
        self.cx, self.cy, self.z, self.rot, self.shake = cx, cy, z, rot, shake
        self.s = z * self.base
        # keep the window inside the stage (no empty borders)
        hw, hh = self.W / (2 * self.s), self.H / (2 * self.s)
        self.cx = min(max(self.cx, hw), WORLD_W - hw)
        self.cy = min(max(self.cy, hh), WORLD_H - hh)
        r = math.radians(rot)
        self.cr, self.sr = math.cos(r), math.sin(r)

    def to_screen(self, x, y):
        dx, dy = (x - self.cx) * self.s, (y - self.cy) * self.s
        return (dx * self.cr - dy * self.sr + self.W / 2 + self.shake[0],
                dx * self.sr + dy * self.cr + self.H / 2 + self.shake[1])

    def matrix(self, parallax=1.0):
        """2x3 affine for a raster layer in world pixels; parallax < 1 = farther (moves and zooms less)"""
        import numpy as np
        z = 1 + (self.z - 1) * parallax
        s = z * self.base
        cx = WORLD_W / 2 + (self.cx - WORLD_W / 2) * parallax
        cy = WORLD_H / 2 + (self.cy - WORLD_H / 2) * parallax
        hw, hh = self.W / (2 * s), self.H / (2 * s)
        cx, cy = min(max(cx, hw), WORLD_W - hw), min(max(cy, hh), WORLD_H - hh)
        a, b = s * self.cr, -s * self.sr
        c, d = s * self.sr, s * self.cr
        tx = self.W / 2 + self.shake[0] - (a * cx + b * cy)
        ty = self.H / 2 + self.shake[1] - (c * cx + d * cy)
        return np.float32([[a, b, tx], [c, d, ty]])


def frame_for(shot, world, t):
    """(cx, cy, z, rot) of a shot at time t. world: callables giving live positions (heads, feet, points)."""
    typ = shot["type"]
    u = ease((t - shot["t0"]) / max(0.01, shot["t1"] - shot["t0"]))
    rot = shot.get("dutch", 0.0) * u if shot.get("dutch_grow") else shot.get("dutch", 0.0)
    head = world["head"]
    if typ == "wide":
        z = shot.get("z0", 1.0) + (shot.get("z1", 1.0) - shot.get("z0", 1.0)) * u
        return shot.get("cx", WORLD_W / 2), shot.get("cy", WORLD_H / 2), z, rot
    if typ in ("two_shot", "medium"):
        a, b = head(shot["a"]), head(shot["b"]) if shot.get("b") else head(shot["a"])
        z = shot.get("z", 1.9) * (1 + shot.get("push", 0.0) * u)
        return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 95, z, rot
    if typ == "ots":                                       # over the listener's shoulder onto the speaker
        sp, ls = head(shot["speaker"]), head(shot["listener"])
        z = shot.get("z", 3.0) * (1 + shot.get("push", 0.04) * u)
        return sp[0] + (ls[0] - sp[0]) * 0.47, sp[1] + 46, z, rot
    if typ in ("close_up", "reaction", "extreme_close_up"):
        h = head(shot["who"])
        z = {"close_up": 3.3, "reaction": 3.6, "extreme_close_up": 5.2}[typ] * (1 + shot.get("push", 0.06) * u)
        return h[0] + shot.get("dx", 0.0), h[1] + (8 if typ == "extreme_close_up" else 26), z, rot
    if typ == "follow":
        f = world["feet"](shot["who"])
        z = shot.get("z", 1.8)
        lead = shot.get("lead", 0.0)
        return f[0] + lead, f[1] - 170, z, rot
    if typ == "reveal":
        p0 = world["point"](shot["from"]) if isinstance(shot["from"], str) else shot["from"]
        p1 = world["point"](shot["to"]) if isinstance(shot["to"], str) else shot["to"]
        z = shot.get("z0", 2.4) + (shot.get("z1", 2.4) - shot.get("z0", 2.4)) * u
        return p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u, z, rot
    if typ in ("push_in", "pull_out", "tilt"):
        z0, z1 = shot.get("z0", 1.0), shot.get("z1", 1.6)
        return (shot.get("cx", WORLD_W / 2), shot.get("cy0", WORLD_H / 2) + (shot.get("cy1", WORLD_H / 2) - shot.get("cy0", WORLD_H / 2)) * u,
                z0 + (z1 - z0) * u, rot)
    return WORLD_W / 2, WORLD_H / 2, 1.0, rot


def shake_at(shot, t):
    a = shot.get("shake", 0.0)
    if not a:
        return (0.0, 0.0)
    return (a * (math.sin(t * 13.1) * 0.6 + math.sin(t * 29.7) * 0.4), a * 0.6 * (math.sin(t * 17.3) * 0.7 + math.sin(t * 7.9) * 0.3))
