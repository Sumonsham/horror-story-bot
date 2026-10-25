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
import numpy as np
import extras
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
        "narrator": ("hi-IN-MadhurNeural", "+2%", "-6Hz"), "gtts": "hi",
        "label": "भूतिया कहानी",
        "intro": "आज की डरावनी कहानी है... {title}।",
        "outro": "कहानी कैसी लगी, कमेंट में ज़रूर बताइए। और ऐसी ही डरावनी कहानियों के लिए {page} को फॉलो कीजिए।",
        "page_default": "हमारे पेज",
        "ai_note": "🎨 यह कहानी और तस्वीरें AI की मदद से बनाई गई हैं। सब काल्पनिक है।",
        "badge": "लाइक • शेयर • फॉलो", "part": "भाग {n}",
        "outro_part1": "कहानी का अगला भाग जल्द ही आएगा... उसे मिस मत कीजिए, अभी {page} को फॉलो कीजिए।",
        "ch_intro": "शुरुआत", "ch_end": "अंत", "chapters": "⏱️ अध्याय",
        "cta": "पूरी कहानी हमारे पेज पर 👉", "playlist": "भूतिया कहानियाँ - Hindi Horror Stories",
        "full_link": "पूरी कहानी देखें:",
        "hp": "हेडफ़ोन लगाकर सुनिए",
        "find_ghost": "🔍 वीडियो की तस्वीरों में भूत कितनी बार छिपा था? ध्यान दिया? कमेंट में लिखिए!",
        "find_ghost_line": "और हाँ... इस वीडियो की तस्वीरों में वो भूत कुछ बार छिपा हुआ था। आपने कितनी बार देखा? कमेंट में ज़रूर बताइए।",
        "vote_line": "{q} अगर आप चाहते हैं {o1}, तो कमेंट में 1 लिखिए। और अगर {o2}, तो 2 लिखिए। आपके वोट से तय होगा कि अगले भाग में क्या होगा!",
        "ann1": "नई भूतिया कहानी", "ann_msg": "👻 {when} आ रही है नई भूतिया कहानी... हेडफ़ोन तैयार रखिए! 🎧🔔",
        "comp_title": "{m} मिनट की भूतिया कहानियाँ 👻 | हफ्ते की {n} कहानियाँ एक साथ", "comp_thumb": "{m} मिनट का डर",
        "bhairab": "भैरव ठाकुर का केस #{n}", "bhairab_pl": "भैरव ठाकुर के केस - Bhairab Thakur Cases",
        "taranath": "तारानाथ तांत्रिक #{n}", "taranath_pl": "तारानाथ तांत्रिक की कहानियाँ - Taranath Tantrik",
        "amavasya": "अमावस्या स्पेशल", "your_story": "📝 आपके साथ भी कभी कुछ अजीब हुआ है? अपनी सच्ची घटना कमेंट में #मेरी_कहानी लिखकर बताइए - हो सकता है अगली कहानी आपकी हो!",
        "reply_viewer": "🙏 आपकी भेजी हुई घटना पर आज की कहानी बनी है! देखिए और बताइए कैसी लगी 👻",
        "how_to_join": "आप भी इस कहानी का हिस्सा बनिए! कमेंट में जवाब दीजिए, जिनका जवाब सही होगा उनका नाम अगले वीडियो में लिया जाएगा। और अपनी सच्ची डरावनी घटना कमेंट में हैशटैग मेरी कहानी लिखकर भेजिए, सबसे अच्छी घटना पर आपके नाम के साथ कहानी बनेगी।",
        "shout_line": "पिछली कहानी में सही जवाब दिया था {names} ने। आप सबको बधाई!",
        "viewer_credit": "आज की ये कहानी हमें भेजी थी {name} ने। धन्यवाद {name}! आप भी अपनी घटना भेजिए।",
        "vote_thanks": "ये भाग आपके वोट से बना है, {names} ने यही चुना था। धन्यवाद!",
        "join_comment": "👇 कैसे हिस्सा लें:\n✅ सवाल का जवाब यहाँ कमेंट में लिखिए - सही जवाब देने वालों का नाम अगले वीडियो में!\n🗳️ वोट हो तो 1 या 2 लिखिए\n📝 अपनी सच्ची डरावनी घटना #मेरी_कहानी लिखकर भेजिए - अगली कहानी आपकी हो सकती है\n🔔 फॉलो कीजिए ताकि अगला भाग मिस न हो",
        "shout_comment": "🏆 पिछली कहानी के सही जवाब: {names} - बधाई!",
        "credit_comment": "📝 आज की कहानी भेजी: {name} 🙏",
        "vote_comment": "🗳️ इस भाग का अंत आपके वोट से तय हुआ - {names}, धन्यवाद!",
        "congrats_reply": "🏆 आपका जवाब सही था! आज के वीडियो में आपका नाम लिया गया है 👉 {link}",
    },
    "bn": {
        "name": "Bengali", "script": "Bengali",
        "font_family": "Noto Sans Bengali", "font_glob": "NotoSansBengali",
        "male": ["bn-IN-BashkarNeural", "bn-IN-BashkarNeural"],
        "female": ["bn-IN-TanishaaNeural", "bn-IN-TanishaaNeural"],
        "narrator": ("bn-IN-BashkarNeural", "+2%", "-6Hz"), "gtts": "bn",
        "label": "ভৌতিক গল্প",
        "intro": "আজকের ভৌতিক গল্প... {title}।",
        "outro": "গল্পটা কেমন লাগল কমেন্টে জানাবেন। আর এরকম আরও ভৌতিক গল্পের জন্য {page} ফলো করুন।",
        "page_default": "আমাদের পেজ",
        "ai_note": "🎨 এই গল্প ও ছবি AI-এর সাহায্যে তৈরি। সবকিছু কাল্পনিক।",
        "badge": "লাইক • শেয়ার • ফলো", "part": "পর্ব {n}",
        "outro_part1": "গল্পের পরের পর্ব আসছে কাল... আর রবিবার আসবে পুরো গল্পটা একসাথে। মিস করতে না চাইলে এখনই {page} ফলো করে রাখুন।",
        "ch_intro": "শুরু", "ch_end": "শেষ", "chapters": "⏱️ অধ্যায়",
        "cta": "পুরো গল্প আমাদের পেজে 👉", "playlist": "ভৌতিক গল্প - Bengali Horror Stories",
        "full_link": "পুরো গল্প দেখুন:",
        "hp": "হেডফোন পরে শুনুন",
        "find_ghost": "🔍 ভিডিওর ছবিগুলোতে ভূতটা কতবার লুকিয়ে ছিল? খেয়াল করেছেন? কমেন্টে লিখুন!",
        "find_ghost_line": "আর হ্যাঁ... এই ভিডিওর ছবিগুলোর মধ্যে সেই ভূত কয়েকবার লুকিয়ে ছিল। আপনি কতবার দেখেছেন? কমেন্টে অবশ্যই জানাবেন।",
        "vote_line": "{q} যদি চান {o1}, কমেন্টে লিখুন ১। আর যদি চান {o2}, লিখুন ২। আপনাদের ভোটেই ঠিক হবে পরের পর্বে কী হবে!",
        "ann1": "নতুন ভৌতিক গল্প", "ann_msg": "👻 {when} আসছে নতুন ভৌতিক গল্প... হেডফোন রেডি রাখুন! 🎧🔔",
        "comp_title": "{m} মিনিটের ভূতের গল্প 👻 | সপ্তাহের সেরা {n}টি গল্প একসাথে", "comp_thumb": "{m} মিনিটের ভয়",
        "bhairab": "ভৈরব ঠাকুরের কেস #{n}", "bhairab_pl": "ভৈরব ঠাকুরের কেস - Bhairab Thakur Cases",
        "taranath": "তারানাথ তান্ত্রিক #{n}", "taranath_pl": "তারানাথ তান্ত্রিকের গল্প - Taranath Tantrik",
        "amavasya": "অমাবস্যার স্পেশাল", "your_story": "📝 আপনার জীবনেও কি কখনো অদ্ভুত কিছু ঘটেছে? সত্যি ঘটনাটা কমেন্টে #আমার_গল্প লিখে জানান - পরের গল্পটা হয়তো আপনারই!",
        "reply_viewer": "🙏 আপনার পাঠানো ঘটনা নিয়েই আজকের গল্প! দেখে জানাবেন কেমন লাগল 👻",
        "how_to_join": "আপনিও এই গল্পের অংশ হয়ে উঠুন! কমেন্টে উত্তর দিন, যাঁদের উত্তর ঠিক হবে পরের ভিডিওতে তাঁদের নাম বলা হবে। আর আপনার জীবনের সত্যি ভৌতিক ঘটনা কমেন্টে হ্যাশট্যাগ আমার গল্প লিখে পাঠান, সেরা ঘটনা নিয়ে আপনার নাম সহ গল্প হবে।",
        "shout_line": "আগের গল্পে ঠিক উত্তর দিয়েছিলেন {names}। আপনাদের সবাইকে অভিনন্দন!",
        "viewer_credit": "আজকের এই গল্পটা আমাদের পাঠিয়েছিলেন {name}। ধন্যবাদ {name}! আপনিও আপনার ঘটনা পাঠান।",
        "vote_thanks": "এই পর্ব তৈরি হয়েছে আপনাদের ভোটে, {names} এটাই বেছে নিয়েছিলেন। ধন্যবাদ!",
        "join_comment": "👇 কীভাবে অংশ নেবেন:\n✅ প্রশ্নের উত্তর এখানে কমেন্টে লিখুন - ঠিক উত্তরদাতাদের নাম পরের ভিডিওতে!\n🗳️ ভোট থাকলে ১ বা ২ লিখুন\n📝 আপনার সত্যি ভৌতিক ঘটনা #আমার_গল্প লিখে পাঠান - পরের গল্পটা আপনার হতে পারে\n🔔 ফলো করে রাখুন, পরের পর্ব যেন মিস না হয়",
        "shout_comment": "🏆 আগের গল্পের ঠিক উত্তর: {names} - অভিনন্দন!",
        "credit_comment": "📝 আজকের গল্প পাঠিয়েছেন: {name} 🙏",
        "vote_comment": "🗳️ এই পর্বের শেষ ঠিক হয়েছে আপনাদের ভোটে - {names}, ধন্যবাদ!",
        "congrats_reply": "🏆 আপনার উত্তর ঠিক ছিল! আজকের ভিডিওতে আপনার নাম বলা হয়েছে 👉 {link}",
    },
}

THEMES = [
    # haunted places
    "a closed cinema hall that still shows a film at midnight", "a hill-station hotel room number 13",
    "an IT office on the 14th floor during the night shift", "an old lighthouse on the Odisha coast",
    "a tea-garden bungalow in Darjeeling fog", "a jute mill closed for 30 years", "a burnt village theatre stage",
    "a hospital morgue during a power cut", "a girls' hostel and the room no one takes",
    # objects and curses
    "a cursed silver anklet bought at a village fair", "an old harmonium that plays by itself",
    "a photo album with one face that keeps moving", "a wedding saree from a dead bride's trunk",
    "a pocket watch that stops at the time of a death", "a well-water mirror that shows the future",
    # people and spirits
    "a tantrik's revenge on a greedy landlord", "a ghost that comes back every Amavasya",
    "twin sisters, one of them died years ago", "a postman delivering letters from the dead",
    "a taxi driver's strangest passenger in heavy rain", "a child's imaginary friend who is not imaginary",
    "the possessed doll of a zamindar's daughter", "a cremation-ground caretaker's last night",
    "a wedding procession of ghosts on a lonely road", "a fisherman and the woman who walks on water",
    "a chudail with backward feet on the village road at night", "a brahmadaitya living in an old bel tree",
    "a shakchunni who wants to become a married woman", "nishi daak - a voice at midnight calling your name",
    "a mechho bhoot who steals fish from the fishermen", "a pishach in the cremation ground (shamshan)",
    "a vetal hanging from a tree in the forest", "a headless ghost (skandhakata) near the railway line",
    "a daayan who takes children's shadows", "a ghost bride in a red saree on the highway",
    "a haunted zamindar bari in a Bengal village", "an old British-era dak bungalow in the hills",
    "a Kolkata tram depot after the last tram", "a Rajasthan stepwell (baori) at night",
    "a Kuldhara-like deserted village", "a Purulia forest guest house",
    "a Sundarbans boat trip and the jungle spirit", "a ghost who asks for a lift at midnight",
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
EMOTIONS = ["normal", "whisper", "scared", "shout", "angry", "sad", "crying", "eerie", "calm"]

ART_STYLE = ("cinematic photorealistic film still, horror movie atmosphere, dark moody low-key lighting, "
             "cold blue and green tones with warm lamp light, light fog, realistic Indian people and places, "
             "35mm photo, shallow depth of field, highly detailed, eerie but not gory, no blood, no gore, "
             "no text, no letters, no watermark")


def log(*a):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}]", *a, flush=True)
    msg = " ".join(str(x) for x in a)
    if any(k in msg for k in ("skipped", "FAILED", "STOPPED", "failed")):
        extras.note_issue(msg.strip())


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


# cron-job.org starts each video about 1 hour before it should be online (India time):
# (start hour, start minute, the hour the video should be out)
TRIGGERS = [(10, 0, 13), (18, 0, 21)]   # start 3 hours early, publish at 1 PM and 9 PM
SLOT = None


def recently_posted(history, hours):
    """True if a video was posted in the last few hours (so a backup run must not post a second one)."""
    for h in history[-3:]:
        if h.get("kind") == "compilation":
            continue
        try:
            t = dt.datetime.fromisoformat(str(h.get("date", "")))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            if dt.datetime.now(dt.timezone.utc) - t < dt.timedelta(hours=hours):
                return True
        except Exception:
            pass
    return False


def save_history(items):
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(items[-200:], f, ensure_ascii=False, indent=1)


def pick_language(history):
    """One language per page/channel (default Bengali) - a mixed-language channel splits its audience.
    Set the secret CHANNEL_LANG to "hi" for Hindi; "both" brings back one Hindi, one Bengali."""
    forced = env("LANGUAGE").lower()
    if forced in LANGS:
        return forced
    chan = (env("CHANNEL_LANG") or "bn").lower()
    if chan in LANGS:
        return chan
    last = history[-1].get("lang", "hi") if history else "bn"
    return "bn" if last == "hi" else "hi"


FORMATS = [
    "a whodunit ghost mystery: midway the narrator stops and asks the listeners which of three suspects is "
    "really the ghost (telling them to comment 1, 2 or 3 and to listen till the end), and the final scene "
    "reveals the answer with a twist",
    "classic third-person radio-drama narration",
    "told in first person by someone who lived through it ('that night I...'), as if sharing a true experience",
    "a listener's letter read out by the narrator, then the events play out",
    "two friends telling ghost stories at night, and one story becomes real",
]


NEXT_PART = os.path.join(HERE, "next_part.json")


def load_next_part(ready_only=True):
    """Part 1 of a series saves what part 2 needs. The next part comes the NEXT DAY (part 1 today, part 2
    tomorrow, part 3 the day after), so viewers wait for it. ready_only=False: also a part not due yet."""
    try:
        with open(NEXT_PART, encoding="utf-8") as f:
            nxt = json.load(f)
        made = dt.datetime.fromisoformat(nxt["created"])
        if (dt.datetime.now(dt.timezone.utc) - made).total_seconds() < 5 * 86400:
            if ready_only and env("SERIES_NEXT_DAY") != "0" and \
                    made.astimezone(extras.IST).date() >= dt.datetime.now(extras.IST).date():
                return None
            return nxt
    except Exception:
        pass
    return None


BHAIRAB = [
    {"name": "Bhairab Thakur", "gender": "male", "age": "old", "kind": "human",
     "look": "a tall thin old Bengali tantrik of about seventy, long grey matted hair tied on top of his head, thick "
             "grey beard, sharp kind eyes lined with kohl, red tilak on forehead, deep red dhoti and a black shawl, "
             "rudraksha beads, carries an old brass lantern and a bamboo staff"},
    {"name": "Paltu", "gender": "male", "age": "young", "kind": "human",
     "look": "a chubby nervous young Bengali man of about twenty-two, round face, messy short black hair, big round "
             "glasses, yellow checked shirt and blue jeans, cloth sling bag, always holding a small torch"},
]
BHAIRAB_RULE = ("RECURRING CHARACTERS: this is a case of our own ghost-hunter duo - BHAIRAB THAKUR (old tantrik, calm, "
                "wise, a little dry humour, never afraid, solves the mystery with knowledge and courage, never with "
                "black magic or harm) and his assistant PALTU (young, scared of everything, very funny, but brave "
                "when it matters). People call Bhairab Thakur for help with a haunting; they investigate, face the "
                "ghost, and Bhairab frees the troubled spirit (give the ghost a sad reason for haunting). Include both "
                "with exactly these looks: {looks}. Start with Paltu's funny line and end with a hint of the next case.")


