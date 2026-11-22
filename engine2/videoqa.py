"""TECHNICAL video QA (never artistic approval): resolution, frame rate, codecs, pixel format, audio present and as
long as the picture, black frames, broken / unreadable file."""
import json
import subprocess


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True, timeout=120)
    return json.loads(r.stdout or "{}")


def black_seconds(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf", "blackdetect=d=0.5:pix_th=0.06", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600)
    tot = 0.0
    for ln in r.stderr.splitlines():
        if "black_duration:" in ln:
            try:
                tot += float(ln.split("black_duration:")[1].split()[0])
            except Exception:
                pass
    return round(tot, 2)


def check(path, W=1280, H=720, fps=24, need_audio=True):
    probs, m = [], {}
    try:
        info = probe(path)
    except Exception as e:
        return {"pass": False, "problems": [f"the file cannot be read: {type(e).__name__}"], "metrics": {}}
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return {"pass": False, "problems": ["no video stream"], "metrics": {}}
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    rate = float(num) / max(1.0, float(den))
    m.update(width=v.get("width"), height=v.get("height"), fps=round(rate, 3), vcodec=v.get("codec_name"),
             pix_fmt=v.get("pix_fmt"), duration=float(info.get("format", {}).get("duration", 0) or 0))
    if (v.get("width"), v.get("height")) != (W, H):
        probs.append(f"resolution {v.get('width')}x{v.get('height')} (expected {W}x{H})")
    if abs(rate - fps) > 0.01:
        probs.append(f"frame rate {rate:.2f} (expected {fps})")
    if v.get("codec_name") != "h264":
        probs.append(f"video codec {v.get('codec_name')} (expected h264)")
    if v.get("pix_fmt") != "yuv420p":
        probs.append(f"pixel format {v.get('pix_fmt')} (expected yuv420p)")
    if need_audio:
        if not a:
            probs.append("no audio")
        else:
            m["acodec"] = a.get("codec_name")
            if a.get("codec_name") != "aac":
                probs.append(f"audio codec {a.get('codec_name')} (expected aac)")
            ad, vd = float(a.get("duration", 0) or 0), float(v.get("duration", 0) or 0)
            m["audio_video_gap"] = round(abs(ad - vd), 2)
            if ad and vd and abs(ad - vd) > 0.5:
                probs.append(f"audio and picture differ by {abs(ad - vd):.2f} s")
    if m["duration"] <= 0:
        probs.append("zero length")
    else:
        b = black_seconds(path)
        m["black_seconds"] = b
        if b > 0.25 * m["duration"]:
            probs.append(f"{b:.1f} s of black picture")
    return {"pass": not probs, "problems": probs, "metrics": m}
