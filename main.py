#!/usr/bin/env python3
"""
Horror Story Bot (Hindi + Bengali)
----------------------------------
Every run makes ONE brand-new, original horror story video and posts it to a
Facebook Page (and YouTube, if YouTube secrets are set):

  1. Google Gemini          -> story with dialogue, title, description, hashtags
  2. Cloudflare Workers AI  -> realistic, cinematic pictures (same characters in every scene)
  3. Microsoft Edge voices  -> narrator + a different voice for every character (gTTS backup)
  4. Built-in sound engine  -> wind, rain, thunder, heartbeat, footsteps, creaks... (no copyright)
  5. FFmpeg + OpenCV        -> moving picture layers, fog, grain, flicker, subtitles
  6. Facebook / YouTube APIs

Languages alternate: Hindi, Bengali, Hindi, ...

Secrets (GitHub > Settings > Secrets > Actions):
  GEMINI_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, FB_PAGE_ID, FB_PAGE_TOKEN
Optional:
  PAGE_NAME_HI, PAGE_NAME_BN        page/channel name said at the end
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN   -> also upload to YouTube
  LANGUAGE=hi|bn (force), DRY_RUN=1 (don't post), MOCK=1 (offline test)
"""
import asyncio
import base64
import datetime as dt
import glob
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import wave

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ----------------------------------------------------------------- settings
W, H, FPS, SR = 1280, 720, 25, 44100
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")
HISTORY = os.path.join(HERE, "history.json")
SFX_DIR = os.path.join(HERE, "sfx")          # optional: your own sounds, e.g. sfx/rain.mp3

MOCK = os.getenv("MOCK") == "1"
DRY_RUN = MOCK or os.getenv("DRY_RUN") == "1"

LANGS = {
    "hi": {
        "name": "Hindi", "script": "Devanagari",
        "font_family": "Noto Sans Devanagari", "font_glob": "NotoSansDevanagari",
        "male": ["hi-IN-MadhurNeural"], "female": ["hi-IN-SwaraNeural"],
        "narrator": ("hi-IN-MadhurNeural", "-6%", "-6Hz"), "gtts": "hi",
        "label": "भूतिया कहानी",
        "intro": "आज की डरावनी कहानी है... {title}।",
        "outro": "कहानी कैसी लगी, कमेंट में ज़रूर बताइए। और ऐसी ही डरावनी कहानियों के लिए {page} को फॉलो कीजिए।",
        "page_default": "हमारे पेज",
        "ai_note": "🎨 यह कहानी और तस्वीरें AI की मदद से बनाई गई हैं। सब काल्पनिक है।",
    },
    "bn": {
        "name": "Bengali", "script": "Bengali",
        "font_family": "Noto Sans Bengali", "font_glob": "NotoSansBengali",
        "male": ["bn-IN-BashkarNeural", "bn-BD-PradeepNeural"],
        "female": ["bn-IN-TanishaaNeural", "bn-BD-NabanitaNeural"],
        "narrator": ("bn-IN-BashkarNeural", "-6%", "-6Hz"), "gtts": "bn",
        "label": "ভৌতিক গল্প",
        "intro": "আজকের ভৌতিক গল্প... {title}।",
        "outro": "গল্পটা কেমন লাগল কমেন্টে জানাবেন। আর এরকম আরও ভৌতিক গল্পের জন্য {page} ফলো করুন।",
        "page_default": "আমাদের পেজ",
        "ai_note": "🎨 এই গল্প ও ছবি AI-এর সাহায্যে তৈরি। সবকিছু কাল্পনিক।",
    },
}

THEMES = [
    "an old haveli where a lamp lights itself every night", "an abandoned railway station and the last train",
    "a village well that whispers names", "a lonely highway dhaba after midnight",
    "a hostel room that is always cold", "a huge banyan tree at the edge of the village",
    "a boat ride across the river on a moonless night", "an ancestral house during the monsoon",
    "a school after everyone has gone home", "a forest bungalow with a locked room",
    "an old photo studio and a photograph that changes", "a night bus with one extra passenger",
    "a wedding house where one guest has no shadow", "a hospital night shift",
    "a doll found in an old trunk", "a radio that plays a station that closed years ago",
    "a fisherman's village and a voice from the water", "a temple bell that rings at 3 am",
    "a new flat in an old building", "a mirror bought from a house auction",
]

SOUND_TAGS = ["wind", "rain", "thunder", "crickets", "owl", "heartbeat", "footsteps", "creak",
              "whisper", "clock", "howl", "drip", "knock", "scare_hit"]
MOODS = ["calm", "creepy", "tense", "scare", "sad"]

ART_STYLE = ("cinematic photorealistic film still, horror movie atmosphere, dark moody low-key lighting, "
             "cold blue and green tones with warm lamp light, light fog, realistic Indian people and places, "
             "35mm photo, shallow depth of field, highly detailed, eerie but not gory, no blood, no gore, "
             "no text, no letters, no watermark")


def log(*a):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}]", *a, flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd[:3])}...\n{r.stderr[-2000:]}")
    return r.stdout


def env(name):
    return (os.getenv(name) or "").strip()


def need_env(name):
    v = env(name)
    if not v:
        sys.exit(f"ERROR: secret {name} is missing. Add it in GitHub > Settings > Secrets > Actions.")
    return v


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", path]).strip())


def ascii_text(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\x20-\x7E]", " ", str(s))).strip()


# ----------------------------------------------------------------- history
def load_history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(items):
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(items[-200:], f, ensure_ascii=False, indent=1)


def pick_language(history):
    forced = env("LANGUAGE").lower()
    if forced in LANGS:
        return forced
    last = history[-1].get("lang") if history else "bn"
    return "bn" if last == "hi" else "hi"


def pick_theme(history):
    used = [h.get("theme") for h in history[-12:]]
    options = [t for t in THEMES if t not in used] or THEMES
    return random.choice(options)


# ----------------------------------------------------------------- 1. story (Gemini)
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def gemini_models(key):
    tries = [env("GEMINI_MODEL")] if env("GEMINI_MODEL") else []
    tries.append("gemini-flash-latest")
    try:
        r = requests.get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": key},
                         params={"pageSize": 200}, timeout=30)
        names = []
        for m in r.json().get("models", []):
            n = m.get("name", "").replace("models/", "")
            if ("generateContent" in m.get("supportedGenerationMethods", []) and "flash" in n
                    and not any(x in n for x in ("image", "tts", "audio", "live", "embed", "exp"))):
                names.append(n)

        def ver(n):
            nums = re.findall(r"\d+(?:\.\d+)?", n)
            return (float(nums[0]) if nums else 0, "lite" not in n, "preview" not in n)
        tries += sorted(names, key=ver, reverse=True)
    except Exception as e:
        log("Could not list Gemini models:", e)
    tries += ["gemini-2.5-flash"]
    out = []
    for t in tries:
        if t and t not in out:
            out.append(t)
    return out


