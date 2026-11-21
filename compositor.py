"""FAST ZERO-COST CINEMATIC COMPOSITOR - one scene of the Scene Manifest -> one film clip (same format as the
classic clips, so the rest of the old pipeline - joining, subtitles, badges, Facebook 9:16 - is unchanged).

Layers (back to front): far background - near background (pseudo depth: they move at different speeds) -
characters (photo cut-outs or rigged silhouettes) with ground shadows - code-drawn foreground (branches / grass,
the fastest layer) - weather and light (fog, rain, smoke, dust, moving shadow, lightning, lamp flicker) - grade,
vignette, grain - fade in / out.
Camera: push-in, pan, tracking the speaker, handheld shake in scares.
Characters: breathing, sway, ghost float, fear trembling; photo characters change expression per beat and open /
close the mouth with the voice by swapping in their REAL 'talking' face (and blink with their real 'blink' face) -
only when those pictures exist; silhouettes nod, gesture and move their hands while speaking. No mouth is ever
drawn on a face that has no talking picture.
Python + numpy + OpenCV + Pillow + FFmpeg only. FAST = half the frames are rendered (ffmpeg doubles them) and the
heavy weather layers are lighter; BALANCED = every frame, every layer.
"""
import math
import subprocess
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import silhouette


def _smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _noise(rng, h, w, cells=(9, 16), blur=22):
    import cv2
    n = cv2.resize(rng.uniform(0, 1, cells).astype("float32"), (w, h), interpolation=cv2.INTER_CUBIC)
    n = cv2.GaussianBlur(n, (0, 0), blur)
    return (n - n.min()) / (n.max() - n.min() + 1e-6)


def foreground_layer(seed, w, h, kind):
    """code-drawn dark foreground (branches at the top corners, grass / rubble at the bottom) as RGBA"""
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (4, 5, 7, 255)
    if kind in ("outdoor", "both"):
        for side in (0, 1):
            x0 = int(w * 0.14) if side == 0 else int(w * 0.86)
            y0 = int(h * rng.uniform(0.02, 0.12))
            for _ in range(int(rng.integers(2, 4))):
                x, y, ang = x0, y0 + int(rng.uniform(-30, 60)), (0.25 if side == 0 else math.pi - 0.25) + rng.uniform(-0.3, 0.3)
                width = rng.uniform(10, 18)
                for _ in range(9):
                    nx, ny = x + math.cos(ang) * rng.uniform(30, 60), y + math.sin(ang) * rng.uniform(-6, 26)
                    d.line([(x, y), (nx, ny)], fill=ink, width=int(width))
                    if rng.uniform() < 0.5:
                        d.line([(nx, ny), (nx + rng.uniform(-40, 40), ny + rng.uniform(10, 50))], fill=ink, width=int(width * 0.4) + 1)
                    x, y, width, ang = nx, ny, max(2, width * 0.8), ang + rng.uniform(-0.25, 0.25)
    gy = int(h * 0.80)
    for x in range(0, w, 3):
        hh = rng.uniform(10, 46) * (1.6 if (x < w * 0.15 or x > w * 0.85) else 0.6)
        d.line([(x, gy + 60), (x + rng.uniform(-8, 8), gy + 46 - hh)], fill=ink, width=2)
    d.rectangle([0, gy + 58, w, h], fill=ink)
    return im.filter(ImageFilter.GaussianBlur(1.6))


