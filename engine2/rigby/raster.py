"""Draws a posed Rigby2D skeleton with OpenCV - the software rasteriser for the vendored pure-Python Rigby2D runtime
(runtime/rigby2d, MIT OR Apache-2.0, frame-for-frame equal to the Rigby2D editor's own runtime).

The runtime gives, per slot in draw order, textured triangles (world position + atlas UV). Each triangle is mapped
from the atlas page with its own affine warp; a slot is assembled in its own buffer first (so the triangles of one
bending mesh never show seams), then composited over the frame. Rendering happens at 2x and is reduced (smooth
edges, no jaggies), entirely on the CPU - it runs on GitHub Actions without a GPU or a browser.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime"))
from rigby2d import Atlas, Pose, RegionLookup, RenderOutput, load_skeleton  # noqa: E402
from rigby2d import model as M  # noqa: E402


class Rig:
    def __init__(self, json_path):
        base = os.path.splitext(json_path)[0]
        self.sk = load_skeleton(open(json_path, "rb").read())
        self.atlas = Atlas.parse(open(base + ".atlas", encoding="utf-8").read())
        self.lookup = RegionLookup(self.sk, self.atlas)
        self.pages = {}
        self.page_list = []
        for pg in self.atlas.pages:
            img = cv2.imread(os.path.join(os.path.dirname(json_path), pg.name), cv2.IMREAD_UNCHANGED)
            if img.shape[2] == 3:
                img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
            f = img.astype(np.float32) / 255.0
            if not pg.pma:
                f[..., :3] *= f[..., 3:4]                   # premultiplied: clean edges when warped
            self.pages[pg.name] = f
            self.page_list.append(f)
        self.anims = {a.name: i for i, a in enumerate(self.sk.animations)}
        self.durations = {a.name: a.duration for a in self.sk.animations}

    def pose(self, anim=None, t=0.0, extra=None, loop=True):
        p = Pose(self.sk)
        p.set_to_setup()
        if anim:
            d = self.durations[anim]
            p.apply(self.anims[anim], t % d if (d > 0 and loop) else min(t, d), 1.0)
        for item in (extra or []):                         # [(animation, time, alpha)] layered on top (e.g. mouth)
            p.apply(self.anims[item[0]], item[1], item[2])
        p.update_world()
        return p


def _tri(dst, src_img, s, d):
    """warps one triangle s (page px) -> d (frame px) into dst (premultiplied RGBA float), overwriting"""
    x, y, w, h = cv2.boundingRect(np.float32(d))
    H, W = dst.shape[:2]
    if w <= 0 or h <= 0 or x >= W or y >= H or x + w <= 0 or y + h <= 0:
        return
    sx, sy, sw, sh = cv2.boundingRect(np.float32(s))
    sx0, sy0 = max(0, sx - 2), max(0, sy - 2)
    sx1, sy1 = min(src_img.shape[1], sx + sw + 2), min(src_img.shape[0], sy + sh + 2)
    patch = src_img[sy0:sy1, sx0:sx1]
    if patch.size == 0:
        return
    s2 = (np.float32(s) - np.float32([sx0, sy0])).astype(np.float32)
    d2 = (np.float32(d) - np.float32([x, y])).astype(np.float32)
    if abs(cv2.contourArea(s2)) < 1e-3 or abs(cv2.contourArea(d2)) < 1e-3:
        return
    Maff = cv2.getAffineTransform(s2, d2)
    warped = cv2.warpAffine(patch, Maff, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(mask, np.int32(np.round(d2 * 4)), 1, lineType=cv2.LINE_8, shift=2)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))       # neighbouring triangles overlap by a pixel: no seam
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    m = mask[y0 - y:y1 - y, x0 - x:x1 - x].astype(bool)
    wv = warped[y0 - y:y1 - y, x0 - x:x1 - x]
    reg = dst[y0:y1, x0:x1]
    keep = m & (wv[..., 3] >= reg[..., 3] - 1e-4)           # inside one slot: the more opaque sample wins (folds)
    reg[keep] = wv[keep]


def draw(rig, pose, frame, scale, ox, oy, ss=2, only=None, alpha=1.0):
    """composites the posed character onto frame (BGR uint8) - rig units (Y up) -> frame px: (x*scale+ox, oy-y*scale)"""
    H, W = frame.shape[:2]
    big = np.zeros((H * ss, W * ss, 4), np.float32)
    sk = pose.sk
    for i in pose.draw_order:
        if only is not None and sk.slots[i].name not in only:
            continue
        att = pose.slot_attachment(i)
        if att is None or att.kind not in (M.REGION, M.MESH, M.LINKED_MESH):
            continue
        ro = RenderOutput()
        ro._transform = (scale * ss, ox * ss, -scale * ss, oy * ss)
        ro._draw_attachment(sk, pose, i, att, rig.lookup, (1.0, 1.0, 1.0, 1.0), None)
        for b in ro.batches:
            page = rig.page_list[b.page]
            pw, ph = page.shape[1], page.shape[0]
            pts = np.float32(b.points).reshape(-1, 2)
            at = np.float32(b.attributes).reshape(-1, 10)
            uv = at[:, :2] * [pw, ph]
            col = at[0, 2:6]
            idx = np.int32(b.indices).reshape(-1, 3)
            bb = cv2.boundingRect(pts)
            x0, y0 = max(0, bb[0] - 2), max(0, bb[1] - 2)
            x1, y1 = min(W * ss, bb[0] + bb[2] + 3), min(H * ss, bb[1] + bb[3] + 3)
            if x1 <= x0 or y1 <= y0:
                continue
            buf = np.zeros((y1 - y0, x1 - x0, 4), np.float32)
            off = np.float32([x0, y0])
            for tri in idx:
                _tri(buf, page, uv[tri], pts[tri] - off)
            buf *= np.float32([col[2], col[1], col[0], col[3]])   # slot tint (BGR)
            reg = big[y0:y1, x0:x1]
            a = buf[..., 3:4]
            reg[...] = buf + reg * (1.0 - a)                 # premultiplied "over"
    small = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA) if ss != 1 else big
    a = np.clip(small[..., 3:4] * alpha, 0, 1)
    rgb = small[..., :3] * alpha
    out = frame.astype(np.float32) / 255.0 * (1 - a) + rgb
    frame[...] = np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return small[..., 3]
