"""60-SECOND PILOT of the character animation pipeline (nothing is published).

    python pilot.py A    - everything local: rigged silhouette characters (the zero-cost fallback), real background
                           pictures already in the repo, real Gemini voices from assets/voice_samples
    python pilot.py B    - the same 3 scenes, but characters and backgrounds made by the free Cloudflare picture
                           model (photo characters with their real expressions, lip-sync from their real 'talking'
                           face) - run on GitHub: Actions > Daily Horror Story > Run workflow > mode = pilot

Writes work/pilot/: pilot.mp4, pilot_report.json (render time, CPU, peak RAM, pictures made, cache hits, face
similarity, lip-sync frames, FAST vs BALANCED), pilot_manifest.json and characters.jpg (every character asset).
"""
import json
import os
import resource
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import zerocost  # noqa: E402
zerocost.install()
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import characters  # noqa: E402
import compositor  # noqa: E402
import manifest  # noqa: E402

OUT = os.path.join(HERE, "work", "pilot")
VS = os.path.join(HERE, "assets", "voice_samples")

CAST = [
    {"name": "Taranath", "gender": "male", "age": "old", "kind": "human",
     "look": "old Bengali tantrik with long matted grey hair, grey beard, red cloth, rudraksha beads, holding a lantern"},
    {"name": "Kishori", "gender": "male", "age": "young adult", "kind": "human",
     "look": "young Bengali man, thin, white kurta, curious nervous face"},
    {"name": "Abhishek", "gender": "male", "age": "adult", "kind": "human",
     "look": "forty-year-old Bengali man, delivery jacket, helmet in hand, moustache"},
    {"name": "Sayan", "gender": "male", "age": "young adult", "kind": "human",
     "look": "young Bengali man in a delivery jacket and jeans, scared"},
    {"name": "Chhaya", "gender": "female", "age": "old", "kind": "ghost",
     "look": "pale old woman ghost in a white sari, long loose white hair"},
]
SERIES = {"taranath", "kishori"}

SCENES = [   # (voice sample, from, seconds, speaker, scene)
    ("s_1111_093344_0.ogg", 9.0, 19.0, None,
     {"place": "foggy night road with street lamps", "characters": ["Taranath", "Kishori"], "mood": "creepy",
      "ambience": ["fog", "wind"], "bg_crop": ("thumb_base/2026-11-14_20.jpg", (0.0, 0.0, 0.56, 1.0))}),
    ("s_1111_093631_6.ogg", 0.0, 20.0, "Taranath",
     {"place": "old banyan tree at the edge of the cremation ground", "characters": ["Taranath", "Kishori"],
      "mood": "tense", "ambience": ["smoke", "lantern"],
      "bg_crop": ("thumb_base/2026-11-15_20.jpg", (0.2, 0.0, 0.66, 1.0)), "emotion": "scared"}),
    ("s_1112_032409_14.ogg", 0.0, 21.0, "Abhishek",
     {"place": "lonely highway shortcut through the jungle at night", "characters": ["Abhishek", "Sayan", "Chhaya"],
      "mood": "scare", "ambience": ["rain", "thunder"],
      "bg_crop": ("thumb_base/2026-11-14_20.jpg", (0.0, 0.0, 0.56, 1.0)), "emotion": "normal"}),
]


def usage():
    s, c = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"cpu_sec": round(s.ru_utime + s.ru_stime + c.ru_utime + c.ru_stime, 1),
            "peak_ram_mb": round(max(s.ru_maxrss, c.ru_maxrss) / 1024, 0)}


def cut_audio(src, start, secs, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(secs), "-i", src, "-ac", "2",
                    "-ar", "44100", "-af", f"afade=t=in:d=0.2,afade=t=out:st={secs - 0.4}:d=0.4", out], check=True)
    return out


def crop_bg(rel, box, out):
    im = Image.open(os.path.join(HERE, "assets", rel)).convert("RGB")
    w, h = im.size
    im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    from PIL import ImageOps
    im = ImageOps.autocontrast(im, cutoff=0.5)        # (very dark old pictures: the scene must still be seen)
    im.resize((1664, int(1664 * im.height / im.width)), Image.LANCZOS).save(out, quality=93)
    return out