def make_story(lang, theme, history):
    if MOCK:
        return mock_story(lang)
    key = need_env("GEMINI_API_KEY")
    L = LANGS[lang]
    old_titles = [h["title"] for h in history[-60:] if h.get("lang") == lang]
    prompt = f"""
You are India's best {L['name']} horror storyteller, writing for a horror story video page.
Write ONE brand-new, ORIGINAL horror story in {L['name']} ({L['script']} script; simple, natural,
spoken {L['name']} that ordinary people use). Idea to build on: {theme}.
Do NOT retell famous stories, films or real incidents, and do not use real people or real place names.
Must be different from these earlier stories: {json.dumps(old_titles, ensure_ascii=False)}

Story rules:
- 10 to 12 scenes, about 3-4 minutes when spoken. Slow-burn build-up, rising fear, a strong twist at the end.
- Spooky and suspenseful, NOT gory: no blood, no violence details, no harm to children, nothing sexual.
- 2 to 4 characters plus a narrator. Real dialogue between characters (short, natural lines).
- Each scene has 1 to 5 lines. The narrator describes; characters speak only their own words
  (no "he said" inside dialogue). Narrator lines 15-45 words, dialogue lines 3-20 words.
- Every picture must show exactly what that scene's lines describe.

Return ONLY JSON with exactly these keys:
{{
 "title": "chilling {L['name']} title, max 60 characters, 1 emoji",
 "thumbnail_text": "2-4 scary punchy {L['name']} words for the thumbnail",
 "description": "3-4 line suspenseful {L['name']} description that makes people want to watch, ending with a question",
 "hashtags": ["10-14 popular hashtags mixing {L['name']} and English, e.g. #HorrorStory #BhootKiKahani"],
 "setting": "ENGLISH: the ONE main place of the story (architecture, objects, era, weather, time of night, colors). Reused in every picture",
 "characters": [{{"name": "name in English letters", "gender": "male or female",
                  "age": "child, young, adult or old", "kind": "human or ghost",
                  "look": "ENGLISH, very specific never-changing look: age, face, hair, skin, clothes with exact colors, one special detail. 20-35 words"}}],
 "thumbnail_image": {{"characters": ["names"], "action": "ENGLISH: the scariest moment, faces showing fear, eerie light"}},
 "scenes": [{{
    "characters": ["names VISIBLE in the picture"],
    "action": "ENGLISH: exactly what happens in this scene: who does what, poses, expressions, key objects",
    "place": "ENGLISH: where in the setting + lighting",
    "mood": "one of {MOODS}",
    "sounds": ["0-3 from {SOUND_TAGS}"],
    "lines": [{{"speaker": "narrator or a character name", "text": "{L['name']} text"}}]
 }}],
 "ending_line": "one short {L['name']} line from the narrator that leaves a chill"
}}
"""
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0, "responseMimeType": "application/json"}}
    last_err = None
    models = gemini_models(key)
    for round_no in range(3):
        if round_no:
            log(f"All Gemini models busy - waiting {90 * round_no} s")
            time.sleep(90 * round_no)
        for model in list(models):
            try:
                log(f"Writing story with {model} ...")
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent",
                                  headers={"x-goog-api-key": key}, json=body, timeout=110)
                if r.status_code in (404, 400):
                    raise LookupError(r.text[:300])
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"busy ({r.status_code})")
                r.raise_for_status()
                cand = r.json()["candidates"][0]
                text = cand["content"]["parts"][0]["text"]
                text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
                story = json.loads(text)
                assert story.get("title") and len(story.get("scenes", [])) >= 6
                assert all(s.get("lines") for s in story["scenes"])
                return story
            except LookupError as e:
                last_err = e
                models.remove(model)
            except Exception as e:
                last_err = e
                log("  trying next model:", str(e)[:200])
                time.sleep(5)
    raise RuntimeError(f"Gemini failed: {last_err}")


# ----------------------------------------------------------------- 2. pictures (Cloudflare)
CF_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
CF_BACKUP = "@cf/black-forest-labs/flux-1-schnell"


def fit(img, w=W, h=H):
    """Whole picture in a w x h frame, nothing cut; empty sides filled with a dark blurred copy."""
    img = img.convert("RGB")
    if abs(img.width / img.height - w / h) < 0.03:
        return img.resize((w, h), Image.LANCZOS)
    s = max(w / img.width, h / img.height)
    bg = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    l, t = (bg.width - w) // 2, (bg.height - h) // 2
    bg = bg.crop((l, t, l + w, t + h)).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (w, h), (0, 0, 0)), 0.45)
    s = min(w / img.width, h / img.height)
    fg = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return bg


class Cast:
    def __init__(self, story):
        self.setting = ascii_text(story.get("setting", ""))
        self.chars = {}        # key -> dict(name, look, gender, age, kind)
        for c in story.get("characters", []) or []:
            if isinstance(c, dict) and c.get("name"):
                k = ascii_text(c["name"]).lower()
                self.chars[k] = {"name": ascii_text(c["name"]), "look": ascii_text(c.get("look", "")),
                                 "gender": str(c.get("gender", "male")).lower(),
                                 "age": str(c.get("age", "adult")).lower(),
                                 "kind": str(c.get("kind", "human")).lower()}
        self.ref = None

    def find(self, name):
        k = ascii_text(name).lower()
        if not k:
            return None
        return self.chars.get(k) or next((v for kk, v in self.chars.items() if k in kk or kk in k), None)

    def pick(self, names):
        out = []
        for n in names or []:
            c = self.find(n)
            if c and c not in out:
                out.append(c)
        return out or list(self.chars.values())

    def describe(self, chosen):
        return " ".join(f"{c['name']}: {c['look']}." for c in chosen)

    def scene_prompt(self, action, place, names, use_ref):
        low = ascii_text(action).lower()
        names = list(names or []) + [c["name"] for c in self.chars.values() if c["name"].lower() in low]
        who = self.describe(self.pick(names))
        p = (f"{ART_STYLE}. Setting: {self.setting}. {ascii_text(place)}. "
             f"People in this picture (show ONLY these, each exactly as described): {who} "
             f"What is happening: {ascii_text(action)}.")
        if use_ref:
            p = ("Image 0 is the cast reference photo. Show the same people with exactly the same faces, "
                 "hair, body and clothes as in image 0, but in a brand-new full scene with a complete "
                 "background (not a reference sheet). " + p)
        return p


def cf_request(model, prompt, ref_path=None, w=1280, h=720, seed=None):
    acct, token = need_env("CF_ACCOUNT_ID"), need_env("CF_API_TOKEN")
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}"
    hdr = {"Authorization": f"Bearer {token}"}
    if model == CF_MODEL:
        fields = {"prompt": (None, prompt[:2000]), "width": (None, str(w)), "height": (None, str(h))}
        if seed is not None:
            fields["seed"] = (None, str(seed))
        if ref_path:
            fields["input_image_0"] = ("ref.jpg", open(ref_path, "rb"), "image/jpeg")
        r = requests.post(url, headers=hdr, files=fields, timeout=150)
    else:
        r = requests.post(url, headers=hdr, json={"prompt": prompt[:2000], "steps": 6}, timeout=150)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    js = r.json()
    img = (js.get("result") or {}).get("image") or js.get("image")
    if not img:
        raise RuntimeError("no image in reply: " + r.text[:200])
    return base64.b64decode(img)


def save_picture(data, path):
    with open(path + ".raw", "wb") as f:
        f.write(data)
    fit(Image.open(path + ".raw")).save(path, quality=93)


def make_cast_sheet(cast, path, seed):
    if MOCK:
        return mock_image(path, seed)
    humans = [c for c in cast.chars.values()]
    prompt = (f"{ART_STYLE}. Cast reference photo: all these people standing side by side, full body, "
              f"facing the camera, neutral grey studio background, even soft light. {cast.describe(humans)}")
    for attempt in range(3):
        try:
            data = cf_request(CF_MODEL, prompt, w=1024, h=576, seed=seed)
            with open(path + ".raw", "wb") as f:
                f.write(data)
            im = Image.open(path + ".raw").convert("RGB")
            im.thumbnail((508, 508))
            im.save(path, quality=92)
            cast.ref = path
            return True
        except Exception as e:
            log(f"  cast sheet attempt {attempt + 1} failed: {str(e)[:300]}")
            time.sleep(6 * (attempt + 1))
    return False


