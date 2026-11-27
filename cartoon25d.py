"""TRUE 2.5D ILLUSTRATED CARTOON ENGINE (zero-cost, story-matched Bengali horror animation).

Turns every story-matched illustrated cartoon scene (made with the free Cloudflare cast reference + per-scene
prompts) into a genuine multi-layer 2.5D animated cartoon clip:

  * 3-plane 2.5D parallax depth:
      1. Far Background (cleanly inpainted behind the character, moves slowest at 0.62x)
      2. Midground Depth & Volumetric Fog/Light (moves at 0.90x, separating behind the character)
      3. Foreground Illustrated Character(s) (soft-feathered cut-out, moves fastest at 1.38x)
     For pure scenery / empty corridor shots, applies a smooth 2.5D perspective depth-field warp.
  * Story-driven character motion & acting (pivoted from the feet so feet stay planted):
      breathing, subtle weight sway, audio-driven dialogue emphasis, story action verbs
      (walk, run, recoil, tremble, loom, ghost float), plus natural blinking & audio lip-sync
      whenever a clear face is detected.
  * Story-matched animated weather & lighting:
      dual-depth falling rain streaks, counter-drifting foreground/background fog, flickering warm
      oil-lamp / lantern glow, glowing fireflies or cremation embers, lightning flashes & jump-scare
      camera punch + ghost-face flash.
  * Dynamic 2.5D camera choreography:
      establishing dolly-in, lateral 2.5D parallax pan, dramatic close-up push on dialogue/scares,
      low-angle vertical reveal, handheld tension drift, and clean cross-fades between shots.

Zero paid APIs: uses only numpy, OpenCV, PIL, optional rembg/animate, and ffmpeg.
"""
import math
import os
import re
import subprocess
import wave

import cv2
import numpy as np
from PIL import Image

CARTOON25D_STYLE = (
    "2.5D dark Bengali horror cartoon illustration, high-end animated TV series film still, "
    "crisp hand-inked dark outlines, rich atmospheric cel-shading with painted depth, "
    "dark moody low-key lighting, cold midnight blue and teal shadows with warm flickering amber lantern rim light, "
    "expressive stylized Indian Bengali cartoon characters and authentic Bengal architecture, "
    "clear separation between foreground character and layered background, eerie suspenseful horror atmosphere, "
    "not gory, no blood, no gore, no text, no letters, no watermark"
)

CARTOON25D_THUMB_STYLE = (
    "2.5D dark Bengali horror cartoon poster illustration, vivid high-contrast animated TV series art, "
    "crisp dark ink outlines, dramatic warm lantern light and cold blue moonlight, expressive terrified face, "
    "no text, no letters, no watermark"
)

_LAYER_CACHE = {}
_CACHE_MAX = 18
_FX_CACHE = {}


def active(env_fn):
    """True when Pure Story-Matched 2.5D Illustrated Horror mode should run (default for all normal runs,
    including ANIM_MODE='' or 'tvtoon' or 'cartoon25d', unless CARTOON_25D=0 is explicitly set)."""
    am = (env_fn("ANIM_MODE") or "").strip().lower()
    if am == "cartoon25d":
        return True
    if am in ("", "tvtoon") and (env_fn("CARTOON_25D") or "").strip() != "0":
        return True
    return False


# ------------------------------------------------------------------ story environment & motion analysis
def detect_weather(place="", ambience=None, mood="creepy", texts=None):
    """Parse place, ambience, mood, and spoken lines (Bengali/Hindi/English) for matching 2.5D weather/light."""
    hay = " ".join(
        [str(place or ""), str(mood or "")]
        + [str(x) for x in (ambience or [])]
        + [str(x) for x in (texts or [])[:6]]
    ).lower()
    storm = any(w in hay for w in ("storm", "thunder", "lightning", "ঝড়", "বাজ", "तूफान", "बिजली"))
    rain = storm or any(w in hay for w in ("rain", "monsoon", "drizzle", "বৃষ্টি", "বর্ষা", "बारिश"))
    indoor = any(w in hay for w in (
        "room", "inside", "interior", "house", "flat", "hostel", "hospital", "morgue", "hall", "kitchen",
        "office", "corridor", "cabin", "compartment", "library", "studio", "bedroom", "ward",
        "ঘর", "ভেতর", "ভিতর", "বাড়ি", "ফ্ল্যাট", "হাসপাতাল", "মর্গ", "কামরা", "দরজা", "कमरा", "घर", "अस्पताल",
    ))
    embers = any(w in hay for w in (
        "cremation", "burning ghat", "shmashan", "shoshan", "pyre", "fire", "ash", "furnace", "kiln",
        "শ্মশান", "চিতা", "আগুন", "ভাটা", "ছাই", "श्मशान", "चिता", "आग",
    ))
    fireflies = (not indoor) and (not rain) and any(w in hay for w in (
        "village", "pond", "ghat", "river", "bamboo", "forest", "jungle", "tree", "field", "banyan", "garden",
        "গ্রাম", "পুকুর", "ঘাট", "নদী", "বাঁশ", "জঙ্গল", "বন", "গাছ", "মাঠ", "गाँव", "जंगल", "नदी", "तालाब",
    ))
    lantern = any(w in hay for w in (
        "lantern", "lamp", "candle", "diya", "torch", "flame", "hurricane", "hariken", "prodip",
        "হারিকেন", "লণ্ঠন", "প্রদীপ", "মোমবাতি", "আলো", "লালটে", "दीया", "लालटेन", "मोमबत्ती",
    )) or indoor
    fog_words = any(w in hay for w in (
        "fog", "mist", "smoke", "haze", "river", "ghat", "hill", "winter", "kartik", "poush", "night",
        "কুয়াশা", "ধোঁয়া", "নদী", "পাহাড়", "শীত", "কার্তিক", "পৌষ", "কোহরা", "धुंध",
    ))
    fog = 0.0 if (indoor and not fog_words) else (0.75 if fog_words else (0.55 if mood in ("creepy", "tense", "scare") else 0.30))
    if indoor and fog > 0.35:
        fog = 0.32
    day = any(w in hay for w in ("morning", "noon", "sunlight", "sunny", "daylight", "সকাল", "দুপুর", "সুबह", "दोपहर"))
    night = (not day) or any(w in hay for w in ("night", "midnight", "dark", "dusk", "evening", "রাত", "অন্ধকার", "সন্ধ্যা", "रात", "अँधेरा"))
    return {
        "rain": rain and not indoor,
        "storm": storm,
        "fog": fog,
        "lantern": lantern,
        "fireflies": fireflies and night,
        "embers": embers,
        "night": night,
        "indoor": indoor,
    }