def contact_sheet(lib, recs, path):
    tiles = []
    for rec in recs:
        if rec.get("mode") == "photo":
            for e, im in lib.sprites(rec).items():
                tiles.append((f"{rec['id']}:{e}", im))
        else:
            import silhouette
            for e in ("neutral", "talking", "fear", "shock"):
                tiles.append((f"{rec['id']}:{e}", silhouette.render(rec["rig"], silhouette.pose_for(e, 0.4, 0.7 if e == "talking" else 0), 300)))
    if not tiles:
        return None
    cols = 8
    th = 260
    sheet = Image.new("RGB", (cols * 170, ((len(tiles) + cols - 1) // cols) * (th + 10)), (70, 76, 88))
    for i, (_name, im) in enumerate(tiles):
        im = im.copy()
        im.thumbnail((165, th))
        sheet.paste(im, ((i % cols) * 170 + (170 - im.width) // 2, (i // cols) * (th + 10) + th - im.height), im)
    sheet.save(path, quality=90)
    return path


def run(mode="A", quality="BALANCED", image_fn=None, upload_fn=None, log=print):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    lib = characters.Library(os.path.join(HERE, "assets") if mode == "B" else OUT, os.path.join(OUT, "cache"),
                             image_fn=image_fn if mode == "B" else None, upload_fn=upload_fn, log=log,
                             style="cinematic photorealistic film still, horror movie, dark moody low-key light")
    recs = {}
    for c in CAST:
        cid = characters.char_id(c, series=c["name"].lower() in SERIES, story_key="pilot")
        need = characters.BASE_SET + (("blink",) if c["name"].lower() in SERIES else ())
        recs[c["name"].lower()] = lib.ensure(c, cid, need=need, seed=1000 + len(recs) * 17)
    t_assets = time.time() - t0
    log(f"characters ready in {t_assets:.0f}s: " + ", ".join(f"{r['id']}={r['mode']}" for r in recs.values()))
    by_id = {r["id"]: r for r in recs.values()}
    manifests, reports, clips = [], [], []
    for i, (wav, st, secs, spk, sc) in enumerate(SCENES):
        a = cut_audio(os.path.join(VS, wav), st, secs, os.path.join(OUT, f"a{i}.wav"))
        if mode == "B" and image_fn:
            bg = lib.background(sc["place"], "Bengal, India, night", sc["mood"], seed=2000 + i)
        else:
            bg = (crop_bg(sc["bg_crop"][0], sc["bg_crop"][1], os.path.join(OUT, f"bg{i}.jpg")), characters.slug(sc["place"]))
        beats = [(0.0, secs, spk, sc.get("emotion", "normal"), sc["place"])]
        m = manifest.build_scene(i, sc, beats, secs, recs, bg)
        manifests.append(m)
        c = os.path.join(OUT, f"clip{i}.mp4")
        reports.append(compositor.render_scene(m, by_id, lib, a, c, quality=quality, log=log))
        clips.append(c)
    fast = None
    try:                                              # the same first scene in FAST, only to measure the speed
        fast = compositor.render_scene(manifests[0], by_id, lib, os.path.join(OUT, "a0.wav"),
                                       os.path.join(OUT, "fast_test.mp4"), quality="FAST", log=log)
    except Exception as e:
        log("FAST test failed:", str(e)[:120])
    with open(os.path.join(OUT, "clips.txt"), "w") as f:
        f.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(OUT, "clips.txt"),
                    "-c", "copy", "-movflags", "+faststart", os.path.join(OUT, "pilot.mp4")], check=True)
    manifest.save(manifests, os.path.join(OUT, "pilot_manifest.json"))
    contact_sheet(lib, list(recs.values()), os.path.join(OUT, "characters.jpg"))
    total_video = sum(r["seconds"] for r in reports)
    render = sum(r["render_sec"] for r in reports)
    sims = [x.get("similarity") for r in recs.values() for x in (r.get("expr") or {}).values()
            if isinstance(x, dict) and x.get("similarity") is not None]
    rep = {"mode": mode, "quality": quality, "video_seconds": round(total_video, 1),
           "render_seconds_balanced": round(render, 1),
           "render_seconds_fast_scene1": fast and fast["render_sec"], "scene1_seconds": reports[0]["seconds"],
           "speed_balanced_x_realtime": round(render / max(total_video, 1), 2),
           "speed_fast_x_realtime": fast and round(fast["render_sec"] / max(reports[0]["seconds"], 1), 2),
           "asset_seconds": round(t_assets, 1), "library": lib.stats,
           "characters": {r["id"]: {"mode": r["mode"], "expressions": sorted((r.get("expr") or {}).keys())} for r in recs.values()},
           "face_similarity_avg": round(float(np.mean(sims)), 3) if sims else None,
           "lip_sync_frames": sum(r["lip_frames"] for r in reports), "scenes": reports,
           "cpu_cores": os.cpu_count(), **usage(), "zero_cost": zerocost.summary_bn(),
           "total_seconds": round(time.time() - t0, 1)}
    with open(os.path.join(OUT, "pilot_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    log(json.dumps({k: v for k, v in rep.items() if k != "scenes"}, ensure_ascii=False))
    return rep


if __name__ == "__main__":
    run((sys.argv[1] if len(sys.argv) > 1 else "A").upper(), (sys.argv[2] if len(sys.argv) > 2 else "BALANCED").upper())
