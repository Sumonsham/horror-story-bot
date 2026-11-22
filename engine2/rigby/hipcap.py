"""THE WAIST ARTIFACT (walk cycle) - its source and its fix.

Source (found 23 Nov 2026): rigprep cut each trouser leg from `legs_top` (598) down. The part between 598 and the
pelvis' lower edge is hidden under the pelvis at rest. In that hidden zone the leg layer still holds whatever the
drawing had there: the pocket fold (a thin grey strip with dark shading, DETACHED from the leg body) and a square
top as wide as the whole trousers. When the leg swings in the walk, the hidden zone rotates out from under the pelvis
and its square corner / the detached strip show as a dark sliver at the front of the waist.

Fix (the rig rule 'hidden regions: only a short own-colour strip'): in the hidden zone each leg becomes a rounded
cap - the leg's own width just below the pelvis, narrowing to a dome towards the top (the shape of a ball joint),
filled with the leg's own trouser colour. Nothing below the pelvis' edge changes, so the visible drawing at rest is
the same; the pocket line stays on the PELVIS layer, where it belongs (a line between a back part and a front part
belongs to the front part).

The same pixels are changed in the layer PNG and in its region of the exported atlas (the mapping is 1:1, checked).
The originals are kept in `<rig>/originals_before_hipcap/` and the fix is idempotent.
"""
import json
import os
import re
import shutil

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _cap(layer, top, cover_y):
    """layer: RGBA full-drawing-size image of one leg. Rows [top, cover_y) are the hidden zone."""
    a = layer[..., 3]
    ref_row = cover_y + 3
    xs = np.where(a[ref_row] > 127)[0]
    if len(xs) < 4:
        raise ValueError("no leg below the pelvis edge")
    xl, xr = int(xs.min()), int(xs.max())
    below = layer[cover_y:cover_y + 60]
    m = below[..., 3] > 200
    lab = cv2.cvtColor(below[..., :3], cv2.COLOR_BGR2LAB)[m]
    bgr = below[..., :3][m]
    own = np.median(bgr[lab[:, 0] > 90], axis=0) if (lab[:, 0] > 90).sum() > 30 else np.median(bgr, axis=0)
    cx, hw = (xl + xr) / 2.0, (xr - xl) / 2.0 - 1.0
    D = float(cover_y - top)
    out = layer.copy()
    out[top:cover_y] = 0
    for y in range(top, cover_y):
        dd = (cover_y - y) / D                                  # 0 at the pelvis edge -> 1 at the top
        w = hw * np.sqrt(max(0.0, 1.0 - dd ** 2))
        x0, x1 = int(round(cx - w)), int(round(cx + w))
        if x1 > x0:
            out[y, x0:x1 + 1, :3] = own.astype(np.uint8)
            out[y, x0:x1 + 1, 3] = 255
    return out, {"xl": xl, "xr": xr, "own_bgr": [int(v) for v in own], "rows": [int(top), int(cover_y)]}


def apply(cid="hari", log=print):
    rdir = os.path.join(ROOT, "assets", "character_rigs", cid)
    cfg = json.load(open(os.path.join(rdir, "prep.json")))
    info = json.load(open(os.path.join(rdir, "layers.json")))
    pants = cfg["pants"]
    top = int(pants["legs_top"])
    cover_y = int(pants["pelvis_bottom"]) - int(pants.get("pelvis_feather", 0))   # fully covered above this row
    bk = os.path.join(rdir, "originals_before_hipcap")
    atlas_p = os.path.join(rdir, "export", f"{cid}.png")
    atlas_txt = open(os.path.join(rdir, "export", f"{cid}.atlas"), encoding="utf-8").read()
    marker = os.path.join(rdir, "hipcap.json")
    if os.path.exists(marker):
        log("  hipcap: already applied")
        return json.load(open(marker))
    os.makedirs(bk, exist_ok=True)
    shutil.copy(atlas_p, os.path.join(bk, os.path.basename(atlas_p)))
    atlas = cv2.imread(atlas_p, cv2.IMREAD_UNCHANGED)
    rep = {"why": "the hidden top of each trouser leg showed as a dark sliver at the waist in the walk", "legs": {}}
    for nm in ("leg_r", "leg_l"):
        lp = os.path.join(rdir, info["layers"][nm]["file"])
        shutil.copy(lp, os.path.join(bk, nm + ".png"))
        layer = cv2.imread(lp, cv2.IMREAD_UNCHANGED)
        fixed, meta = _cap(layer, top, cover_y)
        cv2.imwrite(lp, fixed)
        m = re.search(nm + r"\nbounds: (\d+), (\d+), (\d+), (\d+)", atlas_txt)
        ax, ay, aw, ah = map(int, m.groups())
        x0, y0 = info["layers"][nm]["bbox"][:2]
        reg = fixed[y0:y0 + ah, x0:x0 + aw]
        if reg.shape[:2] != (ah, aw):
            raise ValueError(f"{nm}: atlas region does not match the layer")
        atlas[ay:ay + ah, ax:ax + aw] = reg
        meta["changed_pixels"] = int((np.abs(fixed.astype(int) - layer.astype(int)).sum(axis=2) > 0).sum())
        rep["legs"][nm] = meta
    cv2.imwrite(atlas_p, atlas)
    with open(marker, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    log(f"  hipcap applied: {rep['legs']}")
    return rep


if __name__ == "__main__":
    print(json.dumps(apply(), indent=1))