def detect_motion(text="", action="", emotion="", speaker="", ghost_names=()):
    """Map story action/text/emotion into a 2.5D foreground animation verb."""
    hay = f"{action or ''} {text or ''}".lower()
    emo = str(emotion or "").lower()
    spk = str(speaker or "").lower()
    is_ghost = any(g and g.lower() in spk for g in (ghost_names or ())) or any(
        w in hay for w in ("float", "hover", "ghost", "spirit", "shadowy figure", "ভাস", "শূন্যে", "আত্মা", "ছায়ামূর্তি")
    )
    if is_ghost and any(w in hay for w in ("float", "hover", "drift", "glide", "appear", "ভাস", "শূন্যে", "মিলিয়ে")):
        return "ghost_float"
    if any(w in hay for w in ("run", "flee", "rush", "sprint", "chase", "দৌড়", "ছুট", "পালা", "भाग", "दौड़")):
        return "run"
    if any(w in hay for w in ("walk", "step", "approach", "enter", "come closer", "move toward", "হাঁট", "এগিয়ে", "ঢুক", "পা বাড়", "चल", "कदम")):
        return "walk"
    if any(w in hay for w in ("step back", "recoil", "flinch", "freeze", "stumble", "পিছিয়ে", "চমকে", "সরে", "पीछे हट")):
        return "recoil"
    if emo in ("scared", "shout", "crying") or any(w in hay for w in ("trembl", "shiver", "shak", "কাঁপ", "থরথর", "काँप")):
        return "tremble"
    if is_ghost or emo in ("eerie", "angry"):
        return "loom"
    return "idle"


