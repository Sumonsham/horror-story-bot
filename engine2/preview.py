"""HYBRID TEST (GitHub: mode = hybrid_test) - engine 2 on the REAL character artwork, without any image generation.

1. library.sync() - every existing asset into the permanent library (no picture is made).
2. Per test character (Hari, Saraswati, Kishori): a HybridCharacter from the library. Nobody is approved yet, so
   this is a PREVIEW of the technically valid candidates (today: the puppet cut from the ORIGINAL Cloudflare
   reference, only if it passes the whole assembled check; later also the complete-pose drawings of char_sheet).
3. An ACTION DEMO per character (1280x720, 24 fps): idle + blinking, talking (mouth from a real voice recording),
   pointing, sitting ON a stool, walking (the character's own step) - and the action table: which method does
   which action, what is MISSING (e.g. expressions, running: no drawings yet).
4. A STORY SCENE through the existing scene pipeline (story lines -> the three assistants -> scene planner ->
   background, camera, lip-sync from the real audio -> renderer) with the hybrid characters.
5. Technical video QA (videoqa) of every file. Every frame says PREVIEW - NOT APPROVED. Nothing is published.
"""
import json
import math
import os
import shutil
import subprocess
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "work", "hybrid_test")
W, H, FPS = 1280, 720, 24
PEOPLE = ("hari", "saraswati", "kishori")
WATERMARK = "PREVIEW - NOT APPROVED - engine 2 test (nothing is published)"


def _mark(img, txt=WATERMARK):
    cv2.rectangle(img, (0, 0), (img.shape[1], 34), (20, 20, 20), -1)
    cv2.putText(img, txt, (12, 24), 0, 0.62, (80, 200, 255), 1, cv2.LINE_AA)