def _rain(rng, w, h):
    import cv2
    t = np.zeros((h * 2, w), "float32")
    for _ in range(int(w * h / 900)):
        x, y = int(rng.uniform(0, w)), int(rng.uniform(0, h * 2))
        ln = int(rng.uniform(14, 34))
        cv2.line(t, (x, y), (x - ln // 4, y + ln), float(rng.uniform(0.35, 1.0)), 1)
    return cv2.GaussianBlur(t, (0, 0), 0.6)


def _tint(sprite, light, cool=0.0):
    """make a cut-out sit in the scene's light: darker / tinted like the background"""
    a = np.asarray(sprite).astype("float32")
    rgb = a[..., :3] * light[None, None, :]
    if cool:
        rgb = rgb * (1 - cool) + np.array([170, 205, 215], "float32") * cool
    return np.dstack([np.clip(rgb, 0, 255), a[..., 3]])


def _face_patch(base, src, fb_base, fb_src, part):
    """the REAL mouth (part='mouth') or eyes (part='eyes') of another picture of the same character, aligned to
    this picture's face and blended in with a soft edge"""
    import cv2
    bx, by, bw, bh = fb_base
    sx, sy, sw, sh = fb_src
    y0, y1 = (0.52, 1.02) if part == "mouth" else (0.18, 0.58)
    out = base.copy()
    ry0, ry1 = int(by + bh * y0), int(by + bh * y1)
    rx0, rx1 = int(bx + bw * 0.12), int(bx + bw * 0.88)
    sry0, sry1 = int(sy + sh * y0), int(sy + sh * y1)
    srx0, srx1 = int(sx + sw * 0.12), int(sx + sw * 0.88)
    if min(ry1 - ry0, rx1 - rx0, sry1 - sry0, srx1 - srx0) < 4:
        return base
    patch = cv2.resize(src[sry0:sry1, srx0:srx1], (rx1 - rx0, ry1 - ry0), interpolation=cv2.INTER_LINEAR)
    m = np.zeros((ry1 - ry0, rx1 - rx0), "float32")
    cv2.ellipse(m, ((rx1 - rx0) // 2, (ry1 - ry0) // 2), ((rx1 - rx0) // 2 - 2, (ry1 - ry0) // 2 - 2), 0, 0, 360, 1.0, -1)
    m = cv2.GaussianBlur(m, (0, 0), max(1.5, (rx1 - rx0) * 0.08))[..., None]
    region = out[ry0:ry1, rx0:rx1]
    if region.shape[:2] != patch.shape[:2]:
        return base
    region[..., :3] = region[..., :3] * (1 - m) + patch[..., :3] * m
    return out


class _Actor:
    def __init__(self, spec, rec, lib, H, light):
        self.spec, self.rec = spec, rec
        self.mode = spec["mode"]
        self.h = int(H * 0.78 * spec.get("scale", 1.0))
        self.ghost = spec.get("ghost")
        self.light = light
        self.lip = False
        self.blink_ok = False
        self.cache = {}
        if self.mode == "photo":
            sp = lib.sprites(rec)
            faces = {e: (r.get("face") if isinstance(r, dict) else None) for e, r in rec.get("expr", {}).items()}
            base_face = faces.get("neutral") or faces.get("reference")
            if "neutral" not in sp or not base_face:
                self.mode = "silhouette"
            else:
                ref = sp["neutral"]
                k = self.h / ref.height
                self.size = (max(1, int(ref.width * k)), self.h)
                self.k = k
                self.frames = {}
                for e, im in sp.items():
                    self.frames[e] = _tint(im.resize(self.size, Image.LANCZOS), light, 0.35 if self.ghost else 0.0)
                self.faces = {e: [int(v * k) for v in fb] for e, fb in faces.items() if fb}
                self.lip = "talking" in self.frames and "talking" in self.faces
                self.blink_ok = "blink" in self.frames and "blink" in self.faces
        if self.mode == "silhouette":
            self.rig = rec.get("rig") or silhouette.build(rec["bible"])
            self.cartoon = None
            import os as _os
            if _os.environ.get("ANIM_FALLBACK", "cartoon") == "cartoon":   # a drawn face instead of a black shape
                import cartoon_rig
                self.cartoon = cartoon_rig.Character(rec["id"], cartoon_rig.design_for(rec["bible"]))
                self.mode = "cartoon"
                self.lip = True                         # (a drawn mouth on a drawn face, moved by the real voice)
                self.blink_ok = True

    def frame(self, expr, talk, t, blink):
        """RGBA float array of this character for this moment"""
        if self.mode == "photo":
            e = expr if expr in self.frames else "neutral"
            if e == "talking":
                e = "neutral"
            key = (e, talk > 0.28 and self.lip, blink and self.blink_ok)
            if key not in self.cache:
                base = self.frames[e]
                fb = self.faces.get(e) or self.faces.get("neutral") or self.faces.get("reference")
                img = base
                if key[1]:
                    img = _face_patch(img, self.frames["talking"], fb, self.faces["talking"], "mouth")
                if key[2]:
                    img = _face_patch(img, self.frames["blink"], fb, self.faces["blink"], "eyes")
                self.cache[key] = img
            return self.cache[key]
        if self.mode == "cartoon":
            import cartoon_rig
            pn = {"fear": "stand_fear", "shock": "stand_fear", "talking": "stand_point" if talk > 0.6 else "stand"}.get(expr, "stand")
            p_ = dict(cartoon_rig.POSES[pn])
            p_["farm_n"] += 30 * talk
            shape = "A" if talk > 0.5 else ("E" if talk > 0.28 else "rest")
            st = {"facing": self.spec.get("facing", 1), "head_yaw": self.spec.get("facing", 1) * 0.8, "pose": p_,
                  "mouth": (talk, shape), "blink": 1.0 if blink else 0.0, "head_pitch": 4 * talk * math.sin(t * 6),
                  "brows": {"fear": "fear", "shock": "surprise", "sad": "sad", "angry": "angry", "happy": "happy"}.get(expr, ""),
                  "gaze": (self.spec.get("facing", 1) * 0.6, 0.0), "hand_open": 0.6 if talk > 0.2 else 0.0}
            a = cartoon_rig.sprite(self.cartoon, st, self.h)
            if self.ghost:
                a[..., :3] = a[..., :3] * 0.5 + np.array([200, 225, 230], "float32") * 0.5
            else:
                a[..., :3] *= (0.55 + 0.45 * self.light[None, None, :])
            return a
        pose = silhouette.pose_for(expr if expr in silhouette.POSES else "neutral", t, talk)
        im = silhouette.render(self.rig, pose, h_px=self.h, breath=math.sin(t * 1.7))
        a = np.asarray(im).astype("float32")
        if not self.ghost:                            # silhouettes catch a little of the scene's light at the rim
            a[..., :3] = a[..., :3] + 14 * self.light[None, None, :]
        return a


def render_scene(m, records, lib, audio, out, W=1280, H=720, FPS=25, SR=44100, quality="BALANCED", log=print):
    """one manifest scene -> mp4 with its audio. Returns a small report dict."""
    import cv2
    import animate
    t_start = time.time()
    dur = float(m["duration"])
    fast = str(quality).upper() == "FAST"
    fps_r = FPS // 2 if fast else FPS
    n = max(1, int(math.ceil(dur * fps_r)))
    rng = np.random.default_rng(abs(hash(m["id"])) % (2 ** 32))
    WB, HB = int(W * 1.3), int(H * 1.3)
    bg = cv2.imread(m["background"]["path"])
    if bg is None:
        raise RuntimeError("background missing")
    bh, bw = bg.shape[:2]
    sc = max(WB / bw, HB / bh)
    bg = cv2.resize(bg, (int(bw * sc) + 1, int(bh * sc) + 1), interpolation=cv2.INTER_CUBIC)
    oy, ox = (bg.shape[0] - HB) // 2, (bg.shape[1] - WB) // 2
    bg = bg[oy:oy + HB, ox:ox + WB].astype("float32")
    lum = float(bg.mean())
    if lum < 52:                                       # a very dark picture: lift it so the scene can be seen
        bg = np.clip(255.0 * (bg / 255.0) ** (0.62 if lum < 30 else 0.8) * 1.08, 0, 255)
    bg = bg.astype("uint8")                            # (warping 8-bit pictures is ~3x faster)
    light = np.clip(bg.reshape(-1, 3).mean(axis=0)[::-1] / 255.0 * 2.2, 0.35, 1.0)   # (RGB) the scene's light
    ymask = np.clip((np.linspace(0, 1, H)[:, None, None] - 0.42) / 0.5, 0, 1).astype("float32")
    indoor = any(k in str(m["background"].get("id", "")) for k in ("room", "hall", "house", "interior", "ghar", "corridor", "attic"))
    fg = np.asarray(foreground_layer(int(rng.integers(1, 1 << 30)), WB, HB, "bottom" if indoor else "outdoor"))
    fx = set(m.get("effects") or [])
    fog = _noise(rng, H, W * 2, (8, 22), 30) if "fog" in fx else None
    smoke = _noise(rng, H * 2, W, (18, 10), 26) if "smoke" in fx else None
    rain = _rain(rng, W, H) if "rain" in fx else None
    dust = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(4, 14), rng.uniform(0, 6.28)) for _ in range(60 if not fast else 25)] \
        if "dust" in fx else []
    flashes = sorted(rng.uniform(1.0, max(1.5, dur - 1.0), 2 if dur > 12 else 1)) if "lightning" in fx else []
    shadow_t = rng.uniform(0.25, 0.6) * dur if "shadow" in fx else None
    grains = [(rng.standard_normal((H, W)).astype("float32") * 4.0)[..., None] for _ in range(4)]
    vign = (1 - 0.55 * (((np.linspace(-1, 1, W)[None, :] ** 2) + (np.linspace(-1, 1, H)[:, None] ** 2)) / 2) ** 1.2)[..., None]
    actors = []
    for spec in m.get("characters") or []:
        rec = records.get(spec["id"])
        if rec:
            actors.append(_Actor(spec, rec, lib, H, light))
    env = animate.voice_envelope(audio, fps_r)
    cam = m.get("camera") or {"move": "push_in", "zoom": [1.04, 1.14]}
    beats = m.get("beats") or []
    blinks = sorted(rng.uniform(0.5, max(0.6, dur), max(1, int(dur / 3.5))))
    track_x = WB / 2
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", str(fps_r), "-i", "-", "-i", audio, "-t", f"{dur:.2f}",
         "-vf", (f"fps={FPS}," if fast else "") + f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0, dur - 0.4):.2f}:d=0.4,format=yuv420p",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "3500k", "-bufsize", "7000k",
         "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-ac", "2", out], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    lip_frames = 0
    try:
        for f in range(n):
            t = f / fps_r
            u = t / max(dur, 0.01)
            beat = next((b for b in beats if b["t0"] <= t < b["t1"]), None)
            talk = float(env[f]) if f < len(env) else 0.0
            # ---------------- camera
            z0, z1 = cam.get("zoom", [1.05, 1.15])
            z = z0 + (z1 - z0) * _smooth(u)
            cx, cy = WB / 2, HB * 0.52
            mv = cam.get("move")
            if mv == "pan_right":
                cx = WB * (0.42 + 0.16 * _smooth(u))
            elif mv == "pan_left":
                cx = WB * (0.58 - 0.16 * _smooth(u))
            elif mv == "track" and actors:
                spk = beat.get("speaker") if beat else None
                goal = next((a.spec["x"] for a in actors if a.spec["id"] == spk), 0.5)
                track_x += ((0.15 + 0.7 * goal) * WB - track_x) * (0.04 if fast else 0.02) * (2 if fast else 1)
                cx = track_x
            shake = (3.5 * math.sin(t * 13.0) + 2.0 * math.sin(t * 29.0)) if mv == "handheld" else 0.0
            half_w, half_h = W / (2 * z), H / (2 * z)
            cx = min(max(cx, half_w), WB - half_w)
            cy = min(max(cy, half_h), HB - half_h)
            M = np.float32([[z, 0, W / 2 - z * cx + shake], [0, z, H / 2 - z * cy + shake * 0.6]])
            zf = 1 + (z - 1) * 0.6                     # the far layer moves less (depth)
            Mf = np.float32([[zf, 0, W / 2 - zf * (WB / 2 + (cx - WB / 2) * 0.6)], [0, zf, H / 2 - zf * cy]])
            near = cv2.warpAffine(bg, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT).astype("float32")
            far = cv2.warpAffine(bg, Mf, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT).astype("float32")
            frame = far + (near - far) * ymask
            # ---------------- characters (screen space, on the near layer)
            for a in actors:
                expr = (beat["expression"].get(a.spec["id"], "neutral") if beat else "neutral")
                speaking = bool(beat and beat.get("speaker") == a.spec["id"])
                blink = any(0 <= t - b0 < 0.14 for b0 in blinks)
                spr = a.frame(expr, talk if speaking else 0.0, t, blink)
                if a.mode in ("photo", "cartoon") and speaking and talk > 0.28 and a.lip:
                    lip_frames += 1
                wx = a.spec["x"] * WB + 4.0 * math.sin(t * 0.7 + a.spec["x"] * 5)
                wy = HB * 0.93 - (10 * (1 + math.sin(t * 0.8)) if a.ghost else 0)
                if expr in ("fear", "shock") and a.mode == "photo":
                    wx += 1.6 * math.sin(t * 37)
                s_ = z * (1 + 0.006 * math.sin(t * 1.7)) * 0.77
                sh, sw = spr.shape[:2]
                tw_, th_ = max(2, int(sw * s_)), max(2, int(sh * s_))
                sx = int(M[0, 0] * wx + M[0, 2] - tw_ / 2)
                sy = int(M[1, 1] * wy + M[1, 2] - th_)
                if sx > W or sy > H or sx + tw_ < 0 or sy + th_ < 0:
                    continue
                im = cv2.resize(spr, (tw_, th_), interpolation=cv2.INTER_LINEAR)
                # ground shadow
                if not a.ghost:                            # (only the small area around the feet is touched)
                    ex_, ey_ = sx + tw_ // 2, sy + th_ - 4
                    rx_, ry_ = int(tw_ * 0.42), max(3, int(th_ * 0.03))
                    bx0, by0, bx1, by1 = max(0, ex_ - rx_ - 30), max(0, ey_ - ry_ - 30), min(W, ex_ + rx_ + 30), min(H, ey_ + ry_ + 30)
                    if bx1 > bx0 and by1 > by0:
                        sh_m = np.zeros((by1 - by0, bx1 - bx0), "float32")
                        cv2.ellipse(sh_m, (ex_ - bx0, ey_ - by0), (rx_, ry_), 0, 0, 360, 0.55, -1)
                        sh_m = cv2.GaussianBlur(sh_m, (0, 0), 9)[..., None]
                        frame[by0:by1, bx0:bx1] *= (1 - sh_m)
                x0, y0_ = max(0, sx), max(0, sy)
                x1, y1 = min(W, sx + tw_), min(H, sy + th_)
                part = im[y0_ - sy:y1 - sy, x0 - sx:x1 - sx]
                al = part[..., 3:4] / 255.0
                if a.ghost:
                    al = al * (0.62 + 0.12 * math.sin(t * 5.3))
                frame[y0_:y1, x0:x1] = frame[y0_:y1, x0:x1] * (1 - al) + part[..., 2::-1] * al
            # ---------------- foreground (fastest layer)
            zf2 = 1 + (z - 1) * 1.5
            Mfg = np.float32([[zf2, 0, W / 2 - zf2 * (WB / 2 + (cx - WB / 2) * 1.4)], [0, zf2, H / 2 - zf2 * (HB / 2)]])
            fgw = cv2.warpAffine(fg, Mfg, (W, H), flags=cv2.INTER_LINEAR)
            ys_ = np.nonzero(fgw[..., 3].max(axis=1))[0]
            if len(ys_):                               # (only the rows where the foreground really is)
                r0, r1 = int(ys_.min()), int(ys_.max()) + 1
                fa = fgw[r0:r1, :, 3:4].astype("float32") / 255.0
                frame[r0:r1] = frame[r0:r1] * (1 - fa) + fgw[r0:r1, :, 2::-1].astype("float32") * fa
            # ---------------- weather and light
            if fog is not None:
                off = int((t * 18) % W)
                frame += fog[:, off:off + W, None] * np.array([34, 33, 30], "float32")
            if smoke is not None and not fast or (smoke is not None and f % 2 == 0):
                off = int((t * 22) % H)
                sm = smoke[H - off:2 * H - off] if off else smoke[H:2 * H]
                frame = frame * (1 - 0.28 * sm[..., None] * ymask) + 120 * 0.28 * sm[..., None] * ymask
            if rain is not None:
                off = int((t * 900) % H)
                rl = rain[H - off:2 * H - off][..., None]
                frame = frame * 0.96 + rl * 95
            for (dx, dy, sp, ph) in dust:
                px_ = int((dx + t * sp) % W)
                py_ = int((dy + 6 * math.sin(t * 0.6 + ph)) % H)
                cv2.circle(frame, (px_, py_), 1, (150, 150, 140), -1)
            if shadow_t is not None and shadow_t <= t < shadow_t + 2.2:
                p_ = (t - shadow_t) / 2.2
                xs = np.linspace(0, 1, W)[None, :]
                band = np.exp(-((xs - (1.2 - 1.4 * p_)) ** 2) / 0.02).astype("float32")
                frame = frame * (1 - 0.55 * band[..., None])
            if "flicker" in fx:
                frame *= 0.9 + 0.1 * (0.5 + 0.5 * math.sin(t * 17) * math.sin(t * 7.3)) + (0.08 if rng.uniform() < 0.02 else 0)
            for lt in flashes:
                d_ = t - lt
                if 0 <= d_ < 0.09 or 0.18 <= d_ < 0.25:
                    frame = frame * 0.4 + np.array([255, 248, 238], "float32") * 0.6
            # ---------------- grade
            frame = frame * np.array([1.04, 0.97, 0.9], "float32") * vign * 0.92
            if not fast:
                frame += grains[f % 4]
            ff.stdin.write(np.clip(frame, 0, 255).astype("uint8").tobytes())
        ff.stdin.close()
    except Exception:
        ff.kill()
        raise
    if ff.wait() != 0:
        raise RuntimeError(ff.stderr.read().decode()[-500:])
    rep = {"scene": m["id"], "seconds": round(dur, 2), "render_sec": round(time.time() - t_start, 1),
           "frames": n, "quality": "FAST" if fast else "BALANCED",
           "characters": {a.spec["id"]: {"mode": a.mode, "lip_sync": a.lip, "blink": a.blink_ok} for a in actors},
           "lip_frames_note": "photo: the real talking face; cartoon: a drawn mouth moved by the voice",
           "lip_frames": lip_frames, "effects": sorted(fx)}
    log(f"  scene {m['id']}: {dur:.1f}s rendered in {rep['render_sec']}s ({rep['quality']}) - "
        + ", ".join(f"{k}: {v['mode']}{' + lip-sync' if v['lip_sync'] else ''}" for k, v in rep["characters"].items()))
    return rep