def make_image(cast, action, place, names, path, seed):
    if MOCK:
        return mock_image(path, seed)
    tries = []
    if cast.ref:
        tries.append((CF_MODEL, cast.scene_prompt(action, place, names, True), cast.ref))
    tries.append((CF_MODEL, cast.scene_prompt(action, place, names, False), None))
    tries.append((CF_BACKUP, cast.scene_prompt(action, place, names, False)[:1500], None))
    for attempt, (model, prompt, ref) in enumerate(tries):
        try:
            save_picture(cf_request(model, prompt, ref, seed=seed), path)
            return True
        except Exception as e:
            log(f"  picture attempt {attempt + 1} ({model.split('/')[-1]}) failed: {str(e)[:300]}")
            time.sleep(6 * (attempt + 1))
    return False


# ----------------------------------------------------------------- 3. voices
# Voice "set" for every kind of character: (pitch change in Hz, speed change in %)
AGE_VOICE = {"child": (30, 8), "young": (10, 4), "adult": (0, 0), "old": (-16, -14)}


def age_group(a):
    a = str(a).lower()
    if any(k in a for k in ("child", "kid", "boy", "girl", "baby")):
        return "child"
    if any(k in a for k in ("young", "teen", "youth")):
        return "young"
    if any(k in a for k in ("old", "elder", "aged", "grand")):
        return "old"
    return "adult"


class Voices:
    """Gives every character their own voice: different speaker, pitch and speed.
    Ghosts get a deep, echoing voice."""

    def __init__(self, lang, cast):
        self.L = LANGS[lang]
        self.map = {}
        used = {"male": 0, "female": 0}
        dup = {}
        nar_voice = self.L["narrator"][0]
        for c in cast.chars.values():
            g = "female" if c["gender"].startswith("f") else "male"
            ag = age_group(c["age"])
            pool = [v for v in self.L[g] if v != nar_voice] or self.L[g]
            voice = pool[used[g] % len(pool)]
            used[g] += 1
            k = (voice, ag)
            n = dup.get(k, 0)                 # same voice + same age twice -> nudge pitch
            dup[k] = n + 1
            pitch, rate = AGE_VOICE[ag]
            pitch += [0, -8, 8, -14, 14][n % 5]
            ghost = c["kind"].startswith("ghost")
            if ghost:
                rate -= 10
            self.map[c["name"].lower()] = (voice, f"{rate:+d}%", f"{pitch:+d}Hz", ghost)
        self.cast = cast

    def for_speaker(self, speaker):
        s = ascii_text(speaker).lower()
        if not s or s.startswith("narrat"):
            v, r, p = self.L["narrator"]
            return v, r, p, False
        c = self.cast.find(s)
        if c:
            return self.map[c["name"].lower()]
        v, r, p = self.L["narrator"]
        return v, r, p, False


async def _edge(text, voice, rate, pitch, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out)


def tts_line(text, voice_spec, gtts_lang, out_wav):
    """Speak one line -> mono 44.1k wav. Returns seconds."""
    if MOCK:
        secs = max(1.2, len(text) / 15)
        freq = 180 + (abs(hash(voice_spec[0] + voice_spec[2])) % 200)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs:.2f}",
             "-af", "volume=0.25", "-ar", str(SR), "-ac", "1", out_wav])
        return secs
    voice, rate, pitch, ghost = voice_spec
    mp3 = out_wav + ".mp3"
    ok = False
    for attempt in range(3):
        try:
            asyncio.run(_edge(text, voice, rate, pitch, mp3))
            ok = os.path.getsize(mp3) > 800
            if ok:
                break
        except Exception as e:
            log(f"  voice attempt {attempt + 1} failed ({voice}): {str(e)[:120]}")
            time.sleep(4)
    af = "aresample=44100"
    if not ok:
        # backup (Google) has only one voice -> change its pitch so characters still differ
        from gtts import gTTS
        gTTS(text, lang=gtts_lang).save(mp3)
        hz = int(pitch.replace("Hz", "")) if pitch.replace("Hz", "").lstrip("+-").isdigit() else 0
        male = voice in LANGS["hi"]["male"] + LANGS["bn"]["male"]
        f = max(0.72, min(1.3, (0.80 if male else 1.0) * (1 + hz / 160)))
        af = f"asetrate=44100*{f:.3f},aresample=44100,atempo={min(2.0, max(0.5, 1 / f)):.3f}"
    if ghost:
        # Scary ghost voice, three layers mixed together:
        #  1. a very deep, slow, trembling copy of the voice
        #  2. a thin, high, airy "whisper" copy that follows a moment later
        #  3. a low growl (the deep voice, much lower again, quiet)
        # then a long cold echo, like a voice from an empty hall.
        g = (f"[0:a]{af},asplit=3[a][b][c];"
             "[a]asetrate=44100*0.78,aresample=44100,atempo=1.15,vibrato=f=4.5:d=0.35[deep];"
             "[b]asetrate=44100*1.08,aresample=44100,atempo=0.83,highpass=f=1800,volume=0.45,adelay=70[air];"
             "[c]asetrate=44100*0.62,aresample=44100,atempo=1.445,lowpass=f=700,volume=0.55,adelay=20[growl];"
             "[deep][air][growl]amix=inputs=3:normalize=0,"
             "aecho=0.8:0.88:140|310|520:0.5|0.32|0.2,lowpass=f=6500,"
             "dynaudnorm=f=150:g=7,volume=1.1[out]")
        run(["ffmpeg", "-y", "-i", mp3, "-filter_complex", g, "-map", "[out]", "-ac", "1", "-ar", str(SR), out_wav])
        return duration(out_wav)
    run(["ffmpeg", "-y", "-i", mp3, "-af", af, "-ac", "1", "-ar", str(SR), out_wav])
    return duration(out_wav)


# ----------------------------------------------------------------- 4. sound engine (no copyright)
def _np():
    import numpy as np
    return np


def _filt(x, kind, freq, order=2):
    from scipy.signal import butter, sosfilt
    sos = butter(order, freq, btype=kind, fs=SR, output="sos")
    return sosfilt(sos, x)


def _env_decay(n, secs):
    np = _np()
    return np.exp(-np.arange(n) / (SR * secs))


def _noise(n, rnd):
    np = _np()
    return rnd.standard_normal(n)


def _brown(n, rnd):
    np = _np()
    b = np.cumsum(rnd.standard_normal(n))
    b = _filt(b, "highpass", 20, 1)
    return b / (np.abs(b).max() + 1e-9)


def _smooth_lfo(n, rnd, speed=0.25):
    """Slowly wandering 0..1 curve."""
    np = _np()
    k = max(4, int(n / SR * speed * 4) + 4)
    pts = rnd.uniform(0, 1, k)
    return np.interp(np.linspace(0, k - 1, n), np.arange(k), pts)


def _place(track, sound, at):
    i = int(at * SR)
    if i >= len(track):
        return
    j = min(len(track), i + len(sound))
    track[i:j] += sound[:j - i]


def _user_sfx(tag, n):
    """Use your own file sfx/<tag>.mp3 (or .wav) if you add one."""
    np = _np()
    for ext in ("mp3", "wav", "ogg", "m4a"):
        p = os.path.join(SFX_DIR, f"{tag}.{ext}")
        if os.path.exists(p):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", p, "-t", f"{n / SR:.2f}",
                                  "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True).stdout
            a = np.frombuffer(raw, dtype=np.float32).astype("float64")
            out = np.zeros(n)
            out[:len(a)] = a[:n]
            return out * 0.8
    return None