def _ffmpeg_writer(path, audio=None):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-"]
    if audio:
        cmd += ["-i", audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k", "-shortest"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def _ground(img, gy_s):
    """a plain, calm stage: a wall, a floor, a soft shadow line (the demo is about the CHARACTER)"""
    img[:] = (70, 82, 96)
    img[gy_s:] = (52, 70, 84)
    cv2.line(img, (0, gy_s), (W, gy_s), (40, 52, 62), 2)


def _stool(pt, x, y_floor, seat_y, k):
    pt.ink = pt.ink
    pt.poly([(x - 60 * k, seat_y), (x + 60 * k, seat_y), (x + 54 * k, seat_y + 14 * k), (x - 54 * k, seat_y + 14 * k)], (40, 62, 86))
    for dx in (-44, 44):
        pt.line((x + dx * k, seat_y + 12 * k), (x + dx * 1.1 * k, y_floor), (30, 46, 64), 9 * k)


def action_demo(cid, ch, voice, path, log=print):
    """idle/blink 2 s, talking (real voice) ~3 s, pointing 2 s, sitting on a stool 2.5 s, walking 4 s"""
    import cartoon_rig as R
    import cinematic_camera as cc
    import lip_sync
    vis = lip_sync.visemes(voice, FPS) if voice else []
    segs = [("idle", 2.0), ("talking", 3.0), ("pointing", 2.0), ("sitting", 2.5), ("walking", 4.0)]
    total = sum(d for _, d in segs)
    tmp_audio = None
    if voice:                                               # the voice starts with the talking segment
        tmp_audio = path + ".wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", "2.0", "-i", "anullsrc=r=44100:cl=mono",
                        "-i", voice, "-filter_complex", f"[0][1]concat=n=2:v=0:a=1,apad=whole_dur={total}", "-t", str(total), tmp_audio])
    proc = _ffmpeg_writer(path, tmp_audio)
    cam = cc.Camera(W, H)
    gy = 935
    step = ch.step_length("walk") if hasattr(ch, "step_length") else 118.0
    used = {}
    n = int(total * FPS)
    for f in range(n):
        t = f / FPS
        acc, seg = 0.0, "idle"
        for s, d in segs:
            if t < acc + d:
                seg = s
                break
            acc += d
        u = t - acc
        x, facing, pose, extra = 960.0, 1.0, dict(R.POSES["stand"]), {}
        mouth = (0.0, "rest")
        if seg == "talking":
            pose = dict(R.POSES["stand_talk"])
            i = int(u * FPS)
            if vis and i < len(vis):
                mouth = vis[i]
            extra["gesture"] = True
        elif seg == "pointing":
            pose = dict(R.POSES["stand_point"])
        elif seg == "sitting":
            pose = dict(R.POSES["sit_talk"])
        elif seg == "walking":
            ph = u * 2 * math.pi / 1.1                      # one cycle per 1.1 s
            dist = step * ph / math.pi                      # the body moves exactly one step per half cycle
            x = 700 + dist
            pose = R.walk_pose(ph)
            extra["walk_phase"] = ph
        blink = 1.0 if (t % 3.7) < 0.12 else 0.0
        cam.set(960 if seg != "walking" else min(max(x, 760), 1160), 760, 1.45)
        img = np.zeros((H, W, 3), np.uint8)
        _ground(img, int(cam.to_screen(0, gy)[1]))
        pt = R.Painter(img, cam)
        st = {"x": x, "ground_y": gy, "facing": facing, "head_yaw": 0.6, "pose": pose, "t": t, "mouth": mouth,
              "blink": blink, **extra}
        if seg == "sitting":                                # a seat is in the scene (the rule: no sitting on nothing)
            j = ch.joints(dict(st, ground_y=gy + ch.foot_floor(st)))
            _stool(pt, x - 10, gy, j["hip"][1] + 0.02 * 372, 1.0)
        ch.draw(pt, st)
        m = getattr(ch, "_pick", None)
        used[seg] = m(st)[1] if m else "cutout"
        cv2.putText(img, f"{cid}: {seg}  ({used[seg]})", (12, H - 16), 0, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        _mark(img)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()
    if tmp_audio and os.path.exists(tmp_audio):
        os.remove(tmp_audio)
    return used


def story_scene(cast, path_dir, log=print):
    """one scene through the EXISTING scene pipeline with the hybrid characters (no image generation)"""
    import story_test as ST
    ST.OUT = path_dir
    os.makedirs(path_dir, exist_ok=True)
    sd = {"id": "H1", "place": "গ্রামের উঠোন, সন্ধ্যা", "cast": ["hari", "saraswati"],
          "lines": [("s_1111_093554_4", 0, "hari", "saraswati"), ("s_1111_093554_4", 4, "hari", "saraswati")]}
    r = ST.build_scene(sd, W, H, FPS, None, log, cast, art=None)
    return r


def run(log=print):
    from engine2 import hybrid, library, videoqa
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    lib = library.sync(log=log)
    import char_sheet
    people = {c["id"]: c for c in char_sheet.cast()}
    voice = None
    vs = os.path.join(HERE, "assets", "voice_samples")
    if os.path.isdir(vs):
        cands = sorted(f for f in os.listdir(vs) if f.endswith((".wav", ".mp3")))
        if cands:
            voice = os.path.join(OUT, "voice_cut.wav")      # ~3 s of a real recording for the talking demo
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.0", "-t", "3.0", "-i", os.path.join(vs, cands[0]),
                            "-ac", "1", "-ar", "44100", voice])
            voice = voice if os.path.exists(voice) else None
    report = {"characters": {}, "scene": None, "library": lib, "watermark": WATERMARK, "approved": False}
    cast = []
    for cid in PEOPLE:
        c = people.get(cid)
        if not c:
            continue
        design = dict(c["design"], hybrid=(c["name"], "preview"))
        ch = hybrid.load(cid, design, (c["name"], "preview"), log=log)
        entry = {"loaded": ch is not None}
        if ch is not None:
            poses = sorted(ch.full.poses) if ch.full else []
            entry["methods"] = {"cutout": ch.cut is not None, "full_pose": poses}
            entry["actions"] = hybrid.missing_for(ch.cut is not None, poses)
            entry["expressions"] = {e: ("available (mouth / eyes drawn on the original face)" if e == "neutral" else
                                        "MISSING - needs its own approved drawing") for e in hybrid.EXPRESSIONS}
            p = os.path.join(OUT, f"{c['name']}_actions.mp4")
            try:
                entry["demo_methods"] = action_demo(c["name"], ch, voice, p, log)
                entry["demo"] = p
                entry["demo_qa"] = videoqa.check(p)
            except Exception as e:
                entry["demo_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            cast.append({"id": cid, "name": c["name"], "look": c["look"], "design": design})
        report["characters"][c["name"]] = entry
    if {"hari", "saraswati"} <= {c["id"] for c in cast}:
        try:
            r = story_scene(cast, os.path.join(OUT, "scene"), log)
            v = r.get("video")
            if v and os.path.exists(v):                     # the preview mark on every frame of the scene too
                marked = os.path.join(OUT, "story_scene_720p.mp4")
                png = os.path.join(OUT, "mark.png")
                band = np.zeros((34, W, 4), np.uint8)
                band[..., 3] = 255
                band[..., :3] = (20, 20, 20)
                cv2.putText(band, WATERMARK, (12, 24), 0, 0.62, (80, 200, 255, 255), 1, cv2.LINE_AA)
                cv2.imwrite(png, band)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", v, "-i", png, "-filter_complex", "overlay=0:0",
                                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy",
                                "-movflags", "+faststart", marked])
                report["scene"] = {"video": marked, "drawn_by": r.get("drawn_by"), "qa": videoqa.check(marked),
                                   "location": r.get("location")}
            else:
                report["scene"] = {"error": "no video", "drawn_by": r.get("drawn_by")}
        except Exception as e:
            report["scene"] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    report["seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(OUT, "hybrid_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    return report
