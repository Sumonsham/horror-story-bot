"""ART TEST (GitHub: mode = art_test) - the 2.5D cut-out system on REAL AI pictures, before it is ever switched on.

1. For every test character ONE full-body A-pose reference picture is made on Cloudflare (the bot's own free
   account; never another provider) - or the existing one is REUSED if it is still good (no credit spent).
2. The puppet is cut from that picture (puppet_builder) and must pass the MANDATORY ASSEMBLED CHECK (assembly_qa):
   drawn in 7 poses - standing front, three-quarter, side, seated with both legs, talking, pointing, walking - and
   measured (whole body, one connected figure, solid joints, nothing cut off, human proportions, no duplicated
   person). Only a pass is "ready". A fail keeps its pose pictures + the exact reasons, and the reference is drawn
   again (limited per run; the free limit PAUSES the work and the next run continues).
3. art_poses.jpg = the 7-pose check of EVERY character (green = passed, red = failed, with the reason);
   art_sheet.jpg = each reference picture next to its puppet's parts.
4. A short sample video made ONLY with characters that passed. A scene whose characters did not pass is NOT
   drawn with the old code-drawn figures instead - it is skipped and reported. Nothing is posted anywhere.
"""
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cutout_assets as CA  # noqa: E402
import story_test as ST  # noqa: E402

OUT = os.path.join(HERE, "work", "art_test")
ROOT = os.path.join(HERE, "assets", "cartoon_parts")
SCENES = [
    {"id": "P1", "place": "গ্রামের উঠোন, সন্ধ্যা", "cast": ["hari", "saraswati"],
     "lines": [("s_1111_093554_4", 0, "hari", "saraswati"), ("s_1111_093554_4", 4, "hari", "saraswati")]},
    {"id": "T1", "place": "তারানাথের কুটির, রাত", "cast": ["taranath", "kishori"],
     "lines": [("s_1111_093554_4", 0, "taranath", "kishori"), ("s_1111_093554_4", 4, "taranath", "kishori")]},
    {"id": "T2", "place": "তারানাথের কুটির, অমাবস্যার রাত", "cast": ["taranath", "madhusundari"], "present": ["taranath"],
     "lines": [("s_1111_093344_0", 5, "narrator", None)]},
]


def sheet(reg, keys, path):
    """per character: the reference picture (or the last rejected one) + every part of its puppet"""
    tiles = []
    for name, key in keys.items():
        d = os.path.join(reg.root, key)
        if not os.path.isdir(d):
            continue
        files = sorted(os.listdir(d))
        ref = "body.png" if "body.png" in files else next((f for f in reversed(files) if f.endswith("_body.png")), None)
        row = []
        for f in ([ref] if ref else []) + [x for x in files if x.startswith("part_")]:
            im = cv2.imread(os.path.join(d, f), cv2.IMREAD_UNCHANGED)
            if im is None or im.ndim < 3 or im.shape[2] < 4:
                continue
            a = im[..., 3:4] / 255.0
            t = (np.full(im.shape[:2] + (3,), (90, 90, 90), np.float32) * (1 - a) + im[..., :3] * a).astype(np.uint8)
            h = 260
            t = cv2.resize(t, (max(8, int(t.shape[1] * h / t.shape[0])), h))
            cv2.putText(t, ("REJECTED " if f.startswith("rejected") else "") + f[:16], (3, 14), 0, 0.4, (255, 255, 255), 1)
            row.append(t)
        if row:
            r = np.hstack(row)
            cv2.putText(r, name, (5, 250), 0, 0.7, (0, 255, 255), 2)
            tiles.append(r)
    if not tiles:
        return None
    w = max(t.shape[1] for t in tiles)
    img = np.vstack([np.pad(t, ((0, 0), (0, w - t.shape[1]), (0, 0))) for t in tiles])
    if img.shape[1] > 3000:
        img = cv2.resize(img, (3000, int(img.shape[0] * 3000 / img.shape[1])))
    cv2.imwrite(path, img)
    return path