def synth(tag, n, rnd):
    np = _np()
    user = _user_sfx(tag, n)
    if user is not None:
        return user
    t = np.arange(n) / SR
    out = np.zeros(n)
    if tag == "wind":
        b = _filt(_brown(n, rnd), "bandpass", [150, 900])
        out = b / (np.abs(b).max() + 1e-9) * (0.25 + 0.75 * _smooth_lfo(n, rnd, 0.3)) * 0.55
    elif tag == "rain":
        w = _filt(_noise(n, rnd), "bandpass", [1200, 9000]) * 0.08
        drops = np.zeros(n)
        for _ in range(int(n / SR * 25)):
            k = rnd.integers(0, n)
            drops[k] = rnd.uniform(0.2, 1)
        drops = _filt(drops, "highpass", 2500) * 0.6
        out = (w + drops) * (0.8 + 0.2 * _smooth_lfo(n, rnd))
    elif tag == "thunder":
        for _ in range(max(1, int(n / SR / 12))):
            m = int(SR * rnd.uniform(3, 5))
            th = _filt(_brown(m, rnd), "lowpass", 220) * _env_decay(m, rnd.uniform(0.8, 1.6))
            th[:int(SR * 0.05)] *= np.linspace(0, 1, int(SR * 0.05))
            _place(out, th * 1.4, rnd.uniform(0.3, max(0.4, n / SR - 4)))
    elif tag == "crickets":
        chirp = np.sin(2 * np.pi * 4600 * t[:int(SR * 0.035)]) * np.hanning(int(SR * 0.035))
        x = 0.0
        while x < n / SR:
            for k in range(3):
                _place(out, chirp * 0.07, x + k * 0.06)
            x += rnd.uniform(0.6, 1.1)
    elif tag == "owl":
        def hoot(f, d):
            m = int(SR * d)
            tt = np.arange(m) / SR
            return np.sin(2 * np.pi * (f + 8 * np.sin(2 * np.pi * 6 * tt)) * tt) * np.hanning(m)
        x = rnd.uniform(0.5, 2)
        while x < n / SR - 2:
            _place(out, hoot(380, 0.35) * 0.18, x)
            _place(out, hoot(360, 0.6) * 0.18, x + 0.5)
            x += rnd.uniform(5, 9)
        out = out + _filt(out, "lowpass", 2000) * 0.3
    elif tag == "heartbeat":
        def thump(d):
            m = int(SR * d)
            tt = np.arange(m) / SR
            return np.sin(2 * np.pi * 52 * tt) * _env_decay(m, 0.06)
        x, period = 0.2, 0.95
        while x < n / SR:
            _place(out, thump(0.25) * 0.9, x)
            _place(out, thump(0.25) * 0.6, x + 0.22)
            x += period
            period = max(0.55, period - 0.01)    # speeds up = more tension
    elif tag == "footsteps":
        x = rnd.uniform(0.3, 1)
        while x < n / SR - 0.3:
            m = int(SR * 0.18)
            st = _filt(_noise(m, rnd), "bandpass", [80, 700]) * _env_decay(m, 0.03)
            _place(out, st * 0.6, x)
            x += rnd.uniform(0.55, 0.75)
    elif tag == "creak":
        for _ in range(max(1, int(n / SR / 8))):
            m = int(SR * rnd.uniform(1.2, 2.2))
            tt = np.arange(m) / SR
            f = 170 + 160 * np.sin(np.pi * tt / tt[-1]) + 15 * rnd.standard_normal(m).cumsum() / np.sqrt(m)
            ph = 2 * np.pi * np.cumsum(f) / SR
            saw = (ph / np.pi % 2) - 1
            cr = _filt(saw * (0.5 + 0.5 * (rnd.uniform(0, 1, m) > 0.3)), "bandpass", [300, 2500])
            _place(out, cr * np.hanning(m) * 0.35, rnd.uniform(0.2, max(0.3, n / SR - 2.5)))
    elif tag == "whisper":
        w = _filt(_noise(n, rnd), "bandpass", [1800, 6000])
        syl = (_smooth_lfo(n, rnd, 3.0) > 0.55).astype(float)
        syl = _filt(syl, "lowpass", 12, 1)
        out = w * syl * 0.16 * (0.3 + 0.7 * _smooth_lfo(n, rnd, 0.2))
    elif tag == "clock":
        x = 0.0
        tick = _filt(_noise(int(SR * 0.012), rnd), "highpass", 3000) * np.hanning(int(SR * 0.012))
        while x < n / SR:
            _place(out, tick * 0.35, x)
            x += 1.0
    elif tag == "howl":
        x = rnd.uniform(0.5, 1.5)
        while x < n / SR - 3:
            m = int(SR * 2.6)
            tt = np.arange(m) / SR
            f = 420 + 300 * np.sin(np.pi * tt / tt[-1]) ** 0.7 + 10 * np.sin(2 * np.pi * 5 * tt)
            hw = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.hanning(m)
            hw = hw + 0.5 * np.concatenate([np.zeros(int(SR * 0.25)), hw[:-int(SR * 0.25)]])
            _place(out, hw * 0.12, x)
            x += rnd.uniform(9, 15)
    elif tag == "drip":
        x = rnd.uniform(0.2, 1)
        while x < n / SR:
            m = int(SR * 0.12)
            tt = np.arange(m) / SR
            d = np.sin(2 * np.pi * (1800 - 6000 * tt) * tt) * _env_decay(m, 0.025)
            _place(out, d * 0.3, x)
            x += rnd.uniform(1.2, 3.0)
    elif tag == "knock":
        x = rnd.uniform(0.5, 2)
        for k in range(3):
            m = int(SR * 0.15)
            kn = _filt(_noise(m, rnd), "bandpass", [100, 900]) * _env_decay(m, 0.02)
            _place(out, kn * 1.1, x + k * 0.38)
    elif tag == "scare_hit":
        m = int(SR * 2.5)
        tt = np.arange(m) / SR
        boom = np.sin(2 * np.pi * (60 - 20 * tt) * tt) * _env_decay(m, 0.6)
        stab = _filt(_noise(m, rnd), "bandpass", [2000, 7000]) * _env_decay(m, 0.25) * 0.4
        _place(out, (boom + stab) * 0.9, 0.05)
    return out


