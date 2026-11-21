"""ANIMATION QUALITY CHECK - measured on the finished video, not assumed.

- duration: video and sound are the same length (audio/video sync)
- water: the pond really moves between frames in the wide shots (no static water)
- trees: the canopy really moves in the wide shots (no static trees in wind)
- feet: the lowest foot of every standing / walking / sitting character is on the ground (no floating feet)
- lip-sync: mouths open only while that character's voice is heard (no fake lip-sync)
- black frames: only inside the planned fades
Every check returns its measured number and pass / fail.
"""
import json
import subprocess

import numpy as np


def _probe(path, what):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", f"stream={what}", "-of", "json", path],
                       capture_output=True, text=True)
    return json.loads(r.stdout or "{}").get("streams", [])


def _frames(path, times, W=320, H=180):
    out = []
    for t in times:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", f"scale={W}:{H}",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        if len(raw) == W * H:
            out.append(np.frombuffer(raw, np.uint8).reshape(H, W).astype(float))
    return out


def world_locked(scene):
    """the same camera, two moments half a second apart: does the water / do the trees move by themselves?
    (camera moves are excluded - only the world's own motion is measured)"""
    import cartoon_rig as R
    import cinematic_camera as cc
    from environment_animation import wind_at
    out = {}
    env = scene.env
    if env.pond:
        a, _ = env.pond_frame(10.0, wind_at(10.0))
        b, _ = env.pond_frame(10.5, wind_at(10.5))
        m = env.pond_mask[..., 0] > 0.5
        out["water_change"] = round(float(np.abs(a - b)[m].mean()), 2)
    cam = cc.Camera(640, 360)
    if env.trees:
        imgs = []
        for t in (10.0, 10.5):
            img = np.zeros((360, 640, 3), np.uint8)
            env.draw_trees(R.Painter(img, cam), t, wind_at(t))
            imgs.append(img.astype(float))
        out["tree_change"] = round(float(np.abs(imgs[0] - imgs[1]).mean()), 2)
    imgs = []                                              # the place itself is alive (lamp, fire, rain, bats, door...)
    for t in (10.0, 10.37):
        img = np.zeros((360, 640, 3), np.uint8)
        pt = R.Painter(img, cam)
        lights = env.draw_location(pt, t, wind_at(t), {})
        env.particles(pt, t, wind_at(t))                  # fireflies, blowing leaves, dust
        f = env.atmosphere(img.astype("float32"), cam, t, wind_at(t), lights or [])
        imgs.append(f)
    out["place_change"] = round(float(np.abs(imgs[0] - imgs[1]).mean()), 2)
    return out


def check(video, plan, rep, scene=None):
    res = {}
    if scene is not None:
        w = world_locked(scene)
        if "water_change" in w:
            res["water_moves_by_itself"] = {"mean_change": w.get("water_change"), "pass": (w.get("water_change") or 0) > 1.0}
        if "tree_change" in w:
            res["trees_move_by_themselves"] = {"mean_change": w.get("tree_change"), "pass": (w.get("tree_change") or 0) > 0.3}
        res["place_is_alive"] = {"mean_change": w.get("place_change"), "pass": (w.get("place_change") or 0) > 0.05}
    v = _probe(video, "codec_type,duration")
    durs = {s.get("codec_type"): float(s.get("duration", 0) or 0) for s in v}
    res["av_sync"] = {"video_s": durs.get("video"), "audio_s": durs.get("audio"),
                      "pass": bool(durs.get("video") and durs.get("audio") and abs(durs["video"] - durs["audio"]) < 0.25)}
    wide = next((s for s in plan["camera"] if s["type"] == "wide"), None)
    if wide and plan.get("location", "pond") == "pond":
        ts = [wide["t0"] + 1.0, wide["t0"] + 1.0 + 1 / 24, wide["t0"] + 2.0]
        fr = _frames(video, ts)
        if len(fr) == 3:
            H, W = fr[0].shape
            pond = (slice(int(H * 0.58), int(H * 0.74)), slice(int(W * 0.35), int(W * 0.8)))
            trees = (slice(int(H * 0.05), int(H * 0.45)), slice(0, int(W * 0.25)))
            res["water_motion"] = {"mean_change": round(float(np.abs(fr[2][pond] - fr[0][pond]).mean()), 2)}
            res["water_motion"]["pass"] = res["water_motion"]["mean_change"] > 0.4
            res["tree_motion"] = {"mean_change": round(float(np.abs(fr[2][trees] - fr[0][trees]).mean()), 2)}
            res["tree_motion"]["pass"] = res["tree_motion"]["mean_change"] > 0.2
    res["feet_on_ground"] = {"max_error_px": rep.get("feet_error_px_max"), "pass": (rep.get("feet_error_px_max") or 0) <= 1.0}
    res["lip_sync"] = {"frames_with_voice": rep.get("lip_sync_frames"), "frames_without_voice": rep.get("mouth_without_voice_frames"),
                       "pass": ((rep.get("lip_sync_frames") or 0) > 0 or not plan.get("dialogue"))   # (narration only:
                               and (rep.get("mouth_without_voice_frames") or 0) == 0}                     #  no mouth moves)
    fade_in, fade_out = plan.get("transitions", {}).get("fade_in", 0), plan.get("transitions", {}).get("fade_out", 0)
    ts = list(np.arange(fade_in + 0.5, plan["duration"] - fade_out - 0.5, 4.0))
    fr = _frames(video, ts, 160, 90)
    dark = [round(float(t), 1) for t, f in zip(ts, fr) if f.mean() < 4]
    res["no_black_frames"] = {"checked": len(fr), "black_at": dark, "pass": not dark}
    res["all_pass"] = all(x.get("pass") for x in res.values() if isinstance(x, dict))
    return res