# Taranath Tantrik - the old tantrik of Bibhutibhushan Bandyopadhyay's 1940s stories (that original is public
# domain in India). We only use the character and his world; every case is a NEW story of our own (never retell
# later books or the web series).
TARANATH = [
    {"name": "Taranath", "gender": "male", "age": "old", "kind": "human",
     "look": "a lean dark-skinned Bengali tantrik of about sixty-five, long half-grey hair falling to the shoulders, "
             "short grey beard, deep piercing eyes, a red sindoor line on the forehead, bare chest with thick "
             "rudraksha malas, saffron-red dhoti and a faded black shawl, sitting with a hookah in a dim old room"},
    {"name": "Kishori", "gender": "male", "age": "young", "kind": "human",
     "look": "a curious young Bengali man of about twenty-five in a white kurta and dhoti, neat side-parted black "
             "hair, thin moustache, sitting cross-legged and listening with wide eyes, 1940s Kolkata"},
]
TARANATH_RULE = (
    "TARANATH TANTRIK SERIES: on a rainy evening in his old house in a Kolkata lane, the old tantrik TARANATH tells "
    "young KISHORI a terrifying experience from his wandering years (cremation grounds, lonely villages, forests of "
    "Birbhum and Bengal's rivers, 1920s-1940s). Write it as Taranath telling his OWN experience in first person "
    "(his voice is the main narrator inside the story; Kishori interrupts 2-3 times with a scared question). "
    "Taranath is brave, earthy, honest about his fear, never a cheap magician; real dark forces, ancient spirits, "
    "a dangerous ritual gone wrong, a terrible price. No real ritual instructions, no harm to children, no gore. "
    "Use exactly these looks: {looks}. Open with Taranath's chilling first sentence; end with Kishori shivering and "
    "Taranath hinting at another, even more dangerous experience 'next time'.")


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


def make_story(lang, theme, history, fmt=None, part=0, prev=None, extra_rules="", total=2):
    """part=0: one complete story; part=1: first half of a 2-part series (ends on a cliffhanger);
    part=2: the final part, continuing `prev` (saved from part 1)."""
    if MOCK:
        return mock_story(lang)
    key = need_env("GEMINI_API_KEY")
    L = LANGS[lang]
    old_titles = [h["title"] for h in history[-60:] if h.get("lang") == lang]
    fmt = fmt or random.choice(FORMATS)
    cliff_keys = ("Also add JSON keys: \"summary\" (ENGLISH, 5-8 sentences: EVERYTHING that has happened so far in "
                  "the whole series, including earlier parts) and \"part2_plan\" (ENGLISH, 4-6 sentences: how the NEXT "
                  "part continues). And a key \"choice\": the big decision the main character faces at the cliffhanger, "
                  "which the VIEWERS will vote on: {\"question\": short question in the story language, \"option1\": "
                  "2-5 word choice in the story language, \"option2\": 2-5 word choice in the story language, "
                  "\"plan1\": ENGLISH how the next part goes if option 1 wins, \"plan2\": ENGLISH how it goes if "
                  "option 2 wins}.\n")
    if part == 1:
        series_rule = ("\nSERIES: this is PART 1 of a multi-part horror series (a BIG story that is too long and too "
                       "frightening for one video). Introduce the people and the cursed place, build the fear slowly and "
                       "STOP at the most frightening cliffhanger, unresolved. Decide how many parts the WHOLE story needs: "
                       "add a key \"total_parts\": 2 or 3 (3 only if the plot is truly big, with a new layer of horror "
                       "in each part). " + cliff_keys)
    elif part >= 2 and prev:
        series_rule = (f"\nSERIES: this is PART {part} of {total} of a horror series. Title of part 1: {prev.get('title')}. "
                       f"What happened so far: {prev.get('summary')} Planned continuation: {prev.get('part2_plan')} "
                       f"Use EXACTLY these characters (same names, same looks): "
                       f"{json.dumps(prev.get('characters'), ensure_ascii=False)} and this setting: {prev.get('setting')}. "
                       "Begin with a short gripping recap by the narrator (2-3 lines), then continue - the horror must be "
                       "even WORSE than in the previous part. ")
        if part < total:
            series_rule += ("This is a MIDDLE part: reveal one terrible new secret, and STOP again at an even bigger "
                            "cliffhanger, unresolved. " + cliff_keys)
        else:
            series_rule += "This is the FINAL part: end with a shocking twist that answers the whole mystery.\n"
        vote = prev.get("vote")
        if vote:
            series_rule += (f"VIEWERS VOTED: {vote['v1']} chose '{vote['option1']}', {vote['v2']} chose "
                            f"'{vote['option2']}'. This part MUST follow the winning choice: {vote['plan']} "
                            "The narrator's FIRST line thanks the viewers and says most of them chose "
                            f"'{vote['winner_text']}' - and that is exactly what happened next...\n")
    else:
        series_rule = ""
    prompt = f"""
You are India's best {L['name']} horror storyteller, writing for a horror story video page.
Write ONE brand-new horror story in {L['name']} ({L['script']} script; simple, natural,
spoken {L['name']} that ordinary people use). Idea to build on: {theme}.
You may use classic Indian folk ghosts (chudail, brahmadaitya, shakchunni, nishi, pishach, vetal, daayan...)
but the plot, people and events must be your OWN. Do not copy films or real incidents; no real people.
Must be different from these earlier stories: {json.dumps(old_titles, ensure_ascii=False)}

Story rules:
- LENGTH: 14 to 18 scenes, 5-6 minutes when spoken - at least 800 spoken words in total. Never rush the
  ending; the story must feel complete. It must be GENUINELY SCARY and impossible to stop listening:
  * the FIRST line is a chilling hook (a strange fact, a warning, or a scream) - no slow introduction;
  * every scene ends with a small cliffhanger, the fear grows scene by scene;
  * use the five senses: cold air, a smell of burning flowers or wet earth, a sound behind you, a touch in the dark;
  * the ghost is shown little by little (a shadow, then a voice, then a face) - the full reveal comes late;
  * 2-3 real jump scares, and a shocking twist ending that makes people comment.
  Keep the narration moving at a natural pace - short punchy sentences in tense moments.
- Spooky and suspenseful, NOT gory: no blood, no violence details, no harm to children, nothing sexual.
- 2 to 4 characters plus a narrator. Real dialogue between characters (short, natural lines).
- Each scene has 4 to 7 lines. The narrator describes; characters speak only their own words
  (no "he said" inside dialogue). Narrator lines 25-50 words, dialogue lines 4-20 words.
- Telling style for this story: {fmt}
{series_rule}{extra_rules}
- Every picture must show exactly what that scene's lines describe.
- SOUND DESIGN like a radio horror drama: for every line think what the listener should HEAR.
  When a line mentions a door, footsteps, knocking, wind, rain, a scream, bells, a phone, breaking glass,
  put that exact sound in that line's "sfx" with the right timing. 0-3 sfx per line, only real story events.
  Be very specific so a real recording can be found ('rusty iron gate creaks open', 'barefoot steps on wet floor',
  'anklet bells (ghungroo) jingling slowly', 'woman laughing in the distance', 'heavy breathing close to ear').
  Every time the ghost comes near, add a ghost sound (cold wind gust, whisper, ghungroo, low growl, slow breathing).
- Think like a film director: every line gets its own camera "shot" showing exactly what that line says
  (close-up of a frightened face, a hand on the door handle, the lamp flickering, a shadow in the corridor...).
- PICTURES MUST BE AUTHENTIC AND LOGICAL, frame by frame, like a real horror film storyboard. For every line
  imagine the exact frame: who is in it (count them), where each one is, the BODY POSITION of each (lying /
  sitting / standing / crouching / hiding / running / frozen), what their HANDS are doing (holding the lantern,
  covering the mouth, gripping the door), where they LOOK, and the FEELING on each face (terror, shock, dread).
  Follow real life and the words exactly: someone hiding under the bed = lying flat under the bed, eyes wide;
  a ghost behind someone = the ghost stands behind them in the dark, the person has not seen it yet. Never add
  people who are not in the line, never show the same character twice, ages and sizes stay true, the ghost
  looks the same every time. Night/day, weather and the place must match the story.
- Give every line an emotion so the voice acts it (whisper when hiding, scared when afraid, shout when screaming).
- Mark "jump_scare": true on 1-3 lines in the whole story where the big scare lands (a sudden sound/reveal).
- THE GHOST'S LAUGH: the ghost must LAUGH - a harsh, piercing, blood-curdling laugh - at 2-4 key moments (when it
  first shows itself, when the hero is trapped, at the final twist). On those lines put the ghost's name in
  "ghost_laugh" (the line can be the ghost's own words or the narrator describing the laugh, e.g. 'অন্ধকার চিরে
  ভেসে এল এক কর্কশ, তীব্র হাসি...'). The ghost's own lines may also contain হা-হা-হা / হি-হি-হি.
{extras.STORY_CRAFT}{extras.HOOK_RULES}{extras.HORROR_DREAD}{extras.WRITING_RULES.get(lang, "")}{extras.VOICE_ACTING}

Return ONLY JSON with exactly these keys:
{{
 "title": "chilling {L['name']} title, max 60 characters, 1 emoji",
 "thumbnail_text": "2-4 BIG {L['name']} words that create an unbearable curiosity gap or warning (e.g. 'রাত ১২টায় দরজা খুলো না!', 'ও এখনো ফেরেনি...', 'কে ডাকছে?') - never just the title",
 "description": "3-4 line suspenseful {L['name']} description that makes people want to watch, ending with a question",
 "hashtags": ["10-14 popular hashtags mixing {L['name']} and English, e.g. #HorrorStory #BhootKiKahani"],
 "setting": "ENGLISH: the ONE main place of the story (architecture, objects, era, weather, time of night, colors). Reused in every picture",
 "characters": [{{"name": "name in English letters", "gender": "male or female",
                  "age": "child, young, adult or old", "kind": "human or ghost",
                  "look": "ENGLISH, very specific never-changing look: age, face, hair, skin, clothes with exact colors, one special detail. 20-35 words"}}],
 "episode_name": "2-3 word {L['name']} episode name for the thumbnail, eerie and exact (e.g. 'নিশির ডাক', 'পোড়ো বাড়ির ছায়া')",
 "thumbnail_image": {{"hero": "the main human character's name (big in the foreground)", "hero_action": "ENGLISH: pose, what the hands hold (lantern, torch) and the tense face at the scariest moment, e.g. 'holding a brass lantern, looking up toward the window with tense, focused fear'", "second": "the ghost's name", "ghost": "ENGLISH: exactly how THIS story's ghost looks at its scariest (face, eyes, hair, clothes, skin, special detail like backward feet or red saree) - 25-40 words", "second_action": "ENGLISH: where the ghost is and what it does, e.g. 'standing in the upstairs window behind him, staring down'", "place": "ENGLISH: the exact haunted place with rich authentic Bengal details", "moment": "ENGLISH: one sentence - the visual story of the thumbnail"}},
 "scenes": [{{
    "characters": ["names VISIBLE in the picture"],
    "action": "ENGLISH: exactly what happens in this scene: who does what, poses, expressions, key objects",
    "place": "ENGLISH: where in the setting + lighting",
    "mood": "one of {MOODS}",
    "ambience": ["1-2 ENGLISH continuous background sounds that fit THIS place and moment, e.g. 'heavy rain on tin roof', 'night crickets in fields', 'wind howling through broken windows', 'old wall clock ticking', 'river flowing at night', 'distant temple bells'"],
    "lines": [{{"speaker": "narrator or a character name", "text": "{L['name']} text",
                "en": "the same line translated to natural English (for subtitles)",
                "emotion": "one of {EMOTIONS}",
                "delivery": "ENGLISH acting direction for the voice (pitch, speed, loudness, feeling)",
                "voice_text": "same words as text, with 0-2 sound tags like <gasp> or <sigh> where they fit",
                "sfx": [{{"sound": "ENGLISH short sound name of what HAPPENS in this line, e.g. 'old wooden door creaks open', 'slow footsteps on wooden floor', 'glass shatters', 'three knocks on door', 'woman screams far away', 'dog howls', 'match strike', 'thunder crack', 'bangles jingling', 'heavy breathing'",
                          "when": "before (sound first, then the line), during, or after (line first, then the sound)"}}],
                "jump_scare": false,
                "ghost_laugh": "",
                "image": {{"prompt": "ENGLISH picture prompt for THIS line, 30-50 words, like a horror film still: WHO/WHAT is in frame and their exact action, pose and facial expression matching the words of this line, WHERE (which part of the setting), camera (extreme close-up / close-up / wide / over-the-shoulder / low angle), light source (lantern, moonlight, lightning), key objects. Only things that can be SEEN. Every line gets a different picture that matches its words exactly",
                           "people": [{{"name": "a character name exactly as in characters", "pose": "lying / sitting / standing / crouching / hiding / running / frozen / floating ...", "doing": "exactly what the body and HANDS do, e.g. 'gripping the lantern with both hands'", "where": "left / middle / right of the frame, and on or near what (in the doorway, under the bed, behind the tree)", "feeling": "facial expression and emotion, e.g. 'wide eyes, frozen in terror'"}}],
                           "characters": ["names VISIBLE in this picture, in order from LEFT to RIGHT; [] if only a place or object is shown"]}}}}]
 }}],
 "ending_line": "one short {L['name']} line from the narrator that leaves a chill",
 "comment_question": "one short {L['name']} question to viewers that makes them comment (e.g. 'आप होते तो क्या करते?'), with 1 emoji",
 "mystery_answer": "only for a which-suspect mystery: the right number (1, 2 or 3) as asked in the story; otherwise 0",
 "teaser_scene": "number: the scene (1 = first) where the most gripping 50 seconds START - used for the Reel/Short teaser"
}}
Every scene object also has "chapter": "2-4 word {L['name']} chapter name for YouTube chapters".
"""
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0, "responseMimeType": "application/json",
                                 "maxOutputTokens": 60000}}
    last_err = None
    best, min_words = None, int(env("MIN_WORDS") or 650)       # ~650+ spoken words = 5+ minutes
    models = gemini_models(key)
    for round_no in range(3):
        if round_no:
            log(f"All Gemini models busy - waiting {90 * round_no} s")
            time.sleep(90 * round_no)
        for model in list(models):
            try:
                log(f"Writing story with {model} ...")
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent",
                                  headers={"x-goog-api-key": key}, json=body, timeout=300)
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
                words = sum(len(str(ln.get("text", "")).split()) for sc in story["scenes"] for ln in sc["lines"])
                log(f"  story: {len(story['scenes'])} scenes, {words} spoken words")
                if not best or words > best[0]:
                    best = (words, story)
                if words < min_words:
                    body["contents"][0]["parts"][0]["text"] = prompt + (
                        f"\n\nIMPORTANT: your last story had only {words} spoken words - far too short. "
                        f"Write at least {min_words + 150} spoken words: more scenes and more lines per scene.")
                    raise ValueError("story too short - asking for a longer one")
                return story
            except LookupError as e:
                last_err = e
                models.remove(model)
            except Exception as e:
                last_err = e
                log("  trying next model:", str(e)[:200])
                time.sleep(5)
    if best:
        log(f"  using the longest story written ({best[0]} words)")
        return best[1]
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
        """Picture prompt. The exact moment of the story comes FIRST (the picture model follows the start
        of the prompt most), then who is in it, then the place, then the art style."""
        low = ascii_text(action).lower()
        empty = isinstance(names, list) and not names           # [] = a shot with nobody in it
        names = list(names or []) + [c["name"] for c in self.chars.values() if c["name"].lower() in low]
        chosen = []
        for n in names:
            c = self.find(n)
            if c and c not in chosen:
                chosen.append(c)
        if not chosen and not empty:
            chosen = list(self.chars.values())
        who = (f"Characters in the picture (ONLY these, each exactly as described): {self.describe(chosen)} "
               if chosen else "No people in this picture, only the place and the objects described. ")
        p = (f"{ascii_text(action)}. {who}"
             f"Location: {ascii_text(place)}. {self.setting}. Style: {ART_STYLE}.")
        if use_ref and chosen:
            p = ("Use image 0 ONLY for how the characters look (same faces, hair, body, clothes). Do NOT copy their "
                 "poses or positions from image 0. Draw this NEW scene with a full background, each character in the "
                 "exact pose and action written here: " + p)
        return p