# ------------------------------------------------------------------ audio envelope (pure WAV + ffmpeg fallback)
def voice_envelope(wav_path, fps):
    """Per-frame normalized speech loudness (0..1) from the scene's audio file."""
    if not wav_path or not os.path.exists(wav_path):
        return np.zeros(1, dtype=np.float32)
    a = None
    sr = 44100
    try:
        with wave.open(wav_path, "rb") as w:
            sr = w.getframerate()
            ch = w.getnchannels()
            sw = w.getsampwidth()
            raw = w.readframes(w.getnframes())
            if sw == 2:
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if ch > 1:
                    arr = arr.reshape(-1, ch).mean(axis=1)
                a = arr
    except Exception:
        a = None
    if a is None:
        try:
            raw = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", wav_path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                capture_output=True, check=True,
            ).stdout
            sr = 16000
            a = np.frombuffer(raw, dtype=np.float32)
        except Exception:
            return np.zeros(1, dtype=np.float32)
    if len(a) < 10:
        return np.zeros(1, dtype=np.float32)
    hop = max(1, int(round(sr / float(fps))))
    n = max(1, len(a) // hop)
    rms = np.sqrt(np.mean(a[: n * hop].reshape(n, hop) ** 2, axis=1))
    ref = float(np.percentile(rms, 95)) if n > 4 else float(rms.max())
    if ref < 1e-4:
        return np.zeros(n, dtype=np.float32)
    env = np.clip((rms / ref - 0.08) / 0.92, 0.0, 1.0)
    # smooth slightly across 3 frames for organic mouth/body motion
    if len(env) >= 3:
        env = np.convolve(env, np.array([0.25, 0.5, 0.25], dtype=np.float32), mode="same")
    return env.astype(np.float32)


def audio_duration(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        pass
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out or 0.0)


# ------------------------------------------------------------------ 3-plane 2.5D layer splitter
def _textures(W, H):
    key = (W, H)
    if key in _FX_CACHE:
        return _FX_CACHE[key]
    rnd = np.random.default_rng(2501)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2.0) / (W / 2.0)) ** 2 + ((yy - H / 2.0) / (H / 2.0)) ** 2)
    vig = np.clip(1.12 - 0.44 * (r ** 1.65), 0.34, 1.0)[..., None].astype(np.float32)
    grain = [
        cv2.GaussianBlur((rnd.standard_normal((H, W)) * 3.8).astype(np.float32), (0, 0), 0.7)[..., None]
        for _ in range(6)
    ]
    fog1 = cv2.resize(rnd.uniform(0, 1, (10, 22)).astype(np.float32), (W * 2, H), interpolation=cv2.INTER_CUBIC)
    fog1 = cv2.GaussianBlur(fog1, (0, 0), 27)
    fog1 = np.clip((fog1 - fog1.min()) / (fog1.max() - fog1.min() + 1e-6), 0.0, 1.0)
    fog2 = cv2.resize(rnd.uniform(0, 1, (8, 18)).astype(np.float32), (W * 2, H), interpolation=cv2.INTER_CUBIC)
    fog2 = cv2.GaussianBlur(fog2, (0, 0), 33)
    fog2 = np.clip((fog2 - fog2.min()) / (fog2.max() - fog2.min() + 1e-6), 0.0, 1.0)
    # lower-screen fade for ground mist in front of character legs
    low_band = np.clip((yy - H * 0.48) / (H * 0.52), 0.0, 1.0) ** 1.35
    # warm radial lantern mask
    lx, ly = W * 0.52, H * 0.58
    lr = np.sqrt(((xx - lx) / (W * 0.45)) ** 2 + ((yy - ly) / (H * 0.55)) ** 2)
    lantern = np.clip(1.0 - lr, 0.0, 1.0) ** 2.2
    # fireflies / embers seed positions
    n_p = 28
    px = rnd.uniform(0.05 * W, 0.95 * W, n_p).astype(np.float32)
    py = rnd.uniform(0.18 * H, 0.92 * H, n_p).astype(np.float32)
    ps = rnd.uniform(0.6, 1.8, n_p).astype(np.float32)
    pp = rnd.uniform(0, 2 * math.pi, n_p).astype(np.float32)
    # depth ramp for midground band (bottom 45% soft feathered)
    mid_mask = np.clip((yy - H * 0.52) / (H * 0.16), 0.0, 1.0).astype(np.float32)
    _FX_CACHE[key] = {
        "vig": vig, "grain": grain, "fog1": fog1, "fog2": fog2, "low_band": low_band,
        "lantern": lantern[..., None].astype(np.float32), "mid_mask": mid_mask,
        "particles": (px, py, ps, pp),
    }
    return _FX_CACHE[key]


def _clean_alpha(alpha_u8):
    """Drop tiny stray speckles and soften the cutout edge for clean 2.5D compositing."""
    bw = (alpha_u8 > 120).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if n > 2:
        total = int(bw.sum())
        keep = np.zeros_like(bw)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= max(250, int(0.015 * total)):
                keep[labels == i] = 1
        alpha_u8 = np.where(keep > 0, alpha_u8, 0).astype(np.uint8)
    return cv2.GaussianBlur(alpha_u8, (0, 0), 1.3)


def _fallback_cutout(rgb):
    """Fast OpenCV center-foreground GrabCut fallback if rembg is unavailable (returns mask or None)."""
    h, w = rgb.shape[:2]
    try:
        small = cv2.resize(rgb, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
        sh, sw = small.shape[:2]
        mask = np.zeros((sh, sw), np.uint8)
        rect = (int(sw * 0.14), int(sh * 0.06), int(sw * 0.72), int(sh * 0.90))
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), mask, rect, bgd, fgd, 2, cv2.GC_INIT_WITH_RECT)
        fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        part = (fg > 128).mean()
        if 0.05 <= part <= 0.56:
            return cv2.resize(fg, (w, h), interpolation=cv2.INTER_LINEAR)
    except Exception:
        pass
    return None