PLAN_CAST = [   # the test plan's characters (in this order; a paused run continues with the next one next time)
    {"id": "hari", "name": "Hari", "name_local": "হরি", "gender": "male", "age": "adult", "kind": "human",
     "look": "an ordinary Bengali man of about forty, short black hair, thick moustache, a light blue full-sleeve shirt and grey trousers, black sandals"},
    {"id": "saraswati", "name": "Saraswati", "name_local": "সরস্বতী", "gender": "female", "age": "adult", "kind": "human",
     "look": "a Bengali village woman of about thirty-five, black hair in a bun, a red bindi, a red cotton saree with a broad gold border worn in the Bengali style with the pallu over the left shoulder, a red blouse, gold bangles, bare feet"},
    {"id": "petni", "name": "Petni", "name_local": "পেত্নী", "gender": "female", "age": "young", "kind": "ghost",
     "look": "a female ghost (petni), very long open black hair falling to her waist, pale bluish skin, glowing white eyes, a torn old white saree, no feet visible"},
]
def poses_sheet(reg, people, path):
    """the 7-pose assembled check of every character (the newest one; a failed one is shown with its reasons)"""
    rows = []
    for c in people:
        key = CA.char_key({"name": c["name"], "look": c["look"]})
        d = os.path.join(reg.root, key)
        files = sorted(os.listdir(d)) if os.path.isdir(d) else []
        f = "assembly.jpg" if "assembly.jpg" in files else next((x for x in reversed(files) if x.endswith("_assembly.jpg")), None)
        im = cv2.imread(os.path.join(d, f)) if f else None
        if im is None:
            im = np.full((560, 360 * 7, 3), (50, 50, 60), np.uint8)
            st_ = reg.index["characters"].get(key, {}).get("status", "not made")
            cv2.putText(im, f"no puppet yet ({st_})", (40, 280), 0, 1.2, (255, 255, 255), 2)
        im = im.copy()
        cv2.putText(im, c["name"] + ("" if f == "assembly.jpg" else "  (rejected reference)" if f else ""), (8, 50), 0, 0.8,
                    (0, 255, 255), 2)
        rows.append(cv2.resize(im, (2520, int(im.shape[0] * 2520 / im.shape[1]))))
    if rows:
        cv2.imwrite(path, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
        return path
    return None


def run(image_fn, llm=None, log=print, budget=60, W=1280, H=720, fps=24):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    reg = CA.Registry(ROOT)
    cast = ST.designed_cast(llm, log)
    import character_designer as CD_
    plan_people = [dict(c, design=CD_.design(c)[0]) for c in PLAN_CAST]
    want = plan_people + [c for c in cast if c["id"] in ("taranath", "madhusundari", "kishori")]
    recs = [{"name": c["name"], "look": c["look"], "design": c["design"]} for c in want]
    try:
        gen = CA.ensure_cast(recs, reg, image_fn, log=log, budget=budget, places=[("house_interior", {})])
    except Exception as e:                                 # the exact blocker is reported; finished work stays
        gen = {"characters": {r["name"]: {"status": reg.index["characters"].get(CA.char_key(r), {}).get("status", "pending"),
                                          "problems": []} for r in recs}, "plates": {}, "paused": True, "made": 0,
               "blocker": f"{type(e).__name__}: {str(e)[:300]}"}
        reg.save()
        log(f"  ART TEST BLOCKED: {gen['blocker']}")
    keys = {c["name"]: CA.char_key({"name": c["name"], "look": c["look"]}) for c in want}
    sh = sheet(reg, keys, os.path.join(OUT, "art_sheet.jpg"))
    ps = poses_sheet(reg, want, os.path.join(OUT, "art_poses.jpg"))
    ST.OUT = OUT
    scenes = []
    everyone = cast + plan_people
    ready = {c["id"] for c in everyone if CA.status_of(reg, {"name": c["name"], "look": c["look"]}) == "ready"}
    for sd in SCENES:
        missing = [cid for cid in sd["cast"] if cid not in ready]
        if missing:                                        # never hidden behind the old code-drawn figures
            scenes.append({"id": sd["id"], "error": "skipped - not ready: " + ", ".join(missing)})
            log(f"  art test scene {sd['id']} skipped: {', '.join(missing)} not ready")
            continue
        try:
            scenes.append(ST.build_scene(sd, W, H, fps, llm, log, everyone, art=reg))
        except Exception as e:
            scenes.append({"id": sd["id"], "error": str(e)[:300]})
            log(f"  art test scene {sd['id']} failed: {str(e)[:200]}")
    vids = [s["video"] for s in scenes if s.get("video")]
    final = None
    if vids:
        lst = os.path.join(OUT, "scenes.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{os.path.abspath(v)}'\n" for v in vids)
        final = os.path.join(OUT, "art_test.mp4")
        os.system(f"ffmpeg -y -loglevel error -f concat -safe 0 -i '{lst}' -c copy -movflags +faststart '{final}'")
    report = {"generation": gen, "assets": {n: reg.index["characters"].get(k, {}).get("qa") for n, k in keys.items()},
              "plate": reg.index["plates"].get("house_interior"),
              "scenes": [{"id": s.get("id"), "drawn_by": s.get("drawn_by"), "plate": s.get("plate"),
                          "quality": s.get("quality", {}).get("all_pass") if isinstance(s.get("quality"), dict) else None,
                          "failed_checks": {k: v for k, v in (s.get("quality") or {}).items() if isinstance(v, dict) and not v.get("pass")},
                          "error": s.get("error")} for s in scenes],
              "seconds": round(time.time() - t0, 1), "sheet": sh, "poses": ps, "video": final,
              "plans": {n: reg.index["characters"].get(k, {}).get("plan") for n, k in keys.items()},
              "rig_method": {n: reg.index["characters"].get(k, {}).get("rig_method") for n, k in keys.items()},
              "assembled_check": {n: reg.index["characters"].get(k, {}).get("qa", {}).get("assembly") for n, k in keys.items()},
              "rejected_references": {n: reg.index["characters"].get(k, {}).get("rejected", []) for n, k in keys.items()}}
    with open(os.path.join(OUT, "art_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    keep = os.path.join(ROOT, "_art_test")                 # kept in the repo too: the results can be examined later
    os.makedirs(keep, exist_ok=True)
    import shutil
    for f in ("art_report.json", "art_sheet.jpg", "art_poses.jpg"):
        if os.path.exists(os.path.join(OUT, f)):
            shutil.copy(os.path.join(OUT, f), os.path.join(keep, f))
    return report