CF_QUOTA_OUT = False
PIC_W, PIC_H = 1024, 576        # 16:9; scaled up to 1280x720 for the video


def cf_accounts():
    """All Cloudflare accounts given: CF_ACCOUNT_ID/CF_API_TOKEN, then ..._2, ..._3 (each has its own free limit)."""
    out = []
    for suf in ("", "_2", "_3", "_4"):
        a, t = env("CF_ACCOUNT_ID" + suf), env("CF_API_TOKEN" + suf)
        if a and t:
            out.append((a, t))
    if not out:
        need_env("CF_ACCOUNT_ID")
    return out


CF_ACTIVE = 0


AGNES_SAID = False


def cf_request(model, prompt, ref_path=None, w=PIC_W, h=PIC_H, seed=None):
    """A picture: Cloudflare first (account 1, then 2); when their free daily limit is used up,
    the free Agnes AI pictures (if AGNES_API_KEY is set)."""
    global AGNES_SAID
    if not CF_QUOTA_OUT:
        try:
            return _cf_request_all(model, prompt, ref_path, w, h, seed)
        except RuntimeError:
            if not CF_QUOTA_OUT:
                raise
    if extras.agnes_ok():
        if not AGNES_SAID:
            log("  Cloudflare limit used up - making the rest of the pictures with Agnes AI")
            AGNES_SAID = True
        if "exact pose and action written here: " in prompt:          # no reference picture on Agnes
            prompt = prompt.split("exact pose and action written here: ", 1)[1]
        return extras.agnes_image(prompt)
    raise RuntimeError("all Cloudflare accounts used up their daily free allocation (4006)")


def _cf_request_all(model, prompt, ref_path=None, w=PIC_W, h=PIC_H, seed=None):
    """Ask Cloudflare for a picture. When one account's free daily limit is used up,
    move on to the next account automatically."""
    global CF_ACTIVE, CF_QUOTA_OUT
    accounts = cf_accounts()
    while CF_ACTIVE < len(accounts):
        try:
            return _cf_request_one(accounts[CF_ACTIVE], model, prompt, ref_path, w, h, seed)
        except RuntimeError as e:
            if any(k in str(e).lower() for k in ("4006", "daily free allocation", "neurons")):
                CF_ACTIVE += 1
                if CF_ACTIVE < len(accounts):
                    log(f"  Cloudflare account {CF_ACTIVE} free limit used up - switching to account {CF_ACTIVE + 1}")
                    continue
                CF_QUOTA_OUT = True
            raise
    CF_QUOTA_OUT = True
    raise RuntimeError("all Cloudflare accounts used up their daily free allocation (4006)")


def _cf_request_one(account, model, prompt, ref_path, w, h, seed):
    acct, token = account
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
    plain = [c for c in humans if not str(c.get("kind", "")).startswith("ghost")] or humans
    for attempt in range(3):
        if attempt == 1:          # the safety filter said no: gentler words, a new seed
            prompt = soften(prompt)
        elif attempt == 2:        # still no: only the living people (ghosts are drawn later, scene by scene)
            prompt = soften(f"{ART_STYLE}. Cast reference photo: all these people standing side by side, full body, "
                            f"facing the camera, neutral grey studio background, even soft light. {cast.describe(plain)}")
        try:
            data = cf_request(CF_MODEL, prompt, w=1024, h=576, seed=seed + attempt * 101)
            with open(path + ".raw", "wb") as f:
                f.write(data)
            im = Image.open(path + ".raw").convert("RGB")
            im.thumbnail((508, 508))
            im.save(path, quality=92)
            cast.ref = path
            return True
        except Exception as e:
            log(f"  cast sheet attempt {attempt + 1} failed: {str(e)[:200]}")
            if CF_QUOTA_OUT:
                return False
            time.sleep(6 * (attempt + 1))
    return False


def make_image(cast, action, place, names, path, seed):
    global CF_QUOTA_OUT
    if MOCK:
        return mock_image(path, seed)
    if CF_QUOTA_OUT and not extras.agnes_ok():
        return False
    tries = []
    if cast.ref:
        tries.append((CF_MODEL, cast.scene_prompt(action, place, names, True), cast.ref))
    tries.append((CF_MODEL, cast.scene_prompt(action, place, names, False), None))
    tries.append((CF_BACKUP, cast.scene_prompt(action, place, names, False)[:1500], None))
    soft = False
    for attempt, (model, prompt, ref) in enumerate(tries):
        try:
            if soft:
                prompt = soften(prompt)
            save_picture(cf_request(model, prompt, ref, seed=seed + (attempt * 77 if soft else 0)), path)
            return True
        except Exception as e:
            if "flagged" in str(e).lower() or "3030" in str(e):
                soft = True                       # safety filter: next try uses gentler words
            if any(k in str(e).lower() for k in ("allocation", "4006", "quota", "neurons")) and not extras.agnes_ok():
                CF_QUOTA_OUT = True               # free daily limit used up: reuse earlier pictures
                log("  Cloudflare daily free limit reached - reusing earlier pictures with new camera moves")
                return False
            log(f"  picture attempt {attempt + 1} ({model.split('/')[-1]}) failed: {str(e)[:200]}")
            time.sleep(6 * (attempt + 1))
    return False


SOFT_WORDS = {
    "corpse": "still figure", "dead body": "figure lying still", "dead": "lifeless-looking", "blood": "red paint",
    "bloody": "stained", "kill": "chase", "killed": "gone", "murder": "mystery", "knife": "old key",
    "skull": "old stone", "demon": "shadowy figure", "possessed": "strange-eyed", "hanging": "standing",
    "terrified": "worried", "screaming": "calling out", "horror movie": "mystery movie", "ghost": "pale figure",
    "witch": "old woman", "grave": "old stone", "coffin": "old wooden box", "attack": "approach",
    "rotting": "very old", "rotten": "very old", "decayed": "weathered", "decaying flesh": "pale skin",
    "flesh": "skin", "wound": "mark", "wounds": "marks", "bleeding": "red-stained", "blood-soaked": "red-stained",
    "gore": "shadow", "gory": "dark", "severed": "lost", "corpses": "still figures", "drowned": "pale, wet",
    "hanged": "standing", "noose": "old rope", "fangs": "sharp teeth", "claws": "long nails",
    "burnt": "smoky", "skeleton": "old shape", "bones": "old sticks", "torture": "trouble", "suicide": "sad end",
    "cursed": "mysterious", "evil": "strange", "monster": "shadowy figure", "zombie": "pale figure",
}


def soften(prompt):
    out = prompt
    for k, v in SOFT_WORDS.items():
        out = re.sub(rf"\b{k}\b", v, out, flags=re.I)
    return out.replace("eerie but not gory", "mysterious, suspenseful, family friendly")


# ----------------------------------------------------------------- 3. voices
# Voice "set" for every kind of character: (pitch change in Hz, speed change in %)
AGE_VOICE = {"child": (30, 8), "young": (10, 4), "adult": (0, 0), "old": (-16, -14)}


def ghost_kind(gender, age):
    """female / old_female / male / child - each kind of ghost gets its own frightening sound."""
    if age == "child":
        return "child"
    if gender == "female":
        return "old_female" if age == "old" else "female"
    return "male"


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
            ghost = ghost_kind(g, ag) if c["kind"].startswith("ghost") else False
            if ghost:
                rate -= 10
            self.map[c["name"].lower()] = (voice, f"{rate:+d}%", f"{pitch:+d}Hz", ghost)
        # Gemini voices: never the same voice for two characters
        self.gemini_map, taken = {}, {NARRATOR_GEMINI[0]}
        for c in cast.chars.values():
            g = "female" if c["gender"].startswith("f") else "male"
            ag = age_group(c["age"])
            if c["kind"].startswith("ghost"):
                pool = GHOST_POOL[ghost_kind(g, ag)]
            else:
                pool = GEMINI_POOL[(g, ag)] + [v for k, vs in GEMINI_POOL.items() if k[0] == g for v in vs]
            self.gemini_map[c["name"].lower()] = next((v for v in pool if v not in taken), pool[0])
            taken.add(self.gemini_map[c["name"].lower()])
        # free voice model (Indic Parler-TTS): each character its own speaker / pitch
        self.parler_map = extras.parler_cast(
            [(c["name"], c["gender"], age_group(c["age"]), c["kind"].startswith("ghost")) for c in cast.chars.values()],
            lang, "male")
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


# ---------- Gemini voices: real-sounding, acted from written directions
GEMINI_TTS_OFF = False
GEMINI_POOL = {   # prebuilt Gemini voices for each kind of character (first free one is used)
    ("male", "child"): ["Puck", "Achird"], ("male", "young"): ["Fenrir", "Zubenelgenubi", "Sadachbia"],
    ("male", "adult"): ["Orus", "Iapetus", "Alnilam", "Schedar", "Umbriel"],
    ("male", "old"): ["Algenib", "Rasalgethi", "Sadaltager"],
    ("female", "child"): ["Leda", "Laomedeia"], ("female", "young"): ["Zephyr", "Aoede", "Despina"],
    ("female", "adult"): ["Kore", "Callirrhoe", "Erinome", "Sulafat"],
    ("female", "old"): ["Gacrux", "Pulcherrima", "Autonoe"],
}
GEMINI_VOICES = {k: v[0] for k, v in GEMINI_POOL.items()}
GHOST_POOL = {"female": ["Vindemiatrix", "Achernar"], "old_female": ["Gacrux", "Pulcherrima"],
              "male": ["Enceladus", "Algieba"], "child": ["Laomedeia", "Leda"]}
GHOST_WORDS = {
    "female": "a terrifying FEMALE ghost (a chudail / shakchunni): a cold, shrill, breathy woman's voice that wavers "
              "and hisses, sometimes dropping into a slow cruel whisper, and bursting into a harsh, piercing, blood-curdling laugh",
    "old_female": "a terrifying OLD WOMAN ghost (a witch-like crone): a cracked, rasping, trembling old woman's voice, "
                  "slow and spiteful, with a shrill, cracked, terrifying cackle",
    "male": "a terrifying MALE ghost (a pishach / brahmadaitya): a deep, hollow, growling man's voice, slow and heavy, "
            "as if from the bottom of a well, with a booming, harsh, evil laugh",
    "child": "an eerie dead CHILD ghost: a soft, sing-song, innocent child's voice that is deeply wrong and cold, "
             "with a cold, piercing giggle that turns into a shrill laugh",
}
AGE_WORDS = {"child": "a small child of about eight", "young": "a young person in their early twenties",
             "adult": "an adult of about forty", "old": "a very old person in their late seventies, with a tired, slightly shaky, aged voice"}
EMOTION_WORDS = {
    "normal": "naturally", "calm": "calmly and softly", "whisper": "in a frightened whisper, very quietly",
    "scared": "terrified, breathing fast, voice trembling", "shout": "screaming in panic, very loud",
    "angry": "angrily, sharply", "sad": "sadly, slowly, with a heavy heart", "crying": "while crying and sobbing",
    "eerie": "in a low, mysterious voice", "happy": "happily", "excited": "excitedly", "laughing": "laughing",
}
NARRATOR_GEMINI = ("Charon", "the narrator of a famous late-night radio horror drama: a deep, rich, resonant, "
                   "dramatic male baritone voice, at a normal steady storytelling pace (not slow), gripping, with short suspenseful pauses, every word clear")
GHOST_GEMINI = ("Enceladus", "a ghost: a hollow, breathy, cold, slow, otherworldly whispering voice")


def gemini_persona(voices, speaker):
    s = ascii_text(speaker).lower()
    c = voices.cast.find(s) if s and not s.startswith("narrat") else None
    if not c:
        return NARRATOR_GEMINI
    if c["kind"].startswith("ghost"):
        g = "female" if c["gender"].startswith("f") else "male"
        gk = ghost_kind(g, age_group(c["age"]))
        return voices.gemini_map.get(c["name"].lower(), GHOST_POOL[gk][0]), GHOST_WORDS[gk]
    g = "female" if c["gender"].startswith("f") else "male"
    ag = age_group(c["age"])
    voice = voices.gemini_map.get(c["name"].lower(), GEMINI_VOICES[(g, ag)])
    return voice, f"{AGE_WORDS[ag]} ({'woman' if g == 'female' else 'man'} named {c['name']}), a real person, natural and believable"


def gemini_keys():
    """Voice keys: GEMINI_TTS_KEY, GEMINI_TTS_KEY_2, _3, _4 - each from a different free Google account
    (each account has its own daily limit)."""
    return [k for k in (env("GEMINI_TTS_KEY" + suf) for suf in ("", "_2", "_3", "_4")) if k]


GEMINI_KEY_NOW = 0
GEMINI_CACHE = {}          # (scene, line) -> finished Gemini wav, made before the video is put together
GEMINI_READY = False       # True once the whole story was voiced by Gemini


def _gemini_429(r):
    """Read a 'limit reached' answer: returns ('day' | 'minute', seconds to wait)."""
    txt = r.text
    wait = 30.0
    m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', txt)
    if m:
        wait = float(m.group(1))
    kind = "day" if re.search(r"PerDay|per_day|daily", txt, re.I) else "minute"
    return kind, wait


def gemini_line(text, persona, emotion, lang, out_wav, delivery=""):
    """One line performed by Gemini's expressive voice (3.8 Flash TTS first): the character's own voice,
    the emotion, the exact delivery, sound tags like <sigh>/<gasp>, and correct pronunciation."""
    if MOCK or env("USE_GEMINI_VOICE") == "0" or extras.TTS_STATE["off"]:
        return False
    voice, who = persona
    how = EMOTION_WORDS.get(str(emotion).lower(), "naturally")
    style = f"Character: {who}. Emotion: {how}. " + (f"Delivery: {delivery}. " if delivery else "") + extras.PRONOUNCE[lang]
    return extras.tts_gemini(text, voice, style, LANGS[lang]["name"], out_wav, SR)


def parler_persona(voices, speaker, lang):
    s = ascii_text(speaker).lower()
    c = voices.cast.find(s) if s and not s.startswith("narrat") else None
    if not c:   # storyteller: deep, steady male voice
        return (extras.PARLER_SPK.get(lang, extras.PARLER_SPK["bn"])["male"][0], "a deep, low-pitched", "moderate")
    return voices.parler_map.get(c["name"].lower(), ("Arjun", "a moderate-pitched", "moderate"))


def prepare_free_voices(todo, voices, lang, max_minutes=None):
    """Whole story with the free voice model (runs on GitHub, no daily limit). All lines or none."""
    global GEMINI_READY
    if MOCK:
        return False
    if not (extras.parler_ok() and extras.ensure_parler()):
        return no_voice()
    max_minutes = max_minutes or int(env("FREE_VOICE_MINUTES") or 200)
    log(f"Free voice model for all {len(todo)} lines (slow - the post may be a little late)")
    t0 = time.time()
    for k, (i, j, ln) in enumerate(todo):
        if time.time() - t0 > max_minutes * 60:
            log("  free voice model too slow today")
            break
        p = os.path.join(WORK, f"g_{i:02d}_{j:02d}.wav")
        if not extras.parler_line(str(ln["text"]), parler_persona(voices, ln.get("speaker", "narrator"), lang),
                                  ln.get("emotion", "normal"), p, SR):
            log(f"  free voice model stopped at line {k + 1}/{len(todo)}")
            break
        GEMINI_CACHE[(i, j)] = p
        if k == 0 or (k + 1) % 5 == 0:
            log(f"  free voice: {k + 1}/{len(todo)} lines done ({(time.time() - t0) / 60:.1f} min)")
    else:
        GEMINI_READY = True
        log(f"  all lines voiced by the free model in {(time.time() - t0) / 60:.1f} min")
        return True
    GEMINI_CACHE.clear()
    return no_voice()


def no_voice():
    """No good voice today: no robotic Microsoft voice (unless ALLOW_MICROSOFT=1) - skip this video."""
    if env("ALLOW_MICROSOFT") == "1":
        log("  using Microsoft voices for the whole video")
        return False
    log("STOPPED: no expressive voice available today (Gemini free limit used up and the free voice model "
        "failed). Nothing was posted - the next run will try again. (Microsoft voices are switched off.)")
    extras.telegram("⚠️ Daily Horror Story: today's voices could not be made (Gemini limit over, free voice model failed) "
                    "- this video was skipped. The next run will try again.")
    sys.exit(0)