def split_25d_layers(img_path, W, H, cutout_fn=None):
    """Load an illustrated scene and split it into 3 depth planes (far BG, midground, foreground character)."""
    key = (img_path, W, H)
    if key in _LAYER_CACHE:
        return _LAYER_CACHE[key]
    if len(_LAYER_CACHE) >= _CACHE_MAX:
        _LAYER_CACHE.pop(next(iter(_LAYER_CACHE)))

    pic = Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS)
    rgb = np.array(pic)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    alpha = None
    if cutout_fn is not None:
        try:
            alpha = cutout_fn(pic, W, H)
        except Exception:
            alpha = None
    if alpha is None:
        try:
            from rembg import remove, new_session
            if "_rembg_sess" not in _FX_CACHE:
                try:
                    _FX_CACHE["_rembg_sess"] = new_session("isnet-general-use")
                except Exception:
                    _FX_CACHE["_rembg_sess"] = new_session("u2netp")
            m = remove(pic, session=_FX_CACHE["_rembg_sess"], only_mask=True).convert("L").resize((W, H))
            alpha = np.array(m)
        except Exception:
            alpha = _fallback_cutout(rgb)

    d = {"bg": bgr, "has_fg": False, "cx": W * 0.5, "head_y": H * 0.36, "feet_y": H * 0.92, "faces": []}
    if alpha is not None:
        alpha = _clean_alpha(alpha)
        cov = float((alpha > 128).mean())
        if 0.025 <= cov <= 0.68:
            hole = cv2.dilate((alpha > 36).astype(np.uint8) * 255, np.ones((27, 27), np.uint8))
            sm_bgr = cv2.resize(bgr, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
            sm_hole = cv2.resize(hole, (W // 2, H // 2), interpolation=cv2.INTER_NEAREST)
            inp = cv2.inpaint(sm_bgr, sm_hole, 9, cv2.INPAINT_TELEA)
            bg_clean = cv2.resize(inp, (W, H), interpolation=cv2.INTER_CUBIC)
            soft_hole = cv2.GaussianBlur(hole.astype(np.float32) / 255.0, (0, 0), 4.0)[..., None]
            bg_clean = np.clip(bgr * (1.0 - soft_hole) + cv2.GaussianBlur(bg_clean, (0, 0), 2.5) * soft_hole, 0, 255).astype(np.uint8)

            ys, xs = np.nonzero(alpha > 128)
            y0, y1 = int(ys.min()), int(ys.max())
            d.update(
                bg=bg_clean,
                has_fg=True,
                fg=bgr.astype(np.float32),
                fg_rgb=rgb.astype(np.float32),
                fg_a=(alpha.astype(np.float32) / 255.0),
                cx=float(xs.mean()),
                head_y=float(y0 + 0.25 * (y1 - y0)),
                feet_y=float(y1),
                bbox=(int(xs.min()), y0, int(xs.max()), y1),
            )
            # Detect faces via animate.py if present in the repo
            try:
                import animate
                faces = animate.find_faces(np.ascontiguousarray(rgb))
                d["faces"] = sorted(faces, key=lambda f_: -f_.get("mouth", [0, 0, 0])[2])
            except Exception:
                d["faces"] = []
    _LAYER_CACHE[key] = d
    return d


# ------------------------------------------------------------------ 2.5D shot planner
def plan_25d_shots(segments, total, talk=None, mood="creepy"):
    """Split scene segments into varied 2.5D camera shots: [(img, st, en, kind)]."""
    segs = []
    for k, (img, st) in enumerate(segments):
        en = segments[k + 1][1] if k + 1 < len(segments) else total
        if segs and segs[-1][0] == img:
            segs[-1] = (img, segs[-1][1], en)
        else:
            segs.append((img, st, en))
    talk = talk or []
    out = []
    cycle = ("establish_dolly", "parallax_lr", "dramatic_closeup", "parallax_rl", "low_rise")
    for si, (img, st, en) in enumerate(segs):
        d = max(0.2, en - st)
        parts = 1 if d < 6.5 else (2 if d < 13.5 else 3)
        for p in range(parts):
            a = st + d * p / parts
            b = st + d * (p + 1) / parts
            mid_t = 0.5 * (a + b)
            active_talk = next((tl for tl in talk if tl[0] <= mid_t < tl[1]), None)
            emo = str(active_talk[3] if active_talk and len(active_talk) > 3 else "").lower()
            is_dialogue = bool(active_talk and not active_talk[2])
            if emo in ("scared", "shout", "crying", "angry") or (mood == "scare" and p == parts - 1):
                kind = "dramatic_closeup"
            elif si == 0 and p == 0:
                kind = "establish_dolly"
            elif is_dialogue and p % 2 == 1:
                kind = "dramatic_closeup"
            else:
                kind = cycle[(si + p) % len(cycle)]
            out.append((img, a, b, kind))
    return out


# ------------------------------------------------------------------ 2.5D weather & lighting layers
def _draw_rain(frame, W, H, f, storm=False):
    """Dual-depth diagonal cartoon rain streaks (fast foreground drops + subtle far drops)."""
    rng = np.random.default_rng(7000 + f)
    overlay = np.zeros((H, W, 3), dtype=np.uint8)
    n_far = 65 if storm else 40
    n_near = 35 if storm else 22
    for n_, length, thick, col in ((n_far, 22, 1, (170, 185, 200)), (n_near, 46, 2, (215, 228, 240))):
        xs = rng.integers(0, W, n_)
        ys = rng.integers(0, H, n_)
        dx = -int(length * (0.28 if storm else 0.18))
        for x, y in zip(xs, ys):
            cv2.line(overlay, (int(x), int(y)), (int(x) + dx, int(y) + length), col, thick, cv2.LINE_AA)
    return frame + overlay.astype(np.float32) * (0.38 if storm else 0.28)


def _draw_particles(frame, W, H, sec, tex, embers=False):
    """Glowing fireflies (village/jungle night) or rising red-amber embers (cremation/fire)."""
    px, py, ps, pp = tex["particles"]
    overlay = np.zeros((H, W, 3), dtype=np.float32)
    col = (35.0, 125.0, 255.0) if embers else (95.0, 235.0, 215.0)
    for x0, y0, spd, ph in zip(px, py, ps, pp):
        if embers:
            x = int((x0 + 26.0 * math.sin(sec * 1.4 * spd + ph)) % W)
            y = int((y0 - sec * 55.0 * spd) % H)
            glow = 0.55 + 0.45 * math.sin(sec * 6.0 * spd + ph)
            rad = 2 if spd < 1.2 else 3
        else:
            x = int((x0 + 38.0 * math.sin(sec * 0.7 * spd + ph)) % W)
            y = int((y0 + 24.0 * math.cos(sec * 0.9 * spd + ph)) % H)
            glow = max(0.0, math.sin(sec * 2.2 * spd + ph)) ** 2
            rad = 3 if spd < 1.3 else 4
        if glow > 0.15:
            cv2.circle(overlay, (x, y), rad + 3, tuple(c * 0.35 * glow for c in col), -1, cv2.LINE_AA)
            cv2.circle(overlay, (x, y), rad, tuple(c * glow for c in col), -1, cv2.LINE_AA)
    return frame + overlay


def _fog_slice(fog_tex, W, off):
    off = int(off) % W
    sl = fog_tex[:, off : off + W]
    if sl.shape[1] < W:
        sl = np.concatenate([sl, fog_tex[:, : W - sl.shape[1]]], axis=1)
    return sl


# ------------------------------------------------------------------ single 2.5D frame renderer
def render_frame_25d(
    L, W, H, f, sec, t_norm, shot_kind, mood, wx, tex,
    flicker_val=0.0, mouth=0.0, blink=0.0, shape="a", gaze=(0.0, 0.0),
    speaking=False, emo="", motion_verb="idle", jump_dt=None, flash_on=False,
    ghost_face=None, direction=1, animate_mod=None,
):
    """Render one full 2.5D multi-plane animated cartoon frame (float32 BGR -> uint8 BGR)."""
    ease = 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t_norm)))
    cx, head_y, feet_y = L["cx"], L["head_y"], L["feet_y"]

    # Camera shake (handheld horror tension + jump scare jolt)
    shx = shy = 0.0
    if mood in ("tense", "scare"):
        shx += 2.0 * math.sin(sec * 5.8) + 1.1 * math.sin(sec * 10.7 + 1.2)
        shy += 1.4 * math.cos(sec * 4.9)
    if jump_dt is not None and 0.0 <= jump_dt < 0.7:
        amp = 13.0 * (1.0 - jump_dt / 0.7)
        shx += amp * math.sin(jump_dt * 75.0)
        shy += amp * 0.7 * math.cos(jump_dt * 62.0)

    # 2.5D Camera Choreography (pan + dolly zoom)
    if shot_kind == "dramatic_closeup":
        fx, fy = cx, head_y
        bz = 1.26 + 0.12 * ease
        pan_x = direction * (ease - 0.5) * 18.0
        pan_y = -6.0 * ease
        focus_pull = 1.0
    elif shot_kind == "parallax_lr":
        fx, fy = W * 0.5, H * 0.5
        bz = 1.08 + 0.05 * ease
        pan_x = (ease - 0.5) * 58.0
        pan_y = 0.0
        focus_pull = 0.0
    elif shot_kind == "parallax_rl":
        fx, fy = W * 0.5, H * 0.5
        bz = 1.08 + 0.05 * ease
        pan_x = -(ease - 0.5) * 58.0
        pan_y = 0.0
        focus_pull = 0.0
    elif shot_kind == "low_rise":
        fx, fy = cx, H * 0.56
        bz = 1.10 + 0.08 * ease
        pan_x = direction * (ease - 0.5) * 16.0
        pan_y = (0.5 - ease) * 34.0
        focus_pull = 0.45
    else:  # establish_dolly
        fx, fy = W * 0.5, H * 0.5
        bz = 1.04 + 0.09 * ease
        pan_x = direction * (ease - 0.5) * 28.0
        pan_y = -4.0 * ease
        focus_pull = 0.0

    if jump_dt is not None and 0.0 <= jump_dt < 0.45:
        bz += 0.14 * (1.0 - jump_dt / 0.45)

    # --- LAYER 1: Far Background (0.62x parallax) ---
    bg_z = bz
    Mb = cv2.getRotationMatrix2D((fx, fy), 0.0, bg_z)
    Mb[0, 2] += (W * 0.5 - fx) * (bg_z - 1.0) / bg_z * focus_pull + pan_x * 0.62 + shx * 0.85
    Mb[1, 2] += (H * 0.5 - fy) * (bg_z - 1.0) / bg_z * focus_pull + pan_y * 0.62 + shy * 0.85
    frame = cv2.warpAffine(L["bg"], Mb, (W, H), borderMode=cv2.BORDER_REFLECT).astype(np.float32)

    # --- LAYER 2: Midground Depth Band (0.90x parallax) + Background Volumetric Fog ---
    if not L["has_fg"]:
        # Pure scenery / empty room: synthesize lower-foreground perspective shift for real 2.5D depth
        Mm = cv2.getRotationMatrix2D((fx, fy), 0.0, bz * 1.035)
        Mm[0, 2] += (W * 0.5 - fx) * (bz - 1.0) / bz * focus_pull + pan_x * 1.15 + shx
        Mm[1, 2] += (H * 0.5 - fy) * (bz - 1.0) / bz * focus_pull + pan_y * 1.15 + shy
        mid_img = cv2.warpAffine(L["bg"], Mm, (W, H), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
        mm = tex["mid_mask"][..., None]
        frame = frame * (1.0 - mm) + mid_img * mm
    else:
        # Subtle midground ground shift behind the character
        Mm = cv2.getRotationMatrix2D((fx, fy), 0.0, bz * 1.018)
        Mm[0, 2] += (W * 0.5 - fx) * (bz - 1.0) / bz * focus_pull + pan_x * 0.90 + shx * 0.92
        Mm[1, 2] += (H * 0.5 - fy) * (bz - 1.0) / bz * focus_pull + pan_y * 0.90 + shy * 0.92
        mid_img = cv2.warpAffine(L["bg"], Mm, (W, H), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
        mm = (tex["mid_mask"] * 0.65)[..., None]
        frame = frame * (1.0 - mm) + mid_img * mm

    # Background fog behind the foreground character (depth separation!)
    if wx["fog"] > 0.05:
        fg1 = _fog_slice(tex["fog1"], W, sec * 19.0)
        frame = frame + fg1[..., None] * np.array([34.0, 32.0, 28.0], np.float32) * (wx["fog"] * 0.85)

    # --- LAYER 3: Foreground Illustrated Character (1.38x parallax + story acting + face anim) ---
    if L["has_fg"]:
        src = L["fg"]
        if animate_mod is not None and L.get("faces"):
            try:
                pic = animate_mod.draw_face(L["fg_rgb"], L["faces"], blink, 0.0, "a", gaze)
                pic = animate_mod.draw_face(pic, L["faces"][:1], 0.0, mouth, shape)
                src = cv2.cvtColor(np.clip(pic, 0, 255).astype(np.float32), cv2.COLOR_RGB2BGR)
            except Exception:
                src = L["fg"]


        # Story motion verbs + foot-anchored breathing & vocal emphasis
        char_dx = 0.0
        char_dy = 0.0
        char_rot = 0.45 * math.sin(sec * 1.05)
        char_scale = 1.0 + 0.006 * math.sin(sec * 1.85)
        char_alpha = 1.0

        if motion_verb == "walk":
            char_dx += direction * (ease - 0.5) * 32.0
            char_dy -= abs(math.sin(sec * math.pi * 2.1)) * 7.5
            char_rot += 1.4 * math.sin(sec * math.pi * 2.1)
        elif motion_verb == "run":
            char_dx += direction * (ease - 0.5) * 52.0
            char_dy -= abs(math.sin(sec * math.pi * 3.6)) * 12.0
            char_rot += 2.6 * math.sin(sec * math.pi * 3.6)
        elif motion_verb == "recoil":
            char_dx -= direction * 18.0 * ease
            char_scale -= 0.025 * ease
            char_rot -= direction * 1.6 * ease
        elif motion_verb == "ghost_float":
            char_dy -= 14.0 + 10.0 * math.sin(sec * 2.1)
            char_rot = 1.1 * math.sin(sec * 1.4)
            char_alpha = 0.84 + 0.12 * math.sin(sec * 2.8)
        elif motion_verb == "tremble":
            char_dx += 2.2 * math.sin(sec * 48.0)
            char_dy += 1.2 * math.cos(sec * 41.0)
        elif motion_verb == "loom":
            char_scale += 0.045 * ease
            char_dy -= 4.0 * ease

        if speaking:
            char_dy -= 3.2 * mouth
            char_scale += 0.008 * mouth
            char_rot += 0.55 * math.sin(sec * 6.5) * mouth

        # Pivot character transform near feet so feet remain grounded while upper body breathes/sways
        fz = bz * (1.032 + 0.028 * ease) * char_scale
        pivot_x, pivot_y = cx, feet_y
        Mf = cv2.getRotationMatrix2D((pivot_x, pivot_y), char_rot, fz)
        # Anchor foreground at the same camera-projected pivot, plus stronger 1.38x 2.5D parallax shift!
        cam_px = Mb[0, 0] * pivot_x + Mb[0, 1] * pivot_y + Mb[0, 2]
        cam_py = Mb[1, 0] * pivot_x + Mb[1, 1] * pivot_y + Mb[1, 2]
        Mf[0, 2] += (cam_px - pivot_x) + pan_x * 0.76 + char_dx + shx * 0.25
        Mf[1, 2] += (cam_py - pivot_y) + pan_y * 0.55 + char_dy + shy * 0.25

        fgw = cv2.warpAffine(src, Mf, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        aw = cv2.warpAffine(L["fg_a"], Mf, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        if L.get("bbox") and not wx["indoor"]:
            # Gentle outdoor hair breeze strictly on top crown (never distorts face/eyes)
            _, by0, _, by1 = L["bbox"]
            hair_end = min(H, max(8, int(by0 + 0.11 * (by1 - by0))))
            ys_h = np.arange(hair_end, dtype=np.float32)
            taper = np.clip(1.0 - ys_h / float(hair_end), 0.0, 1.0) ** 1.6
            shifts = (1.6 * taper * np.sin(sec * 2.8 + ys_h * 0.05)).astype(np.int32)
            for row_i, sh_px in enumerate(shifts):
                if sh_px != 0:
                    fgw[row_i] = np.roll(fgw[row_i], int(sh_px), axis=0)
                    aw[row_i] = np.roll(aw[row_i], int(sh_px), axis=0)
        aw = np.clip(aw * char_alpha, 0.0, 1.0)[..., None]

        # Subtle warm rim glow on character edge when lantern/indoor is active
        if wx["lantern"]:
            warm = 0.06 * (0.75 + 0.25 * math.sin(sec * 7.3) + 0.15 * math.sin(sec * 15.1))
            fgw = fgw * np.array([1.0 - warm * 0.3, 1.0 + warm * 0.25, 1.0 + warm * 0.85], np.float32)

        frame = frame * (1.0 - aw) + fgw * aw

    # --- LAYER 4: Foreground Atmosphere, Weather, Lantern Glow & Cartoon Film Grade ---
    if wx["fog"] > 0.1:
        fg2 = _fog_slice(tex["fog2"], W, -sec * 34.0) * tex["low_band"]
        frame = frame + fg2[..., None] * np.array([42.0, 40.0, 36.0], np.float32) * (wx["fog"] * 0.7)

    if wx["rain"]:
        frame = _draw_rain(frame, W, H, f, storm=wx["storm"])

    if wx["embers"]:
        frame = _draw_particles(frame, W, H, sec, tex, embers=True)
    elif wx["fireflies"]:
        frame = _draw_particles(frame, W, H, sec, tex, embers=False)

    if wx["lantern"]:
        pulse = 0.85 + 0.15 * math.sin(sec * 6.4) + 0.10 * math.sin(sec * 14.7)
        frame = frame + tex["lantern"] * np.array([6.0, 18.0, 34.0], np.float32) * pulse

    # Crisp dark Bengali horror cartoon grade (preserves rich cartoon ink & color contrast)
    gray = frame.mean(axis=2, keepdims=True)
    frame = frame * 0.90 + gray * 0.10
    if wx["night"]:
        frame *= np.array([1.05, 0.99, 0.93], np.float32)  # cool midnight shadows, clear faces
    frame = (frame - 128.0) * 1.06 + 128.0                  # gentle cartoon contrast pop
    frame *= tex["vig"]
    if mood in ("creepy", "tense", "scare") and flicker_val > 0.0:
        frame *= (1.0 - 0.09 * flicker_val)
    frame += tex["grain"][f % 6]

    # Jump-scare ghost-face flash + crimson vignette
    if jump_dt is not None and -0.04 <= jump_dt < 0.36:
        if ghost_face is not None:
            a_ = 0.88 if jump_dt < 0.20 else 0.88 * (0.36 - jump_dt) / 0.16
            gf = ghost_face if ghost_face.shape[:2] == (H, W) else cv2.resize(ghost_face, (W, H))
            frame = frame * (1.0 - a_) + gf.astype(np.float32) * a_
        frame[..., 2] += 36.0 * max(0.0, 1.0 - abs(jump_dt) / 0.36)

    # Lightning flash synced to thunder
    if flash_on:
        frame = frame * 0.38 + np.array([255.0, 246.0, 236.0], np.float32) * 0.62

    return np.clip(frame, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ full scene clip renderer
def render_scene(
    segments, audio, out, idx, mood="creepy", talk=None, meta=None,
    W=1280, H=720, FPS=25, SR=44100, scene_fx=None, ghost_face=None,
    vhs=False, vhs_fn=None, cutout_fn=None, log=print,
):
    """Render one complete True 2.5D Illustrated Cartoon clip (MP4 H.264 + AAC) matched to the scene audio."""
    dur = audio_duration(audio)
    if dur <= 0.05:
        raise RuntimeError("scene audio has zero length")
    meta = meta or {}
    talk = talk or []
    env_track = voice_envelope(audio, FPS)
    try:
        import animate as animate_mod
    except Exception:
        animate_mod = None

    wx = detect_weather(
        place=meta.get("place", ""),
        ambience=meta.get("ambience") or [],
        mood=mood,
        texts=[t[4] for t in talk if len(t) > 4] + list(meta.get("actions") or []),
    )
    tex = _textures(W, H)
    shots = plan_25d_shots(segments, dur, talk, mood)
    n_frames = max(1, int(round(dur * FPS)))

    rnd = np.random.default_rng(idx + 250)
    flicker = (rnd.uniform(0, 1, 400) > 0.93).astype(np.float32) * rnd.uniform(0.35, 1.0, 400)
    blinks, bt = [], float(rnd.uniform(0.8, 2.4))
    while bt < dur:
        blinks.append(bt)
        bt += float(rnd.uniform(2.4, 4.8))
    blinks += [tl[0] + 0.05 for tl in talk]

    looks, lt = [], 0.0
    while lt < dur:
        looks.append((lt, float(rnd.uniform(-0.32, 0.32)), float(rnd.uniform(-0.18, 0.18))))
        lt += float(rnd.uniform(1.1, 2.5))
    gaze_now = [0.0, 0.0]

    actions_list = meta.get("actions") or []
    ghost_names = meta.get("ghost_names") or []
    fxi = scene_fx or {}

    ff = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-i", audio, "-t", f"{dur:.2f}",
            "-vf", f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.0, dur - 0.4):.2f}:d=0.4,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-maxrate", "3800k", "-bufsize", "7600k",
            "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-ac", "2", out,
        ],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    XF = 8
    prev_last, cur_k, frame_in_shot = None, -1, 0
    try:
        for f in range(n_frames):
            sec = f / float(FPS)
            k = next((i for i, s in enumerate(shots) if s[1] <= sec < s[2]), len(shots) - 1)
            img, st, en, shot_kind = shots[k]
            if k != cur_k:
                cur_k, frame_in_shot = k, 0
            L = split_25d_layers(img, W, H, cutout_fn=cutout_fn)
            t_norm = min(1.0, max(0.0, (sec - st) / max(en - st, 0.1)))

            mouth, emo, shape, speaking, verb = 0.0, "", "a", False, "idle"
            for ti, tl in enumerate(talk):
                ta, tb, nar, em, tx = tl[0], tl[1], tl[2], tl[3], tl[4]
                if ta <= sec < tb:
                    emo = str(em or "").lower()
                    act_txt = actions_list[ti] if ti < len(actions_list) else ""
                    spk_txt = meta.get("speakers", [""] * len(talk))[ti] if ti < len(meta.get("speakers", [])) else ""
                    verb = detect_motion(tx, act_txt, emo, spk_txt, ghost_names)
                    if not nar and f < len(env_track):
                        mouth = float(env_track[f])
                        speaking = mouth > 0.08
                        if animate_mod is not None:
                            try:
                                shape = animate_mod.viseme_at(tx, sec - ta, tb - ta)
                                if shape == "m":
                                    mouth = 0.0
                            except Exception:
                                shape = "a"
                    break

            blink = 0.0
            for b0 in blinks:
                if 0.0 <= sec - b0 < 0.19:
                    blink = math.sin(math.pi * (sec - b0) / 0.19)
                    break

            lx, ly = 0.0, 0.0
            for t0_, gx_, gy_ in looks:
                if t0_ <= sec:
                    lx, ly = gx_, gy_
            if emo in ("scared", "whisper", "shout") or mood in ("tense", "scare"):
                lx = 0.55 * math.sin(sec * 6.5) + 0.18 * math.sin(sec * 15.0)
            elif emo in ("sad", "crying"):
                ly = 0.5
            gaze_now[0] += (lx - gaze_now[0]) * 0.35
            gaze_now[1] += (ly - gaze_now[1]) * 0.35

            jump_dt = None
            for jt in fxi.get("jump", []):
                if -0.05 <= sec - jt < 0.72:
                    jump_dt = sec - jt
                    break
            flash_on = any((0.0 <= sec - fl < 0.10) or (0.22 <= sec - fl < 0.30) for fl in fxi.get("flash", []))

            u8 = render_frame_25d(
                L, W, H, f, sec, t_norm, shot_kind, mood, wx, tex,
                flicker_val=float(flicker[f % len(flicker)]),
                mouth=mouth, blink=blink, shape=shape, gaze=tuple(gaze_now),
                speaking=speaking, emo=emo, motion_verb=verb,
                jump_dt=jump_dt, flash_on=flash_on, ghost_face=ghost_face,
                direction=1 if (idx + k) % 2 == 0 else -1,
                animate_mod=animate_mod,
            )

            if prev_last is not None and k > 0 and frame_in_shot < XF:
                a_ = (frame_in_shot + 1) / float(XF + 1)
                u8 = cv2.addWeighted(prev_last, 1.0 - a_, u8, a_, 0.0)
            frame_in_shot += 1
            if f + 1 < n_frames:
                nk = next((i for i, s in enumerate(shots) if s[1] <= (f + 1) / float(FPS) < s[2]), len(shots) - 1)
                if nk != k:
                    prev_last = u8.copy()
            if vhs and vhs_fn is not None:
                u8 = vhs_fn(u8, f, sec)
            ff.stdin.write(u8.tobytes())
        ff.stdin.close()
    except Exception:
        ff.kill()
        raise
    if ff.wait() != 0:
        raise RuntimeError(ff.stderr.read().decode()[-600:])
    return dur