def drone(n, rnd, mood):
    """Background horror music bed made from slow detuned tones."""
    np = _np()
    t = np.arange(n) / SR
    base = rnd.choice([49.0, 55.0, 58.27, 61.74])
    level = {"calm": 0.07, "sad": 0.08, "creepy": 0.10, "tense": 0.12, "scare": 0.14}.get(mood, 0.09)
    out = np.zeros(n)
    for mult, amp in ((1, 1.0), (1.5, 0.45), (2.02, 0.35), (2.38, 0.18 if mood in ("tense", "scare") else 0.0)):
        f = base * mult * (1 + 0.003 * np.sin(2 * np.pi * rnd.uniform(0.05, 0.15) * t))
        out += amp * np.sin(2 * np.pi * np.cumsum(f) / SR)
    air = _filt(_noise(n, rnd), "bandpass", [300, 1400]) * 0.12
    out = (out / 2.0 + air) * (0.6 + 0.4 * _smooth_lfo(n, rnd, 0.15))
    fade = min(n // 4, int(SR * 1.5))
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out * level


def read_wav(path):
    np = _np()
    with wave.open(path) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float64") / 32768
    return a


def write_wav(path, a):
    np = _np()
    a = np.clip(a, -1, 1)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((a * 32767).astype(np.int16).tobytes())


def make_scene_audio(lines, voices, lang, idx, sounds, mood, out_wav):
    """Speak every line with the right voice, place them one after another, put sounds
    and music underneath. Returns (seconds, [(start, dur, speaker_is_narrator, text)])."""
    np = _np()
    rnd = np.random.default_rng(1000 + idx)
    gap, lead, tail = 0.35, 0.5, 0.9
    pieces, subs, t = [], [], lead
    for j, ln in enumerate(lines):
        text = str(ln.get("text", "")).strip()
        if not text:
            continue
        spec = voices.for_speaker(ln.get("speaker", "narrator"))
        p = os.path.join(WORK, f"v_{idx:02d}_{j:02d}.wav")
        tts_line(text, spec, LANGS[lang]["gtts"], p)
        a = read_wav(p)
        pieces.append((t, a))
        sp = ascii_text(ln.get("speaker", "")).lower()
        is_nar = (not sp) or sp.startswith("narrat") or voices.cast.find(sp) is None
        subs.append((t, len(a) / SR, is_nar, text))
        t += len(a) / SR + gap
    total = t - gap + tail
    n = int(total * SR)
    voice = np.zeros(n)
    for start, a in pieces:
        _place(voice, a, start)
    bed = drone(n, rnd, mood)
    for (start, a), (_, _, is_nar, _), ln in zip(pieces, subs, [l for l in lines if str(l.get("text", "")).strip()]):
        if voices.for_speaker(ln.get("speaker", ""))[3]:            # a ghost is speaking
            m = int(SR * 1.2)
            swell = _filt(_noise(m, rnd), "bandpass", [300, 3000]) * np.linspace(0, 1, m) ** 2 * 0.35
            _place(bed, swell, max(0.0, start - 1.1))
            k = len(a) + int(SR * 0.8)
            wh = synth("whisper", k, rnd) * 1.4
            _place(bed, wh, start)
    for tag in (sounds or [])[:3]:
        if tag in SOUND_TAGS:
            bed += synth(tag, n, rnd) * (0.55 if tag != "scare_hit" else 0.8)
    if mood == "scare" and "scare_hit" not in (sounds or []):
        bed += synth("scare_hit", n, rnd) * 0.6
    # duck the background while people speak
    talk = np.zeros(n)
    for start, a in pieces:
        talk[int(start * SR):int(start * SR) + len(a)] = 1
    talk = _filt(talk, "lowpass", 3, 1)
    bed *= 1 - 0.55 * np.clip(talk, 0, 1)
    mix = voice * 0.95 + bed
    peak = np.abs(mix).max()
    if peak > 0.98:
        mix *= 0.98 / peak
    write_wav(out_wav, mix)
    return total, subs


# ----------------------------------------------------------------- fonts
def find_font(lang):
    g = LANGS[lang]["font_glob"]
    cands = [env(f"FONT_PATH_{lang.upper()}")]
    cands += glob.glob(f"/usr/share/fonts/**/{g}-Bold.ttf", recursive=True)
    cands += glob.glob(os.path.join(HERE, "fonts", f"{g}*.ttf"))
    cands += glob.glob(f"/usr/share/fonts/**/{g}*.tt*", recursive=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    sys.exit(f"ERROR: font for {lang} not found (install fonts-noto-core).")


FONT = None


def font(size):
    return ImageFont.truetype(FONT, size, layout_engine=ImageFont.Layout.RAQM)


# ----------------------------------------------------------------- 5. thumbnail
def make_thumbnail(base_img, text, out, label):
    img = Image.open(base_img).convert("RGB").resize((W, H))
    img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.15)
    shade = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(shade)
    for y in range(H // 2, H):
        d.line([(0, y), (W, y)], fill=int(220 * (y - H / 2) / (H / 2)))
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shade)
    draw = ImageDraw.Draw(img)
    words = text.strip().split()
    half = len(words) // 2 + len(words) % 2
    lines = [text.strip()] if len(words) <= 2 else [" ".join(words[:half]), " ".join(words[half:])]
    size = 150
    while size > 50:
        f = font(size)
        if all(draw.textlength(l, font=f) <= W - 90 for l in lines) and size * 1.3 * len(lines) <= H * 0.55:
            break
        size -= 6
    f = font(size)
    lh = int(size * 1.3)
    y = H - 40 - lh * len(lines)
    colors = [(235, 20, 30), (255, 255, 255)]
    for i, l in enumerate(lines):
        x = (W - draw.textlength(l, font=f)) / 2
        draw.text((x, y + i * lh), l, font=f, fill=colors[i % 2],
                  stroke_width=max(6, size // 13), stroke_fill=(0, 0, 0))
    lf = font(38)
    tw = draw.textlength(label, font=lf)
    draw.rounded_rectangle([28, 26, 28 + tw + 40, 26 + 70], radius=12, fill=(150, 0, 10))
    draw.text((48, 30), label, font=lf, fill=(255, 255, 255))
    img.save(out, quality=92)


# ----------------------------------------------------------------- 6. video
_REMBG = None
_LOOK = {}


def cutout_session():
    global _REMBG
    if _REMBG is None:
        from rembg import new_session
        try:
            _REMBG = new_session("isnet-general-use")
        except Exception as e:
            log("  cut-out model unavailable, using small model:", str(e)[:120])
            _REMBG = new_session("u2netp")
    return _REMBG


def split_layers(img_path):
    np = _np()
    import cv2
    from rembg import remove
    pic = Image.open(img_path).convert("RGB").resize((W, H))
    alpha = np.array(remove(pic, session=cutout_session(), only_mask=True).convert("L").resize((W, H)))
    part = (alpha > 128).mean()
    if part < 0.03 or part > 0.60:
        return None
    rgb = np.array(pic)
    hole = cv2.dilate((alpha > 40).astype("uint8") * 255, np.ones((25, 25), "uint8"))
    small = cv2.inpaint(cv2.resize(rgb, (W // 2, H // 2)), cv2.resize(hole, (W // 2, H // 2)), 9,
                        cv2.INPAINT_TELEA)
    bg = cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)
    bg = np.where(hole[..., None] > 0, cv2.GaussianBlur(bg, (0, 0), 3), rgb)
    return bg, np.dstack([rgb, cv2.GaussianBlur(alpha, (0, 0), 1.2)])


def horror_look():
    """Pre-made vignette, film grain and fog textures (made once, reused every frame)."""
    if _LOOK:
        return _LOOK
    np = _np()
    import cv2
    rnd = np.random.default_rng(7)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    _LOOK["vignette"] = np.clip(1.15 - 0.55 * r ** 1.6, 0.25, 1)[..., None].astype("float32")
    _LOOK["grain"] = [cv2.GaussianBlur((rnd.standard_normal((H, W)) * 4.5).astype("float32"), (0, 0), 0.8)[..., None]
                      for _ in range(6)]   # soft grain: looks like film, keeps the file small
    fog = cv2.resize(rnd.uniform(0, 1, (12, 24)).astype("float32"), (W * 2, H), interpolation=cv2.INTER_CUBIC)
    fog = cv2.GaussianBlur(fog, (0, 0), 25)
    _LOOK["fog"] = np.clip((fog - fog.min()) / (fog.max() - fog.min() + 1e-6), 0, 1)
    return _LOOK


def grade(frame_f32, f, sec, mood, rnd_flicker):
    """Cold colors, vignette, drifting fog, grain and a little light flicker."""
    np = _np()
    look = horror_look()
    gray = frame_f32.mean(axis=2, keepdims=True)
    frame = frame_f32 * 0.78 + gray * 0.22                       # slightly desaturated
    frame *= np.array([1.06, 0.98, 0.90], "float32")             # BGR: cooler
    off = int((sec * 18) % W)
    fog = look["fog"][:, off:off + W]
    if fog.shape[1] < W:
        fog = np.concatenate([fog, look["fog"][:, :W - fog.shape[1]]], axis=1)
    frame = frame + fog[..., None] * np.array([38, 36, 32], "float32")
    frame *= look["vignette"]
    flick = 1.0
    if mood in ("creepy", "tense", "scare"):
        flick = 1 - 0.10 * rnd_flicker[f % len(rnd_flicker)]
    frame = frame * flick + look["grain"][f % 6]
    return frame


def scene_clip_animated(img, audio, out, idx, mood):
    np = _np()
    import cv2
    layers = split_layers(img)
    dur = duration(audio)
    n = int(dur * FPS) + 1
    direction = 1 if idx % 2 == 0 else -1
    rnd = np.random.default_rng(idx + 50)
    flicker = (rnd.uniform(0, 1, 400) > 0.93).astype("float32") * rnd.uniform(0.4, 1, 400)
    if layers is not None:
        bg, fg = layers
        fg_a = fg[..., 3].astype("float32") / 255.0
        fg_bgr = cv2.cvtColor(fg[..., :3], cv2.COLOR_RGB2BGR).astype("float32")
        ys, xs = np.nonzero(fg_a > 0.5)
        cx, cy = float(xs.mean()), float(ys.max())
    else:
        bg = np.array(Image.open(img).convert("RGB").resize((W, H)))
    bg_bgr = cv2.cvtColor(bg, cv2.COLOR_RGB2BGR)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", audio, "-t", f"{dur:.2f}",
         "-vf", f"fade=t=in:st=0:d=0.5,fade=t=out:st={dur - 0.5:.2f}:d=0.5,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "3500k", "-bufsize", "7000k",
         "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-ac", "2", out],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(n):
            t = f / max(n - 1, 1)
            ease = 0.5 - 0.5 * math.cos(math.pi * t)
            sec = f / FPS
            shake = 0.0
            if mood == "scare" and sec < 0.6:
                shake = 7 * math.sin(sec * 90) * (1 - sec / 0.6)
            bz = 1.04 + 0.05 * ease                        # slow creeping push-in
            Mb = cv2.getRotationMatrix2D((W / 2, H / 2), 0, bz)
            Mb[0, 2] += direction * (ease - 0.5) * 24 + shake
            Mb[1, 2] += shake * 0.6
            frame = cv2.warpAffine(bg_bgr, Mb, (W, H), borderMode=cv2.BORDER_REFLECT).astype("float32")
            if layers is not None:
                fz = 1.04 + 0.07 * ease + 0.004 * math.sin(sec * 1.6)
                Mf = cv2.getRotationMatrix2D((cx, cy), 0.3 * math.sin(sec * 0.9), fz)
                Mf[0, 2] += direction * (ease - 0.5) * 46 + shake + (W / 2 - cx) * (bz - 1)
                Mf[1, 2] += shake * 0.6 - 2.0 * math.sin(sec * 1.1)
                fgw = cv2.warpAffine(fg_bgr, Mf, (W, H))
                aw = cv2.warpAffine(fg_a, Mf, (W, H))[..., None]
                frame = frame * (1 - aw) + fgw * aw
            frame = grade(frame, f, sec, mood, flicker)
            ff.stdin.write(np.clip(frame, 0, 255).astype("uint8").tobytes())
        ff.stdin.close()
    except Exception:
        ff.kill()
        raise
    if ff.wait() != 0:
        raise RuntimeError(ff.stderr.read().decode()[-500:])
    return dur


def scene_clip_simple(img, audio, out, idx, mood):
    dur = duration(audio)
    frames = int(dur * FPS) + 1
    z = "min(1+0.0005*on,1.07)" if idx % 2 == 0 else "max(1.07-0.0005*on,1)"
    vf = (f"scale={W * 2}:{H * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}"
          f":s={W}x{H}:fps={FPS},eq=saturation=0.8:brightness=-0.03,vignette=PI/4,noise=alls=5:allf=t,"
          f"fade=t=in:st=0:d=0.5,fade=t=out:st={dur - 0.5:.2f}:d=0.5,format=yuv420p")
    run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-i", audio, "-vf", vf, "-t", f"{dur:.2f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "3500k", "-bufsize", "7000k",
         "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-ac", "2", out])
    return dur


def scene_clip(img, audio, out, idx, mood):
    if env("SIMPLE_MOTION") == "1" or (MOCK and env("TEST_ANIM") != "1"):
        return scene_clip_simple(img, audio, out, idx, mood)
    try:
        return scene_clip_animated(img, audio, out, idx, mood)
    except Exception as e:
        log(f"  animation skipped ({str(e)[:150]}) - simple motion")
        return scene_clip_simple(img, audio, out, idx, mood)


def ass_time(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def split_subs(text, max_len=44):
    parts = [p.strip() for p in re.split(r"(?<=[।!?,\.])\s+", text) if p.strip()]
    out = []
    for p in parts:
        cur = ""
        for w in p.split():
            if cur and len(cur) + 1 + len(w) > max_len:
                out.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            out.append(cur)
    return out


def write_ass(segments, path, family):
    """segments: (start, dur, is_narrator, text). Narration white, dialogue yellow."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Nar,{family},52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,38,1
Style: Talk,{family},54,&H0000E6FF,&H0000E6FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,38,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = []
    for start, dur, is_nar, text in segments:
        chunks = split_subs(text)
        total = sum(len(c) for c in chunks) or 1
        t = start
        for c in chunks:
            d = dur * len(c) / total
            rows.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d)},{'Nar' if is_nar else 'Talk'},,0,0,0,,{c}")
            t += d
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(rows) + "\n")


def build_video(scene_parts, lang, out):
    """scene_parts: list of dict(image, lines, sounds, mood). Returns mp4 path."""
    clips, segs, t = [], [], 0.0
    voices = scene_parts[0]["voices"]
    for i, sp in enumerate(scene_parts):
        log(f"Voices + sound + clip {i + 1}/{len(scene_parts)}")
        a = os.path.join(WORK, f"audio_{i:02d}.wav")
        d, subs = make_scene_audio(sp["lines"], voices, lang, i, sp.get("sounds"), sp.get("mood", "creepy"), a)
        c = os.path.join(WORK, f"clip_{i:02d}.mp4")
        d = scene_clip(sp["image"], a, c, i, sp.get("mood", "creepy"))
        segs += [(t + s, du, nar, tx) for s, du, nar, tx in subs]
        clips.append(c)
        t += d
    lst = os.path.join(WORK, "clips.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", os.path.join(WORK, "joined.mp4")])
    write_ass(segs, os.path.join(WORK, "subs.ass"), LANGS[lang]["font_family"])
    vf = f"ass=subs.ass:fontsdir={os.path.dirname(FONT)}:shaping=complex"
    r = subprocess.run(["ffmpeg", "-y", "-i", "joined.mp4", "-vf", vf, "-c:v", "libx264", "-preset", "medium",
                        "-crf", "23", "-maxrate", "3500k", "-bufsize", "7000k", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                        os.path.abspath(out)], capture_output=True, text=True, cwd=WORK)
    if r.returncode != 0:
        raise RuntimeError("final render failed:\n" + r.stderr[-2000:])
    return out


# ----------------------------------------------------------------- 7. posting
def _fb_json(r):
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"Facebook replied HTTP {r.status_code}: {r.text[:200]!r}")


def post_to_facebook(video, thumb, title, description):
    """Uploads in pieces (resumable), so big videos don't fail half-way."""
    page, token = need_env("FB_PAGE_ID"), need_env("FB_PAGE_TOKEN")
    url = f"https://graph-video.facebook.com/v21.0/{page}/videos"
    size = os.path.getsize(video)
    log(f"  video size: {size / 1e6:.0f} MB")
    for attempt in range(3):
        try:
            js = _fb_json(requests.post(url, data={"access_token": token, "upload_phase": "start",
                                                   "file_size": str(size)}, timeout=120))
            if "error" in js:
                err = js["error"]
                if err.get("code") in (190, 200, 10, 100):
                    raise PermissionError(f"Facebook refused: {err.get('message')} -> check FB_PAGE_ID / FB_PAGE_TOKEN")
                raise RuntimeError(err.get("message"))
            sid, start, end = js["upload_session_id"], int(js["start_offset"]), int(js["end_offset"])
            with open(video, "rb") as f:
                while start < end:
                    f.seek(start)
                    chunk = f.read(end - start)
                    for t in range(4):
                        try:
                            jr = _fb_json(requests.post(url, data={"access_token": token, "upload_phase": "transfer",
                                                                   "upload_session_id": sid, "start_offset": str(start)},
                                                        files={"video_file_chunk": ("chunk", chunk, "application/octet-stream")},
                                                        timeout=600))
                            if "error" in jr:
                                raise RuntimeError(jr["error"].get("message"))
                            break
                        except Exception as e:
                            if t == 3:
                                raise
                            log(f"    piece retry: {str(e)[:120]}")
                            time.sleep(10)
                    start, end = int(jr["start_offset"]), int(jr["end_offset"])
                    log(f"    uploaded {start / 1e6:.0f}/{size / 1e6:.0f} MB")
            with open(thumb, "rb") as th:
                jf = _fb_json(requests.post(url, data={"access_token": token, "upload_phase": "finish",
                                                       "upload_session_id": sid, "title": title,
                                                       "description": description, "published": "true"},
                                            files={"thumb": ("thumb.jpg", th, "image/jpeg")}, timeout=300))
            if jf.get("success") or jf.get("id"):
                return js.get("video_id") or jf.get("id") or sid
            raise RuntimeError(str(jf)[:300])
        except PermissionError:
            raise
        except Exception as e:
            log(f"  Facebook upload attempt {attempt + 1} failed: {str(e)[:250]}")
            time.sleep(30)
    raise RuntimeError("Facebook upload failed 3 times")


def youtube_ready():
    return all(env(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def post_to_youtube(video, thumb, title, description, tags, lang):
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET"),
        "refresh_token": env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"}, timeout=60)
    if not r.ok:
        raise PermissionError("YouTube login failed (check YT_ secrets): " + r.text[:300])
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}
    meta = {
        "snippet": {"title": title[:100], "description": description[:4900],
                    "tags": [t.lstrip("#") for t in tags][:15], "categoryId": "24",
                    "defaultLanguage": lang, "defaultAudioLanguage": lang},
        "status": {"privacyStatus": env("YT_PRIVACY") or "public", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }
    size = os.path.getsize(video)
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                      headers={**hdr, "Content-Type": "application/json; charset=UTF-8",
                               "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
                      data=json.dumps(meta), timeout=60)
    if not r.ok:
        raise RuntimeError("YouTube start failed: " + r.text[:400])
    with open(video, "rb") as f:
        up = requests.put(r.headers["Location"], headers={**hdr, "Content-Type": "video/mp4"}, data=f, timeout=1800)
    if not up.ok:
        raise RuntimeError("YouTube upload failed: " + up.text[:400])
    vid = up.json()["id"]
    try:
        with open(thumb, "rb") as f:
            t = requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
                              headers={**hdr, "Content-Type": "image/jpeg"}, data=f, timeout=120)
        if not t.ok:
            log("  YouTube thumbnail not set (channel may need phone verification):", t.text[:150])
    except Exception as e:
        log("  YouTube thumbnail error:", e)
    return vid


# ----------------------------------------------------------------- voice demo
DEMO_LINES = {
    "hi": {"narrator": "मैं इस कहानी का सूत्रधार हूँ।", "man": "मैं एक आदमी हूँ, मेरी आवाज़ ऐसी है।",
           "woman": "मैं एक औरत हूँ, मेरी आवाज़ ऐसी है।", "young man": "मैं एक नौजवान लड़का हूँ।",
           "young woman": "मैं एक नौजवान लड़की हूँ।", "old man": "मैं एक बूढ़ा आदमी हूँ।",
           "old woman": "मैं एक बूढ़ी औरत हूँ।", "boy": "मैं एक छोटा बच्चा हूँ।", "girl": "मैं एक छोटी बच्ची हूँ।",
           "ghost": "मैं... इस हवेली की आत्मा हूँ..."},
    "bn": {"narrator": "আমি এই গল্পের কথক।", "man": "আমি একজন পুরুষ, আমার গলা এরকম।",
           "woman": "আমি একজন মহিলা, আমার গলা এরকম।", "young man": "আমি একজন যুবক।",
           "young woman": "আমি একজন যুবতী।", "old man": "আমি একজন বুড়ো মানুষ।", "old woman": "আমি একজন বুড়ি।",
           "boy": "আমি একটা ছোট ছেলে।", "girl": "আমি একটা ছোট মেয়ে।", "ghost": "আমি... এই বাড়ির আত্মা..."},
}
DEMO_CAST = [("man", "male", "adult", "human"), ("woman", "female", "adult", "human"),
             ("young man", "male", "young", "human"), ("young woman", "female", "young", "human"),
             ("old man", "male", "old", "human"), ("old woman", "female", "old", "human"),
             ("boy", "male", "child", "human"), ("girl", "female", "child", "human"),
             ("ghost", "female", "old", "ghost")]


def voice_demo():
    """Makes work/voice_demo_hi.mp3 and work/voice_demo_bn.mp3 - every voice type says one line."""
    np = _np()
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    for lang in ("hi", "bn"):
        cast = Cast({"characters": [{"name": n, "gender": g, "age": a, "kind": k, "look": ""}
                                    for n, g, a, k in DEMO_CAST]})
        voices = Voices(lang, cast)
        lines = [{"speaker": "narrator", "text": DEMO_LINES[lang]["narrator"]}]
        lines += [{"speaker": n, "text": DEMO_LINES[lang][n]} for n, *_ in DEMO_CAST]
        out = os.path.join(WORK, f"voice_demo_{lang}.wav")
        make_scene_audio(lines, voices, lang, 0, ["wind"], "creepy", out)
        run(["ffmpeg", "-y", "-i", out, "-b:a", "160k", out.replace(".wav", ".mp3")])
        for n, *_ in DEMO_CAST:
            log(f"  {lang} {n:12s} -> {voices.map[n.lower()]}")
    log("Voice demo ready: download 'horror-video' from this run's page (Artifacts).")


# ----------------------------------------------------------------- main
def main():
    global FONT
    if env("MODE") == "voice_demo":
        return voice_demo()
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    history = load_history()
    lang = pick_language(history)
    L = LANGS[lang]
    FONT = find_font(lang)
    theme = pick_theme(history)
    log(f"Language: {L['name']} | Idea: {theme}")

    story = make_story(lang, theme, history)
    title = story["title"].strip()[:95]
    log("Title:", title)
    with open(os.path.join(WORK, "story.json"), "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=1)

    cast = Cast(story)
    voices = Voices(lang, cast)
    for c in cast.chars.values():
        log(f"  {c['name']} ({c['gender']}, {c['age']}, {c['kind']}) -> voice {voices.map[c['name'].lower()][:3]}")
    seed = random.randint(1, 1_000_000)
    scenes = story["scenes"][:13]

    log("Cast reference picture")
    if not make_cast_sheet(cast, os.path.join(WORK, "cast.jpg"), seed):
        log("  no cast picture - using text descriptions only")

    imgs, last_ok = [], None
    for i, s in enumerate(scenes):
        p = os.path.join(WORK, f"scene_{i:02d}.jpg")
        log(f"Picture {i + 1}/{len(scenes)}")
        if make_image(cast, s.get("action", ""), s.get("place", ""), s.get("characters"), p, seed):
            last_ok = p
        elif last_ok:
            shutil.copy(last_ok, p)
        else:
            p = None
        imgs.append(p)
    first_ok = next((p for p in imgs if p), None)
    if not first_ok:
        raise RuntimeError("No pictures could be made (check CF_ACCOUNT_ID / CF_API_TOKEN).")
    imgs = [p or first_ok for p in imgs]

    thumb_base = os.path.join(WORK, "thumb_base.jpg")
    ti = story.get("thumbnail_image") or {}
    if isinstance(ti, str):
        ti = {"action": ti}
    if not make_image(cast, (ti.get("action") or scenes[-1].get("action", "")) +
                      ", terrified faces close to the camera, very dramatic", "", ti.get("characters"),
                      thumb_base, seed):
        shutil.copy(first_ok, thumb_base)
    thumb = os.path.join(WORK, "thumbnail.jpg")
    make_thumbnail(thumb_base, story.get("thumbnail_text") or title, thumb, L["label"])

    clean_title = re.sub(r"[^\w\sऀ-ॿঀ-৿,।!?-]", "", title).strip()
    page = env(f"PAGE_NAME_{lang.upper()}") or env("PAGE_NAME") or L["page_default"]
    parts = [{"image": thumb_base, "lines": [{"speaker": "narrator", "text": L["intro"].format(title=clean_title)}],
              "sounds": ["wind"], "mood": "creepy", "voices": voices}]
    for img, s in zip(imgs, scenes):
        parts.append({"image": img, "lines": s.get("lines", []), "sounds": s.get("sounds", []),
                      "mood": s.get("mood", "creepy"), "voices": voices})
    end_lines = []
    if story.get("ending_line"):
        end_lines.append({"speaker": "narrator", "text": story["ending_line"]})
    end_lines.append({"speaker": "narrator", "text": L["outro"].format(page=page)})
    parts.append({"image": imgs[-1], "lines": end_lines, "sounds": ["wind"], "mood": "creepy", "voices": voices})

    video = os.path.join(WORK, "final.mp4")
    build_video(parts, lang, video)
    log(f"Video ready: {duration(video):.0f} seconds")

    tags = [t if t.startswith("#") else "#" + t.replace(" ", "") for t in story.get("hashtags", [])[:15]]
    description = f"{title}\n\n{story.get('description', '').strip()}\n\n{L['ai_note']}\n\n{' '.join(tags)}"

    results = {}
    if DRY_RUN:
        log("DRY RUN - not posting. Files are in the 'work' folder.")
    else:
        try:
            results["facebook"] = post_to_facebook(video, thumb, title, description)
            log("Posted to Facebook:", results["facebook"])
        except Exception as e:
            log("FACEBOOK FAILED:", e)
            results["facebook_error"] = str(e)[:200]
        if youtube_ready():
            try:
                results["youtube"] = post_to_youtube(video, thumb, title, description, tags, lang)
                log("Posted to YouTube:", results["youtube"])
            except Exception as e:
                log("YOUTUBE FAILED:", e)
                results["youtube_error"] = str(e)[:200]
        else:
            log("YouTube secrets not set - skipping YouTube")
        if not results.get("facebook") and not results.get("youtube"):
            raise SystemExit("Posting failed everywhere - see messages above.")

    history.append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "lang": lang,
                    "theme": theme, "title": title, **results})
    if not MOCK:
        save_history(history)


# ----------------------------------------------------------------- offline test helpers
def mock_story(lang):
    if lang == "bn":
        return {
            "title": "পুরনো বাড়ির শেষ প্রদীপ 🕯️", "thumbnail_text": "প্রদীপ নিজে জ্বলে!",
            "description": "রাত বারোটায় প্রদীপটা নিজে থেকে জ্বলে ওঠে...\nআপনি হলে কী করতেন?",
            "hashtags": ["#ভৌতিকগল্প", "#HorrorStory"], "setting": "old crumbling haveli at night",
            "characters": [{"name": "Rana", "gender": "male", "age": "adult", "kind": "human", "look": "man, grey shawl"},
                           {"name": "Mitali", "gender": "female", "age": "adult", "kind": "human", "look": "woman, red saree"},
                           {"name": "Chhaya", "gender": "female", "age": "old", "kind": "ghost", "look": "pale old woman in white"}],
            "thumbnail_image": {"characters": ["Chhaya"], "action": "ghost at window"},
            "scenes": [
                {"characters": ["Rana", "Mitali"], "action": "arrive", "place": "gate", "mood": "creepy",
                 "sounds": ["wind", "owl"], "lines": [
                    {"speaker": "narrator", "text": "অনেক বছর পর রানা আর মিতালি তাদের পুরনো বাড়িতে ফিরল। চারদিক নিস্তব্ধ।"},
                    {"speaker": "Mitali", "text": "এত অন্ধকার কেন? আলো জ্বালাও না!"},
                    {"speaker": "Rana", "text": "দাঁড়াও, প্রদীপটা খুঁজছি।"}]},
                {"characters": ["Chhaya"], "action": "ghost", "place": "hall", "mood": "scare",
                 "sounds": ["heartbeat", "whisper"], "lines": [
                    {"speaker": "narrator", "text": "হঠাৎ প্রদীপটা নিজে থেকেই জ্বলে উঠল।"},
                    {"speaker": "Chhaya", "text": "এতদিন পরে এলে?"}]},
            ], "ending_line": "আর সেই প্রদীপ আজও জ্বলে।"}
    return {
        "title": "हवेली का आख़िरी दीया 🕯️", "thumbnail_text": "दीया खुद जलता है!",
        "description": "रात बारह बजे दीया अपने आप जल उठता है...\nआप होते तो क्या करते?",
        "hashtags": ["#BhootKiKahani", "#HorrorStory"], "setting": "old crumbling haveli at night",
        "characters": [{"name": "Raghav", "gender": "male", "age": "adult", "kind": "human", "look": "man, grey shawl"},
                       {"name": "Meera", "gender": "female", "age": "adult", "kind": "human", "look": "woman, red saree"},
                       {"name": "Chhaya", "gender": "female", "age": "old", "kind": "ghost", "look": "pale old woman in white"}],
        "thumbnail_image": {"characters": ["Chhaya"], "action": "ghost at window"},
        "scenes": [
            {"characters": ["Raghav", "Meera"], "action": "arrive", "place": "gate", "mood": "creepy",
             "sounds": ["wind", "crickets"], "lines": [
                {"speaker": "narrator", "text": "बरसों बाद राघव और मीरा अपनी पुरानी हवेली लौटे। चारों तरफ़ सन्नाटा था।"},
                {"speaker": "Meera", "text": "इतना अँधेरा क्यों है? रोशनी करो ना!"},
                {"speaker": "Raghav", "text": "रुको, दीया ढूँढ रहा हूँ।"}]},
            {"characters": ["Chhaya"], "action": "ghost", "place": "hall", "mood": "scare",
             "sounds": ["heartbeat", "creak"], "lines": [
                {"speaker": "narrator", "text": "अचानक दीया अपने आप जल उठा।"},
                {"speaker": "Chhaya", "text": "इतने साल बाद आए हो?"}]},
        ], "ending_line": "और वो दीया आज भी जलता है।"}


def mock_image(path, seed):
    rnd = random.Random(seed + hash(path) % 1000)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=(20 + y // 30, 25 + y // 25, 40 + y // 18))
    d.rectangle([700, 260, 1100, 640], fill=(50, 45, 40), outline=(10, 10, 10), width=6)
    d.ellipse([rnd.randint(380, 520), 300, 600, 420], fill=(200, 200, 190), outline=(0, 0, 0), width=5)
    d.rectangle([420, 410, 580, 660], fill=(220, 220, 215), outline=(0, 0, 0), width=5)
    img.save(path, quality=90)
    return True


if __name__ == "__main__":
    main()