def prepare_gemini_voices(scenes, voices, lang, max_minutes=45):
    """Voice the WHOLE story with Gemini before the video is made. If Gemini cannot finish every line
    (limit reached), none of it is used - the whole video then uses Microsoft voices, so a character's
    voice never changes and the sound never breaks in the middle of the video."""
    global GEMINI_READY
    if MOCK:
        return False
    todo = [(i, j, ln) for i, s in enumerate(scenes) for j, ln in enumerate(s.get("lines") or [])
            if str(ln.get("text", "")).strip()]
    if not extras.tts_keys() or env("USE_GEMINI_VOICE") == "0":
        extras.TTS_STATE["off"] = True
        return prepare_free_voices(todo, voices, lang)
    log(f"Expressive voices for all {len(todo)} lines")
    items = []
    for (i, j, ln) in todo:
        voice, who = gemini_persona(voices, ln.get("speaker", "narrator"))
        feel = EMOTION_WORDS.get(str(ln.get("emotion", "normal")).lower(), "naturally") + (
            f", {ln.get('delivery')}" if ln.get("delivery") else "")
        items.append({"text": extras.performed(ln), "plain": extras.strip_tags(str(ln["text"])), "voice": voice,
                      "who": who, "feel": feel, "spk": voice, "out": os.path.join(WORK, f"g_{i:02d}_{j:02d}.wav"),
                      "lang": lang})
    if extras.tts_gemini_batch(items, LANGS[lang]["name"], SR, extras.voice_minutes(max_minutes)):
        for (i, j, ln), it in zip(todo, items):
            GEMINI_CACHE[(i, j)] = it["out"]
        GEMINI_READY = True
        log("  all lines voiced by Gemini")
        return True
    GEMINI_CACHE.clear()
    extras.TTS_STATE["off"] = True
    return prepare_free_voices(todo, voices, lang)


async def _edge(text, voice, rate, pitch, out, volume="+0%"):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume).save(out)


# how each emotion changes the voice: (speed %, pitch Hz, volume %, extra sound filter)
EMOTION_VOICE = {
    "normal": (0, 0, 0, ""),
    "calm": (-2, -2, -5, ""),
    "whisper": (-10, -6, -35, "highpass=f=180"),
    "scared": (12, 12, 5, ""),
    "shout": (8, 22, 25, "acompressor=threshold=0.2:ratio=4,volume=1.3"),
    "angry": (5, -6, 20, "acompressor=threshold=0.25:ratio=3"),
    "sad": (-14, -10, -10, ""),
    "crying": (-10, 6, -5, ""),
    "eerie": (-6, -8, -5, ""),
}


def _add(a, b, unit):
    return f"{int(str(a).rstrip(unit).replace('+', '') or 0) + b:+d}{unit}"


GHOST_FX = {
    # a woman's ghost stays a WOMAN: wavering voice + a shrill hiss above it + a backwards "breath" before each word
    "female": ("[a]asetrate=44100*0.94,aresample=44100,atempo=1.064,vibrato=f=6:d=0.5[main];"
               "[b]asetrate=44100*1.32,aresample=44100,atempo=0.758,highpass=f=2500,volume=0.42,adelay=60[high];"
               "[c]areverse,aecho=0.8:0.6:280:0.5,areverse,volume=0.38[pre]"),
    "old_female": ("[a]asetrate=44100*0.9,aresample=44100,atempo=1.111,tremolo=f=7:d=0.45[main];"
                   "[b]asetrate=44100*1.25,aresample=44100,atempo=0.8,highpass=f=2200,volume=0.35,adelay=80[high];"
                   "[c]areverse,aecho=0.8:0.6:300:0.5,areverse,volume=0.35[pre]"),
    # a man's ghost: very deep, slow, trembling, with a growl underneath
    "male": ("[a]asetrate=44100*0.76,aresample=44100,atempo=1.18,vibrato=f=4.5:d=0.35[main];"
             "[b]asetrate=44100*1.08,aresample=44100,atempo=0.83,highpass=f=1800,volume=0.35,adelay=70[high];"
             "[c]asetrate=44100*0.6,aresample=44100,atempo=1.5,lowpass=f=700,volume=0.65,adelay=20[pre]"),
    # a child's ghost: innocent and wrong - slightly higher, sing-song wobble, a whisper and a backwards echo
    "child": ("[a]asetrate=44100*1.05,aresample=44100,atempo=0.952,vibrato=f=5:d=0.3[main];"
              "[b]asetrate=44100*1.2,aresample=44100,atempo=0.833,highpass=f=2000,volume=0.35,adelay=90[high];"
              "[c]areverse,aecho=0.8:0.7:350:0.55,areverse,volume=0.4[pre]"),
}


def ghost_fx(src, out_wav, kind, af="anull"):
    """Turns a voice into a frightening ghost voice that still sounds like the right gender and age."""
    layers = GHOST_FX.get(kind, GHOST_FX["male"])
    g = (f"[0:a]{af},asplit=3[a][b][c];{layers};"
         "[main][high][pre]amix=inputs=3:normalize=0,aecho=0.8:0.8:130:0.22,lowpass=f=8000,"
         "dynaudnorm=f=150:g=7,volume=1.1[out]")
    run(["ffmpeg", "-y", "-i", src, "-filter_complex", g, "-map", "[out]", "-ac", "1", "-ar", str(SR), out_wav])


def tts_line(text, voice_spec, gtts_lang, out_wav, emotion="normal"):
    """Speak one line -> mono 44.1k wav, acted with the given emotion. Returns seconds."""
    if MOCK:
        secs = max(1.2, len(text) / 15)
        freq = 180 + (abs(hash(voice_spec[0] + voice_spec[2])) % 200)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs:.2f}",
             "-af", "volume=0.25", "-ar", str(SR), "-ac", "1", out_wav])
        return secs
    voice, rate, pitch, ghost = voice_spec
    er, ep, ev, efx = EMOTION_VOICE.get(str(emotion).lower(), EMOTION_VOICE["normal"])
    rate, pitch = _add(rate, er, "%"), _add(pitch, ep, "Hz")
    volume = f"{ev:+d}%"
    mp3 = out_wav + ".mp3"
    # clean text: symbols/emoji can make the voice service return nothing
    text = re.sub(r"[\u2026]", "...", text)
    text = re.sub(r"[^\w\s\u0900-\u097F\u0980-\u09FF.,!?;:'\"\-()\u0964\u0965]", " ", text)
    text = re.sub(r"\s+", " ", text).strip() or "..."
    ok = False
    # Microsoft's free voice sometimes returns "No audio was received" for some pitch/speed
    # settings (seen with hi-IN-Madhur). So: ask with full settings once; if that fails, ask with
    # plain settings and change pitch/speed ourselves afterwards (sounds the same, never fails).
    def _num(x):
        try:
            return int(str(x).rstrip("%Hz").replace("+", "") or 0)
        except ValueError:
            return 0
    post_pitch, post_tempo = 1.0, 1.0
    tries = [(rate, pitch, volume, False), (rate, "+0Hz", volume, True), ("+0%", "+0Hz", "+0%", True),
             ("+0%", "+0Hz", "+0%", True)]
    for attempt, (r_, p_, v_, manual) in enumerate(tries):
        try:
            asyncio.run(_edge(text, voice, r_, p_, mp3, v_))
            ok = os.path.exists(mp3) and os.path.getsize(mp3) > 800
            if ok:
                if manual:
                    post_pitch = max(0.9, min(1.15, 1 + _num(pitch) / 200))
                    if r_ == "+0%":
                        post_tempo = max(0.7, min(1.4, 1 + _num(rate) / 100))
                break
        except Exception as e:
            log(f"  voice attempt {attempt + 1} failed ({voice}): {str(e)[:80]}")
            time.sleep(2 + 3 * attempt)
    af = "aresample=44100"
    if ok and (post_pitch != 1.0 or post_tempo != 1.0):
        af = (f"rubberband=pitch={post_pitch:.3f}:tempo={post_tempo:.3f}:formant=preserved,"
              f"aresample=44100")
    if not ok:
        # backup (Google) has only one voice -> change its pitch so characters still differ
        from gtts import gTTS
        gTTS(text, lang=gtts_lang).save(mp3)
        hz = int(pitch.replace("Hz", "")) if pitch.replace("Hz", "").lstrip("+-").isdigit() else 0
        male = voice in LANGS["hi"]["male"] + LANGS["bn"]["male"]
        f = max(0.72, min(1.3, (0.80 if male else 1.0) * (1 + hz / 160)))
        af = f"asetrate=44100*{f:.3f},aresample=44100,atempo={min(2.0, max(0.5, 1 / f)):.3f}"
    if efx:
        af += "," + efx
    if ghost:
        ghost_fx(mp3, out_wav, ghost if isinstance(ghost, str) else "male", af)
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


SFX_KEYWORDS = [  # words in a sound name -> built-in sound used when no real recording is available
    (("door", "creak", "hinge", "gate", "floorboard", "chair"), "creak"),
    (("knock", "bang on", "tap"), "knock"),
    (("step", "walk", "footstep", "running"), "footsteps"),
    (("thunder", "lightning", "storm"), "thunder"),
    (("rain", "drizzle", "monsoon"), "rain"),
    (("wind", "breeze", "gust"), "wind"),
    (("heart",), "heartbeat"),
    (("clock", "tick"), "clock"),
    (("owl",), "owl"),
    (("howl", "dog", "wolf", "jackal"), "howl"),
    (("drip", "drop", "tap water"), "drip"),
    (("whisper", "murmur", "breath", "giggle", "laugh"), "whisper"),
    (("cricket", "insect", "night", "field"), "crickets"),
    (("scream", "slam", "crash", "shatter", "glass", "hit", "bang", "jump", "sudden", "boom"), "scare_hit"),
]
_SFX_CACHE = {}


def _keyword_tag(name):
    low = str(name).lower()
    for words, tag in SFX_KEYWORDS:
        if any(w in low for w in words):
            return tag
    return None


def _decode(path, max_sec):
    np = _np()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-t", f"{max_sec:.2f}", "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.float32).astype("float64")
    peak = np.abs(a).max() if len(a) else 0
    return a / peak * 0.8 if peak > 0 else a


def freesound(query, loop):
    """Real recorded sound from freesound.org (only Creative-Commons-0 = free for any use)."""
    key = env("FREESOUND_API_KEY")
    if not key or MOCK:
        return None
    ck = (query.lower(), loop)
    if ck in _SFX_CACHE:
        return _SFX_CACHE[ck]
    path = None
    try:
        dur = "[20 TO 600]" if loop else "[0.3 TO 10]"
        words = re.sub(r"[^a-z ]", " ", query.lower()).split()
        stop = {"a", "an", "the", "on", "of", "in", "at", "slowly", "suddenly", "old", "far", "away", "three", "two"}
        core = [w for w in words if w not in stop]
        pairs = [" ".join(core[i:i + 2]) for i in range(len(core) - 1)]
        generic = {"creak": "door creak", "knock": "knocking door", "footsteps": "footsteps wood floor",
                   "thunder": "thunder", "rain": "rain", "wind": "wind howling", "heartbeat": "heartbeat",
                   "clock": "clock ticking", "owl": "owl hoot", "howl": "dog howling night", "drip": "water drip",
                   "whisper": "whisper", "crickets": "crickets night", "scare_hit": "horror impact"}
        g = generic.get(_keyword_tag(query) or "", "")
        tries = [" ".join(words), " ".join(core)] + pairs + core[:2] + ([g] if g else [])
        res = []
        for q in dict.fromkeys(t for t in tries if t):
            r = requests.get("https://freesound.org/apiv2/search/", timeout=30, params={
                "query": q, "token": key, "fields": "id,name,duration,previews,avg_rating,num_downloads",
                "filter": f'license:"Creative Commons 0" duration:{dur}', "sort": "score", "page_size": 8})
            res = r.json().get("results", []) if r.ok else []
            if res:
                # among the most relevant, prefer well-liked, much-used recordings (better quality)
                res = sorted(res[:5], key=lambda x: (x.get("avg_rating") or 0) * 10 + min(x.get("num_downloads") or 0, 5000) / 500,
                             reverse=True)
                break
        if res:
            pick = res[0]
            url = pick["previews"].get("preview-hq-mp3") or pick["previews"].get("preview-lq-mp3")
            path = os.path.join(WORK, f"fs_{pick['id']}.mp3")
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(requests.get(url, timeout=60).content)
            log(f"    sound: '{query}' -> freesound #{pick['id']} {pick['name'][:40]}")
    except Exception as e:
        log(f"    freesound error for '{query}': {str(e)[:100]}")
        path = None
    _SFX_CACHE[ck] = path
    return path


def get_oneshot(name, rnd, max_sec=4.0):
    """A single sound effect (door creak, scream...). Real recording if possible, else built-in."""
    np = _np()
    p = freesound(name, loop=False)
    if p:
        a = _decode(p, max_sec)
        if len(a) > SR * 0.2:
            fade = min(len(a) // 4, int(SR * 0.3))
            a[-fade:] *= np.linspace(1, 0, fade)
            return a
    tag = _keyword_tag(name)
    if not tag:
        return None
    a = synth(tag, int(SR * max_sec), rnd)
    nz = np.nonzero(np.abs(a) > 0.02)[0]
    if len(nz) == 0:
        return None
    a = a[max(0, nz[0] - int(SR * 0.05)):]
    end = nz[-1] - nz[0] + int(SR * 0.4)
    return a[:max(int(SR * 0.3), end)] / (np.abs(a).max() + 1e-9) * 0.8


LAUGH_WORDS = ("হা হা", "হা-হা", "হাহা", "হি হি", "হি-হি", "হিহি", "খিলখিল", "অট্টহাসি", "হাসি", "হাসল", "হেসে",
               "laugh", "cackle")


def ensure_ghost_laughs(story, want=3):
    """Every story gets the ghost's terrible laugh 2-3 times, even if the story writer forgot to mark it:
    lines where someone laughs, the ghost's first lines, the jump scares."""
    ghosts = [str(c.get("name", "")) for c in story.get("characters", []) if str(c.get("kind", "")).startswith("ghost")]
    if not ghosts:
        return
    lines = [ln for sc in story.get("scenes", []) for ln in sc.get("lines", []) or []]
    have = [ln for ln in lines if ln.get("ghost_laugh")]
    gl = {g.lower(): g for g in ghosts}
    def mark(ln, who):
        if len(have) < want and not ln.get("ghost_laugh"):
            ln["ghost_laugh"] = who
            have.append(ln)
    strong = LAUGH_WORDS[:8] + ("cackle",)            # 'হা হা', 'অট্টহাসি'... anywhere; a plain 'হাসি' only from a ghost
    for ln in lines:                                  # 1) lines that talk about a laugh
        txt, sp = str(ln.get("text", "")), str(ln.get("speaker", "")).lower()
        if any(w in txt for w in strong) or (sp in gl and any(w in txt for w in LAUGH_WORDS)):
            mark(ln, gl.get(sp, ghosts[0]))
    for ln in lines:                                  # 2) the ghost's own first line
        sp = str(ln.get("speaker", "")).lower()
        if sp in gl:
            mark(ln, gl[sp])
            break
    for ln in lines:                                  # 3) the big scares
        if ln.get("jump_scare"):
            mark(ln, ghosts[0])
    for ln in reversed(lines):                        # 4) still too few: the ghost's last words, then the finale
        if len(have) >= 2:
            break
        sp = str(ln.get("speaker", "")).lower()
        if sp in gl:
            mark(ln, gl[sp])
    if len(have) < 2 and len(lines) > 6:
        mark(lines[int(len(lines) * 0.8)], ghosts[0])
    # never two laughs right next to each other
    last = -9
    for k, ln in enumerate(lines):
        if ln.get("ghost_laugh"):
            if k - last < 3:
                ln["ghost_laugh"] = ""
            else:
                last = k
    log(f"  ghost laughs in this story: {sum(1 for ln in lines if ln.get('ghost_laugh'))}")


GHOST_LAUGH_QUERIES = {
    "female": ["evil woman laugh", "female evil laugh", "witch laugh", "creepy woman laugh"],
    "old_female": ["witch cackle", "old woman cackle", "evil witch laugh", "evil woman laugh"],
    "male": ["evil laugh male", "demonic laugh", "deep evil laugh", "monster laugh"],
    "child": ["creepy child laugh", "evil child laugh", "child giggle creepy", "creepy girl laugh"],
}


def ghost_of(voices, name, speaker):
    """Which kind of ghost laughs (female / old_female / male / child): the named ghost, else the speaker,
    else the story's first ghost."""
    for n in (name, speaker):
        spec = voices.map.get(str(n or "").lower())
        if spec and spec[3]:
            return spec[3]
    return next((v[3] for v in voices.map.values() if v[3]), "female")


def ghost_laugh_sound(kind, rnd, max_sec=4.5):
    """A harsh, piercing ghost laugh for this kind of ghost: a real recording, pitched for the ghost
    (deeper for a man, shriller for a woman/child), with a cold double voice and echoes."""
    np = _np()
    kind = kind if kind in GHOST_LAUGH_QUERIES else "female"
    for q in GHOST_LAUGH_QUERIES[kind]:
        p = freesound(q, loop=False)
        if not p:
            continue
        a = _decode(p, max_sec)
        if len(a) < SR * 0.5:
            continue
        def shift(x, f):                              # f < 1 deeper/slower, f > 1 higher
            idx = np.arange(0, len(x) - 1, f)
            return np.interp(idx, np.arange(len(x)), x).astype(np.float32)
        main_f, layer_f = {"male": (0.86, 0.72), "old_female": (0.97, 1.18),
                           "child": (1.06, 1.25), "female": (1.03, 1.22)}[kind]
        a = shift(a, main_f)
        b = shift(a, layer_f / main_f)
        n = max(len(a), len(b))
        out = np.zeros(n + int(SR * 0.9), np.float32)
        out[:len(a)] += a
        out[:len(b)] += b * 0.35                      # a second, inhuman voice inside the laugh
        for d, g in ((0.11, 0.45), (0.26, 0.3), (0.47, 0.18)):   # cold stone-room echoes
            k = int(SR * d)
            out[k:k + len(a)] += a * g
        fade = min(len(out) // 4, int(SR * 0.4))
        out[-fade:] *= np.linspace(1, 0, fade)
        return out / (np.abs(out).max() + 1e-9) * 0.95
    log(f"    no ghost laugh found ({kind})")
    return None


def get_ambience(name, n, rnd):
    """A background sound for the whole scene (rain, crickets...), looped to n samples."""
    np = _np()
    p = freesound(name, loop=True)
    if p:
        a = _decode(p, 120)
        if len(a) > SR * 3:
            reps = int(np.ceil(n / len(a))) + 1
            a = np.tile(a, reps)[:n]
            fade = min(n // 6, int(SR * 1.5))
            a[:fade] *= np.linspace(0, 1, fade)
            a[-fade:] *= np.linspace(1, 0, fade)
            return a * 0.6
    tag = _keyword_tag(name)
    if tag and tag != "scare_hit":
        return synth(tag, n, rnd)
    return None


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


SCENE_FX = {}          # scene index -> {"jump": [seconds], "flash": [seconds]} for the camera effects


def make_scene_audio(lines, voices, lang, idx, sounds, mood, out_wav, ambience=None, place=""):
    """Like a radio drama: every line is spoken with its own voice + emotion, and each sound
    effect is placed exactly where the story says it happens (before / during / after the line).
    Ambience (rain, crickets...) and music run underneath and get quieter while people talk.
    Returns (seconds, [(start, dur, speaker_is_narrator, text)])."""
    np = _np()
    rnd = np.random.default_rng(1000 + idx)
    gap, lead, tail = 0.35, 0.5, 1.0
    pieces, subs, cues, silences, t = [], [], [], [], lead
    for j, ln in enumerate(lines):
        text = str(ln.get("text", "")).strip()
        if not text:
            continue
        sfx = [x for x in (ln.get("sfx") or []) if isinstance(x, dict) and x.get("sound")]
        before = [x for x in sfx if str(x.get("when", "")).startswith("before")]
        during = [x for x in sfx if str(x.get("when", "")).startswith("during")]
        after = [x for x in sfx if str(x.get("when", "")).startswith("after")]
        # sounds that happen first, e.g. "the door creaked..." -> creak, then the words
        for x in before[:3]:
            snd = get_oneshot(x["sound"], rnd)
            if snd is not None:
                cues.append((t, snd, 0.85, x["sound"]))
                t += min(len(snd) / SR, 2.2) * 0.75 + 0.15
        if ln.get("ghost_laugh"):
            # the ghost's harsh, piercing laugh (a real recording, made bigger and colder), then the words
            lg = ghost_laugh_sound(ghost_of(voices, ln.get("ghost_laugh"), ln.get("speaker")), rnd)
            if lg is not None:
                cues.append((t, lg, 1.0, "ghost_laugh"))
                t += min(len(lg) / SR, 4.0) * 0.8 + 0.1
                log("    ghost laugh added")
        if ln.get("jump_scare"):
            # classic jump scare: everything goes almost silent, then a sudden hit
            silences.append((max(0.0, t - 0.9), t))
            cues.append((t, synth("scare_hit", int(SR * 2.5), rnd), 1.0, "scare_hit"))
            t += 0.45
        spec = voices.for_speaker(ln.get("speaker", "narrator"))
        p = os.path.join(WORK, f"v_{idx:02d}_{j:02d}.wav")
        from_gemini = True
        if (idx, j) in GEMINI_CACHE:
            shutil.copy(GEMINI_CACHE[(idx, j)], p)
        elif not gemini_line(extras.performed(ln), gemini_persona(voices, ln.get("speaker", "narrator")),
                             ln.get("emotion", "normal"), lang, p, str(ln.get("delivery", ""))):
            from_gemini = False
            tts_line(extras.strip_tags(text), spec, LANGS[lang]["gtts"], p, ln.get("emotion", "normal"))
        if from_gemini and spec[3]:
            raw_g = p.replace(".wav", "_g.wav")
            shutil.move(p, raw_g)
            ghost_fx(raw_g, p, spec[3] if isinstance(spec[3], str) else "male")
        a = read_wav(p)
        pk = np.abs(a).max()
        if pk > 0:                                    # every voice equally clear; whispers softer
            emo = str(ln.get("emotion", "normal")).lower()
            a = a / pk * {"whisper": 0.6, "shout": 0.97, "angry": 0.93}.get(emo, 0.88)
        if spec[3]:                                   # ghost speaking: cold swell + whispers
            m = int(SR * 1.2)
            swell = _filt(_noise(m, rnd), "bandpass", [300, 3000]) * np.linspace(0, 1, m) ** 2 * 0.35
            cues.append((max(0.0, t - 1.1), swell, 1.0, "ghost_swell"))
            cues.append((t, synth("whisper", len(a) + int(SR * 0.8), rnd) * 1.4, 0.8, "ghost_whisper"))
        pieces.append((t, a, bool(spec[3])))
        sp = ascii_text(ln.get("speaker", "")).lower()
        is_nar = (not sp) or sp.startswith("narrat") or voices.cast.find(sp) is None
        subs.append((t, len(a) / SR, is_nar, text))
        for x in during[:3]:
            snd = get_oneshot(x["sound"], rnd, max_sec=min(6.0, len(a) / SR + 1))
            if snd is not None:
                cues.append((t + 0.25, snd, 0.55, x["sound"]))
        t += len(a) / SR + gap
        for x in after[:3]:
            snd = get_oneshot(x["sound"], rnd)
            if snd is not None:
                cues.append((t - gap + 0.1, snd, 0.85, x["sound"]))
                t += min(len(snd) / SR, 2.0) * 0.7
    total = t - gap + tail
    n = int(total * SR)

    # voices: people in the middle; a ghost's voice drifts around the listener's head
    vL, vR = np.zeros(n), np.zeros(n)
    for start, a, is_ghost in pieces:
        if is_ghost and SPATIAL:
            side = 1 if rnd.uniform() < 0.5 else -1
            l, r = extras.spatialize(a, side * 70, -side * 40, SR)
            l, r = extras.reverb_stereo(l, r, "hall", SR, seed=idx + 7)
        else:
            l, r = a, a
        _place(vL, l, start)
        _place(vR, r, start)

    # background: music + place ambience (from the story) + any old-style tags
    bed = drone(n, rnd, mood)
    for name in (ambience or [])[:3]:
        amb = get_ambience(str(name), n, rnd)
        if amb is not None:
            bed += amb * 0.5
    for tag in (sounds or [])[:3]:
        if tag in SOUND_TAGS and tag != "scare_hit":
            bed += synth(tag, n, rnd) * 0.5

    # sound effects come from a direction (3D for headphones), with the echo of the place
    fxL, fxR = np.zeros(n), np.zeros(n)
    fxinfo = {"jump": [], "flash": []}
    for start, snd, vol, name in cues:
        low = str(name).lower()
        if low == "scare_hit":
            fxinfo["jump"].append(start)
        if any(k in low for k in ("thunder", "lightning", "storm")):
            fxinfo["flash"].append(start + 0.05)
        a0, a1, _ = extras.spatial_path(name, rnd) if SPATIAL else (0, 0, 0)
        l, r = extras.spatialize(snd * vol, a0, a1, SR)
        _place(fxL, l, start)
        _place(fxR, r, start)
    SCENE_FX[idx] = fxinfo
    if SPATIAL:
        fxL, fxR = extras.reverb_stereo(fxL, fxR, extras.room_kind(f"{place} {' '.join(ambience or [])}"), SR, seed=idx)
    bedL, bedR = extras.widen(bed, SR) if SPATIAL else (bed, bed)

    # quieter background while someone talks; near silence before a jump scare
    talk = np.zeros(n)
    for start, a, _g in pieces:
        talk[int(start * SR):int(start * SR) + len(a)] = 1
    talk = np.clip(_filt(talk, "lowpass", 3, 1), 0, 1)
    quiet = np.ones(n)
    for s0, s1 in silences:
        quiet[int(s0 * SR):int(s1 * SR)] = 0.08
    quiet = _filt(quiet, "lowpass", 6, 1)
    duck = (1 - 0.6 * talk) * quiet
    mixL = vL * 0.95 + bedL * duck + fxL * (1 - 0.3 * talk)
    mixR = vR * 0.95 + bedR * duck + fxR * (1 - 0.3 * talk)
    peak = max(np.abs(mixL).max(), np.abs(mixR).max())
    if peak > 0.98:
        mixL, mixR = mixL * 0.98 / peak, mixR * 0.98 / peak
    extras.write_stereo_wav(out_wav, mixL, mixR, SR)
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
    """Viral YouTube-style thumbnail: punchy, high-contrast picture with the scary face on the
    right, huge 2-line text on the left (white + red banner), glow, red frame and a label tag."""
    from PIL import ImageEnhance
    img = Image.open(base_img).convert("RGB").resize((W, H))
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Sharpness(img).enhance(1.8)
    img = ImageEnhance.Brightness(img).enhance(1.08)
    # dark fade on the left half so the text pops
    shade = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(shade)
    for x in range(int(W * 0.62)):
        d.line([(x, 0), (x, H)], fill=int(215 * (1 - x / (W * 0.62)) ** 1.3))
    for y in range(int(H * 0.7), H):                                   # and a bit at the bottom
        d.line([(0, y), (W, y)], fill=max(0, min(255, int(160 * (y - H * 0.7) / (H * 0.3)))))
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shade)

    words = text.strip().split()
    if len(words) >= 2:
        half = len(words) // 2 + len(words) % 2
        lines = [" ".join(words[:half]), " ".join(words[half:])]
    else:
        lines = [text.strip()]
    box_w = int(W * 0.62)
    probe = ImageDraw.Draw(img)
    size = 170
    while size > 56:
        f = font(size)
        if all(probe.textlength(l, font=f) <= box_w - 70 for l in lines) and size * 1.35 * len(lines) <= H * 0.7:
            break
        size -= 6
    f = font(size)
    lh = int(size * 1.38)
    y0 = int((H - lh * len(lines)) / 2) + 10
    x0 = 46

    # red glow behind the text
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, l in enumerate(lines):
        gd.text((x0, y0 + i * lh), l, font=f, fill=(255, 0, 0, 255), stroke_width=size // 6, stroke_fill=(255, 0, 0, 255))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    draw = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        y = y0 + i * lh
        if i == len(lines) - 1 and len(lines) > 1:                    # last line on a red banner
            tw = draw.textlength(l, font=f)
            draw.rounded_rectangle([x0 - 18, y - size * 0.02, x0 + tw + 18, y + size * 1.22], radius=18,
                                   fill=(210, 0, 0))
            draw.text((x0, y), l, font=f, fill=(255, 255, 255), stroke_width=max(4, size // 22), stroke_fill=(70, 0, 0))
        else:
            draw.text((x0, y), l, font=f, fill=(255, 238, 0), stroke_width=max(6, size // 12), stroke_fill=(0, 0, 0))

    # label tag + red frame
    lf = font(40)
    tw = draw.textlength(label, font=lf)
    draw.rounded_rectangle([30, 26, 30 + tw + 44, 26 + 72], radius=14, fill=(0, 0, 0), outline=(255, 30, 30), width=4)
    draw.text((52, 30), label, font=lf, fill=(255, 255, 255))
    draw.rectangle([0, 0, W - 1, H - 1], outline=(220, 0, 0), width=12)
    img.save(out, quality=94)


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


_LAYER_CACHE = {}


def _layers_for(img):
    """Background + cut-out foreground for one picture (cached, pictures repeat)."""
    np = _np()
    import cv2
    if img in _LAYER_CACHE:
        return _LAYER_CACHE[img]
    layers = None
    try:
        layers = split_layers(img)
    except Exception as e:
        log(f"  cut-out failed: {str(e)[:100]}")
    d = {}
    if layers is not None:
        bg, fg = layers
        d["fg_a"] = fg[..., 3].astype("float32") / 255.0
        d["fg"] = cv2.cvtColor(fg[..., :3], cv2.COLOR_RGB2BGR).astype("float32")
        d["fg_rgb"] = fg[..., :3].astype("float32")
        d["faces"] = []
        if env("FACE_ANIM") == "1":                   # face animation is OFF for horror (turn on with FACE_ANIM=1)
            try:                                      # eyes + mouth for blinking, looking around and talking
                import animate
                d["faces"] = sorted(animate.find_faces(np.ascontiguousarray(fg[..., :3])),
                                    key=lambda f_: -f_["mouth"][2])
            except Exception as e:
                log(f"  face animation skipped: {str(e)[:100]}")
        ys, xs = np.nonzero(d["fg_a"] > 0.5)
        d["cx"], d["cy"] = float(xs.mean()), float(ys.max())
        d["head"] = float(ys.min() + 0.28 * (ys.max() - ys.min()))
    else:
        bg = np.array(Image.open(img).convert("RGB").resize((W, H)))
        d["cx"], d["cy"], d["head"] = W / 2, H / 2, H * 0.42
    d["bg"] = cv2.cvtColor(bg, cv2.COLOR_RGB2BGR)
    _LAYER_CACHE[img] = d
    return d


def plan_shots(segments, total):
    """segments: [(image, start_sec)] -> [(image, start, end, close_up)].
    Long shots are split into a wide part and a close-up part so the screen keeps changing."""
    segs = []
    for k, (img, st) in enumerate(segments):
        en = segments[k + 1][1] if k + 1 < len(segments) else total
        if segs and segs[-1][0] == img:                       # same picture twice in a row -> one shot
            segs[-1] = (img, segs[-1][1], en, False)
        else:
            segs.append((img, st, en, False))
    out = []
    for i, (img, st, en, _) in enumerate(segs):
        d = en - st
        parts = 1 if d < 8 else (2 if d < 15 else 3)
        for p in range(parts):
            out.append((img, st + d * p / parts, st + d * (p + 1) / parts, p % 2 == 1))
    return out


SPATIAL = os.getenv("SPATIAL_AUDIO", "1") != "0"
GHOST_FACE = None      # BGR picture of this story's ghost, flashed for a split second on jump scares
VHS = False            # "found footage" look for first-person stories


def _vhs(img_u8, f, sec):
    import cv2
    np = _np()
    out = img_u8.copy()
    out[::2] = (out[::2] * 0.82).astype("uint8")                     # scan lines
    out[..., 2] = np.roll(out[..., 2], 3, axis=1)                    # colour bleeding
    band = int((sec * 140) % (H + 60)) - 30                          # rolling tracking noise
    if 0 <= band < H - 12:
        noise = np.random.default_rng(f).integers(0, 255, (12, W, 3), dtype="uint8")
        out[band:band + 12] = (out[band:band + 12] * 0.4 + noise * 0.6).astype("uint8")
    cv2.putText(out, "REC", (48, 64), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
    if int(sec * 2) % 2 == 0:
        cv2.circle(out, (28, 53), 10, (0, 0, 230), -1)
    stamp = f"PLAY  00:{int(sec) // 60:02d}:{int(sec) % 60:02d}"
    cv2.putText(out, stamp, (W - 330, H - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def scene_clip_animated(segments, audio, out, idx, mood, talk=None):
    """talk: [(start, end, silent, emotion, text)] - when characters speak (mouth moves in sync with the words)."""
    np = _np()
    import cv2
    dur = duration(audio)
    talk = talk or []
    try:
        import animate
        voice_env = animate.voice_envelope(audio, FPS)
    except Exception:
        animate, voice_env = None, None
    brnd = np.random.default_rng(idx + 900)
    blinks, bt = [], brnd.uniform(0.8, 2.5)
    while bt < dur:
        blinks.append(bt)
        bt += brnd.uniform(2.5, 5.0)
    blinks += [tl[0] + 0.05 for tl in talk]
    looks, lt = [], 0.0
    while lt < dur:
        looks.append((lt, brnd.uniform(-0.35, 0.35), brnd.uniform(-0.2, 0.2)))
        lt += brnd.uniform(1.0, 2.6)
    gaze_now = [0.0, 0.0]
    n = int(dur * FPS) + 1
    shots = plan_shots(segments, dur)
    rnd = np.random.default_rng(idx + 50)
    flicker = (rnd.uniform(0, 1, 400) > 0.93).astype("float32") * rnd.uniform(0.4, 1, 400)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", audio, "-t", f"{dur:.2f}",
         "-vf", f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0, dur - 0.4):.2f}:d=0.4,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "3500k", "-bufsize", "7000k",
         "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-ac", "2", out],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    XF = 8                                                  # cross-fade frames between shots
    prev_last, cur_k, frame_in_shot = None, -1, 0
    fxi = SCENE_FX.get(idx, {})
    try:
        for f in range(n):
            sec = f / FPS
            k = next((i for i, s in enumerate(shots) if s[1] <= sec < s[2]), len(shots) - 1)
            img, st, en, close = shots[k]
            if k != cur_k:
                cur_k, frame_in_shot = k, 0
            L = _layers_for(img)
            t = min(1.0, max(0.0, (sec - st) / max(en - st, 0.1)))
            ease = 0.5 - 0.5 * math.cos(math.pi * t)
            direction = 1 if (idx + k) % 2 == 0 else -1
            shake = 0.0
            if mood == "scare" and sec < 0.6:
                shake = 7 * math.sin(sec * 90) * (1 - sec / 0.6)
            if mood in ("tense", "scare"):                  # hand-held camera
                shake += 2.2 * math.sin(sec * 6.1) + 1.4 * math.sin(sec * 11.3 + 1)
            for jt in fxi.get("jump", []):                  # camera jolts on a jump scare
                if 0 <= sec - jt < 0.7:
                    shake += 10 * math.sin((sec - jt) * 70) * (1 - (sec - jt) / 0.7)
            if close:                                       # slow push towards the face
                fx, fy = L["cx"], L["head"]
                bz = 1.32 + 0.08 * ease
            else:                                           # wide shot, gentle drift
                fx, fy = W / 2, H / 2
                bz = 1.04 + 0.06 * ease
            Mb = cv2.getRotationMatrix2D((fx, fy), 0, bz)
            Mb[0, 2] += (W / 2 - fx) * (bz - 1) / bz * (1 if close else 0) + direction * (ease - 0.5) * 22 + shake
            Mb[1, 2] += (H / 2 - fy) * (bz - 1) / bz * (1 if close else 0) + shake * 0.6
            frame = cv2.warpAffine(L["bg"], Mb, (W, H), borderMode=cv2.BORDER_REFLECT).astype("float32")
            if "fg" in L:
                mouth, emo, shape, speaking = 0.0, "", "a", False
                for (ta, tb, nar, em, tx) in talk:
                    if ta <= sec < tb:
                        emo = str(em or "").lower()
                        if not nar and voice_env is not None and f < len(voice_env):
                            mouth, speaking = float(voice_env[f]), True
                            if animate is not None:
                                shape = animate.viseme_at(tx, sec - ta, tb - ta)
                                if shape == "m":
                                    mouth = 0.0
                        break
                blink = 0.0
                for b0 in blinks:
                    if 0 <= sec - b0 < 0.2:
                        blink = math.sin(math.pi * (sec - b0) / 0.2)
                lx, ly = 0.0, 0.0
                for (t0_, gx_, gy_) in looks:
                    if t0_ <= sec:
                        lx, ly = gx_, gy_
                if not speaking and L.get("faces"):
                    lx += 0.45 if L["faces"][0]["mouth"][0] < W / 2 else -0.45
                if emo in ("scared", "whisper", "shout") or mood in ("tense", "scare"):
                    lx = 0.65 * math.sin(sec * 7) + 0.2 * math.sin(sec * 17)     # frightened darting eyes
                elif emo in ("sad", "crying"):
                    ly = 0.6
                gaze_now[0] += (lx - gaze_now[0]) * 0.4
                gaze_now[1] += (ly - gaze_now[1]) * 0.4
                tremble = math.sin(sec * 55) * 1.5 if emo in ("scared", "shout") else 0.0
                src = L["fg"]
                if animate is not None and L.get("faces"):
                    pic = animate.draw_face(L["fg_rgb"], L["faces"], blink, 0.0, "a", tuple(gaze_now))
                    pic = animate.draw_face(pic, L["faces"][:1], 0.0, mouth, shape)
                    src = cv2.cvtColor(np.clip(pic, 0, 255).astype("float32"), cv2.COLOR_RGB2BGR)
                fz = bz * (1.0 + 0.03 * ease) + 0.004 * math.sin(sec * 1.6)
                Mf = cv2.getRotationMatrix2D((fx, fy), 0.3 * math.sin(sec * 0.9), fz)
                Mf[0, 2] = Mb[0, 2] + direction * (ease - 0.5) * 26 - (fz - bz) * fx + tremble
                Mf[1, 2] = Mb[1, 2] - 2.0 * math.sin(sec * 1.1) - (fz - bz) * fy - 2.0 * mouth
                fgw = cv2.warpAffine(src, Mf, (W, H))
                aw = cv2.warpAffine(L["fg_a"], Mf, (W, H))[..., None]
                frame = frame * (1 - aw) + fgw * aw
            frame = grade(frame, f, sec, mood, flicker)
            for jt in fxi.get("jump", []):                  # the ghost's face flashes for a split second
                d_ = sec - jt
                if GHOST_FACE is not None and -0.04 <= d_ < 0.34:
                    a_ = 0.9 if d_ < 0.2 else 0.9 * (0.34 - d_) / 0.14
                    frame = frame * (1 - a_) + GHOST_FACE * a_
            for lt in fxi.get("flash", []):                 # lightning
                d_ = sec - lt
                if 0 <= d_ < 0.1 or 0.22 <= d_ < 0.3:
                    frame = frame * 0.35 + np.array([255, 245, 235], "float32") * 0.65
            if prev_last is not None and k > 0 and frame_in_shot < XF:
                a_ = (frame_in_shot + 1) / (XF + 1)
                frame = prev_last * (1 - a_) + frame * a_
            frame_in_shot += 1
            if f + 1 < n:
                nk = next((i for i, s in enumerate(shots) if s[1] <= (f + 1) / FPS < s[2]), len(shots) - 1)
                if nk != k:
                    prev_last = frame.copy()
            u8 = np.clip(frame, 0, 255).astype("uint8")
            if VHS:
                u8 = _vhs(u8, f, sec)
            ff.stdin.write(u8.tobytes())
        ff.stdin.close()
    except Exception:
        ff.kill()
        raise
    if ff.wait() != 0:
        raise RuntimeError(ff.stderr.read().decode()[-500:])
    return dur


def scene_clip_simple(segments, audio, out, idx, mood):
    """Backup: each picture as its own slow zoom, joined, with the scene sound."""
    dur = duration(audio)
    shots = plan_shots(segments, dur)
    parts = []
    for k, (img, st, en, close) in enumerate(shots):
        d = max(0.2, en - st)
        frames = int(d * FPS) + 1
        z = f"min(1.25+0.0006*on,1.35)" if close else ("min(1+0.0005*on,1.07)" if k % 2 == 0 else "max(1.07-0.0005*on,1)")
        p = os.path.join(WORK, f"seg_{idx:02d}_{k:02d}.mp4")
        run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", f"{d:.3f}", "-vf",
             f"scale={W * 2}:{H * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
             f"eq=saturation=0.8:brightness=-0.03,vignette=PI/4,noise=alls=5:allf=t,format=yuv420p",
             "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", p])
        parts.append(p)
    lst = os.path.join(WORK, f"seg_{idx:02d}.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(x)}'\n" for x in parts)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio, "-t", f"{dur:.2f}",
         "-vf", f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0, dur - 0.4):.2f}:d=0.4,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "3500k", "-bufsize", "7000k",
         "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-ac", "2", out])
    return dur


def scene_clip(segments, audio, out, idx, mood, talk=None):
    if env("SIMPLE_MOTION") == "1" or (MOCK and env("TEST_ANIM") != "1"):
        return scene_clip_simple(segments, audio, out, idx, mood)
    try:
        return scene_clip_animated(segments, audio, out, idx, mood, talk)
    except Exception as e:
        log(f"  animation skipped ({str(e)[:150]}) - simple motion")
        return scene_clip_simple(segments, audio, out, idx, mood)


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


TIMELINE = ([], [])          # (start second of every part, every spoken line) of the last video
BADGE_COLORS = ((200, 0, 20), (255, 255, 255))


def build_video(scene_parts, lang, out):
    """scene_parts: list of dict(image, lines, sounds, mood). Returns mp4 path."""
    global TIMELINE
    clips, segs, t, wavs, part_times = [], [], 0.0, [], []
    voices = scene_parts[0]["voices"]
    prepare_gemini_voices(scene_parts, voices, lang)       # all lines (intro + story + ending) or none
    for i, sp in enumerate(scene_parts):
        log(f"Voices + sound + clip {i + 1}/{len(scene_parts)}")
        part_times.append(t)
        a = os.path.join(WORK, f"audio_{i:02d}.wav")
        wavs.append(a)
        d, subs = make_scene_audio(sp["lines"], voices, lang, i, sp.get("sounds"), sp.get("mood", "creepy"), a,
                                   sp.get("ambience"), sp.get("place", ""))
        c = os.path.join(WORK, f"clip_{i:02d}.mp4")
        shots = sp.get("shots") or []
        segments = []
        for k, (st, du, nar, tx) in enumerate(subs):        # picture changes when the next line starts
            img = shots[k] if k < len(shots) and shots[k] else sp["image"]
            segments.append((img, 0.0 if k == 0 else max(0.0, st - 0.2)))
        if not segments:
            segments = [(sp["image"], 0.0)]
        spoken = [ln for ln in sp["lines"] if str(ln.get("text", "")).strip()]
        talk = [(st, st + du, nar, (spoken[k].get("emotion", "") if k < len(spoken) else ""), tx)
                for k, (st, du, nar, tx) in enumerate(subs)]
        d = scene_clip(segments, a, c, i, sp.get("mood", "creepy"), talk)
        segs += [(t + s, du, nar, tx) for s, du, nar, tx in subs]
        clips.append(c)
        t += d
    lst = os.path.join(WORK, "clips.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", os.path.join(WORK, "joined.mp4")])
    alst = os.path.join(WORK, "audio.txt")
    with open(alst, "w") as f:
        f.writelines(f"file '{os.path.basename(a)}'\n" for a in wavs)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", alst, "-c", "pcm_s16le", os.path.join(WORK, "full.wav")])
    write_ass(segs, os.path.join(WORK, "subs.ass"), LANGS[lang]["font_family"])
    vf = f"ass=subs.ass:fontsdir={os.path.dirname(FONT)}:shaping=complex,tpad=stop_mode=clone:stop_duration=3"
    total = duration(os.path.join(WORK, "full.wav"))
    TIMELINE = (part_times, segs)
    try:                                   # small "Like - Share - Follow" pill, top right, at the start and the end
        extras.make_badge(FONT, LANGS[lang]["badge"], os.path.join(WORK, "badge.png"), BADGE_COLORS)
        extras.headphone_hint(FONT, LANGS[lang]["hp"], os.path.join(WORK, "hp.png"))
        pic = ["-i", "badge.png", "-i", "hp.png", "-filter_complex",
               f"[0:v]{vf}[b];[b][2:v]overlay=W-w-24:22:enable='{extras.badge_filter(total)}'[c];"
               f"[c][3:v]overlay=(W-w)/2:H-h-110:enable='between(t,0.5,7)'[v]", "-map", "[v]"]
    except Exception as e:
        log("  badge skipped:", str(e)[:120])
        pic = ["-vf", vf, "-map", "0:v"]
    r = subprocess.run(["ffmpeg", "-y", "-i", "joined.mp4", "-i", "full.wav"] + pic + ["-map", "1:a",
                        "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "23", "-maxrate", "3500k", "-bufsize", "7000k", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart",
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


def fb_when():
    at = extras.publish_time()
    if at:
        log(f"  Facebook: scheduled for {at.strftime('%H:%M')} India time")
        return {"published": "false", "scheduled_publish_time": str(int(at.timestamp()))}
    return {"published": "true"}


def post_to_facebook(video, thumb, title, description):
    """Uploads in pieces (resumable), so big videos don't fail half-way."""
    video, thumb = extras.fb_square(video, thumb, WORK)       # 1:1 ranks better on phones
    description = extras.fb_caption(description)               # Facebook likes 10-400 characters
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
                                                       "description": description, **fb_when()},
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
    at = extras.publish_time()
    if at and not env("YT_PRIVACY"):                  # private until the planned time, then public by itself
        meta["status"]["privacyStatus"] = "private"
        meta["status"]["publishAt"] = at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log(f"  YouTube: scheduled for {at.strftime('%H:%M')} India time")
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
    if not thumb:
        return vid
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
    global SLOT
    SLOT = None if env("MODE") in ("amavasya", "compilation") else extras.current_slot(TRIGGERS)
    extras.plan_publish(SLOT)
    if env("MODE") == "compilation":
        return make_compilation(history)
    # automatic runs (GitHub's clock or the cron-job.org clock) must not post twice for one time slot
    if env("MODE") == "amavasya" and not extras.is_amavasya_night():
        log("Not an Amavasya night - nothing to do.")
        return
    if env("MODE") != "amavasya" and (env("EVENT") == "schedule" or env("MODE") == "auto") and (extras.slot_done(history, SLOT) or recently_posted(history, hours=2)):
        log("A video for this time slot was already posted - this backup run has nothing to do.")
        return
    if not MOCK:
        try:
            extras.refresh_stats(history)            # learn which stories people liked
        except Exception as e:
            log("  stats skipped:", str(e)[:150])
    prev = load_next_part()
    series_waiting = prev is None and load_next_part(ready_only=False) is not None   # next part comes tomorrow
    festival, special, extra_rules, viewer = None, "", "", None
    shout_names, shout_ids = [], []
    lastp = extras.last_post(history)                # who answered the last video's question right?
    if lastp and not MOCK and not lastp.get("continues", lastp.get("part") == 1) and (lastp.get("mystery_answer") or lastp.get("hidden")):
        try:
            digit = lastp.get("mystery_answer") or lastp.get("hidden")
            shout_names, shout_ids = extras.winners(extras.post_comments(lastp.get("facebook"), lastp.get("youtube")),
                                                    digit=digit)
            log(f"Right answers to the last video: {len(shout_names)}")
        except Exception as e:
            log("  right-answer check skipped:", str(e)[:120])
    if env("MODE") == "amavasya":                    # extra midnight story on the new-moon night
        prev = None
    if prev:                                         # finish the series that was started last time
        part, lang, theme, fmt = int(prev.get("done", 1)) + 1, prev["lang"], prev["theme"], prev.get("fmt")
        total = max(part, int(prev.get("total", 2)))
        ch = prev.get("choice") or {}
        if ch.get("plan1") and ch.get("plan2"):      # count the viewers' votes (1 / 2) in the comments
            vc = extras.vote_count(extras.post_comments(prev.get("fb"), prev.get("yt")))
            v1, v2 = len(vc["1"]), len(vc["2"])
            log(f"Viewers' vote: option 1 = {v1}, option 2 = {v2}")
            if v1 + v2 > 0:
                win = 1 if v1 >= v2 else 2
                voter_names = [c["name"] for c in vc[str(win)] if c["name"]]
                prev["vote"] = {"v1": v1, "v2": v2, "option1": ch.get("option1"), "option2": ch.get("option2"),
                                "plan": ch[f"plan{win}"], "winner_text": ch.get(f"option{win}"),
                                "names": list(dict.fromkeys(voter_names))}
            else:
                prev["part2_plan"] = ch.get("plan1") or prev.get("part2_plan")
    else:
        lang, theme = pick_language(history), pick_theme(history)
        fmt = extras.weighted_choice(FORMATS, extras.weights(history, "format", FORMATS))
        part = 1 if (not series_waiting and random.random() < float(env("SERIES_CHANCE") or 0.45)) else 0
        total = 2
        fest = extras.festival_today("horror")
        if fest and not any(h.get("festival") == fest[0] and
                            (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(h["date"])).total_seconds() < 20 * 3600
                            for h in history[-3:] if h.get("date")):
            festival, theme, part = fest[0], fest[1], 0
            log(f"Festival special: {festival}")
        if env("MODE") == "amavasya":
            special, part = "amavasya", 0
            theme = random.choice(["the darkest Amavasya night in a village where no lamp may be lit",
                                   "an Amavasya midnight ritual at the cremation ground that goes wrong",
                                   "the Amavasya night when the dead come back to their old house",
                                   "a lonely road on Amavasya night and the woman with a lantern"])
            extra_rules += ("\nSPECIAL: this is our AMAVASYA MIDNIGHT SPECIAL - tonight is the new-moon night. The story "
                            "happens on an Amavasya night and must be the scariest of the month.\n")
        elif not festival and not part:
            used = {h.get("viewer_story_id") for h in history}
            last_v = max((h.get("date", "") for h in history if h.get("viewer_story_id")), default="")
            days_v = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last_v)).days if last_v else 99
            if days_v >= 6:                          # about once a week: a story sent by a viewer
                try:
                    vs = extras.viewer_stories(history, used)
                except Exception as e:
                    vs = []
                    log("  viewer stories skipped:", str(e)[:120])
                if vs:
                    viewer = vs[0]
                    special = "viewer"
                    theme = "a viewer's own true experience"
                    extra_rules += (f"\nVIEWER'S STORY: build the story on this real experience sent by our viewer "
                                    f"{viewer['name'] or 'a viewer'}: <<<{viewer['text'][:1500]}>>> Keep its core events "
                                    "but dramatize it. Do NOT include any real address, phone number, full name or "
                                    "exact real place - change those. The narrator's FIRST line thanks "
                                    f"{viewer['name'] or 'our viewer'} for sending this experience.\n")
                    log(f"Viewer's story from {viewer['name']}")
            if not special and random.random() < float(env("TARANATH_CHANCE") or 0.35):
                special = "taranath"
                fmt = "Taranath Tantrik telling his own true experience to Kishori, in first person"
                extra_rules += "\n" + TARANATH_RULE.format(looks=json.dumps(TARANATH)) + "\n"
                log("Taranath Tantrik story")
            if not special and random.random() < float(env("BHAIRAB_CHANCE") or 0.15):
                special = "bhairab"
                extra_rules += "\n" + BHAIRAB_RULE.format(looks=json.dumps(BHAIRAB)) + "\n"
                log("Bhairab Thakur case")
        wx = extras.weather_now(lang) if not MOCK else None
        if wx:
            extra_rules += f"\nTODAY'S REAL WEATHER: {wx}. Set the story in this weather and let the listener feel it.\n"
            log("Weather:", wx)
    global VHS
    L = LANGS[lang]
    FONT = find_font(lang)
    VHS = "first person" in str(fmt)               # found-footage camera look for "I lived it" stories
    log(f"Language: {L['name']} | Idea: {theme} | Style: {fmt}" + (f" | SERIES part {part}" if part else ""))

    story = make_story(lang, theme, history, fmt=fmt, part=part, prev=prev, extra_rules=extra_rules,
                       total=total if part else 2)
    ensure_ghost_laughs(story)
    if part == 1:                                    # the story itself says how big it is (2 or 3 parts)
        try:
            total = min(3, max(2, int(str(story.get("total_parts") or 2)[:1])))
        except ValueError:
            total = 2
    continues = bool(part) and part < total          # this part ends on a cliffhanger, the next run goes on
    series_id = (((prev or {}).get("series_id") or (prev or {}).get("created")) if part >= 2 else
                 (dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes") if part == 1 else None))
    if special in ("bhairab", "taranath"):           # always the same faces for our recurring heroes
        fixed = BHAIRAB if special == "bhairab" else TARANATH
        names = {c["name"].lower(): c for c in fixed}
        story["characters"] = [names.get(str(c.get("name", "")).lower(), c) for c in story.get("characters", [])]
        for b in fixed:
            if b["name"].lower() not in [str(c.get("name", "")).lower() for c in story["characters"]]:
                story["characters"].append(b)
    if part >= 2:                                    # same people and place as part 1
        story["characters"], story["setting"] = prev["characters"], prev["setting"]
    title = story["title"].strip()[:85]
    if part:
        title = f"{title} | {L['part'].format(n=part)}"
    if special == "bhairab":
        case_no = 1 + sum(1 for h in history if h.get("special") == "bhairab")
        title = f"{L['bhairab'].format(n=case_no)}: {title}"[:95]
        story["_playlist"] = L["bhairab_pl"]
    elif special == "taranath":
        case_no = 1 + sum(1 for h in history if h.get("special") == "taranath")
        title = f"{L['taranath'].format(n=case_no)}: {title}"[:95]
        story["_playlist"] = L["taranath_pl"]
    elif special == "amavasya":
        title = f"{L['amavasya']}: {title}"[:95]
    log("Title:", title)
    with open(os.path.join(WORK, "story.json"), "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=1)

    cast = Cast(story)
    voices = Voices(lang, cast)
    for c in cast.chars.values():
        log(f"  {c['name']} ({c['gender']}, {c['age']}, {c['kind']}) -> voice {voices.map[c['name'].lower()][:3]}")
    seed = random.randint(1, 1_000_000)
    scenes = story["scenes"][:24]          # never cut the story short

    log("Cast reference picture")
    if not make_cast_sheet(cast, os.path.join(WORK, "cast.jpg"), seed):
        log("  no cast picture - using text descriptions only")

    # one picture per spoken line (a new "camera shot" every few seconds), within the free budget
    budget = int(env("MAX_IMAGES") or 48)
    scene_lines = [[ln for ln in (s.get("lines") or []) if str(ln.get("text", "")).strip()] for s in scenes]
    total_lines = sum(len(x) for x in scene_lines) or 1
    imgs, shots_per_scene, last_ok, count = [], [], None, 0
    for i, (s, lines) in enumerate(zip(scenes, scene_lines)):
        want = max(1, min(len(lines), round(len(lines) * budget / total_lines))) if lines else 1
        groups = [lines[round(g * len(lines) / want):round((g + 1) * len(lines) / want)] for g in range(want)] or [[]]
        scene_shots = []
        for g, grp in enumerate(groups):
            count += 1
            p = os.path.join(WORK, f"shot_{i:02d}_{g:02d}.jpg")
            first = grp[0] if grp else {}
            pic = first.get("image") if isinstance(first.get("image"), dict) else {}
            action = pic.get("prompt") or first.get("shot") or s.get("action", "")
            names = pic.get("characters") if isinstance(pic.get("characters"), list) else s.get("characters")
            people = [x for x in (pic.get("people") or []) if isinstance(x, dict) and x.get("name")]
            if people:                                   # exact poses first: the picture model follows them best
                side_ = lambda x: (0 if "left" in str(x.get("where", "")).lower() else
                                   2 if "right" in str(x.get("where", "")).lower() else 1)
                people = sorted(people, key=side_)
                n_ = len(people)
                desc = "; ".join(
                    f"{x['name']} is {x.get('pose', '')} {x.get('where', '')}, {x.get('doing', '')}, face: {x.get('feeling', '')}"
                    for x in people[:4])
                action = (f"EXACTLY {n_} {'figure' if n_ == 1 else 'figures'} in the picture, no one else, nobody "
                          f"appears twice. {desc}. {action}")
                names = [x["name"] for x in people]
            log(f"Picture {count} (scene {i + 1}, shot {g + 1}/{len(groups)})")
            if make_image(cast, action, s.get("place", ""), names, p, seed):
                last_ok = p
            elif scene_shots:
                p = scene_shots[-1]                      # reuse; the camera move makes it look different
            elif last_ok:
                p = last_ok
            else:
                p = None
            scene_shots += [p] * max(1, len(grp))
        shots_per_scene.append(scene_shots)
        imgs.append(next((x for x in scene_shots if x), None))
    first_ok = next((p for p in imgs if p), None)
    if not first_ok:
        if CF_QUOTA_OUT:
            extras.telegram("⚠️ Daily Horror Story: today's free picture limit is used up - this video was skipped. "
                            "It resets at 5:30 AM India time.")
            log("STOPPED: today's free Cloudflare picture limit is used up on every account. "
                "Nothing was posted. It resets every day at 5:30 AM India time; the next run will work.")
            sys.exit(0)
        raise RuntimeError("No pictures could be made (check CF_ACCOUNT_ID / CF_API_TOKEN).")
    imgs = [p or first_ok for p in imgs]
    shots_per_scene = [[x or imgs[i] for x in sh] for i, sh in enumerate(shots_per_scene)]

    global GHOST_FACE
    hidden = 0
    gchar = next((c for c in cast.chars.values() if c["kind"].startswith("ghost")), None)
    gface = os.path.join(WORK, "ghost_face.jpg")
    if gchar and make_image(cast, f"extreme close-up of {gchar['name']}'s terrifying face staring straight into the "
                            "camera, wide glowing eyes, emerging from pure black darkness, plain pitch-black background",
                            "", [gchar["name"]], gface, seed + 1):
        import cv2
        gf = cv2.imread(gface)
        gf = cv2.resize(gf, (W, H)).astype("float32") * np.array([0.75, 0.75, 1.2], "float32")
        GHOST_FACE = np.clip(gf, 0, 255)
        # "find the ghost": hide the face faintly in 3-4 pictures that are shown only once
        rnd_h = np.random.default_rng(seed)
        flat = [p for sh in shots_per_scene[2:] for p in dict.fromkeys(sh)]
        once = [p for p in flat if sum(sh.count(p) for sh in shots_per_scene) == 1]
        for p in list(rnd_h.permutation(once))[:int(rnd_h.integers(3, 5))] if once else []:
            hp = p.replace(".jpg", "_h.jpg")
            try:
                extras.hide_ghost(p, gface, hp, rnd_h)
                shots_per_scene = [[hp if x == p else x for x in sh] for sh in shots_per_scene]
                hidden += 1
            except Exception as e:
                log("  hide ghost:", str(e)[:100])
        log(f"Ghost face ready; hidden in {hidden} pictures")

    thumb_base = os.path.join(WORK, "thumb_base.jpg")
    ti = story.get("thumbnail_image") or {}
    if isinstance(ti, str):
        ti = {"action": ti}
    ghost = ascii_text(ti.get("ghost", ""))
    ghost_names = [c["name"] for c in cast.chars.values() if c["kind"].startswith("ghost")]
    t_names = list(ti.get("characters") or []) + [n for n in ghost_names[:1] if n not in (ti.get("characters") or [])]
    # poster-style thumbnail: the same formula every time, only the people, the ghost and the moment change
    hero = ti.get("hero") or next((n for n in (ti.get("characters") or []) if n not in ghost_names), "")
    gname = ti.get("second") or (ghost_names[0] if ghost_names else "")
    def describe(n):
        c = cast.find(n) if n else None
        if c and c["kind"].startswith("ghost"):
            return f"{ghost or c['look']} ghost"
        return f"{c['name']} ({c['look']})" if c else n
    t_prompt = extras.poster_prompt("horror", {**ti, "hero": hero, "second": gname}, describe, "", cast.setting)
    if not extras.hq_image(t_prompt, thumb_base, seed):
        if not make_image(cast, t_prompt, "", [n for n in (hero, gname) if n], thumb_base, seed):
            shutil.copy(first_ok, thumb_base)
    thumb = os.path.join(WORK, "thumbnail.jpg")
    series_bn = {"taranath": L["taranath"].split(" #")[0], "bhairab": L["bhairab"].split(" #")[0].replace("ের কেস", "")
                 .replace(" का केस", "")}.get(special)
    big = series_bn or str(story.get("thumbnail_text") or title).strip()
    sub = str(story.get("episode_name") or (story.get("thumbnail_text") if series_bn else "") or "").strip()
    try:
        extras.poster_thumbnail(thumb_base, big, sub, thumb, "horror", FONT)
    except Exception as e:
        log("  poster thumbnail failed, simple one:", str(e)[:120])
        make_thumbnail(thumb_base, story.get("thumbnail_text") or title, thumb, L["label"])

    clean_title = re.sub(r"[^\w\sऀ-ॿঀ-৿,।!?-]", "", title).strip()
    page = env(f"PAGE_NAME_{lang.upper()}") or env("PAGE_NAME") or L["page_default"]
    parts = [{"image": thumb_base, "lines": [{"speaker": "narrator", "text": L["intro"].format(title=clean_title)}],
              "sounds": ["wind"], "mood": "creepy", "voices": voices}]
    for img, s, sh in zip(imgs, scenes, shots_per_scene):
        parts.append({"image": img, "shots": sh, "lines": s.get("lines", []), "sounds": s.get("sounds", []),
                      "ambience": s.get("ambience", []), "mood": s.get("mood", "creepy"), "voices": voices,
                      "place": f"{s.get('place', '')} {story.get('setting', '')}"})
    end_lines = []
    choice = story.get("choice") if continues and isinstance(story.get("choice"), dict) else None
    vote_text = ""
    if choice and choice.get("question") and choice.get("option1") and choice.get("option2"):
        vote_text = L["vote_line"].format(q=choice["question"], o1=choice["option1"], o2=choice["option2"])
    if story.get("ending_line"):
        end_lines.append({"speaker": "narrator", "text": story["ending_line"]})
    if vote_text:
        end_lines.append({"speaker": "narrator", "text": vote_text})
    if hidden:
        end_lines.append({"speaker": "narrator", "text": L["find_ghost_line"]})
    lang_names = lambda ns: extras.name_list(ns, lang)
    if viewer and viewer.get("name"):
        end_lines.append({"speaker": "narrator", "text": L["viewer_credit"].format(name=viewer["name"])})
    vote_names = (prev or {}).get("vote", {}).get("names") if part >= 2 else None
    if vote_names:
        end_lines.append({"speaker": "narrator", "text": L["vote_thanks"].format(names=lang_names(vote_names))})
    if shout_names:
        end_lines.append({"speaker": "narrator", "text": L["shout_line"].format(names=lang_names(shout_names))})
    end_lines.append({"speaker": "narrator", "text": L["how_to_join"]})
    end_lines.append({"speaker": "narrator", "text": (L["outro_part1"] if continues else L["outro"]).format(page=page)})
    parts.append({"image": shots_per_scene[-1][-1] if shots_per_scene[-1] else imgs[-1], "lines": end_lines, "sounds": ["wind"], "mood": "creepy", "voices": voices})

    video = os.path.join(WORK, "final.mp4")
    build_video(parts, lang, video)
    log(f"Video ready: {duration(video):.0f} seconds")

    tags = [t if t.startswith("#") else "#" + t.replace(" ", "") for t in story.get("hashtags", [])[:15]]
    description = (f"{title}\n\n{story.get('description', '').strip()}\n\n" + (f"🗳️ {vote_text}\n\n" if vote_text else "")
                   + (f"{L['find_ghost']}\n\n" if hidden else "") + f"{L['your_story']}\n\n"
                   + f"{L['ai_note']}\n\n{' '.join(tags)}")
    part_times, segs = TIMELINE
    chap = extras.chapters_text(part_times, [L["ch_intro"]] + [sc.get("chapter") or f"{k + 1}" for k, sc in
                                                                 enumerate(scenes)] + [L["ch_end"]], L["chapters"])
    yt_description = description.replace(f"\n\n{L['ai_note']}", (f"\n\n{chap}" if chap else "") + f"\n\n{L['ai_note']}")

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
                results["youtube"] = post_to_youtube(video, thumb, title, yt_description, tags, lang)
                log("Posted to YouTube:", results["youtube"])
            except Exception as e:
                log("YOUTUBE FAILED:", e)
                results["youtube_error"] = str(e)[:200]
        else:
            log("YouTube secrets not set - skipping YouTube")
        if not results.get("facebook") and not results.get("youtube"):
            raise SystemExit("Posting failed everywhere - see messages above.")

    first = [vote_text or str(story.get("comment_question", "")).strip()]
    if hidden:
        first.append(L["find_ghost"])
    if viewer and viewer.get("name"):
        first.append(L["credit_comment"].format(name=viewer["name"]))
    if vote_names:
        first.append(L["vote_comment"].format(names=extras.name_list(vote_names, lang, 10)))
    if shout_names:
        first.append(L["shout_comment"].format(names=extras.name_list(shout_names, lang, 10)))
    first.append(L["join_comment"])
    story["comment_question"] = "\n\n".join(x for x in first if x)
    results.update(grow(video, story, title, lang, L, tags, results, history, page))

    history.append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "lang": lang, "slot": SLOT,
                    "theme": theme, "format": fmt, "part": part, "continues": continues, "series_id": series_id, "title": title, "festival": festival,
                    "special": special, "viewer_story_id": viewer["id"] if viewer else None,
                    "hidden": hidden, "mystery_answer": int(str(story.get("mystery_answer", 0) or 0)[:1] or 0)
                    if str(story.get("mystery_answer", 0) or 0)[:1].isdigit() else 0, **results})
    if not MOCK:
        save_history(history)
        if continues:
            with open(NEXT_PART, "w", encoding="utf-8") as f:
                json.dump({"created": dt.datetime.now(dt.timezone.utc).isoformat(), "lang": lang, "theme": theme,
                           "fmt": fmt, "title": (prev or {}).get("title") or story["title"],
                           "done": part, "total": total, "series_id": series_id, "summary": story.get("summary", ""),
                           "part2_plan": story.get("part2_plan", ""), "characters": story.get("characters"),
                           "setting": story.get("setting", ""), "choice": choice,
                           "fb": results.get("facebook"), "yt": results.get("youtube")}, f, ensure_ascii=False, indent=1)
            log(f"Series: part {part + 1} of {total} will be made in the next horror run")
        elif part >= 2 and os.path.exists(NEXT_PART):
            os.remove(NEXT_PART)
    if viewer and not DRY_RUN:                       # tell the viewer their story is out
        try:
            if viewer["id"].startswith("fb_") and results.get("facebook"):
                extras.fb_comment(viewer["id"][3:], L["reply_viewer"] + f" https://www.facebook.com/{results['facebook']}")
        except Exception as e:
            log("  reply to viewer skipped:", str(e)[:120])
    if shout_ids and results.get("facebook") and not DRY_RUN:
        n = extras.reply_to(shout_ids, L["congrats_reply"].format(link=f"https://www.facebook.com/{results['facebook']}"))
        log(f"  congratulated {n} viewers under their comments")
    page_name = env(f"PAGE_NAME_{lang.upper()}") or "Daily Horror Story"
    extras.telegram(extras.report_text(page_name, title, results, history))


def make_series_full(history):
    """Sunday: every big story finished this week (all its parts) as ONE full video - 'সম্পূর্ণ গল্প'."""
    global FONT
    now = dt.datetime.now(dt.timezone.utc)
    groups = {}
    for h in history[-60:]:
        if not h.get("part") or not h.get("facebook") or h.get("kind"):
            continue
        try:
            t = dt.datetime.fromisoformat(str(h.get("date")))
        except Exception:
            continue
        if (now - t.replace(tzinfo=t.tzinfo or dt.timezone.utc)).days > 8:
            continue
        key = h.get("series_id") or f"{h.get('lang')}|{h.get('theme')}"
        groups.setdefault(key, {})[int(h["part"])] = h
    done = {h.get("series_key") for h in history if h.get("kind") == "series_full"}
    for key, parts in groups.items():
        last = parts[max(parts)]
        finished = max(parts) >= 2 and not last.get("continues", False)
        if key in done or not finished or sorted(parts) != list(range(1, max(parts) + 1)):
            continue
        lang = parts[1].get("lang", "bn")
        L = LANGS[lang]
        FONT = find_font(lang)
        base_title = str(parts[1].get("title", "")).split(" | ")[0].strip()
        full = "সম্পূর্ণ গল্প" if lang == "bn" else "पूरी कहानी"
        log(f"Full story of the series: {base_title} ({len(parts)} parts)")
        try:
            clips, chapters, t = [], [], 0.0
            for n in sorted(parts):
                src, _ = extras.fb_video_source(parts[n]["facebook"])
                if not src:
                    raise RuntimeError(f"no video link for part {n}")
                raw = extras.download(src, os.path.join(WORK, f"sraw_{n}.mp4"))
                c = extras.normalize_clip(raw, os.path.join(WORK, f"s_{n:02d}.mp4"))
                os.remove(raw)
                chapters.append((t, L["part"].format(n=n)))
                t += duration(c)
                clips.append(c)
            lst = os.path.join(WORK, "series.txt")
            with open(lst, "w") as f:
                f.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
            video = os.path.join(WORK, "series_full.mp4")
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", video])
            fr = os.path.join(WORK, "series_frame.jpg")
            run(["ffmpeg", "-y", "-ss", f"{min(60, t / 4):.1f}", "-i", video, "-frames:v", "1", fr])
            thumb = os.path.join(WORK, "series_thumb.jpg")
            try:
                extras.poster_thumbnail(fr, full, base_title[:40], thumb, "horror", FONT)
            except Exception:
                make_thumbnail(fr, full, thumb, L["label"])
            title = f"{base_title} | {full} ({len(parts)} {'পর্ব একসাথে' if lang == 'bn' else 'भाग एक साथ'})"[:95]
            chap = L["chapters"] + "\n" + "\n".join(f"{extras.fmt_time(s)} {n}" for s, n in chapters)
            tags = ["#HorrorStory", "#BhooterGolpo", "#FullStory", "#BanglaHorror"]
            description = f"{title}\n\n{chap}\n\n{L['ai_note']}\n\n{' '.join(tags)}"
            results = {}
            if not DRY_RUN:
                try:
                    results["facebook"] = post_to_facebook(video, thumb, title, description)
                    log("Posted full story to Facebook:", results["facebook"])
                except Exception as e:
                    log("FACEBOOK FAILED:", e)
                if youtube_ready() and extras.yt_extra_ok():
                    try:
                        results["youtube"] = post_to_youtube(video, thumb, title, description, tags, lang)
                        log("Posted full story to YouTube:", results["youtube"])
                        extras.yt_add_to_playlist(results["youtube"], L["playlist"], lang)
                    except Exception as e:
                        log("YouTube full story skipped:", str(e)[:200])
                history.append({"date": now.isoformat(timespec="minutes"), "lang": lang, "kind": "series_full",
                                "series_key": key, "title": title, **results})
                save_history(history)
            for c in clips + [video]:
                if os.path.exists(c):
                    os.remove(c)
        except Exception as e:
            log("  full story skipped:", str(e)[:200])


def make_compilation(history):
    """Sunday special: this week's stories (one language) joined into one long video with chapters.
    First, every big story finished this week is posted as one full video."""
    global FONT
    try:
        make_series_full(history)
    except Exception as e:
        log("  full stories skipped:", str(e)[:200])
    now = dt.datetime.now(dt.timezone.utc)
    week = []
    for h in history[-40:]:
        try:
            t = dt.datetime.fromisoformat(str(h.get("date")))
        except Exception:
            continue
        if (now - t.replace(tzinfo=t.tzinfo or dt.timezone.utc)).days <= 7 and h.get("facebook") \
                and h.get("kind") not in ("compilation", "series_full"):
            week.append(h)
    langs = [h.get("lang") for h in week]
    lang = env("LANGUAGE") if env("LANGUAGE") in LANGS else (max(set(langs), key=langs.count) if langs else "bn")
    items = [h for h in week if h.get("lang") == lang][-12:]
    if len(items) < 3:
        log(f"Weekly compilation: only {len(items)} stories this week - skipped")
        return
    L = LANGS[lang]
    FONT = find_font(lang)
    clips, chapters, frames, t = [], [], [], 0.0
    for k, h in enumerate(items):
        try:
            src, _ = extras.fb_video_source(h["facebook"])
            if not src:
                raise RuntimeError("no video link")
            raw = extras.download(src, os.path.join(WORK, f"raw_{k}.mp4"))
            c = extras.normalize_clip(raw, os.path.join(WORK, f"c_{k:02d}.mp4"))
            os.remove(raw)
            d = duration(c)
            fr = os.path.join(WORK, f"fr_{k}.jpg")
            run(["ffmpeg", "-y", "-ss", f"{min(40, d / 3):.1f}", "-i", c, "-frames:v", "1", fr])
            frames.append(fr)
            chapters.append((t, h.get("title", f"{k + 1}")))
            clips.append(c)
            t += d
            log(f"  added: {h.get('title', '')[:50]} ({d / 60:.1f} min)")
        except Exception as e:
            log(f"  skipped one story: {str(e)[:150]}")
    if len(clips) < 3:
        log("Weekly compilation: not enough videos could be downloaded - skipped")
        return
    lst = os.path.join(WORK, "comp.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
    video = os.path.join(WORK, "final.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", video])
    minutes = int(round(t / 60))
    title = L["comp_title"].format(m=minutes, n=len(clips))[:95]
    base = extras.collage(frames, os.path.join(WORK, "thumb_base.jpg"))
    thumb = os.path.join(WORK, "thumbnail.jpg")
    make_thumbnail(base, L["comp_thumb"].format(m=minutes), thumb, L["label"])
    chap = L["chapters"] + "\n" + "\n".join(f"{extras.fmt_time(s)} {n[:60]}" for s, n in chapters)
    tags = ["#HorrorStories", "#BhootKiKahani", "#BhooterGolpo", "#HorrorCompilation"]
    description = f"{title}\n\n{chap}\n\n{L['ai_note']}\n\n{' '.join(tags)}"
    log(f"Compilation ready: {minutes} minutes, {len(clips)} stories")
    results = {}
    if not DRY_RUN:
        try:
            results["facebook"] = post_to_facebook(video, thumb, title, description)
            log("Posted compilation to Facebook:", results["facebook"])
        except Exception as e:
            log("FACEBOOK FAILED:", e)
        if youtube_ready() and extras.yt_extra_ok():
            try:
                results["youtube"] = post_to_youtube(video, thumb, title, description, tags, lang)
                log("Posted compilation to YouTube:", results["youtube"])
                extras.yt_add_to_playlist(results["youtube"], L["playlist"], lang)
            except Exception as e:
                log("YouTube compilation skipped:", str(e)[:200])
        history.append({"date": now.isoformat(timespec="minutes"), "lang": lang, "kind": "compilation",
                        "title": title, **results})
        save_history(history)


def grow(video, story, title, lang, L, tags, results, history, page):
    """Extra reach after the main post: Reel + Short teaser, first comment, playlist. Never stops the run."""
    out = {}
    part_times, segs = TIMELINE
    teaser = os.path.join(WORK, "teaser.mp4")
    try:
        st, en = extras.pick_window(segs, part_times, story.get("teaser_scene") or 2)
        extras.make_teaser(video, st, en, teaser, FONT, story.get("thumbnail_text") or title, L["cta"], WORK,
                           colors=((255, 230, 0), (200, 0, 20)))
        log(f"Teaser ready ({en - st:.0f} s, from {st:.0f} s)")
    except Exception as e:
        log("  teaser skipped:", str(e)[:200])
        teaser = None
    if DRY_RUN:
        return out
    question = str(story.get("comment_question", "")).strip()
    short_desc = f"{title}\n{L['full_link']} {page}\n{' '.join(tags[:6])}"
    if teaser and env("FB_REELS") != "0":
        try:
            out["fb_reel"] = extras.fb_post_reel(teaser, short_desc)
            log("Posted Facebook Reel:", out["fb_reel"])
        except Exception as e:
            log("  Facebook Reel skipped:", str(e)[:200])
    if teaser and env("INSTAGRAM") == "1":           # only if you switch Instagram on (secret INSTAGRAM = 1)
        try:
            out["ig_reel"] = extras.ig_post_reel(teaser, short_desc)
            log("Posted Instagram Reel:", out["ig_reel"])
        except Exception as e:
            log("  Instagram Reel skipped:", str(e)[:200])
    if results.get("youtube"):
        try:
            extras.yt_add_to_playlist(results["youtube"], story.get("_playlist") or L["playlist"], lang)
            log("  added to YouTube playlist")
        except Exception as e:
            log("  playlist skipped:", str(e)[:200])
        if (teaser and extras.yt_extra_ok() and env("YT_SHORTS") != "0"
                and extras.shorts_today(history) < int(env("YT_SHORTS_PER_DAY") or 2)):
            try:
                desc = f"{title}\n{L['full_link']} https://youtu.be/{results['youtube']}\n{' '.join(tags[:6])}"
                out["yt_short"] = post_to_youtube(teaser, None, f"{title[:80]} #Shorts", desc, tags, lang)
                log("Posted YouTube Short:", out["yt_short"])
            except Exception as e:
                log("  YouTube Short skipped:", str(e)[:200])
    if results.get("youtube") and extras.yt_extra_ok():
        try:                                          # English subtitles: more people can follow, better search
            tr = {str(ln.get("text", "")).strip(): str(ln.get("en", "")).strip()
                  for sc in story.get("scenes", []) for ln in sc.get("lines", []) if ln.get("en")}
            srt = extras.write_srt(segs, tr, os.path.join(WORK, "subs_en.srt"))
            if srt:
                extras.yt_upload_captions(results["youtube"], srt)
                log("  English subtitles added on YouTube")
        except Exception as e:
            log("  subtitles skipped:", str(e)[:160])
    if results.get("facebook") and env("ANNOUNCE") != "0" and env("MODE") != "amavasya":
        try:                                          # "coming soon" post 2 hours before the next video
            nxt = extras.next_slot([13, 21], [13, 21])
            if nxt:
                slot, when, day = nxt
                words = f"{extras.DAY_WORDS[lang][day]} {extras.TIME_WORDS[lang][slot.hour]}"
                card = extras.announcement_card(os.path.join(WORK, "thumb_base.jpg"), FONT, L["ann1"], words,
                                                os.path.join(WORK, "announce.jpg"))
                extras.fb_schedule_photo(card, L["ann_msg"].format(when=words), when)
                log(f"  'coming soon' post scheduled for {when.strftime('%d %b %H:%M')} India time")
        except Exception as e:
            log("  announcement skipped:", str(e)[:160])
    extras.wait_for_publish()
    if question and results.get("facebook"):
        try:
            extras.fb_comment(results["facebook"], question)
            log("  first comment posted on Facebook")
        except Exception as e:
            log("  Facebook comment skipped (needs pages_manage_engagement):", str(e)[:160])
    if question and results.get("youtube"):
        try:
            extras.yt_comment(results["youtube"], question)
            log("  first comment posted on YouTube")
        except Exception as e:
            log("  YouTube comment skipped:", str(e)[:160])
    return out


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
                 "ambience": ["night crickets", "wind through trees"], "lines": [
                    {"speaker": "narrator", "text": "অনেক বছর পর রানা আর মিতালি তাদের পুরনো বাড়িতে ফিরল। চারদিক নিস্তব্ধ।", "emotion": "eerie",
                     "sfx": [{"sound": "old iron gate creaks open", "when": "after"}]},
                    {"speaker": "Mitali", "text": "এত অন্ধকার কেন? আলো জ্বালাও না!", "emotion": "scared", "sfx": []},
                    {"speaker": "Rana", "text": "দাঁড়াও, প্রদীপটা খুঁজছি।", "emotion": "whisper",
                     "sfx": [{"sound": "slow footsteps on wooden floor", "when": "during"}]}]},
                {"characters": ["Chhaya"], "action": "ghost", "place": "hall", "mood": "scare",
                 "ambience": ["wind howling"], "lines": [
                    {"speaker": "narrator", "text": "হঠাৎ দরজায় তিনবার টোকা পড়ল।", "emotion": "normal",
                     "sfx": [{"sound": "three knocks on door", "when": "after"}]},
                    {"speaker": "Chhaya", "text": "এতদিন পরে এলে?", "emotion": "eerie", "jump_scare": True, "sfx": []}]},
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
