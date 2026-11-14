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
        "outro": "ऐसी और डरावनी कहानियों के लिए {page} को फ़ॉलो कर लीजिए। आज रात बत्ती बुझाकर मत सोइएगा... फिर मिलेंगे, अंधेरे में।",
        "outro_short": "आज रात बत्ती बुझाकर मत सोइएगा... फिर मिलेंगे, अंधेरे में।",
        "page_default": "हमारे पेज",
        "share_cta": "📌 हर दोपहर और रात नई डरावनी कहानी - पेज फ़ॉलो करके रखिए।",
        "share_cta": "📌 हर दोपहर और रात नई डरावनी कहानी - पेज फ़ॉलो करके रखिए।",
        "ai_note": "🎨 यह कहानी और तस्वीरें AI की मदद से बनाई गई हैं। सब काल्पनिक है।",
        "ai_true": "🎨 यह कहानी हमें भेजी गई एक सच्ची घटना पर आधारित है (नाम और कुछ बातें बदली गई हैं); आवाज़ें और तस्वीरें AI की मदद से बनी हैं।",
        "badge": "रोज़ नई कहानी • फॉलो", "part": "भाग {n}",
        "outro_part1": "कहानी का अगला भाग जल्द ही आएगा... उसे मिस मत कीजिए, अभी {page} को फॉलो कीजिए।",
        "ch_intro": "शुरुआत", "ch_end": "अंत", "chapters": "⏱️ अध्याय",
        "cta": "पूरी कहानी का लिंक नीचे लिखा है 👇", "link_below": "पूरी कहानी का लिंक नीचे लिखा है", "follow": "फ़ॉलो कीजिए - हर रात नई डरावनी कहानी",
        "guess_card": "आपका जवाब क्या है? कमेंट में लिखिए 1 या 2 या 3", "core_tags": ["#BhootKiKahani", "#HindiHorrorStories", "#डरावनीकहानी", "#horrorstories"], "playlist": "भूतिया कहानियाँ - Hindi Horror Stories",
        "full_link": "👉 पूरी कहानी सुनने के लिए इस लिंक पर क्लिक करें:",
        "hp": "हेडफ़ोन लगाकर सुनिए",
        "find_ghost": "🔍 वीडियो की तस्वीरों में भूत कितनी बार छिपा था? ध्यान दिया? कमेंट में लिखिए!",
        "find_ghost_line": "और हाँ... इस वीडियो की तस्वीरों में वो भूत कुछ बार छिपा हुआ था। आपने कितनी बार देखा? कमेंट में ज़रूर बताइए।",
        "vote_line": "{q} अगर आप चाहते हैं {o1}, तो कमेंट में 1 लिखिए। और अगर {o2}, तो 2 लिखिए। आपके वोट से तय होगा कि अगले भाग में क्या होगा!",
        "ann1": "नई भूतिया कहानी", "ann_msg": "👻 {when} आ रही है नई भूतिया कहानी... हेडफ़ोन तैयार रखिए! 🎧🔔",
        "comp_title": "{m} मिनट की भूतिया कहानियाँ 👻 | हफ्ते की {n} कहानियाँ एक साथ", "comp_thumb": "{m} मिनट का डर",
        "bhairab": "भैरव ठाकुर का केस #{n}", "bhairab_pl": "भैरव ठाकुर के केस - Bhairab Thakur Cases",
        "karna": "कर्णपिशाचिनी #{n}", "karna_pl": "कर्णपिशाचिनी - Karna Pishachini",
        "taranath": "तारानाथ तांत्रिक #{n}", "taranath_pl": "तारानाथ तांत्रिक की कहानियाँ - Taranath Tantrik",
        "amavasya": "अमावस्या स्पेशल", "your_story": "📝 आपके साथ भी कभी कुछ अजीब हुआ है? अपनी सच्ची घटना कमेंट में #मेरी_कहानी लिखकर बताइए - हो सकता है अगली कहानी आपकी हो!",
        "reply_viewer": "🙏 आपकी भेजी हुई घटना पर आज की कहानी बनी है! देखिए और बताइए कैसी लगी 👻",
        "show_21": "रात का डर", "show_13": "दोपहर का डर",
        "title_21": "रात का डर... {title}।", "title_13": "दोपहर का डर... {title}।",
        "next_generic": "और कल रात... फिर आ रही है एक नई डरावनी कहानी, और गहरी, और अँधेरी। ज़रूर आइए।",
        "tonight_title": "और आज रात... आज की बड़ी कहानी, '{title}'। {hook} आधे घंटे की कहानी... लाइट बुझाकर सुनिए, मिस मत कीजिए।",
        "tonight_long": "और आज रात... आज की बड़ी कहानी, पूरे आधे घंटे की। लाइट बुझाइए, हेडफ़ोन लगाइए... मिस मत कीजिए।",
        "title_karna": "कर्णपिशाचिनी... {title}।", "title_classic": "मशहूर भूतिया कहानियाँ... {writer} की लिखी... '{title}'।",
        "open_21": "रात हो गई है... कमरे की बत्ती बुझा दीजिए, हेडफ़ोन कानों में लगा लीजिए... शुरू हो रहा है 'रात का डर'।",
        "open_13": "शुरू हो रहा है 'दोपहर का डर'... हेडफ़ोन लगा लीजिए... और अगर आप अकेले हैं, तो ज़रा संभलकर सुनिए।",
        "open_karna": "कर्णपिशाचिनी... वो आत्मा जो कान में हर सच फुसफुसा देती है... पर उसकी क़ीमत बहुत भयानक है।",
        "next_own": "और कल रात... '{title}'। {hook} कल रात, मिस मत कीजिए।",
        "next_classic": "कल रात... {writer} की मशहूर कहानी '{title}'। ज़रूर सुनिए।",
        "next_karna": "कल रात... कर्णपिशाचिनी का नया केस। वो फिर फुसफुसाएगी... ज़रूर आइए।",
        "guess_line": "रुकिए... एक पल यहीं रुकिए। आपको क्या लगता है? {q} एक, {o1}। दो, {o2}। तीन, {o3}। कमेंट में सिर्फ़ नंबर लिखिए - सही जवाब देने वालों का नाम अगले वीडियो में लिया जाएगा।",
        "at_13": "आज दोपहर पूरी कहानी", "at_21": "आज रात पूरी कहानी",
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
        "outro": "এরকম আরও ভৌতিক গল্পের জন্য {page} ফলো করে রাখুন। আজ রাতে আলো নিভিয়ে ঘুমোবেন না যেন... আবার দেখা হবে, অন্ধকারে।",
        "outro_short": "আজ রাতে আলো নিভিয়ে ঘুমোবেন না যেন... আবার দেখা হবে, অন্ধকারে।",
        "page_default": "আমাদের পেজ",
        "share_cta": "📌 রোজ দুপুরে আর রাতে নতুন ভূতের গল্প - পেজটা ফলো করে রাখুন।",
        "ai_note": "🎨 এই গল্প ও ছবি AI-এর সাহায্যে তৈরি। সবকিছু কাল্পনিক।",
        "ai_true": "🎨 আমাদের কাছে আসা একটি সত্যি ঘটনা অবলম্বনে (নাম ও কিছু খুঁটিনাটি বদলানো); গলা ও ছবি AI-এর সাহায্যে তৈরি।",
        "badge": "রোজ নতুন গল্প • ফলো", "part": "পর্ব {n}",
        "outro_part1": "গল্পের পরের পর্ব আসছে কাল... আর রবিবার আসবে পুরো গল্পটা একসাথে। মিস করতে না চাইলে এখনই {page} ফলো করে রাখুন।",
        "ch_intro": "শুরু", "ch_end": "শেষ", "chapters": "⏱️ অধ্যায়",
        "cta": "পুরো গল্পের লিংক নিচের লেখায় 👇", "link_below": "পুরো গল্পের লিংক নিচের লেখায়", "follow": "ফলো করুন — রোজ রাতে নতুন ভূতের গল্প",
        "guess_card": "আপনার উত্তর কী? কমেন্টে লিখুন ১ বা ২ বা ৩", "core_tags": ["#ভূতেরগল্প", "#BengaliHorrorStory", "#BhuterGolpo", "#ভৌতিকগল্প", "#horrorstories"], "playlist": "ভৌতিক গল্প - Bengali Horror Stories",
        "full_link": "👉 পুরো গল্প শুনতে ক্লিক করুন এই লিংকে:",
        "hp": "হেডফোন পরে শুনুন",
        "find_ghost": "🔍 ভিডিওর ছবিগুলোতে ভূতটা কতবার লুকিয়ে ছিল? খেয়াল করেছেন? কমেন্টে লিখুন!",
        "find_ghost_line": "আর হ্যাঁ... এই ভিডিওর ছবিগুলোর মধ্যে সেই ভূত কয়েকবার লুকিয়ে ছিল। আপনি কতবার দেখেছেন? কমেন্টে অবশ্যই জানাবেন।",
        "vote_line": "{q} যদি চান {o1}, কমেন্টে লিখুন ১। আর যদি চান {o2}, লিখুন ২। আপনাদের ভোটেই ঠিক হবে পরের পর্বে কী হবে!",
        "ann1": "নতুন ভৌতিক গল্প", "ann_msg": "👻 {when} আসছে নতুন ভৌতিক গল্প... হেডফোন রেডি রাখুন! 🎧🔔",
        "comp_title": "{m} মিনিটের ভূতের গল্প 👻 | সপ্তাহের সেরা {n}টি গল্প একসাথে", "comp_thumb": "{m} মিনিটের ভয়",
        "bhairab": "ভৈরব ঠাকুরের কেস #{n}", "bhairab_pl": "ভৈরব ঠাকুরের কেস - Bhairab Thakur Cases",
        "karna": "কর্ণপিশাচিনী #{n}", "karna_pl": "কর্ণপিশাচিনী - Karna Pishachini",
        "taranath": "তারানাথ তান্ত্রিক #{n}", "taranath_pl": "তারানাথ তান্ত্রিকের গল্প - Taranath Tantrik",
        "amavasya": "অমাবস্যার স্পেশাল", "your_story": "📝 আপনার জীবনেও কি কখনো অদ্ভুত কিছু ঘটেছে? সত্যি ঘটনাটা কমেন্টে #আমার_গল্প লিখে জানান - পরের গল্পটা হয়তো আপনারই!",
        "reply_viewer": "🙏 আপনার পাঠানো ঘটনা নিয়েই আজকের গল্প! দেখে জানাবেন কেমন লাগল 👻",
        "show_21": "রাতের ভয়", "show_13": "দুপুরের ভয়",
        "title_21": "রাতের ভয়... {title}।", "title_13": "দুপুরের ভয়... {title}।",
        "next_generic": "আর কাল রাতে... আবার আসছে নতুন এক ভয়ের গল্প, আরও গভীর, আরও অন্ধকার। অবশ্যই আসবেন।",
        "tonight_title": "আর আজ রাতে... আজকের বড় গল্প, '{title}'। {hook} আধ ঘণ্টার গল্প... আলো নিভিয়ে শুনবেন, মিস করবেন না।",
        "tonight_long": "আর আজ রাতে... আজকের বড় গল্প, পুরো আধ ঘণ্টার। আলো নিভিয়ে, হেডফোন কানে দিয়ে... অবশ্যই শুনবেন।",
        "title_karna": "কর্ণপিশাচিনী... {title}।", "title_classic": "বিখ্যাত ভূতের গল্প... {writer} লেখা... '{title}'।",
        "open_21": "রাত নামল... ঘরের আলোটা নিভিয়ে দিন, হেডফোনটা কানে দিন... শুরু হচ্ছে 'রাতের ভয়'।",
        "open_13": "শুরু হচ্ছে 'দুপুরের ভয়'... হেডফোনটা কানে দিন... আর যদি একা থাকেন, তাহলে একটু সাবধানে শুনবেন।",
        "open_karna": "কর্ণপিশাচিনী... যে আত্মা কানে কানে সব সত্যি বলে দেয়... কিন্তু তার দাম বড় ভয়ঙ্কর।",
        "next_own": "আর কাল রাতে... '{title}'। {hook} কাল রাতে, মিস করবেন না।",
        "next_classic": "কাল রাতে... {writer} বিখ্যাত গল্প '{title}'। অবশ্যই শুনবেন।",
        "next_karna": "কাল রাতে... কর্ণপিশাচিনীর নতুন কেস। সে আবার কানে কানে ফিসফিস করবে... অবশ্যই আসবেন।",
        "guess_line": "দাঁড়ান... এক মুহূর্ত এখানে থামুন। আপনার কী মনে হয়? {q} এক, {o1}। দুই, {o2}। তিন, {o3}। কমেন্টে শুধু নম্বরটা লিখুন - যাঁদের উত্তর ঠিক হবে, পরের ভিডিওতে তাঁদের নাম বলা হবে।",
        "at_13": "আজ দুপুরে পুরো গল্প", "at_21": "আজ রাতে পুরো গল্প",
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
    "a shankchunni (শাঁকচুন্নি) who wants to become a married woman", "nishi daak - a voice at midnight calling your name",
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
MORNING, NOON, EVENING = 10, 14, 20     # 2 PM and 8 PM ~22-minute stories; the morning run makes their teasers
TRIGGERS = [(6, 0, MORNING), (10, 0, NOON), (15, 30, EVENING)]   # earliest start for each (cron-job.org: 3-4 h before)
SLOTS = (MORNING, NOON, EVENING)

# ---- the weekly programme: every day and time has its own kind of story (like a TV channel)
HORROR_CATS = {
    "gram": {"bn": "গ্রামবাংলার ভূত", "hi": "गाँव का भूत", "about": "a Bengal VILLAGE ghost story with the real folk "
             "ghosts of Bengal (shankchunni, brahmadaitya, petni, mamdo, skondhokata, nishi, ekanore, mechho, gechho "
             "bhoot...) exactly as the village belief describes them",
             "themes": ["a shankchunni (শাঁকচুন্নি) who wants to become a married woman",
                        "nishi daak - a voice at midnight calling your name", "the brahmadaitya of the old bel tree",
                        "a mechho bhoot who steals fish from the fisherman's boat at night",
                        "the headless skondhokata on the railway line by the paddy fields",
                        "kanabhulo - the ghost that makes a man lose his way in the fields all night",
                        "the petni in the tamarind tree behind the village school",
                        "a gechho bhoot in the giant banyan near the burning ghat",
                        "the old zamindar's pond where no one bathes after dusk",
                        "a village wedding night and the bride who was not the bride"]},
    "shohor": {"bn": "শহরের আতঙ্ক", "hi": "शहर का डर", "about": "an URBAN horror in Kolkata / a big Indian city today "
               "(phones, metro, flats, hostels, night shifts) - the supernatural inside very modern ordinary life. "
               "Viewers love places they know and use every day: set it at a familiar, NAMED Kolkata spot (a metro "
               "station, a Howrah/Sealdah local train, a ghat, an old north-Kolkata para, a hospital, a flyover, a mall "
               "basement) and make the place itself part of the fear",
               "themes": ["a boys' hostel room in north Kolkata that is always cheap", "the last metro train at Tollygunge",
                          "a night shift in an old government hospital", "a rented flat in Salt Lake with one locked room",
                          "an app cab ride at 2 AM on the EM Bypass", "a call-centre night shift on the 14th floor",
                          "an old single-screen cinema that shows one more show at midnight",
                          "a second-hand book from College Street with notes written by a dead man",
                          "a PG room where the previous girl left everything behind",
                          "a lift in an old north Kolkata building that stops at a floor that does not exist"]},
    "jayga": {"bn": "ভুতুড়ে জায়গা", "hi": "भुतहा जगहें", "about": "a story set in a REAL place of India famous for "
              "ghost legends (its real history and legend researched, then a believable dramatized story there)",
              "themes": ["Dow Hill and the Victoria Boys' School road in Kurseong", "Begunkodor railway station in Purulia",
                         "Putulbari in north Kolkata", "the old Nimtala burning ghat at night", "Bhangarh fort in Rajasthan",
                         "Kuldhara, the deserted village of Rajasthan", "an old rajbari of Nadia", "Lambi Dehar mines near Mussoorie",
                         "the Writers' Building corridors at night", "the abandoned sanatorium on a foggy hilltop near Kurseong"]},
    "sotti": {"bn": "সত্যি ঘটনা", "hi": "सच्ची घटना", "about": "a 'TRUE EXPERIENCE' story told like a real person's "
              "own account (first person, exact dates, places and small real details), believable and unsettling",
              "themes": ["what happened on my first night duty as a young doctor", "my grandmother's house in the village",
                         "the night bus from Siliguri", "the old photograph in my new office", "a phone call from my dead friend",
                         "the room above ours in the rented house", "what I saw at the ghat on Mahalaya morning",
                         "a weekend trip to a forest bungalow in Purulia"]},
    "tantrik": {"bn": "তারানাথ তান্ত্রিক", "hi": "तारानाथ तांत्रिक", "about": "a Taranath Tantrik story", "special": "taranath"},
    "rohoshyo": {"bn": "ভৈরব ঠাকুরের কেস", "hi": "भैरव ठाकुर का केस", "about": "a Bhairab Thakur mystery-horror case",
                 "special": "bhairab", "parts": 2},
    "karna": {"bn": "কর্ণপিশাচিনী", "hi": "कर्णपिशाचिनी", "about": "the Karna Pishachini series", "special": "karna",
              "parts": 2},
    "classic": {"bn": "বিখ্যাত লেখকের গল্প", "hi": "मशहूर लेखक की कहानी", "about": "a famous writer's ghost story",
                "special": "classic"},
    # v80: our five new horror series take turns on these nights (see NEW_SERIES)
    "notun": {"bn": "রাতের সিরিজ", "hi": "रात की सीरीज़", "about": "one of our own horror series", "special": "notun"},
}
HORROR_GRID = {   # weekday (0 = Monday): category at 10 AM, 2 PM, 8 PM
    0: ("gram", "shohor", "rohoshyo"), 1: ("jayga", "gram", "karna"), 2: ("shohor", "sotti", "tantrik"),
    3: ("gram", "jayga", "notun"), 4: ("sotti", "shohor", "karna"), 5: ("jayga", "gram", "notun"),
    6: ("shohor", "sotti", "classic"),
}
BN_DAYS = ["সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার", "রবিবার"]
HI_DAYS = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
SLOT_WORD = {"bn": {MORNING: "সকালে", NOON: "দুপুরে", EVENING: "রাতে"},
             "hi": {MORNING: "सुबह", NOON: "दोपहर", EVENING: "रात"}}
SHOW_NAME = {"bn": {MORNING: "সকালের ভয়", NOON: "দুপুরের ভয়", EVENING: "রাতের ভয়"},
             "hi": {MORNING: "सुबह का डर", NOON: "दोपहर का डर", EVENING: "रात का डर"}}


def category_of(slot_hour, day=None):
    day = dt.datetime.now(extras.IST) if day is None else day
    k = SLOTS.index(slot_hour) if slot_hour in SLOTS else 2
    return HORROR_GRID[day.weekday()][k]


def when_words(lang, slot_hour, days_ahead):
    lw = SLOT_WORD.get(lang, SLOT_WORD["bn"])[slot_hour]
    if days_ahead == 0:
        return ("আজ " if lang == "bn" else "आज ") + lw
    if days_ahead == 1:
        return ("কাল " if lang == "bn" else "कल ") + lw
    wd = (dt.datetime.now(extras.IST) + dt.timedelta(days=days_ahead)).weekday()
    return (BN_DAYS if lang == "bn" else HI_DAYS)[wd] + " " + lw


def next_time_of(cat, slot_hour):
    """when this category comes next (after the current slot): (days_ahead, slot)"""
    now = dt.datetime.now(extras.IST)
    start = SLOTS.index(slot_hour) + 1 if slot_hour in SLOTS else 3
    for d in range(0, 8):
        day = now + dt.timedelta(days=d)
        for k in range(start if d == 0 else 0, 3):
            if SLOTS[k] == MORNING and env("MORNING_TEASERS") != "0":
                continue                              # no morning story any more (the morning has teasers)
            if HORROR_GRID[day.weekday()][k] == cat:
                return d, SLOTS[k]
    return 7, slot_hour


def next_slot_of(slot_hour):
    """the very next video: (days_ahead, slot, category)"""
    now = dt.datetime.now(extras.IST)
    k = SLOTS.index(slot_hour) if slot_hour in SLOTS else 2
    k0 = 1 if env("MORNING_TEASERS") != "0" else 0    # the first story of a day: 2 PM (the morning has the teasers)
    if k < 2:
        k = max(k + 1, k0)
        return 0, SLOTS[k], HORROR_GRID[now.weekday()][k]
    return 1, SLOTS[k0], HORROR_GRID[(now + dt.timedelta(days=1)).weekday()][k0]
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


NO_BAIT = os.getenv("COMMENT_ASKS") != "1"    # v86: never "comment 1, 2 or 3 / write your answer" (it breaks the story
                                              # mid-way, and Facebook cuts the reach of such posts)


HORROR_WORD_RE = re.compile(
    r"bhoo?t|bhut|ভূত|ভুত|ভৌতিক|ভয়|bhoy|bhay|डर|भूत|भुत|horror|ghost|haunt|scary|spooky|creepy|paranormal|"
    r"daini|ডাইনি|डायन|tantri|তান্ত্রিক|तांत्रिक|pret|প্রেত|प्रेत|atma|আত্মা|आत्मा|pishach|পিশাচ|पिशाच|"
    r"shakchunni|শাঁকচুন্নি|petni|পেত্নী|brahmo|ব্রহ্মদৈত্য|nishi|নিশি|amavas|অমাবস্যা|अमावस|smashan|শ্মশান|"
    r"श्मशान|রহস্য|rohosyo|rahasya|रहस्य|mystery|thriller|golpo|গল্প|kahani|कहानी|story|stories|অলৌকিক|"
    r"alaukik|अलौकिक|chudail|चुड़ैल|কালো জাদু|kala jadu|काला जादू|tarana|তারানাথ|ভৈরব|bhairab", re.I)


def horror_only(words):
    """v86: only words that belong to ghost stories ('belly gurgles', 'feet soles girl' brought the wrong people)"""
    return [w for w in (words or []) if HORROR_WORD_RE.search(str(w))]


RETENTION_RULE = (
    "\nKEEP THEM TILL THE END (our numbers: most viewers leave in the first minute):\n"
    "- The first 3 lines are already INSIDE the fear: a sound, a touch, a voice, a wrong thing seen - no greeting, no "
    "'today I will tell you', no slow description of the village, the weather or the house.\n"
    "- Within the first minute the listener must have one burning question (who / what / why) that is answered only "
    "at the very end.\n"
    "- The first real scare comes before minute 3; after that something new happens at least every 2 minutes "
    "(a clue, a sound, a reversal, a death, a secret) - never two calm scenes in a row.\n"
    "- Every chapter ends on a small hook that pulls into the next one. Never stop the story to talk to the "
    "listeners, never ask them to comment, like or vote.\n")


def _hist_safe():
    try:
        with open(os.path.join(HERE, "history.json"), encoding="utf-8") as f:
            h = json.load(f)
        return h if isinstance(h, list) else []
    except Exception:
        return []


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
    "a whodunit ghost mystery: three people could be behind it, the clues are hidden in the story, and the final "
    "scene reveals the answer with a twist (never stop the story to ask the listeners anything)",
    "classic third-person radio-drama narration",
    "told in first person by someone who lived through it ('that night I...'), as if sharing a true experience",
    "a listener's letter read out by the narrator, then the events play out",
    "two friends telling ghost stories at night, and one story becomes real",
]


NEXT_PART = os.path.join(HERE, "next_part.json")


def load_next_part(ready_only=True, slot_hour=None):
    """Part 1 of a series saves what part 2 needs. The next part comes the NEXT DAY (part 1 today, part 2
    tomorrow, part 3 the day after), so viewers wait for it. ready_only=False: also a part not due yet."""
    try:
        with open(NEXT_PART, encoding="utf-8") as f:
            nxt = json.load(f)
        made = dt.datetime.fromisoformat(nxt["created"])
        if ready_only and slot_hour is not None and len(TRIGGERS) > 1 and \
                {21: EVENING}.get(nxt.get("slot"), nxt.get("slot")) not in (None, slot_hour):
            return None                              # the next part comes at the SAME time as part 1
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
     "look": "a lean dark-skinned Bengali man of about sixty-five, once a wandering tantrik, now a poor astrologer: "
             "half-grey hair, short grey beard, deep piercing eyes, a faded vermilion mark on the forehead, one old "
             "rudraksha mala, a worn white dhoti and an old brown shawl, sitting by a hurricane lamp in a damp room"},
    {"name": "Kishori", "gender": "male", "age": "young", "kind": "human",
     "look": "a curious young Bengali man of about twenty-five in a white kurta and dhoti, neat side-parted black "
             "hair, thin moustache, sitting cross-legged and listening with wide eyes, 1940s Kolkata"},
]
TARANATH_RULE = (
    "TARANATH TANTRIK - in the spirit of Bibhutibhushan Bandyopadhyay's Taranath (the classic Bengali radio-drama "
    "favourite). Write a NEW story of our own - never retell or copy any published Taranath story or any radio "
    "script; use only the classic FORM below.\n"
    "THE FRAME (the present, 1940s Kolkata): KISHORI, a young man, and his friend visit old TARANATH in his "
    "damp, poor little house in a north Kolkata lane on a rainy evening - load-shedding, a hurricane lamp, rain on "
    "the tin shade, tea in chipped cups. Taranath once wandered as a tantrik; now he is a poor astrologer who has "
    "left that life and does not boast. At first he does not want to talk; a remark, an old object or the rain "
    "brings back a memory, and he begins: 'সে অনেক দিন আগের কথা...'. Kishori introduces the frame in a few calm "
    "lines (he is the narrator of the frame).\n"
    "THE TALE (the past, young Taranath's wandering years in the villages, cremation grounds, rivers and forests "
    "of Birbhum and rural Bengal, 1910s-1930s): Taranath tells it in FIRST PERSON, and the people of the tale speak "
    "in their own voices as he remembers them - a lonely village, a strange sadhak or a mysterious woman sadhika, a "
    "cremation ground at night, an old temple, a forbidden ritual someone else performs. The fear grows slowly, in "
    "real everyday detail (hunger, the long walk, a borrowed lantern, a village that will not speak); the "
    "supernatural is awesome and terrible, never cheap; Taranath is brave but honest about his fear and his "
    "mistakes; something in the end is NOT fully explained - it stays in the mind.\n"
    "Kishori interrupts only 2-3 times at tense moments with a hushed question; the tale goes back to the frame at "
    "the end: the rain has stopped or the lamp burns low, Taranath falls silent, and the friends walk home through "
    "the dark wet lanes carrying one small unexplained detail with them.\n"
    "No real mantra or ritual steps, no gore, no harm to children. Use exactly these looks: {looks}.")


# ----------------------------------------------------------------- Taranath special: Madhusundari Devi
# Bibhutibhushan Bandyopadhyay (died 1950 - public domain) wrote Taranath's second story, "মধুসুন্দরী দেবীর
# আবির্ভাব": the yogini Madhusundari. We retell THAT story (only Bibhutibhushan's, never Taradas's later books) in
# our own words as a 2-part Taranath special.
MADHU_CAST = [
    {"name": "Madhusundari", "name_local": "মধুসুন্দরী", "gender": "female", "age": "young", "kind": "ghost",
     "look": "Madhusundari Devi, a yogini (not a human being) in the form of a breathtakingly beautiful young woman "
             "of about twenty: fair glowing skin, very large calm dark eyes that seem to know everything, long open "
             "black hair to the waist, an unfamiliar ancient-looking dress unlike any Bengali saree (deep red and "
             "black cloth with old heavy gold ornaments), bare feet that make no sound, a faint silver mist around "
             "her; her presence always brings a strong musky fragrance"},
    {"name": "Sadhu", "name_local": "সাধুবাবা", "gender": "male", "age": "old", "kind": "human",
     "look": "a very tall, very dark-skinned old sadhu with long matted grey hair tied on top, a long grey beard, "
             "bloodshot calm eyes, ash on his body, a red loincloth and a rudraksha mala, sitting on a seat of five "
             "skulls under a huge chhatim tree beside a ruined temple in a sal forest"},
    {"name": "Matu Pagli", "name_local": "মাতু পাগলি", "gender": "female", "age": "old", "kind": "human",
     "look": "Matu Pagli, a wild-eyed cremation-ground madwoman of about fifty, thin and dark, tangled grey-black "
             "hair, a torn dirty red saree, iron and conch bangles, a cracked laugh, who knows far more than she says"},
    {"name": "Santhal woman", "name_local": "সাঁওতাল মেয়েটি", "gender": "female", "age": "adult", "kind": "human",
     "look": "a poor Santhal village woman of about thirty, dark skin, hair in a bun with a red flower, a simple "
             "white-and-red saree worn Santhal style, silver anklets, desperate tearful eyes"},
]
MADHU_RULE = (
    "TODAY'S TARANATH SPECIAL - 'মধুসুন্দরী দেবীর আবির্ভাব': retell Bibhutibhushan Bandyopadhyay's own (public "
    "domain) Taranath story of the yogini MADHUSUNDARI DEVI in OUR OWN WORDS (never copy his sentences; do not use "
    "anything from later Taranath books by other writers). Keep the classic frame: Kishori and his friend in "
    "Taranath's damp Kolkata room on a rainy evening; Taranath, unwilling at first, remembers.\n"
    "THE STORY, in this order (a 2-part series; never jump ahead):\n"
    "PART 1: young Taranath's wandering years in Birbhum; MATU PAGLI at a cremation ground, whose strange power "
    "first shakes him; then a ruined temple in a lonely sal forest near the BARAKAR river and a tall dark SADHU who "
    "sits under a chhatim tree on a seat of five skulls - Taranath stays and serves him. At night he sees a "
    "dazzlingly beautiful young woman in strange, foreign-looking ancient clothes talking with the sadhu, and a "
    "heavy musky fragrance fills the forest; hiding in the trees he feels she KNOWS he is watching. One night he "
    "dares to sit on the sadhu's seat himself - and suddenly she is sitting right beside him. He faints, burns "
    "with fever for days, the sadhu nurses him. The sadhu tells him the truth: she is not a woman at all but a "
    "YOGINI, MADHUSUNDARI DEVI; he teaches him how to call her (never say any real mantra or ritual step - only "
    "that he was taught) and warns him gravely: worship her as a mother or sister, NEVER desire her as a lover. "
    "Taranath leaves and begins the sadhana alone at a lonely place by the river; months of fear and failure; "
    "then one night the musk comes back... CLIFFHANGER: she appears before him.\n"
    "PART 2: for three months she comes every night - Taranath is enchanted, proud, and slowly losing his balance "
    "(he can tell people's fortunes uncannily; the villagers fear him). A poor SANTHAL WOMAN comes weeping for an "
    "amulet to save her sick children; Madhusundari's beauty turns terrifying - jealous, cold fury, she threatens "
    "to kill the woman. Taranath understands he has been playing with a venomous snake: she is a power, not a "
    "person. The climax: he protects the Santhal woman and her children, and with the old sadhu's last warning in "
    "mind he gives up the sadhana and breaks free - at a price. Madhusundari leaves him, but not completely.\n"
    "ENDING (back in the Kolkata room): Taranath falls silent; the lamp flickers; as Kishori and his friend get "
    "up, a faint MUSKY FRAGRANCE drifts through the damp room for a moment - and Taranath does not look up. "
    "Nothing is explained.\n"
    "Madhusundari speaks rarely: few words, calm, sweet, far older than her face; when angry, quiet and icy, "
    "never shouting. Use exactly these looks: {looks}.")


# ----------------------------------------------------------------- our own series: Karna Pishachini
KARNA = [
    {"name": "Nilkantha", "gender": "male", "age": "old", "kind": "human",
     "look": "Nilkantha Acharya, a thin Bengali astrologer of about sixty, grey hair combed back, grey stubble, deep "
             "tired eyes with dark circles, a red-and-black thread and a copper ring on his left hand, a cream "
             "panjabi and white dhoti, a brown woollen shawl, small round brass-rimmed glasses"},
    {"name": "Bapi", "gender": "male", "age": "young", "kind": "human",
     "look": "Bapi, Nilkantha's nephew, a slim Bengali college student of about twenty, short messy black hair, "
             "light moustache, a checked half-sleeve shirt and grey trousers, a cloth bag, a torch in his hand"},
    {"name": "Pishachini", "gender": "female", "age": "young", "kind": "ghost",
     "look": "the Karna Pishachini, a fierce tantric yogini spirit: tall, dark-skinned, wild loose black hair down to "
             "her knees, burning red eyes, a red sindoor mark on the forehead, a black saree with a blood-red border, "
             "bone and rudraksha ornaments, silver anklets, long thin fingers; she stays in smoke and lamp-shadow, "
             "mostly only a dark shape at the left shoulder; her face is seen only for a moment"},
]
KARNA_RULE = (
    "OUR OWN SERIES 'KARNA PISHACHINI', episode {n} (an original series; never copy any existing book, film or "
    "series).\n"
    "THE TRUE BELIEF - FOLLOW IT EXACTLY (it is the base of the whole series):\n"
    "* In the tantric belief of Bengal the Karna Pishachini is NOT a common ghost. She is a fierce YOGINI - in our "
    "series one of the yoginis in the following of Ma Kali - a spirit-power who NEVER comes on her own. She comes "
    "ONLY to a sadhak who calls her by a long, hard, dangerous SADHANA (night after night of japa alone at a "
    "cremation ground, on amavasya nights, with fasting, a lamp that must not go out, and terrifying tests: she "
    "frightens and tempts him to break him; if he fails or breaks a rule, he goes mad or dies).\n"
    "* When the sadhana is complete she is BOUND to that sadhak: she sits at his LEFT shoulder unseen and whispers "
    "into his ear (karna = ear) the hidden truth of anyone in front of him - their PAST and PRESENT. She does not "
    "know the future for certain. Nobody else can see or hear her.\n"
    "* She comes when he calls her - he closes his eyes, touches his left ear, says her name under his breath - "
    "never in the middle of nowhere without reason. Her presence: a sudden cold at the left ear, the smell of "
    "burnt camphor and wet earth, anklets, the lamp flame bending.\n"
    "* Her conditions (the price of the bond): he must keep her secret, keep her rules (purity, never use her "
    "power for greed or to harm the innocent), give her offerings, and give her his loyalty; she is jealous and "
    "possessive - she wants him only for herself. If a rule is broken she turns cruel: she misleads him, hurts the "
    "people close to him, and in the end she can take his life or his mind.\n"
    "* She is a power to be respected and feared, never mocked. No real mantra, no real ritual steps - show the "
    "sadhana only as a story (the night, the fear, the tests, the cost).\n"
    "THE CHARACTERS (introduce each by name and relation the first time: 'আমার মামা, নীলকণ্ঠ আচার্য...'): "
    "NILKANTHA ACHARYA, an astrologer in a small town of Nadia in the 1980s (lanterns, radio, bicycles, the last "
    "bus), who did the sadhana of the Karna Pishachini as a young man and has been bound to her ever since. His "
    "nephew BAPI, a college student who lives with him, is the only one who knows - Bapi tells the story ('my "
    "uncle...') and asks the questions the viewers would ask.\n"
    "{origin}"
    "PLOT LIKE A MASTER: every episode is one complete, tightly plotted MYSTERY-HORROR case that feels like it "
    "really happened: someone comes to Nilkantha with a problem nobody can solve (a missing daughter, a death that "
    "looks natural, a lamp that lights itself, a stolen temple idol, a letter from a dead man...). Nilkantha CALLS "
    "the Pishachini (as above) to learn the truth; she answers in riddles and half-truths, and once misleads him "
    "out of jealousy; plant 3-4 real clues and 2-3 believable suspects early; a false lead; then a twist the "
    "listener did not see coming but that is FAIR. Every whisper has a PRICE (an offering she demands, a year of "
    "his life, the peace of someone he loves). ONE STORY LINE from first to last scene: each scene follows from "
    "the previous one; nothing happens without a reason. Before the scenes, add the JSON key \"plot_plan\": "
    "{{\"case\", \"suspects\", \"clues\", \"false_lead\", \"twist\", \"price\"}} (ENGLISH) and follow it. "
    "Also add \"episode_summary\": ENGLISH, 2 sentences.\n"
    "SERIES SO FAR (never repeat a case; keep the running thread - her growing jealousy, Bapi coming closer to "
    "danger): {past}\n"
    "Use exactly these looks: {looks}. No gore, no harm to children. End with a hook: the Pishachini whispers "
    "something chilling about the NEXT case - or about Bapi.\n")


def pick_karna(history, lang):
    """the Karna Pishachini series: the day's first video on its days (Tuesday and Friday by default)"""
    days = [int(x) for x in re.findall(r"\d", env("KARNA_DAYS") or "1,4")]
    now = dt.datetime.now(extras.IST)
    if now.weekday() not in days or env("KARNA") == "0":
        return False
    today = now.date().isoformat()
    for h in history[-6:]:
        try:
            if h.get("special") == "karna" and \
                    dt.datetime.fromisoformat(h["date"]).astimezone(extras.IST).date().isoformat() == today:
                return False
        except Exception:
            pass
    return True


def karna_rule(history, lang):
    eps = [h for h in history if h.get("special") == "karna" and h.get("lang") == lang]
    past = " | ".join(f"Ep {k + 1}: {h.get('episode_summary') or h.get('title')}" for k, h in enumerate(eps))[-2500:]
    told = any(h.get("karna_origin") for h in eps)
    origin = ("" if told else
              "THIS EPISODE ALSO TELLS HOW SHE CAME (the viewers must know it): woven into the case, Nilkantha tells "
              "Bapi - in 2-3 flashback scenes - how as a young man, against his guru's warning, he did her sadhana at "
              "the cremation ground by the Jalangi river: the amavasya nights, the lamp, the fear, her tests (voices "
              "of his dead mother calling, a woman's laughter, the lamp almost going out), the night she finally "
              "came and the conditions she set. This is how she is bound to him - she never came on her own.\n")
    return KARNA_RULE.format(n=len(eps) + 1, origin=origin, past=past or "this is the FIRST episode - also show "
                             "how the town first learns that Nilkantha 'knows everything'", looks=json.dumps(KARNA))


PROMISE_FILE = os.path.join(HERE, "assets", "next_up.json")
STATE = {}                   # this run's time slot and series (for the trailer)


def load_promise(slot_hour):
    """yesterday's video promised this story for this time slot"""
    try:
        with open(PROMISE_FILE, encoding="utf-8") as f:
            d = json.load(f)
            p = d.get(str(slot_hour)) or d.get("21")      # (older promises were saved for 9 PM)
        made = dt.datetime.fromisoformat(p["made"])
        if p.get("idea") and (dt.datetime.now(dt.timezone.utc) - made).days <= 3:
            return p
    except Exception:
        pass
    return None


def save_promise(story, slot_hour, lang, continues):
    ns = story.get("next_story") if isinstance(story.get("next_story"), dict) else {}
    try:
        data = {}
        if os.path.exists(PROMISE_FILE):
            with open(PROMISE_FILE, encoding="utf-8") as f:
                data = json.load(f)
        if slot_hour == EVENING and not continues and not tomorrow_special() and ns.get("title") and ns.get("idea"):
            up = STATE.get("upcoming")
            data[str(EVENING)] = {"title": str(ns["title"])[:60], "hook": str(ns.get("hook", ""))[:200],
                          "idea": str(ns["idea"])[:600], "lang": lang,
                          "from_idea": up[0] if up else None, "series": bool(up and up[1]),
                          "made": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
        else:
            data.pop(str(slot_hour), None)           # the promise is kept: remove it
        os.makedirs(os.path.dirname(PROMISE_FILE), exist_ok=True)
        with open(PROMISE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log("  next-story promise not saved:", str(e)[:120])


BN_MONTHS = [((4, 14), "Boishakh (বৈশাখ), hot summer"), ((5, 15), "Joishtho (জ্যৈষ্ঠ), burning summer, mango season"),
             ((6, 15), "Asharh (আষাঢ়), first monsoon rain"), ((7, 16), "Srabon (শ্রাবণ), heavy monsoon"),
             ((8, 17), "Bhadro (ভাদ্র), humid late monsoon"), ((9, 17), "Ashwin (আশ্বিন), autumn, puja season"),
             ((10, 18), "Kartik (কার্তিক), misty autumn evenings, lamps for the dead (akash prodip)"),
             ((11, 17), "Ogrohayon (অগ্রহায়ণ), early winter, harvest"), ((12, 16), "Poush (পৌষ), cold winter, fog"),
             ((1, 15), "Magh (মাঘ), deep winter"), ((2, 13), "Falgun (ফাল্গুন), spring winds"),
             ((3, 15), "Choitro (চৈত্র), dry late spring")]


def tonight():
    """what kind of night tonight is in Bengal: weekday, Bengali month and season, Amavasya / Purnima"""
    now = dt.datetime.now(extras.IST)
    md = (now.month, now.day)
    order = sorted(BN_MONTHS)                        # by calendar date
    month = next((name for (start, name) in reversed(order) if md >= start), order[-1][1])
    late = now.replace(hour=23, minute=59, second=0, microsecond=0)
    moon = ""
    try:
        if extras.is_amavasya_night(late):
            moon = "AMAVASYA - the new-moon night, the darkest night of the month"
        else:
            # Purnima night = the night before the exact full moon (the tithi ends at the full moon):
            # the full moon falls between 6 PM today and 6 PM tomorrow (India time)
            import ephem
            eve = now.replace(hour=18, minute=0, second=0, microsecond=0).astimezone(dt.timezone.utc)
            full = ephem.next_full_moon(eve.strftime("%Y/%m/%d %H:%M:%S")).datetime().replace(tzinfo=dt.timezone.utc)
            if full - eve <= dt.timedelta(hours=24):
                moon = "PURNIMA - the full-moon night"
    except Exception:
        pass
    day = now.strftime("%A")
    belief = {"Saturday": "Shonibar - in Bengal a night for Shani, tantriks and spirits",
              "Tuesday": "Mongolbar - an inauspicious night, when tantriks do their sadhana"}.get(day, day)
    return day, month, moon, belief


def tomorrow_special_today():
    """is TONIGHT's 8 PM a Karna Pishachini / classic night (then yesterday's promise waits)?"""
    today = dt.datetime.now(extras.IST).weekday()
    return (today in [int(x) for x in re.findall(r"\d", env("KARNA_DAYS") or "1,4")] and env("KARNA") != "0") or \
           (today in [int(x) for x in re.findall(r"\d", env("CLASSIC_DAYS") or "6")] and env("CLASSICS") != "0")


def tomorrow_special():
    """what tomorrow's 8 PM story is: 'karna', 'classic' or None (our own story)"""
    tomorrow = (dt.datetime.now(extras.IST) + dt.timedelta(days=1)).weekday()
    if tomorrow in [int(x) for x in re.findall(r"\d", env("KARNA_DAYS") or "1,4")] and env("KARNA") != "0":
        return "karna"
    if tomorrow in [int(x) for x in re.findall(r"\d", env("CLASSIC_DAYS") or "6")] and env("CLASSICS") != "0":
        return "classic"
    return None


def next_preview(story, history, lang, slot_hour, classic, cat="", continues=False):
    """The last words: when this story's next part comes (its category's next day) - or what comes next."""
    if continues and cat:
        d, sl = next_time_of(cat, slot_hour)
        w = when_words(lang, sl, d)
        return (f"এই গল্পের পরের পর্ব আসবে {w}... তার আগে পেজটা ফলো করে রাখুন, যাতে মিস না হয়।" if lang == "bn" else
                f"इस कहानी का अगला भाग आएगा {w}... तब तक पेज फ़ॉलो कर लीजिए, ताकि छूट न जाए।")
    d, sl, ncat = next_slot_of(slot_hour)
    w = when_words(lang, sl, d)
    pending = extras.series_get(NEXT_PART, ncat, ready_only=False)
    name = HORROR_CATS[ncat][lang]
    if pending and pending.get("title"):
        return (f"আর {w}... {name}: '{pending['title']}'-এর পরের পর্ব। অবশ্যই আসবেন।" if lang == "bn" else
                f"और {w}... {name}: '{pending['title']}' का अगला भाग। ज़रूर आइए।")
    return (f"আর {w}... {name}। আরও গভীর, আরও অন্ধকার এক গল্প। অবশ্যই আসবেন।" if lang == "bn" else
            f"और {w}... {name}। और गहरी, और अँधेरी एक कहानी। ज़रूर आइए।")


IDEAS_FILE = os.path.join(HERE, "assets", "ideas.json")


def next_idea(history, also_used=()):
    """an idea from assets/ideas.json (e.g. from Meta's suggestions) that has not been used yet: (idea, series)"""
    try:
        with open(IDEAS_FILE, encoding="utf-8") as f:
            ideas = json.load(f).get("ideas") or []
    except Exception:
        return None
    used = ({str(h.get("theme", "")).strip() for h in history} | {str(h.get("idea_used", "")).strip() for h in history}
            | {str(x).strip() for x in also_used if x})
    for it in ideas:
        idea = str((it or {}).get("idea", "")).strip()
        if idea and idea not in used:
            return idea, bool(it.get("series"))
    return None


def pick_theme(history):
    used = [h.get("theme") for h in history[-12:]]
    options = [t for t in THEMES if t not in used] or THEMES
    return random.choice(options)


# ----------------------------------------------------------------- 1. story (Gemini)
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


LORE_DIR = os.path.join(HERE, "assets", "lore")


def plan_text(plan, limit=14000):
    """The plan as JSON text that is ALWAYS complete. (11 Nov 2026: it was simply cut off after 12,000 letters -
    a long plan then was no valid JSON any more, the chapters never got their beats, and the story was written
    'without a plan': no clear beginning, no Sunday-Suspense build-up.) Too long -> its long texts are shortened."""
    def cut(v, n):
        if isinstance(v, str):
            return v[:n]
        if isinstance(v, list):
            return [cut(x, n) for x in v]
        if isinstance(v, dict):
            return {k: cut(x, n) for k, x in v.items()}
        return v
    s, n = json.dumps(plan, ensure_ascii=False), 700
    while len(s) > limit and n > 90:
        n = int(n * 0.8)
        s = json.dumps(cut(plan, n), ensure_ascii=False)
    return s


def plan_load(text):
    """the plan back from its text - also from an older one that was cut off in the middle (its complete beats)"""
    text = str(text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    pos = len(text)
    for _ in range(60):                               # back to the end of the last complete beat
        pos = text.rfind("}", 0, pos)
        if pos < 0:
            break
        for tail in ("]}", "}", "]}}"):
            try:
                j = json.loads(text[:pos + 1] + tail)
                if isinstance(j, dict):
                    return j
            except Exception:
                continue
    return {}


def plan_story(lang, theme, extra_rules, fmt, parts=1):
    """A professional writers' room BEFORE the script: (1) plan the whole plot as a chain of cause and effect,
    every decision and its consequence, the escalating scares, clues and twist; (2) a 'script doctor' finds the
    plot holes and unrealistic choices and returns the corrected plan. The script then follows it beat by beat."""
    if MOCK or env("PLAN") == "0" or not env("GEMINI_API_KEY"):
        return ""
    key = env("GEMINI_API_KEY")
    ask1 = f"""You are the head writer of India's best horror audio-drama series. Plan (do not write yet) ONE
long, realistic, truly frightening {LANGS[lang]['name']} horror story. Idea: {theme}. Telling style: {fmt}.
Rules and material to use:
{extra_rules[-9000:]}

Return ONLY JSON (ENGLISH):
{{"premise": "2 sentences",
 "when_where": "month, weekday, time of day it begins; the exact town/village and place",
 "characters": [{{"name": "", "gender": "male/female", "age": "", "kind": "human/ghost", "who": "relation/job/home", "wants": "", "fears": "", "secret": ""}}],
 "beats": [{{"n": 1, "step": 1, "what_happens": "", "because": "what in the previous beat causes this one", "decision": "who decides what, and WHY (or '')", "follow_up": "how and in which beat this decision is carried out or why it fails - shown, not skipped", "new_fear": "the new, fresh frightening detail of this beat (never a stock phrase)"}}],
 "clues": ["clue - beat where planted - beat where it pays off"],
 "twist": "", "resolution": "what really happened, why, and what became of every character", "last_line": ""}}
Make {max(14, int(16 * parts))} beats{f" for a story told in {parts} parts of about {int(LONG_MIN)} minutes each (add the key part to every beat: 1 or 2...; part 1 = steps 1-9 and ends on a big cliffhanger, the last part = steps 9-14 and solves everything)" if parts > 1 else ""} that follow THE SHAPE below EXACTLY, step by step,
in this order (a step may take 2 beats; add the key "step": 1-14 to every beat, and "because": what in the
previous beat causes this one).
THE SHAPE (the classic Bengali radio-thriller plot, as in the great Sunday-evening suspense plays - the SHAPE
only, never their stories, names or lines):
 1 HOOK - the most frightening sound or line from later in the story, heard for a moment, not explained.
 2 THE STORYTELLER'S DOOR - the narrator sets the year, season, place and why this story is being told.
 3 ARRIVAL - who comes where, when and WHY (a believable reason: a job, a transfer, an inheritance, a wedding,
   a shortcut, a holiday); the 3-5 people, how they are related, a little warmth and a little friction.
 4 THE FIRST WRONG NOTE - one small, specific strange detail; someone explains it away.
 5 THE WARNING - a local (old servant, caretaker, villager, priest) warns or tells the rule of the place
   ('never answer if someone calls your name three times after midnight'); the hero half-ignores it.
 6 FIRST FRIGHT - the rule is broken or the sign comes back, closer and personal; the first real fear.
 7 THE SEARCH - they look for an explanation (a locked room, an old register, a photograph, a grave); a human,
   rational explanation is believed for a while (the false lead).
 8 MIDPOINT REVEAL - a piece of the past comes out IN DIALOGUE (a death, an injustice, a broken promise); it
   changes how we see the ghost.
 9 THE GHOST COMES CLOSER - it turns on someone close (a voice of the dead mother, a companion who vanishes or
   changes); they are cut off (power cut, storm, last train gone, door locked from outside).
10 ALL IS LOST - the night of the climax; the false lead collapses; there is no way out.
11 FACE TO FACE - the confrontation, told slowly, sound by sound, line by line.
12 THE TWIST - the truth everyone missed; it was PLANTED earlier (a clue from steps 4-8) - fair, never random.
13 RESOLUTION - calm, in dialogue: what really happened, why, and what became of EVERY person.
14 THE LAST LINE - one quiet, chilling line from the narrator that keeps the listener awake.
THE FEAR LADDER: every beat is more frightening than the one before (only one short calm moment, just before
step 9, to make the next fall harder). Every scare is NEW, specific and sensory - never a stock phrase.
THE CLASSIC BENGALI RADIO-THRILLER SHAPE (the style of the great Kolkata radio suspense plays - style only):
- a SMALL cast (3-5 people, each with a clear voice: age, temper, way of speaking) and ONE main place;
- ACT 1 (first quarter): a calm, real, ordinary situation; the people and why they are there; the first small
  wrong note that nobody can explain;
- ACT 2 (middle half): the dread grows step by step - every beat is a scene of real conversation in which
  something new is noticed, argued about, tested; the midpoint reveals a piece of the past; a false
  explanation is believed for a while;
- ACT 3 (last quarter): the night of the climax, the truth comes out in dialogue (a confession, a letter, an
  old servant who finally speaks), the twist, and a calm explanation of everything - then ONE last chilling line;
- every beat follows from the one before (cause -> effect); nothing important happens off-stage; no beat
  repeats an earlier scare; the listener can always follow who is where and why;
- TIME ONLY MOVES FORWARD, beat after beat: never 'a month later' in the middle and then back to the same
  night; no flash-forwards; the past appears ONLY when a character tells it or reads it (clearly as a memory).
  A big time jump is allowed only once, at the very end (an epilogue), with a clear spoken bridge."""
    ask2 = """You are a strict script doctor. Here is a horror story plan as JSON. FIRST check THE SHAPE: the
beats must follow the 14 steps in order (hook, storyteller, arrival, first wrong note, warning, first fright, the
search with a false lead, midpoint reveal, the ghost comes closer, all is lost, face to face, twist, resolution,
last line) - add any missing step, move any step that is out of order. Every beat must be CAUSED by the beat
before it ("because"); the fear must rise beat by beat; the twist's clue must be planted in steps 4-8.
Then find EVERY other problem: a decision
that is not followed up (someone decides to leave - why couldn't he? show it), a person acting unrealistically,
a coincidence, an unexplained event, a jump in time or place without a bridge, a clue with no payoff, a scare
that repeats an earlier one, a weak or unfair twist, an unclear ending, anything that breaks the belief/facts.
Fix all of them. Return ONLY the corrected plan as JSON with the same keys plus "fixed": ["each problem and fix"].
PLAN:
"""
    plan = None
    # the plan is too important to skip: the best models first, then (after a wait) EVERY model, the light ones
    # too - without a plan the chapters cannot be given their own beats and the story falls apart
    for model in (gemini_models(key)[:3] + ["WAIT"] + gemini_models(key)):
        if model == "WAIT":
            if plan:
                break
            log("  story plan: Gemini busy - waiting 90 s and trying again (a story without a plan falls apart)")
            time.sleep(90)
            continue
        try:
            body = {"contents": [{"parts": [{"text": ask1}]}],
                    "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"}}
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json=body, timeout=240)
            if not r.ok:
                log(f"  story plan: {model} {r.status_code}")
                continue
            plan = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            if not plan.get("beats"):
                plan = None
                continue
            body["contents"][0]["parts"][0]["text"] = ask2 + json.dumps(plan, ensure_ascii=False)
            body["generationConfig"]["temperature"] = 0.5
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json=body, timeout=240)
            if r.ok:
                p2 = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                if p2.get("beats") and len(p2["beats"]) >= len(plan["beats"]) * 0.8:
                    log(f"  script doctor fixed {len(p2.get('fixed') or [])} problem(s) in the plan")
                    plan = p2
            break
        except Exception as e:
            log(f"  story plan ({model}) failed: {str(e)[:120]}")
    if not plan:
        return ""
    log(f"Story plan ready: {len(plan['beats'])} beats - {str(plan.get('premise', ''))[:120]}")
    plan.pop("fixed", None)
    return plan_text(plan)


def find_source_story(theme, history):
    """Search the internet for ONE big, really frightening horror story to build today's story on - a folk legend,
    an urban legend, a famous haunted-place story, a reported 'true' experience or a public-domain story (never a
    copyrighted modern book / film / series). Returns (source name, full plot + facts) or ("", "")."""
    if MOCK or env("SOURCE_STORY") == "0" or not env("GEMINI_API_KEY"):
        return "", ""
    key = env("GEMINI_API_KEY")
    used = [h.get("source") for h in history if h.get("source")][-60:]
    prompt = f"""Search the internet, then answer. We make Bengali horror audio-story videos. Find ONE big, truly
terrifying, well-loved horror story that fits this idea: {theme}
It must be a folk legend, an urban legend, a famous haunted-place story (India / Bengal first, else the world), a
widely reported 'true' ghost experience, or a public-domain story (author died more than 60 years ago). NOT the
plot of a copyrighted modern book, film or web series. Not one of these (already used): {json.dumps(used)}

Answer in English:
SOURCE: <the story's name> - <where it comes from>
PEOPLE: every person: name, who they are, where they come from
FULL STORY (600-900 words), in time order: how it began (when, who, where from, why and how they came to the
place), every event in order as the fear grows, the climax, the ending and what really happened.
FACTS: what the tradition says about this ghost / spirit / belief (its form, how it comes, its rules)."""
    for model in gemini_models(key)[:3]:
        for tools in ([{"google_search": {}}], None):
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.7}}
            if tools:
                body["tools"] = tools
            try:
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                                  json=body, timeout=200)
                if r.status_code == 400 and tools:
                    continue
                if not r.ok:
                    log(f"  source story: {model} {r.status_code}")
                    break
                text = "\n".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"]).strip()
                mm = re.search(r"SOURCE:\s*(.+)", text)
                if not mm or len(text) < 800:
                    break
                name = mm.group(1).strip()[:120]
                log(f"Source story from the internet ({model}): {name}")
                return name, text[:7000]
            except Exception as e:
                log(f"  source story ({model}) failed: {str(e)[:120]}")
                break
    return "", ""
HORROR_HOOK = """
KEEP THEM LISTENING:
- One short chilling hook line first, then the real beginning (see above) - no slow, empty description, but a
  proper introduction of the people: the listener must know who they are and care about them.
- OPEN LOOPS: every 2-3 scenes raise a new question before answering the old one. Every scene ends on a small
  cliffhanger or a strong feeling. Change the rhythm: tense short lines, a quiet moment, then a shock.
- NEVER REPEAT: no line, sentence or event is said twice; every scene shows something NEW.
- The text of a line is ONLY the spoken words - never stage directions like (long pause), [short pause], (sighs)
  in "text"; such tags go only in "voice_text" as <long pause>, <sigh>.
"""


def research_brief(subject, cache_key=None):
    """BEFORE WRITING: look the subject up on the internet (Gemini with Google Search) - the true belief, form, look,
    behaviour, how it comes, its rules; for a known story its real characters and plot. The story must follow it.
    Fixed subjects (a series, a classic) are kept in assets/lore for 60 days."""
    if MOCK or env("RESEARCH") == "0":
        return ""
    key = env("GEMINI_API_KEY")
    if not key:
        return ""
    path = os.path.join(LORE_DIR, re.sub(r"[^a-z0-9]+", "_", cache_key.lower())[:60] + ".json") if cache_key else None
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                c = json.load(f)
            if (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(c["made"])).days <= 60 and c.get("brief"):
                log("Research brief (saved):", c["brief"][:160].replace("\n", " "), "...")
                return c["brief"]
        except Exception:
            pass
    prompt = f"""Search the internet first, then answer. Subject of a horror story we are going to write:
{subject}

Identify the central supernatural being / belief / ritual / place / custom of this subject (and, if it is a known
published story, the story itself). Then write a factual RESEARCH BRIEF in English (max 280 words) of what the
traditional sources and folklore REALLY say, as bullet points:
- what it is and which tradition/region it belongs to (Bengal, India...)
- its true form and look
- how it behaves; what it can and cannot do
- how it comes: what calls it, binds it or wakes it (does it ever come on its own?)
- its rules, taboos, the price, and how people protect themselves
- for a known story: the real characters' names and how they are related, the plot in order, the ending
- COMMON MISTAKES a writer must avoid about it
No mantras, no step-by-step ritual instructions. If sources disagree, give the most common Bengali belief."""
    for model in gemini_models(key)[:3]:
        for tools in ([{"google_search": {}}], None):
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3}}
            if tools:
                body["tools"] = tools
            try:
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                                  json=body, timeout=180)
                if r.status_code == 400 and tools:
                    continue                         # this model cannot search: ask it without searching
                if not r.ok:
                    break
                parts = r.json()["candidates"][0]["content"]["parts"]
                brief = "\n".join(p.get("text", "") for p in parts).strip()[:2500]
                if len(brief) < 150:
                    break
                log(f"Research brief ({model}{', web search' if tools else ''}):", brief[:160].replace("\n", " "), "...")
                if path:
                    try:
                        os.makedirs(LORE_DIR, exist_ok=True)
                        with open(path, "w", encoding="utf-8") as f:
                            json.dump({"made": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                                       "subject": subject, "brief": brief}, f, ensure_ascii=False, indent=1)
                    except Exception:
                        pass
                return brief
            except Exception as e:
                log(f"  research ({model}) failed: {str(e)[:120]}")
                break
    return ""


STAGE_RX = re.compile(r"\s*[\(\[\{<][^\)\]\}>]{0,40}[\)\]\}>]\s*")
PAUSE_RX = re.compile(r"\b(?:long|short|brief|dramatic)?\s*pause\b|\b(?:sighs?|gasps?|laughs?|whispers?)\b|"
                      r"(?:দীর্ঘ|লম্বা|ছোট|সংক্ষিপ্ত)\s*(?:বিরতি|বিরাম|পজ)|(?:लंबा|लम्बा|छोटा)\s*(?:विराम|ठहराव|पॉज़)", re.I)


SPELL_FIX = [   # common wrong spellings (they are also read out wrongly)
    (r"শাক(?:\s*)চু(?:ন্নি|নি|ন্নী|নী)|শাঁকচু(?:নি|নী|ন্নী)|শাঁকচুন্নী", "শাঁকচুন্নি"),
    (r"ব্রম্ভদৈত্য|ব্রহ্মদত্যি|ব্রম্মদৈত্য", "ব্রহ্মদৈত্য"), (r"পেত্নী", "পেত্নি"), (r"শশ্মান|শ্মষান", "শ্মশান"),
    (r"তান্ত্রীক", "তান্ত্রিক"), (r"স্কন্দকাটা", "স্কন্ধকাটা"),
]


SOUND_WORDS = [   # (words in the line, the sound to play exactly on that word)
    (("ঢং", "ঢঙ", "ঘণ্টা", "ঘন্টা", "टन टन", "घंटा", "घंटे की", "घंटी"), "bell"),
    (("টোকা", "ঠকঠক", "ঠক ঠক", "খটখট", "খট খট", "কড়া নাড়", "दस्तक", "खट-खट", "खटखट", "ठक-ठक"), "knocking on a wooden door"),
    (("নূপুর", "ঘুঙুর", "মল বাজ", "पायल", "घुंघरू"), "anklet bells jingling slowly"),
    (("ক্যাঁচ", "কাঁচকোঁচ", "चरमराह", "चूँ-चूँ"), "old wooden door creaks open"),
    (("চিৎকার", "আর্তনাদ", "চেঁচিয়ে", "चीख", "चिल्ला"), "terrified scream"),
    (("কুকুরের কান্না", "কুকুরটা কেঁদে", "কুকুর ডেকে", "কুকুরের ডাক", "कुत्ते रो", "कुत्ता रो", "कुत्ते भौंक"), "dog howling at night"),
    (("শেয়াল", "हुआँ", "सियार"), "jackals howling at night"),
    (("বাজ পড়", "মেঘ ডাক", "মেঘের গর্জন", "बिजली कड़", "बादल गरज"), "thunder crack"),
    (("শাঁখ", "शंख"), "conch shell blowing"),
    (("উলু", "উলুধ্বনি"), "bengali women ululation"),
    (("হুইসল", "ট্রেনের বাঁশি", "सीटी"), "train whistle"),
    (("পায়ের শব্দ", "পায়ের আওয়াজ", "পায়ের আওয়াজ", "পায়ের শব্দ", "কদমों", "कदमों की आहट", "क़दमों"), "slow footsteps on wooden floor"),
    (("ফুঁপিয়ে", "কান্নার শব্দ", "কেউ কাঁদছে", "सिसक", "रोने की आवाज़"), "woman sobbing softly"),
    (("কাচ ভাঙ", "কাঁচ ভাঙ", "शीशा टूट", "कांच टूट"), "glass shatters"),
    (("শেকল", "শিকল", "जंजीर", "ज़ंजीर"), "chains rattling"),
    (("পেঁচা", "उल्लू"), "owl hooting at night"),
    (("দড়াম", "দুম করে", "সজোরে বন্ধ", "धड़ाम", "ज़ोर से बंद"), "door slams shut"),
    (("ঝনঝন", "ঝন ঝন", "झनझन"), "metal pots falling and clattering"),
]


def bell_kind(text):
    if any(w in text for w in ("ঘড়ি", "घड़ी")):
        return "old wall clock chiming slowly"
    if any(w in text for w in ("মন্দির", "আরতি", "मंदिर", "आरती")):
        return "temple bell ringing"
    if any(w in text for w in ("গির্জা", "চার্চ", "चर्च")):
        return "church bell tolling in the distance"
    return "heavy bell tolling slowly"


def sync_sounds(story):
    """A sound that the words name is heard EXACTLY when it is said: 'ঘণ্টা বাজছে, ঢং... ঢং...' -> the bell on
    'ঢং'. Adds the missing sound effects and ties existing ones to their word (never before or after)."""
    added = tied = 0
    for sc in story.get("scenes") or []:
        for ln in sc.get("lines") or []:
            text = str(ln.get("text", ""))
            sfx = [x for x in (ln.get("sfx") or []) if isinstance(x, dict) and x.get("sound")]
            n_auto = 0
            for words, sound in SOUND_WORDS:
                hit = next((w for w in words if w in text), None)
                if not hit:
                    continue
                if sound == "bell":
                    sound = bell_kind(text)
                key = set(re.findall(r"[a-z]+", sound)) - {"a", "on", "the", "at", "of", "slowly", "night", "in"}
                same = next((x for x in sfx if key & set(re.findall(r"[a-z]+", str(x["sound"]).lower()))), None)
                if same:
                    if not str(same.get("word", "")).strip() or str(same["word"]).strip(" .,!?।") not in text:
                        same["word"] = hit
                        tied += 1
                elif n_auto < 2:
                    sfx.append({"sound": sound, "word": hit})
                    n_auto += 1
                    added += 1
            ln["sfx"] = sfx
    if added or tied:
        log(f"  sounds in sync with the words: {added} added, {tied} tied to their word")


def dedupe_story(story, window=10):
    """THE SAME THING NEVER SAID TWICE (8 Nov 2026): a sentence that repeats (or almost repeats) one of the last few
    sentences is taken out - also when the storyteller just repeats what a character has said ('she said she would
    not go' + 'I will not go'). Only that sentence goes; the rest of the line stays."""
    from difflib import SequenceMatcher
    key = lambda s: re.sub(r"[^\wঀ-৿ऀ-ॿ]", "", extras.strip_tags(s))
    recent, removed = [], 0                           # (key, speaker) of the last sentences, scenes included
    calls = {}                                        # short calls ('ঠাকুরমশাই!') and how often they came already
    laugh = re.compile(r"^(?:[হহিহোখি]+|[हहिहोखि]+|ha|hi)+$", re.I)
    lines = [(sc, ln) for sc in story.get("scenes") or [] for ln in sc.get("lines") or []]
    for idx, (sc, ln) in enumerate(lines):
        spk = str(ln.get("speaker", "narrator")).lower()
        nar = spk.startswith("narrat")
        neigh = [key(lines[q][1].get("text", "")) for q in (idx - 1, idx + 1)
                 if 0 <= q < len(lines) and not str(lines[q][1].get("speaker", "narrator")).lower().startswith("narrat")]
        sents = split_sentences(str(ln.get("text", "")))
        keep = []
        for s in sents:
            k = key(s)
            # the same short call over and over (9 Nov 2026: Paltu began 7 lines with 'ঠাকুরমশাই!') - after twice it
            # goes, when the line has more to say (a laugh of the ghost is meant to come back)
            if 0 < len(k) < 14 and len(sents) > 1 and not laugh.match(k):
                calls[k] = calls.get(k, 0) + 1
                if calls[k] > 2:
                    removed += 1
                    continue
            dup = len(k) >= 14 and any(SequenceMatcher(None, k, r).ratio() >= 0.8 for r, _sp in recent[-window:])
            echo = nar and len(k) >= 14 and any(len(nk) >= 10 and (nk in k or SequenceMatcher(None, k, nk).ratio() >= 0.75)
                                                 for nk in neigh)
            if dup or echo:
                removed += 1
                continue
            keep.append(s)
            recent.append((k, spk))
        if len(keep) != len(sents):
            ln["text"] = " ".join(keep)
            ln.pop("voice_text", None)
    for sc in story.get("scenes") or []:
        sc["lines"] = [ln for ln in sc.get("lines") or [] if str(ln.get("text", "")).strip()]
    story["scenes"] = [sc for sc in story.get("scenes") or [] if sc.get("lines")]
    if removed:
        log(f"  removed {removed} repeated sentence(s) (the same thing is never said twice)")


def clean_story_text(story):
    """Only the spoken words go into "text" (= subtitles + voice): stage directions like (long pause), [sighs],
    <short pause> are removed; a line that repeats an earlier one is dropped."""
    seen, removed = set(), 0
    for sc in story.get("scenes") or []:
        out = []
        for ln in sc.get("lines") or []:
            t = str(ln.get("text", ""))
            for a, b in SPELL_FIX:
                if re.search(a, t):
                    t = re.sub(a, b, t)
                    ln["text"] = t
                    if ln.get("voice_text"):
                        ln["voice_text"] = re.sub(a, b, str(ln["voice_text"]))
            t2 = STAGE_RX.sub(" ", t)
            t2 = PAUSE_RX.sub(" ", t2) if re.search(r"[ঀ-৿ऀ-ॿ]", t2) else t2
            t2 = re.sub(r"\s{2,}", " ", t2).strip(" ,")
            if t2 != t.strip():
                t2 = t2.lstrip(" ,.…।")
            for k in ("en",):
                if ln.get(k):
                    ln[k] = re.sub(r"\s{2,}", " ", STAGE_RX.sub(" ", str(ln[k]))).strip()
            key = re.sub(r"[^\wঀ-৿ऀ-ॿ]", "", t2)
            if not key or (len(key) > 12 and key in seen):
                removed += 1
                continue
            seen.add(key)
            if t2 != t:
                ln["text"] = t2
                if ln.get("voice_text"):              # keep the acting tags, but the same words
                    ln["voice_text"] = re.sub(r"\[([^\]]{1,24})\]|\(([^\)]{1,24})\)",
                                              lambda mm: f"<{mm.group(1) or mm.group(2)}>", str(ln["voice_text"]))
            out.append(ln)
        sc["lines"] = out
    story["scenes"] = [sc for sc in story.get("scenes") or [] if sc.get("lines")]
    if removed:
        log(f"  removed {removed} repeated / empty line(s)")
    try:
        dedupe_story(story)
    except Exception as e:
        log("  repeat check skipped:", str(e)[:100])
    try:                                             # v81: how real people call each other
        natural_names(story)
    except Exception as e:
        log("  name check skipped:", str(e)[:100])
    try:                                             # v81: no sentence that an earlier story already said
        drop_said_before(story)
    except Exception as e:
        log("  said-before check skipped:", str(e)[:100])


HONORIFICS = ("ডাক্তার", "ডঃ", "ডা.", "মিস্টার", "শ্রী", "শ্রীমতী", "ইন্সপেক্টর", "অফিসার", "প্রফেসর", "মাস্টার", "দারোগা",
              "डॉक्टर", "डॉ.", "मिस्टर", "श्री", "श्रीमती", "इंस्पेक्टर", "प्रोफेसर")
RELATION_TAIL = ("পিসি", "মাসি", "দিদি", "দাদা", "কাকা", "কাকু", "জেঠু", "জেঠা", "বৌদি", "মামা", "মাসিমা", "পিসিমা", "দাদু",
                 "ঠাকুমা", "দিদিমা", "ঠাকুর", "মশাই", "बुआ", "मौसी", "दीदी", "भैया", "चाचा", "मामा", "दादा", "दादी")
BN_VOWEL_END = "ািীুূৃেৈোৌঅআইঈউঊএঐওঔ"


def _bn_attach(word, suffix):
    """Bengali case endings after a name: 'অনির্বাণ' + possessive -> 'অনির্বাণের', 'মিনু' -> 'মিনুর'"""
    if suffix in ("র", "ের"):
        return word + ("র" if word[-1] in BN_VOWEL_END else "ের")
    return word + suffix


def natural_names(story):
    """(13 Nov 2026: 'অনির্বাণ চ্যাটার্জি, আমার পাশে এসে দাঁড়া!' - nobody talks like that) In what people SAY, a
    full name becomes the first name (an elder: surname + 'মশাই', a doctor/officer: title + surname); the storyteller
    keeps the full name only the first time."""
    changes = 0
    for c in story.get("characters") or []:
        if not isinstance(c, dict) or str(c.get("kind", "human")).startswith("ghost"):
            continue
        full = re.sub(r"\s+", " ", str(c.get("name_local") or "")).strip()
        ws = full.split()
        if len(ws) < 2 or ws[-1] in RELATION_TAIL or len(ws) > 4:
            continue
        title = ws[0] if ws[0] in HONORIFICS else ""
        rest = ws[1:] if title else ws
        if len(rest) < 2:
            continue
        given, surname = rest[0], rest[-1]
        old = str(c.get("age", "")).lower() in ("old",) or "old" in str(c.get("age", "")).lower()
        male = not str(c.get("gender", "male")).lower().startswith("f")
        if title:
            talk = f"{title} {surname}"
        elif old and male and re.search(r"[\u0980-\u09FF]", surname):
            talk = f"{surname}মশাই"
        else:
            talk = given
        rx = re.compile(re.escape(full) + r"(দের|ের|র|কে|ও|ই)?(?![\u0980-\u09FF\u0900-\u097F])")
        first_seen = [False]

        def sub(m, who):
            nonlocal changes
            if who == "narrator" and not first_seen[0]:
                first_seen[0] = True
                return m.group(0)
            changes += 1
            base = talk if who != "narrator" else given if not title else f"{title} {surname}"
            suf = m.group(1) or ""
            return _bn_attach(base, suf) if suf and re.search(r"[\u0980-\u09FF]", base) else base + suf
        for sc in story.get("scenes") or []:
            for ln in sc.get("lines") or []:
                who = "narrator" if str(ln.get("speaker", "narrator")).lower().startswith("narrat") else "person"
                before = first_seen[0]
                if ln.get("text") and full in str(ln["text"]):
                    ln["text"] = rx.sub(lambda m: sub(m, who), str(ln["text"]))
                after = first_seen[0]
                if ln.get("voice_text") and full in str(ln["voice_text"]):
                    first_seen[0] = before            # (the voice says exactly what the subtitle shows)
                    ln["voice_text"] = rx.sub(lambda m: sub(m, who), str(ln["voice_text"]))
                    first_seen[0] = after
    if changes:
        log(f"  names: {changes} full name(s) made natural (people call each other by first name / relation)")


SAID_FILE = os.path.join(HERE, "assets", "said_before.json")


def _sent_keys(text):
    for s in re.split(r"(?<=[।!?])\s+|\.{3}\s*", str(text)):
        k = re.sub(r"[^\u0980-\u09FF\u0900-\u097F]", "", s)
        if len(k) >= 18:
            yield s, k


def drop_said_before(story):
    """a storyteller's sentence that an EARLIER story already said word for word is taken out (a stock line that
    comes in story after story makes every story sound the same)"""
    old = set((_jload(SAID_FILE, {}) or {}).get("keys") or [])
    if not old:
        return
    cut = 0
    for sc in story.get("scenes") or []:
        keep = []
        for ln in sc.get("lines") or []:
            if not str(ln.get("speaker", "narrator")).lower().startswith("narrat"):
                keep.append(ln)
                continue
            t = str(ln.get("text", ""))
            bad = [s for s, k in _sent_keys(t) if k in old]
            for s in bad:
                t = t.replace(s, " ")
                cut += 1
            t = re.sub(r"\s{2,}", " ", t).strip()
            if bad:
                ln["text"] = t
                ln.pop("voice_text", None)
            if re.search(r"[\u0980-\u09FF\u0900-\u097F]", t):
                keep.append(ln)
        sc["lines"] = keep
    if cut:
        log(f"  {cut} sentence(s) that earlier stories already said were taken out")


def remember_said(story):
    """after a story is out: its storyteller's sentences are remembered (the last ~40 stories)"""
    d = _jload(SAID_FILE, {}) or {}
    keys = list(d.get("keys") or [])
    for sc in story.get("scenes") or []:
        for ln in sc.get("lines") or []:
            if str(ln.get("speaker", "narrator")).lower().startswith("narrat"):
                keys += [k for _s, k in _sent_keys(ln.get("text", ""))]
    d["keys"] = list(dict.fromkeys(keys))[-6000:]
    _jsave(SAID_FILE, d)


CLICHES = {
    "bn": ["শিরদাঁড়া বেয়ে ঠান্ডা স্রোত", "পচা ফুলের গন্ধ", "রক্ত জল করা হাসি", "গা ছমছম করে উঠল", "হিমশীতল হাওয়া",
           "দপদপ করে নিভে গেল", "বুকের ভেতরটা ধড়াস করে উঠল", "সারা শরীরে কাঁটা দিয়ে উঠল", "পায়ের তলার মাটি সরে গেল",
           "নিঃশ্বাস আটকে এল", "কেউ যেন পেছনে দাঁড়িয়ে আছে", "চোখ দুটো জ্বলছে", "অদ্ভুত এক গন্ধ", "রক্ত হিম হয়ে গেল"],
    "hi": ["रीढ़ की हड्डी में ठंडी लहर", "सड़े फूलों की गंध", "खून जमा देने वाली हँसी", "रोंगटे खड़े हो गए", "बर्फ़ जैसी ठंडी हवा",
           "दिल धक से रह गया", "पैरों तले ज़मीन खिसक गई", "साँस अटक गई", "कोई पीछे खड़ा है", "आँखें जल रही थीं",
           "अजीब सी गंध", "खून जम गया", "सन्नाटा छा गया", "दीया टिमटिमा कर बुझ गया"],
}
CLICHE_ROOTS = {"bn": ["শিরদাঁড়া", "পচা ফুল", "রক্ত জল", "গা ছমছম", "হিমশীতল", "দপদপ", "ধড়াস", "কাঁটা দিয়ে", "রক্ত হিম",
                       "মাটি সরে"],
                "hi": ["रीढ़", "सड़े फूल", "खून जमा", "रोंगटे", "धक से", "ज़मीन खिसक", "खून जम"]}


def find_cliches(story, lang):
    """the worn-out phrases still in the story (so the editor replaces them)"""
    found = []
    for sc in story.get("scenes") or []:
        for ln in sc.get("lines") or []:
            t = str(ln.get("text", ""))
            if any(r in t for r in CLICHE_ROOTS.get(lang, [])):
                found.append(t[:120])
    return found


FEMALE_WORDS = ("পিসি", "মাসি", "দিদি", "বউ", "বৌ", "মা ", "মাগো", "ঠাকুমা", "দিদিমা", "মেয়ে", "কাকিমা", "জেঠিমা",
                "বৌদি", "রানি", "দেবী", "বালা", "pishi", "mashi", "didi", "bou", "boudi", "thakuma", "didima",
                "kakima", "jethima", "rani", "devi", "bala", "girl", "woman", "aunt", "mother", "grandma", "wife",
                "mrs", "बुआ", "मौसी", "दीदी", "माँ", "दादी", "नानी", "चाची", "ताई", "भाभी", "लड़की", "औरत", "देवी",
                "bua", "mausi", "dadi", "nani", "chachi", "tai", "bhabhi")
# (11 Nov 2026) words that ALWAYS mean a woman / a female spirit - whatever gender the writer wrote. The Karna
# Pishachini, a petni, a shakchunni, a daini, a yogini ... is a WOMAN and always gets a woman's voice.
FEMALE_STRONG = ("পিশাচিনী", "পেত্নী", "পেতনি", "শাকচুন্নি", "শাঁকচুন্নি", "ডাইনি", "ডাকিনী", "যোগিনী", "ভৈরবী", "চুড়েল",
                 "সুন্দরী", "মহিলা", "নারী", "বুড়ি", "বৃদ্ধা", "কন্যা", "মেয়ে", "বউ", "বৌ", "বৌদি", "পিসি", "মাসি", "দিদি",
                 "ঠাকুমা", "দিদিমা", "কাকিমা", "জেঠিমা", "রানি", "রাণী", "দেবী", "ঠাকরুন", "গিন্নি", "মা ",
                 "pishachini", "pisachini", "pishachi", "petni", "petni", "shakchunni", "shankchunni", "daini", "dakini",
                 "yogini", "jogini", "bhairavi", "chudail", "churel", "witch", "sundari", "woman", "women", "girl", "lady",
                 "wife", "widow", "mother", "grandmother", "grandma", "daughter", "sister", "aunt", "queen", "bride",
                 "nun", "she-", "female", "mrs", "miss ", "didi", "boudi", "pishi", "mashi", "thakuma", "didima",
                 "kakima", "jethima", "rani", "devi", "thakrun", "ginni", "kanya", "nari", "mahila", "buri",
                 "पिशाचिनी", "चुड़ैल", "डायन", "योगिनी", "औरत", "लड़की", "माँ", "दादी", "नानी", "चाची", "भाभी", "दीदी",
                 "मौसी", "बुआ", "देवी", "रानी")
FEMALE_SERIES = {"karna pishachini", "the karna pishachini", "pishachini", "madhusundari", "matu pagli"}


def is_woman(c):
    """The ONE rule for a character's voice gender: the words about the person decide before the gender field."""
    name = f" {c.get('name', '')} {c.get('name_local', '')} ".lower()
    key = re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", name)).strip()
    if key in FEMALE_SERIES or key.replace("the ", "", 1) in FEMALE_SERIES or "pishachini" in key:
        return True
    if any(w in name for w in FEMALE_STRONG):
        return True
    g = str(c.get("gender", "")).lower().strip()
    if g.startswith("f") or g in ("woman", "girl", "she"):
        return True
    if any(w in name for w in MALE_WORDS):
        return False
    about = f" {c.get('look', '')} {c.get('intro_en', '')} {c.get('intro', '')} ".lower()
    she = len(re.findall(r"\b(?:she|her|hers|woman|girl|lady)\b", about))
    he = len(re.findall(r"\b(?:he|him|his|man|boy)\b", about))
    return bool(she >= 2 and she > 2 * he)


MALE_A_NAMES = {"bapi", "raja", "krishna", "ravi", "hari", "shibu", "sona", "bhola", "gora", "kana", "nanda", "rama",
                "nitai", "gopi", "kali", "bhai", "dada", "kaka", "mama", "jethu", "thakurda", "dadu", "pishemoshai",
                "ali", "babai", "tapai", "rabi", "shashi", "bishu", "montu", "pintu", "kishori", "paltu", "bapida"}
MALE_WORDS = ("দাদু", "ঠাকুরদা", "কাকা", "মামা", "জ্যাঠা", "বাবা", "খোকা", "বুড়ো", "দাদা", "মশাই", "বাবু", "ঠাকুর",
              "dadu", "kaka", "mama", "jethu", "babu", "moshai", "thakur", "khoka", "uncle", "grandfather",
              "दादा", "नाना", "चाचा", "मामा", "बाबा", "बाबू")
OLD_WORDS = ("দাদু", "ঠাকুমা", "ঠাকুরদা", "দিদিমা", "বুড়ো", "বুড়ি", "বৃদ্ধ", "বৃদ্ধা", "জ্যাঠামশাই", "dadu", "thakuma",
             "didima", "buro", "buri", "old man", "old woman", "elderly", "grandfather", "grandmother", " aged ",
             "दादा", "दादी", "नाना", "नानी", "बूढ़", "बुज़ुर्ग")
CHILD_WORDS = ("খোকা", "খুকি", "বাচ্চা", "শিশু", "ছোট্ট", "khoka", "khuki", " child", " kid", "little boy", "little girl",
               "small boy", "small girl", "baby", "बच्चा", "बच्ची", "मुन्ना", "मुन्नी")
NARRATOR_DELIVERY = ("a deep, heavy, grave, low male voice, like a man in his fifties quietly telling a true incident "
                     "late at night: natural spoken Bengali/Hindi as in real conversation, steady and a little slow; "
                     "NOT theatrical, NOT sing-song, NOT like jatra or stage drama, no musical rise and fall, no "
                     "exaggerated stress - the fear comes from the words and the silences")


GENERIC_FIRST = {"the", "a", "an", "old", "young", "mr", "mr.", "mrs", "mrs.", "dr", "dr.", "sri", "shri", "sree",
                 "srimati", "smt", "smt.", "ghost", "spirit", "little", "big", "baba", "ma", "the,"}


SPIRIT_ALIAS = {"পিশাচিনী": "pishachini", "पिशाचिनी": "pishachini", "পেত্নী": "petni", "পেতনি": "petni",
                "শাকচুন্নি": "shakchunni", "শাঁকচুন্নি": "shakchunni", "ডাইনি": "daini", "চুড়েল": "churel",
                "মধুসুন্দরী": "madhusundari", "মাতু পাগলি": "matu"}


def fix_speakers(story):
    """Every speaking person gets the right voice: a speaker written in Bengali or with a title ('সরলা পিসি')
    is matched to the character; someone who speaks but is missing from the list is added (a woman is never
    voiced by a man); a woman's title fixes a wrong gender. Narrator lines get a plain, grave delivery."""
    chars = [c for c in story.get("characters", []) if isinstance(c, dict) and c.get("name")]
    story["characters"] = chars

    def norm(s):
        return re.sub(r"\s+", " ", str(s or "")).strip().lower()

    def match(sp):
        s = norm(sp)
        if not s:
            return None
        for c in chars:
            keys = [norm(c["name"]), norm(c.get("name_local"))]
            for k in keys:
                if k and (k == s or re.search(rf"(?<!\w){re.escape(k)}(?!\w)", s)
                          or re.search(rf"(?<!\w){re.escape(s)}(?!\w)", k)
                          or (k.split()[0] == s.split()[0] and k.split()[0] not in GENERIC_FIRST)):
                    return c
        for bn, en in SPIRIT_ALIAS.items():          # "কর্ণপিশাচিনী" is the character "Karna Pishachini"
            if bn in s:
                for c in chars:
                    if en in norm(c["name"]):
                        return c
        return None
    fixed, added = 0, 0
    for sc in story.get("scenes") or []:
        for ln in sc.get("lines") or []:
            sp = str(ln.get("speaker", "")).strip()
            if not sp or norm(sp).startswith("narrat") or sp in ("কথক", "সূত্রধর", "कथावाचक"):
                ln["speaker"] = "narrator"
                ln["delivery"] = NARRATOR_DELIVERY + (f"; feeling: {ln['emotion']}" if ln.get("emotion") else "")
                continue
            c = match(sp)
            if not c:
                fem = any(w in sp.lower() for w in FEMALE_WORDS) or is_woman({"name": sp})
                nm = re.sub(r"[^A-Za-z]", "", sp.split()[0]).lower() if re.search(r"[A-Za-z]", sp) else ""
                if not fem and nm and nm[-1] in "ai" and nm not in MALE_A_NAMES:
                    fem = True                       # Mala, Sarala, Mita, Rani ... (Bapi, Raja are men)
                latin = re.sub(r"[^A-Za-z ]", "", sp).strip() or f"Person{len(chars) + 1}"
                c = {"name": latin.title(), "name_local": sp, "gender": "female" if fem else "male", "age": "adult",
                     "kind": "human", "look": f"an ordinary Bengali {'woman' if fem else 'man'}"}
                chars.append(c)
                added += 1
            if c["name"] != sp:
                ln["speaker"] = c["name"]
                fixed += 1
    for c in chars:                                  # the right voice: gender AND age from the words about the person
        both = f"{c['name']} {c.get('name_local', '')}".lower()
        about = f"{both} {c.get('intro', '')} {c.get('intro_en', '')} {c.get('look', '')}".lower()
        g0, a0 = str(c.get("gender", "")).lower(), str(c.get("age", "")).lower()
        if is_woman(c):
            c["gender"] = "female"                    # a woman / a female spirit is NEVER voiced by a man
        elif g0.startswith("f") and any(w in both for w in MALE_WORDS):
            c["gender"] = "male"
        elif not g0:
            c["gender"] = "female" if any(w in about for w in (" woman", " girl", " mother", " wife", " lady")) else "male"
        if any(w in about for w in OLD_WORDS) or re.search(r"\b(?:[6-9]\d)\s*(?:years|-year)", about):
            c["age"] = "old"
        elif any(w in about for w in CHILD_WORDS) or re.search(r"\b(?:[2-9]|1[0-2])\s*(?:years|-year)", about):
            c["age"] = "child"
        elif any(w in about for w in (" student", " young", " college", "ছাত্র", "যুবক", "তরুণ", "छात्र", "नौजवान")):
            c["age"] = "young"
        elif a0 not in ("child", "young", "adult", "old"):
            c["age"] = "adult"
        if (c.get("gender"), c.get("age")) != (g0, a0):
            fixed += 1
    if fixed or added:
        log(f"  voices: {fixed} speaker name(s) matched / corrected, {added} missing speaker(s) added")


SERIES_RX = {   # the series name is added in front of the title once - never twice (or misspelt) inside it
    "karna": r"(?:কর্[ণন]া?\s*-?\s*পিশাচিনী|कर्[णन]ा?\s*-?\s*पिशाचिनी|करना\s*पिशाचिनी|karna\s*pi?sh?achini)",
    "taranath": r"(?:তারানাথ(?:\s*তান্ত্রিক)?|तारानाथ(?:\s*तांत्रिक)?|taranath(?:\s*tantrik)?)",
    "bhairab": r"(?:ভৈরব\s*ঠাকুর(?:ের)?(?:\s*কেস)?|भैरव\s*ठाकुर(?:\s*का)?(?:\s*केस)?|bhairab\s*thakur)",
}


def no_series_name(title, special):
    rx = SERIES_RX.get(special)
    if not rx:
        return title
    t = re.sub(rf"^\s*{rx}\s*(?:#?\s*[\d০-৯०-९]+)?\s*[:：।|\-–—]*\s*", "", str(title), flags=re.I).strip()
    t = re.sub(rf"\s*\|\s*[^|]*{rx}[^|]*", "", t, flags=re.I).strip()     # '... | তারানাথ তান্ত্রিক #2' in the middle too
    t = re.sub(r"\s*\|\s*", " | ", t)
    return t if len(t) >= 3 else title


def ensure_intros(story, cold=False):
    """Every person is introduced (name + who they are) the moment they ENTER the story. If the script forgot it,
    the narrator's intro line goes in just before their first line (for the cold-open scene 1: right after the
    time-bridge at the start of scene 2, so the hook stays fast). Ghosts keep their mystery."""
    chars = [c for c in story.get("characters", []) if isinstance(c, dict) and c.get("name")]
    scenes = story.get("scenes") or []
    if not chars or not scenes:
        return
    said = ""

    def known(c):
        keys = [str(c.get("name_local") or "").strip(), str(c["name"]).strip()]
        return any(k and k.split()[0] in said for k in keys)

    def words_of(t):
        return {w for w in re.sub(r"[^\w\u0980-\u09ff\u0900-\u097f]", " ", str(t)).split() if len(w) > 2}

    def introduced_here(c, lines, k):
        """the story itself names / describes the person in this line or the next two (10 Nov 2026: the intro was
        put just before 'দিব্যেন্দু সেন নামে কলকাতার এক প্রবীণ শব্দ গবেষক...' - the same thing said twice)"""
        ahead = " ".join(str(x.get("text", "")) for x in lines[k:k + 3])
        keys = [str(c.get("name_local") or "").strip(), str(c["name"]).strip()]
        named = any(kk and kk.split()[0] in ahead for kk in keys)
        iw = words_of(c.get("intro", ""))
        same = len(iw & words_of(ahead)) / len(iw) if iw else 0.0
        # named there AND described there (age, job, who they are) - or most of the intro's words are there anyway;
        # a mere mention of the name ('...ভৈরব ঠাকুরের ডেরায়') keeps the intro
        return (named and same >= 0.2) or same >= 0.35

    def intro_line(c):
        return {"speaker": "narrator", "emotion": "calm", "text": str(c["intro"]).strip(),
                "en": str(c.get("intro_en", "")), "intro_of": c["name"],
                "image": {"prompt": f"introduction shot of {c['name']}: {c.get('look', '')}", "characters": [c["name"]],
                          "people": [{"name": c["name"], "pose": "standing", "where": "middle",
                                      "doing": "looking at the camera", "feeling": "natural"}]}}
    late, added = [], 0
    for si, sc in enumerate(scenes):
        lines = sc.get("lines") or []
        out = []
        visible = [n for n in (sc.get("characters") or []) if isinstance(n, str)]
        for k, ln in enumerate(lines):
            if si == 1 and k == 1 and late:          # after scene 2's time-bridge: those of the cold open
                new_ = [intro_line(c) for c in late if c.get("intro") and not known(c)
                        and not introduced_here(c, lines, k)]
                out += new_
                added += len(new_)
                late = []
            sp = str(ln.get("speaker", ""))
            pic = ln.get("image") if isinstance(ln.get("image"), dict) else {}
            here = {sp} | set(visible if k == 0 else []) | set(pic.get("characters") or [])
            for c in chars:
                if c["name"] not in here or known(c) or not c.get("intro") or c.get("kind") == "ghost" \
                        or c in late or any(x.get("intro_of") == c["name"] for x in out):
                    continue
                if introduced_here(c, lines, k):     # the story introduces this person itself, right here
                    said += " " + str(c["name"]) + " " + str(c.get("name_local") or "")
                    continue
                if si == 0 and cold and k == 0:
                    late.append(c)
                else:
                    out.append(intro_line(c))
                    said += " " + str(c["intro"])
                    added += 1
            out.append(ln)
            said += " " + str(ln.get("text", ""))
        if si == 1 and late:                         # scene 2 had only one line
            new_ = [intro_line(c) for c in late if c.get("intro") and not known(c) and not introduced_here(c, lines, 1)]
            out[1:1] = new_
            added += len(new_)
            late = []
        sc["lines"] = out
    if added:
        log(f"  introduced {added} character(s) where they first enter")


def edit_story(story, lang, classic=False, brief="", outline="", chapter=None):
    """A second pass by a 'chief editor' (like a publisher's editor): scores the story and rewrites the weak parts
    - more fear, a fairer and bigger twist, logic, scenes flowing into each other, natural dialogue, correct
    language. Returns the better story, or the original if anything goes wrong."""
    if MOCK or env("EDITOR") == "0":
        return story
    key = env("GEMINI_API_KEY")
    if not key:
        return story
    L = LANGS[lang]
    words0 = sum(len(str(ln.get("text", "")).split()) for sc in story.get("scenes", []) for ln in sc.get("lines", []))
    rule = ("This is a retelling of a famous classic: do NOT change its events, characters or ending - improve only "
            "the telling (suspense, dialogue, sound, pictures, language)." if classic else
            "Improve the plot too where it is weak: a bigger, fairer twist, a cleverer ghost, a stronger ending.")
    chapter_note = ""
    if chapter:                                       # (k, n, final): this is ONE chapter of a long story
        k_, n_, fin_ = chapter
        chapter_note = (f"\nIMPORTANT - THIS IS CHAPTER {k_} OF {n_} OF ONE LONG STORY, NOT A WHOLE STORY: judge the "
                        "STRUCTURE only inside this chapter. "
                        + ("" if k_ == 1 else "Do NOT add a hook line, a new beginning or a new introduction of known "
                                              "people - it continues from the previous chapter. ")
                        + ("" if fin_ else "Do NOT add a climax, a twist, an explanation or an ending - the story goes on "
                                           "in the next chapter; it must end on a cliffhanger. ")
                        + "Never add scenes from earlier or later in the story; time only moves forward.")
    prompt = f"""You are the chief editor of India's most successful horror audio-drama channel.
Here is a {L['name']} horror story script as JSON. First judge it honestly (1-10) on: real fear and dread, the twist
(surprising but fair), logic and consistency (names, time, place, who knows what), each scene flowing into the next,
natural dialogue with feeling (a radio thriller: mostly living dialogue, the narrator only bridges), a hook in the first lines, sound design that matches the words exactly, CHARACTERS
INTRODUCED (the first time anyone appears, the listener hears their NAME and WHO they are - relation or job - and
names are used often enough that the listener always knows who is speaking), CONTINUITY (one unbroken chain: every
scene follows from the scene before it - cause and effect, or a clear time/place bridge said aloud; no scene that
comes from nowhere; the story is told in time order from its real beginning - never a flash-forward),
TRUTH TO THE BELIEF (it must follow the research brief below exactly), PLOT HOLES (find EVERY decision a person
makes and check it is followed up in its own scene - he decides to leave: either he leaves, or we SEE why he
could not; nothing unexplained, no coincidence, every person acts like a real person; fix each hole by adding or
rewriting scenes), FRESH WORDS (no stock horror phrases - replace every worn-out line with a new, exact image
that belongs to this place; never the same image twice), STRUCTURE (a clear beginning: one hook line, then
WHEN it began (month, weekday, time of day), the main person's name, village/town, family, situation, WHY and
HOW he/she came to this place - in that order; a full middle with at least three
escalating events, a clue, a false lead and a discovery; a clear end with climax, twist, and a resolution scene
that explains the whole mystery and what became of everyone - ADD the missing scenes if the beginning, middle or
end is thin or abrupt), and correct,
natural {L['name']} ({'pure Kolkata cholit Bengali, correct spelling' if lang == 'bn' else 'natural correct Hindi'}).
Then REWRITE every weak line and scene to make it a 10. {rule}{chapter_note}
Keep EXACTLY the same JSON structure and ALL keys (every scene, line, sfx, image, people, ghost_reveal, guess,
next_story...), the same characters with the same names and looks, and about the same length (no more than 10% longer - our videos have a fixed length).
Add one key "editor_scores": {{"fear": n, "twist": n, "logic": n, "flow": n, "structure": n, "names": n, "belief": n, "dialogue": n, "language": n}} with the
scores of YOUR improved version. Return ONLY the complete improved JSON.

{"RESEARCH BRIEF (true facts - the story must not contradict them):" + chr(10) + brief + chr(10) if brief else ""}
{"MASTER OUTLINE (the planned plot - the story must follow it):" + chr(10) + outline + chr(10) if outline else ""}
{"WORN-OUT LINES TO REPLACE (rewrite each with a fresh image):" + chr(10) + chr(10).join(find_cliches(story, lang)) + chr(10) if find_cliches(story, lang) else ""}
Add also the key "plot_holes_fixed": ["ENGLISH: each hole you found and how you fixed it"].
STORY JSON:
{json.dumps(story, ensure_ascii=False)}"""
    if chapter:                                       # a chapter: no 'whole story' structure demands at all
        prompt = re.sub(r"a hook in the first lines, ", "", prompt)
        prompt = re.sub(r"STRUCTURE \(a clear beginning:.*?end is thin or abrupt\)", "STRUCTURE (inside this chapter only: "
                        "its planned beats in order, each fully lived in scenes)", prompt, flags=re.S)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "responseMimeType": "application/json", "maxOutputTokens": 60000}}
    for model in gemini_models(key)[:4]:
        try:
            log(f"Editor checking the story with {model} ...")
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json=body, timeout=360)
            if not r.ok:
                log(f"  editor: {model} {r.status_code}")
                continue
            new = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            sc = new.get("scenes") or []
            words = sum(len(str(ln.get("text", "")).split()) for s in sc for ln in s.get("lines", []) or [])
            if (new.get("title") and len(sc) >= max(6, int(len(story["scenes"]) * 0.8)) and
                    all(s.get("lines") for s in sc) and words >= words0 * 0.9):
                for k, v in story.items():               # anything the editor dropped stays as it was
                    new.setdefault(k, v)
                log(f"  editor improved the story ({words0} -> {words} words), scores: {new.get('editor_scores')}")
                return new
            log(f"  editor's version not complete enough ({len(sc)} scenes, {words} words) - keeping the original")
            return story
        except Exception as e:
            log(f"  editor ({model}) failed: {str(e)[:150]}")
    return story


TEXT_DAY_OUT = set()          # writing models whose free DAILY limit is used up (not tried again this run)
_post = requests.post


def _post_watch(url, *a, **k):
    """Every Gemini writing request: a model that answers 'daily limit reached' is skipped for the rest of the
    run - no more wasted requests (each refused one also counts) and no long waits on it."""
    r = _post(url, *a, **k)
    try:
        if r.status_code == 429 and ":generateContent" in str(url) and "tts" not in str(url):
            if re.search(r"PerDay|per_day|daily", r.text, re.I):
                mdl = str(url).split("/models/")[1].split(":")[0]
                if mdl not in TEXT_DAY_OUT:
                    TEXT_DAY_OUT.add(mdl)
                    log(f"  {mdl}: today's free limit is used up - the next model writes")
    except Exception:
        pass
    return r


requests.post = _post_watch


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
    tries += ["gemini-flash-lite-latest"]           # ('gemini-2.5-flash' was retired by Google: 404)
    out = []
    for t in tries:
        if t and t not in out and t not in TEXT_DAY_OUT:
            out.append(t)
    return out or tries[-1:]


# ----------------------------------------------------------------- famous writers' ghost stories (public domain)
# Only writers whose works are free to use in India (author died 60+ years ago, counted from 1 January after
# the death). Retold faithfully, with the writer and the book named at the start.
CLASSICS = [  # id, writer (bn, hi), book (bn, hi), story (bn, hi), English identification for the model
    ("tagore_kshudhita", ("রবীন্দ্রনাথ ঠাকুর", "रवींद्रनाथ टैगोर"), ("গল্পগুচ্ছ", "गल्पगुच्छ"),
     ("ক্ষুধিত পাষাণ", "क्षुधित पाषाण"), "Rabindranath Tagore's 'Kshudhita Pashan' (The Hungry Stones, 1895)"),
    ("tagore_monihara", ("রবীন্দ্রনাথ ঠাকুর", "रवींद्रनाथ टैगोर"), ("গল্পগুচ্ছ", "गल्पगुच्छ"),
     ("মণিহারা", "मणिहारा"), "Rabindranath Tagore's 'Monihara' (The Lost Jewels, 1898)"),
    ("tagore_kankal", ("রবীন্দ্রনাথ ঠাকুর", "रवींद्रनाथ टैगोर"), ("গল্পগুচ্ছ", "गल्पगुच्छ"),
     ("কঙ্কাল", "कंकाल"), "Rabindranath Tagore's 'Kankal' (The Skeleton, 1892)"),
    ("tagore_nishithe", ("রবীন্দ্রনাথ ঠাকুর", "रवींद्रनाथ टैगोर"), ("গল্পগুচ্ছ", "गल्पगुच्छ"),
     ("নিশীথে", "निशीथे"), "Rabindranath Tagore's 'Nishithe' (In the Night, 1894)"),
    ("tagore_jibito", ("রবীন্দ্রনাথ ঠাকুর", "रवींद्रनाथ टैगोर"), ("গল্পগুচ্ছ", "गल्पगुच्छ"),
     ("জীবিত ও মৃত", "जीवित और मृत"), "Rabindranath Tagore's 'Jibito o Mrito' (The Living and the Dead, 1892)"),
    ("bibhuti_taranath", ("বিভূতিভূষণ বন্দ্যোপাধ্যায়", "विभूतिभूषण बंद्योपाध्याय"), ("তারানাথ তান্ত্রিক", "तारानाथ तांत्रिक"),
     ("তারানাথ তান্ত্রিকের গল্প", "तारानाथ तांत्रिक की कहानी"),
     "Bibhutibhushan Bandyopadhyay's original 'Taranath Tantriker Golpo' (the first Taranath Tantrik story, "
     "Taranath's youth and Madhusundari Devi) - NOT the later stories by his son Taradas"),
    ("bibhuti_rankini", ("বিভূতিভূষণ বন্দ্যোপাধ্যায়", "विभूतिभूषण बंद्योपाध्याय"), ("", ""),
     ("রঙ্কিনী দেবীর খড়্গ", "रंकिणी देवी का खड्ग"), "Bibhutibhushan Bandyopadhyay's 'Rankini Debir Khorgo'"),
    ("bibhuti_abhishapta", ("বিভূতিভূষণ বন্দ্যোপাধ্যায়", "विभूतिभूषण बंद्योपाध्याय"), ("", ""),
     ("অভিশপ্ত", "अभिशप्त"), "Bibhutibhushan Bandyopadhyay's 'Abhishapta'"),
    ("bibhuti_medal", ("বিভূতিভূষণ বন্দ্যোপাধ্যায়", "विभूतिभूषण बंद्योपाध्याय"), ("", ""),
     ("মেডেল", "मेडल"), "Bibhutibhushan Bandyopadhyay's ghost story 'Medal'"),
    ("trailokya_lullu", ("ত্রৈলোক্যনাথ মুখোপাধ্যায়", "त्रैलोक्यनाथ मुखोपाध्याय"), ("ভূত ও মানুষ", "भूत और मानुष"),
     ("লুল্লু", "लुल्लु"), "Trailokyanath Mukhopadhyay's 'Lullu' (from Bhoot o Manush)"),
    ("parashuram_bhushondi", ("পরশুরাম", "परशुराम"), ("গড্ডলিকা", "गड्डलिका"),
     ("ভুশণ্ডীর মাঠে", "भुशंडी के मैदान में"), "Parashuram (Rajshekhar Basu)'s 'Bhushondir Mathe' (from Gaddalika)"),
]
WORLD_CLASSICS = [  # world classics (writers who died long ago - free to use in India), told 'based on'
    ('poe_telltale', ('এডগার অ্যালান পো', 'एडगर एलन पो'), ('', ''), ('দ্য টেল-টেল হার্ট', 'द टेल-टेल हार्ट'), "Edgar Allan Poe's 'The Tell-Tale Heart' (1843)", True),
    ('jacobs_paw', ('ডব্লিউ. ডব্লিউ. জেকবস', 'डब्ल्यू. डब्ल्यू. जैकब्स'), ('', ''), ('বাঁদরের থাবা', 'बंदर का पंजा'), "W. W. Jacobs' 'The Monkey's Paw' (1902)", True),
    ('dickens_signal', ('চার্লস ডিকেন্স', 'चार्ल्स डिकेंस'), ('', ''), ('সিগন্যালম্যান', 'सिग्नलमैन'), "Charles Dickens' 'The Signal-Man' (1866)", True),
    ('kipling_rickshaw', ('রাডইয়ার্ড কিপলিং', 'रुडयार्ड किपलिंग'), ('', ''), ('ভুতুড়ে রিকশা', 'भुतहा रिक्शा'), "Rudyard Kipling's 'The Phantom Rickshaw' (1885, Shimla)", True),
    ('stoker_judge', ('ব্রাম স্টোকার', 'ब्रैम स्टोकर'), ('', ''), ('জজসাহেবের বাড়ি', 'जज का मकान'), "Bram Stoker's 'The Judge's House' (1891)", True),
    ('poe_blackcat', ('এডগার অ্যালান পো', 'एडगर एलन पो'), ('', ''), ('কালো বিড়াল', 'काली बिल्ली'), "Edgar Allan Poe's 'The Black Cat' (1843) - without cruelty details", True),
    ('mrjames_whistle', ('এম. আর. জেমস', 'एम. आर. जेम्स'), ('', ''), ('বাঁশি বাজালেই আসব', 'सीटी बजाओ, मैं आऊँगा'), "M. R. James' 'Oh, Whistle, and I'll Come to You, My Lad' (1904)", True),
    ('kipling_owntrue', ('রাডইয়ার্ড কিপলিং', 'रुडयार्ड किपलिंग'), ('', ''), ('আমার নিজের সত্যি ভূতের গল্প', 'मेरी अपनी सच्ची भूत-कथा'), "Rudyard Kipling's 'My Own True Ghost Story' (1888, an Indian dak-bungalow)", True),
    ('crawford_upper', ('এফ. ম্যারিয়ন ক্রফোর্ড', 'एफ. मैरियन क्रॉफ़र्ड'), ('', ''), ('ওপরের বার্থ', 'ऊपर की बर्थ'), "F. Marion Crawford's 'The Upper Berth' (1886)", True),
    ('poe_usher', ('এডগার অ্যালান পো', 'एडगर एलन पो'), ('', ''), ('আশার বংশের পতন', 'अशर वंश का पतन'), "Edgar Allan Poe's 'The Fall of the House of Usher' (1839)", True),
    ('maupassant_horla', ('গী দ্য মোপাসাঁ', 'गी द मोपासाँ'), ('', ''), ('লে অর্লা', 'ला होर्ला'), "Guy de Maupassant's 'Le Horla' (1887)", True),
    ('benson_tower', ('ই. এফ. বেনসন', 'ई. एफ. बेन्सन'), ('', ''), ('মিনারের ঘর', 'मीनार का कमरा'), "E. F. Benson's 'The Room in the Tower' (1912)", True),
    ('mrjames_runes', ('এম. আর. জেমস', 'एम. आर. जेम्स'), ('', ''), ('অভিশপ্ত রুন', 'शापित रून'), "M. R. James' 'Casting the Runes' (1911)", True),
    ('gogol_viy', ('নিকোলাই গোগোল', 'निकोलाई गोगोल'), ('', ''), ('ভিই', 'वीय'), "Nikolai Gogol's 'Viy' (1835)", True),
    ('saki_window', ('সাকি', 'साकी'), ('', ''), ('খোলা জানালা', 'खुली खिड़की'), "Saki's 'The Open Window' (1914)", True),
    ('stevenson_snatcher', ('রবার্ট লুই স্টিভেনসন', 'रॉबर्ट लुई स्टीवेन्सन'), ('', ''), ('লাশচোর', 'लाश-चोर'), "Robert Louis Stevenson's 'The Body Snatcher' (1884)", True),
    ('gaskell_nurse', ('এলিজাবেথ গাসকেল', 'एलिज़ाबेथ गैस्केल'), ('', ''), ('বুড়ি দাইমার গল্প', 'बूढ़ी आया की कहानी'), "Elizabeth Gaskell's 'The Old Nurse's Story' (1852)", True),
    ('poe_masque', ('এডগার অ্যালান পো', 'एडगर एलन पो'), ('', ''), ('লাল মৃত্যুর মুখোশ', 'लाल मौत का नक़ाब'), "Edgar Allan Poe's 'The Masque of the Red Death' (1842)", True),
    ('mrjames_lost', ('এম. আর. জেমস', 'एम. आर. जेम्स'), ('', ''), ('হারানো হৃদয়', 'खोए हुए दिल'), "M. R. James' 'Lost Hearts' (1895) - without harm details to children", True),
    ('harvey_hand', ('ডব্লিউ. এফ. হার্ভে', 'डब्ल्यू. एफ. हार्वे'), ('', ''), ('পাঁচ আঙুলের দানব', 'पाँच उँगलियों वाला दानव'), "W. F. Harvey's 'The Beast with Five Fingers' (1919)", True),
    ('lefanu_tea', ('শেরিডান লে ফানু', 'शेरिडन ले फ़ानू'), ('', ''), ('সবুজ চা', 'हरी चाय'), "Sheridan Le Fanu's 'Green Tea' (1869)", True),
    ('doyle_pole', ('আর্থার কোনান ডয়েল', 'आर्थर कॉनन डॉयल'), ('', ''), ('পোল-স্টারের ক্যাপ্টেন', 'पोल-स्टार का कप्तान'), "Arthur Conan Doyle's 'The Captain of the Pole-Star' (1883)", True),
    ('irving_sleepy', ('ওয়াশিংটন আরভিং', 'वॉशिंगटन इरविंग'), ('', ''), ('স্লিপি হলোর মুণ্ডহীন ঘোড়সওয়ার', 'स्लीपी हॉलो का बिना सिर वाला घुड़सवार'), "Washington Irving's 'The Legend of Sleepy Hollow' (1820)", True),
    ('wilde_canterville', ('অস্কার ওয়াইল্ড', 'ऑस्कर वाइल्ड'), ('', ''), ('ক্যান্টারভিলের ভূত', 'कैंटरविल का भूत'), "Oscar Wilde's 'The Canterville Ghost' (1887)", True),
]
_BN = [c + (False,) for c in CLASSICS]
CLASSICS = [x for pair in zip(_BN, WORLD_CLASSICS) for x in pair] + _BN[len(WORLD_CLASSICS):] + \
    WORLD_CLASSICS[len(_BN):]        # Bengali and world classics in turn
CLASSIC_RULE = (
    "\nFAMOUS CLASSIC (very important): this video retells {en} - a public-domain classic. Tell THAT story "
    "faithfully: the same events in the same order, the same characters and their relations, the same place and "
    "era, the same mystery and the same ending - nothing invented that changes the plot (this overrides the rules "
    "about inventing your own plot; build the hook and the fear through suspense, not by changing events). You "
    "only dramatize it: natural spoken dialogue for the characters, sound, pictures and suspense, in today's "
    "simple spoken {lang} (if the original's language is old-fashioned, keep the meaning but tell it the way "
    "people speak today). Begin "
    "where the original begins, in the same order (the writer is credited separately before the story), with one "
    "short chilling hook line first, and introduce every character by name and who they are when they enter. Use the original title as the title. If you do "
    "NOT remember this story well enough to retell it faithfully, return ONLY this JSON: {{\"unknown\": true}}.\n")
MASTER_STYLE = (
    "\nCRAFT OF THE GREAT BENGALI HORROR WRITERS: write with the atmosphere of Bibhutibhushan's Taranath, "
    "Hemendra Kumar Roy, Sharadindu's Baroda and Satyajit Ray's ghost stories - a slow, REALISTIC build-up in "
    "ordinary life, exact everyday detail, every event with a believable cause, people who act like real people, "
    "logic that holds to the end, and the supernatural entering quietly. Never retell or closely follow any "
    "copyrighted modern book, film or series (a folk legend or the SOURCE STORY given is fine). "
    "No call, exclamation or catchphrase over and over: a name called out ('ঠাকুরমশাই!', 'মা গো!') at most twice "
    "in the whole story - every line must say something new.\n"
    "REAL PEOPLE, REAL TALK (it must feel as if real people lived it): people speak to each other the way Bengalis "
    "really do - by first name or pet name (ডাকনাম), or by the relation (দাদা, দিদি, কাকু, মাসিমা, বৌদি, মামা, "
    "স্যার, ডাক্তারবাবু, মাস্টারমশাই) - NEVER by full name with surname, and they do not say the other person's name in "
    "every line; an elder may be called by surname + 'মশাই'. The storyteller says a person's full name only once, "
    "when he or she first comes in, then the first name. Half sentences, interruptions, small everyday worries "
    "(the bus fare, the electricity bill, a child's exam), exact real places (a real para, a real bus route, a real "
    "shop sign), exact times; people are not brave or wise in every line.\n"
    "NO STOCK LINES: every story begins in its OWN way and has its own sentences - never a ready-made line that "
    "could fit any story (like 'the day had begun like any ordinary day', 'little did they know', 'that night "
    "changed everything'): show it with this story's own concrete detail instead.\n")


LONG_MIN = float(os.environ.get("HORROR_MINUTES") or 22)     # two ~22-minute stories a day (2 PM, 8 PM)
SLOT_MINUTES = {10: 15.0, 14: 22.0, 20: 22.0}      # every character in the Gemini voice fits the free limit
os.environ.setdefault("VOICE_MAX", "240")        # Gemini may take its time for a long story (it is the best voice)
os.environ.setdefault("VOICE_RESERVE", "60")     # ... but leaves an hour for making and posting the video
JOB_START = time.time()                          # GitHub stops a job after 6 hours - we must finish well before


def job_minutes_left():
    return (float(env("JOB_LIMIT_MINUTES") or 350) * 60 - (time.time() - JOB_START)) / 60


def fix_language(story, lang):
    """Every spoken line must be in the story's language: a line the writer left in English (or mostly Latin
    letters) is translated - a Bengali radio drama that suddenly speaks English breaks the spell."""
    script = r"[\u0980-\u09FF]" if lang == "bn" else r"[\u0900-\u097F]"
    bad = []
    for i, sc in enumerate(story.get("scenes") or []):
        for j, ln in enumerate(sc.get("lines") or []):
            t = str(ln.get("text", "")).strip()
            lat = len(re.findall(r"[A-Za-z]", t))
            loc = len(re.findall(script, t))
            if t and ((lat > 6 and lat > loc) or re.search(r"[A-Za-z]{2,}(?:[\s,.'-]+[A-Za-z]{2,}){2,}", t)):
                bad.append((i, j, t))
    if not bad:
        return
    key = env("GEMINI_API_KEY")
    if MOCK or not key:
        return
    rows = [{"k": k, "text": t[:400]} for k, (_i, _j, t) in enumerate(bad[:80])]
    prompt = (f"Translate each line into natural spoken {LANGS[lang]['name']} for a radio drama"
              + (" (pure Kolkata cholit bhasha)" if lang == "bn" else "") + ". Keep names. Answer ONLY JSON: "
              "[{\"k\": number, \"text\": \"translated line\"}]\n" + json.dumps(rows, ensure_ascii=False))
    for model in gemini_models(key):
        try:
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}},
                              timeout=180)
            if not r.ok:
                continue
            out = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            n = 0
            for o in out if isinstance(out, list) else []:
                try:
                    i, j, old = bad[int(o["k"])]
                except Exception:
                    continue
                t = str(o.get("text", "")).strip()
                if t and re.search(script, t):
                    ln = story["scenes"][i]["lines"][j]
                    ln.setdefault("en", old)
                    ln["text"] = t
                    n += 1
            log(f"  language check: {n} of {len(bad)} English line(s) put into {LANGS[lang]['name']}")
            return
        except Exception as e:
            log("  language check:", str(e)[:100])
    # no model answered: an English line is better left out than read out in English
    for i, j, _t in sorted(bad, reverse=True):
        del story["scenes"][i]["lines"][j]
    log(f"  language check: {len(bad)} English line(s) left out")


def continuity_bridges(story, lang):
    """The whole joined story read once more as ONE film: a scene that seems to come from nowhere ('where did this
    come from?') gets a short narrator bridge at its start that ties it to what came before."""
    key = env("GEMINI_API_KEY")
    if MOCK or not key or env("CONTINUITY") == "0":
        return
    rows = []
    for i, sc in enumerate(story.get("scenes") or []):
        ls = [ln for ln in sc.get("lines") or [] if str(ln.get("text", "")).strip()]
        if not ls:
            continue
        rows.append({"n": i, "place": str(sc.get("place", ""))[:80],
                     "starts": str(ls[0].get("en") or ls[0].get("text"))[:160],
                     "ends": str(ls[-1].get("en") or ls[-1].get("text"))[:160]})
    prompt = (f"These are the scenes of ONE {LANGS[lang]['name']} horror audio story, in order (how each starts and "
              "ends). Find every scene that does NOT follow from the scene before it - a sudden new place, time, "
              "person or event the listener cannot place. For each, write ONE short narrator bridge line in "
              f"{LANGS[lang]['name']} (pure Kolkata cholit for Bengali, max 22 words) that ties it naturally to what "
              "came before (time, place, why). ALSO find every scene whose LAST line stops in the middle (an unfinished "
              "sentence, thought or action) and write ONE short closing line for it (same speaker or the narrator). "
              "ALSO find every scene whose TIME does not follow (it jumps ahead, or goes back before the scene "
              "before it): give it a bridge line that makes the time clear and natural. "
              "ALSO, if ONE person is called by two different names in different scenes, add "
              "{\"rename_from\": \"wrong name\", \"rename_to\": \"the name used most\"}. "
              "Answer ONLY JSON: [{\"n\": scene number, \"bridge\": \"line\"} or {\"n\": scene number, "
              "\"close\": \"line\", \"speaker\": \"name or narrator\"}] ([] if everything flows).\n" + json.dumps(rows, ensure_ascii=False))
    for model in (gemini_models(key)[:3] * 2):
        r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}},
                          timeout=180)
        if not r.ok:
            log(f"  continuity check: {model} {r.status_code}")
            if r.status_code == 503:
                time.sleep(30)                         # Google busy: a short wait, the check matters
            continue
        fixes = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        n = 0
        for fx in fixes if isinstance(fixes, list) else []:
            a_, b_ = str(fx.get("rename_from") or "").strip(), str(fx.get("rename_to") or "").strip()
            if a_ and b_ and a_ != b_ and len(a_) >= 2:   # one person, one name - everywhere
                for sc_ in story.get("scenes") or []:
                    for ln_ in sc_.get("lines") or []:
                        if str(ln_.get("speaker", "")).strip().lower() == a_.lower():
                            ln_["speaker"] = b_
                        for k_ in ("text", "en"):
                            if a_ in str(ln_.get(k_, "")):
                                ln_[k_] = str(ln_[k_]).replace(a_, b_)
                log(f"  continuity check: one name for one person - '{a_}' -> '{b_}'")
                continue
            try:
                sc = story["scenes"][int(fx["n"])]
            except Exception:
                continue
            cl = str(fx.get("close", "")).strip()
            if cl:
                sc.setdefault("lines", []).append({"speaker": str(fx.get("speaker") or "narrator"), "emotion": "eerie",
                                                   "text": cl, "en": ""})
                n += 1
            b = str(fx.get("bridge", "")).strip()
            if b and int(fx["n"]) > 0:
                sc.setdefault("lines", []).insert(0, {"speaker": "narrator", "emotion": "eerie", "text": b, "en": ""})
                n += 1
        log(f"  continuity check: {n} bridge line(s) added")
        return


def line_flow_check(story, lang):
    """v89: the joined story read LINE BY LINE as one film (the scene check only sees how scenes start and end):
    an answer that does not answer, a line that comes from nowhere, someone who knows what he cannot know, a thing
    or person used before it was introduced, a dead or absent person speaking, a fact that contradicts an earlier
    one - each is mended with ONE changed line or ONE added line, so nothing feels cut or patched together."""
    key = env("GEMINI_API_KEY")
    if MOCK or not key or env("LINE_FLOW") == "0":
        return 0
    rows, idx = [], {}
    for i, sc in enumerate(story.get("scenes") or []):
        rows.append(f"--- scene {i} ({str(sc.get('place', ''))[:60]})")
        for j, ln in enumerate(sc.get("lines") or []):
            tx = str(ln.get("text", "")).strip()
            if tx:
                rows.append(f"{i}.{j} {ln.get('speaker', 'narrator')}: {extras.strip_tags(tx)[:300]}")
                idx[f"{i}.{j}"] = (i, j)
    prompt = (f"This is ONE {LANGS[lang]['name']} horror audio story, line by line ('scene.line speaker: text'). "
              "Read it like a strict film editor. Find ONLY real breaks in the flow: (1) a reply that does not fit "
              "the line before it; (2) a line or event that comes from nowhere; (3) a person who knows something he "
              "was never told; (4) a person, object or place used before it was introduced; (5) a dead or absent "
              "person speaking; (6) a fact that contradicts an earlier line; (7) the same thing told twice. "
              "Mend each with the SMALLEST change: replace that one line, or add ONE short line after a given line. "
              f"New text in {LANGS[lang]['name']} (pure Kolkata cholit for Bengali), the same speaker's way of "
              "talking, max 25 words, no English, no sound tags. At most 12 fixes; [] if the story flows. "
              "Answer ONLY JSON: [{\"id\": \"scene.line\", \"replace\": \"new text\"} or "
              "{\"after\": \"scene.line\", \"speaker\": \"name or narrator\", \"insert\": \"new line\"}]\n"
              + "\n".join(rows))
    fixes = None
    for model in (gemini_models(key)[:3] + extras.helper_models(key)[:3]):
        try:
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}},
                              timeout=240)
        except Exception:
            continue
        if not r.ok:
            log(f"  line-by-line check: {model} {r.status_code}")
            if r.status_code == 503:
                time.sleep(20)
            continue
        fixes = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        break
    if not isinstance(fixes, list):
        return 0
    names = {str(ln.get("speaker", "")).strip().lower() for sc in story["scenes"] for ln in sc.get("lines") or []}
    inserts, n = [], 0
    for fx in fixes[:12]:
        if not isinstance(fx, dict):
            continue
        if fx.get("id") in idx and str(fx.get("replace", "")).strip():
            i, j = idx[fx["id"]]
            new = str(fx["replace"]).strip()
            if 2 <= len(new.split()) <= 30 and not re.search(r"[A-Za-z]{4,}", new):
                story["scenes"][i]["lines"][j]["text"] = new
                story["scenes"][i]["lines"][j]["en"] = ""
                n += 1
        elif fx.get("after") in idx and str(fx.get("insert", "")).strip():
            new = str(fx["insert"]).strip()
            spk = str(fx.get("speaker") or "narrator").strip()
            if spk.lower() not in names:
                spk = "narrator"
            if 2 <= len(new.split()) <= 30 and not re.search(r"[A-Za-z]{4,}", new):
                inserts.append((idx[fx["after"]], {"speaker": spk, "emotion": "normal", "text": new, "en": ""}))
    for (i, j), ln in sorted(inserts, key=lambda z: z[0], reverse=True):   # from the end, so the numbers stay right
        story["scenes"][i]["lines"].insert(j + 1, ln)
        n += 1
    log(f"  line-by-line check: {n} place(s) mended so every line follows the one before")
    return n


def ensure_ending(story, lang, cut_short=False):
    """The story must END: the mystery explained, every person's fate told, a last chilling line. The written
    ending is read once more; if it stops in the middle (a cliffhanger, an unexplained ghost, a chapter that
    failed), a closing passage is written from the same people and threads and added to the last scene."""
    key = env("GEMINI_API_KEY")
    if MOCK or not key or env("ENDING_CHECK") == "0" or not story.get("scenes"):
        return
    names = [str(c.get("name")) for c in story.get("characters") or [] if isinstance(c, dict) and c.get("name")]
    tail = []
    for sc in story["scenes"][-3:]:
        for ln in sc.get("lines") or []:
            if str(ln.get("text", "")).strip():
                tail.append(f"{ln.get('speaker', 'narrator')}: {ln.get('en') or ln.get('text')}"[:220])
    prompt = (f"A {LANGS[lang]['name']} horror audio story. What happened (by chapter):\n{story.get('summary', '')}\n\n"
              "Its LAST lines:\n" + "\n".join(tail[-30:]) + "\n\n"
              + ("The writing STOPPED before the ending. " if cut_short else "")
              + "Does the story END completely - the mystery explained, the ghost's reason clear, what became of every "
              "main person told, a final chilling line - with nothing left hanging? If YES answer {\"complete\": true}. "
              "If NOT, write ONLY the missing closing as a continuation of exactly these last lines (never retell, repeat "
              "or add any earlier event or scene): 6-12 lines, mostly "
              f"dialogue, the same people ({', '.join(names[:8])}) and ONLY threads that already exist - no new "
              "person, no new event. Then the narrator's resolution and one last chilling line. "
              f"Lines in {LANGS[lang]['name']} (Bengali: pure Kolkata cholit). Answer ONLY JSON: "
              "{\"complete\": false, \"lines\": [{\"speaker\": name or \"narrator\", \"emotion\": one word, "
              "\"text\": line, \"en\": english}], \"ending_line\": last chilling line}")
    for model in gemini_models(key)[:2]:
        try:
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json"}},
                              timeout=180)
        except Exception as e:
            log("  ending check:", str(e)[:100])
            continue
        if not r.ok:
            log(f"  ending check: {model} {r.status_code}")
            continue
        try:
            ans = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception:
            continue
        if not isinstance(ans, dict):
            continue
        if ans.get("complete") is True and not cut_short:
            log("  ending check: the story ends completely")
            return
        add = [ln for ln in ans.get("lines") or [] if isinstance(ln, dict) and str(ln.get("text", "")).strip()]
        if add:
            story["scenes"][-1].setdefault("lines", []).extend(add)
            if str(ans.get("ending_line", "")).strip():
                story["ending_line"] = str(ans["ending_line"]).strip()
            log(f"  ending check: the ending was missing - {len(add)} closing lines added")
        return


def write_long_story(lang, theme, history, fmt, extra_rules, classic=False, ending="resolve", opening="start", part=0):
    """ONE long story (about LONG_MIN minutes) written chapter by chapter from the master outline, each chapter
    continuing exactly where the last one stopped and checked by the editor, then joined into one script."""
    # TWO halves (not 4-5 small chapters): every join is a place where a story can lose its thread, so a ~22-minute
    # story is written as two big halves - the first ends on the midpoint cliffhanger, the second finishes it
    n_ch = 2 if LONG_MIN <= 26 else max(2, round(LONG_MIN / 11))
    sc = length_scale()                               # learned from OUR real videos (see learn_length)
    STATE["len_scale"] = sc
    STATE.pop("short_plan", None)
    wpm = 120 * sc                                    # script words that make one minute of the finished video
    words_per = int(LONG_MIN * wpm / n_ch)
    need = int(float(env("MIN_LONG_MINUTES") or max(12.0, LONG_MIN - 2)) * wpm)
    sc_lo, sc_hi = max(6, round(words_per / 70)), max(8, round(words_per / 48))   # scenes per chapter
    max_ch = n_ch + 3
    # THE PLAN DECIDES THE ORDER: the outline's beats are shared out between the chapters in advance - chapter 1
    # tells beats 1-5, chapter 2 beats 6-10 ... - so nothing is told too early, nothing is skipped and nothing is
    # pushed to the end. (Without this, a weak model 'forgot' beats and they were crammed into the last chapter.)
    try:
        allb = plan_load(STATE.get("outline")).get("beats") or []
        if part and any(isinstance(b, dict) and b.get("part") for b in allb):     # a series: only THIS part's beats
            allb = [b for b in allb if not isinstance(b, dict) or str(b.get("part", part)) == str(part)]
        beats = []
        for b in allb:
            if isinstance(b, dict):
                t = str(b.get("what_happens") or b.get("beat") or b.get("text") or "").strip()
                if b.get("because"):                  # the cause keeps every beat tied to the one before
                    t += f" (because: {str(b['because'])[:160]})"
                if b.get("decision"):
                    t += f" (decision: {b['decision']}; follow-up: {b.get('follow_up', '')})"
                if b.get("new_fear"):
                    t += f" (new fear: {b['new_fear']})"
                beats.append(t[:600])
            else:
                beats.append(str(b)[:600])
    except Exception:
        beats = []
    if len(beats) >= n_ch * 2:
        max_ch = n_ch
        share = [beats[round(i * len(beats) / n_ch):round((i + 1) * len(beats) / n_ch)] for i in range(n_ch)]
        ends = [round((i + 1) * len(beats) / n_ch) for i in range(n_ch)]
        starts = [round(i * len(beats) / n_ch) for i in range(n_ch)]
        log(f"  the plan's {len(beats)} beats shared out over {n_ch} chapters")
    else:
        # no plan at all (Google refused every model): only TWO chapters - a shorter story that holds together
        # is far better than a long one whose chapters wander off on their own
        share, starts, ends = [], [], []
        n_ch, max_ch = 2, 3                           # (a 3rd chapter only if the first ones came out too short)
        words_per = int(LONG_MIN * wpm / 2)
        log("  no story plan today - writing the story in 2 chapters so it stays in one piece")
    full_outline = STATE.get("outline") or ""

    def outline_for(k, final):
        """What a chapter may SEE of the plan: never the twist, the solution or the beats of later chapters
        before the last chapter - a writer who knows the ending tends to tell it at once (part 2 'ended' in
        its first 5 minutes and then started again)."""
        if final or not full_outline:
            return full_outline
        pl = plan_load(full_outline)
        if not pl:
            return full_outline
        for key_ in ("twist", "resolution", "last_line"):
            pl.pop(key_, None)
        bl = pl.get("beats") or []
        if part and any(isinstance(b, dict) and b.get("part") for b in bl):
            bl = [b for b in bl if not isinstance(b, dict) or str(b.get("part", part)) == str(part)]
        if ends and k - 1 < len(ends):
            bl = bl[:ends[k - 1]]
        pl["beats"] = bl
        pl["note"] = "the rest of the plan (and the solution) is told only in the later chapters"
        return json.dumps(pl, ensure_ascii=False)
    chapters, summary, last, total, k, force_final, final_tries = [], "", "", 0, 0, False, 0
    carry = []                                        # beats of a chapter that failed go to the next one
    while k < max_ch:
        k += 1
        # without a plan: chapter 2 ends the story - unless the story so far is clearly too short for the
        # 20-minute minimum (11 Nov 2026: chapters of 500-650 words gave 11-15 minute videos); then one more
        # chapter comes before the ending
        final = force_final or k == max_ch or (not share and k >= 2 and total >= words_per * 0.6 * (k - 1))
        mine = (carry + share[k - 1]) if share and k - 1 < len(share) else []
        if share and final and k - 1 < len(share):
            mine = carry + [b for s in share[k - 1:] for b in s]
        rule = (f"\nLONG STORY - CHAPTER {k} (of {n_ch if share else f'about {n_ch}'}): today's video is ONE long "
                f"story of about {int(LONG_MIN)} minutes, written chapter by chapter. Write ONLY chapter {k}. ")
        if mine:
            first_no = (starts[k - 1] + 1 - len(carry)) if k - 1 < len(starts) else 1
            rule += ("THIS CHAPTER TELLS EXACTLY THESE BEATS OF THE MASTER OUTLINE, IN THIS ORDER - nothing from the "
                     "beats before them (already told), nothing from the beats after them (later chapters): "
                     + " | ".join(f"beat {first_no + i}: {b}" for i, b in enumerate(mine)) + ". Every beat becomes "
                     "one or more full scenes, lived in dialogue. ")
        else:
            rule += "Tell the NEXT beats of the MASTER OUTLINE in order (continue from where the story so far stopped). "
        if k == 1 and opening == "recap":
            rule += ("It opens THIS PART of the series: first the narrator's short recap of where the last part ended "
                     "(3-4 lines), then the story goes on from that exact moment - no new beginning. ")
        elif k == 1:
            rule += ("It is the real BEGINNING: the hook line, then when / who / where from / why / how they came, "
                     "the people, ordinary life and the first strange signs. ")
        else:
            rule += (f"Continue EXACTLY from where chapter {k - 1} stopped - same people, names, place and time; no "
                     f"recap, no new introduction, no hook line. Story so far:{summary}\nThe last lines were (ALREADY "
                     f"SPOKEN - never repeat or re-tell them, start with what happens NEXT): {last}\n")
        rule += (("This is the LAST chapter of THIS PART of a series: tell this part's remaining beats and STOP at its "
                  "big turning point on a strong cliffhanger - the mystery is NOT solved yet, the next part continues "
                  "it. " if ending == "cliffhanger" else
                  "This is the FINAL chapter: tell all remaining beats - the climax, the twist, a full resolution scene "
                  "that explains everything and what became of every person, then the last chilling line. ") if final else
                 "End the chapter on a strong cliffhanger that leads straight into the next chapter (never say "
                 "'next part' or 'to be continued'). Do NOT end the story yet. ")
        rule += ("TIME ONLY MOVES FORWARD: this chapter starts at the moment the last one ended and goes on in order - "
                 "never jump ahead ('a month later', 'next year') and never go back to an earlier night; the past "
                 "comes in ONLY as a character's spoken memory. "
                 "LANGUAGE: every spoken line ONLY in " + LANGS[lang]["name"] + " (pure Kolkata cholit for Bengali) - "
                 "never an English sentence in the text (English only in the 'en' field). "
                 "EVERY SCENE ENDS COMPLETE: its last line is a finished sentence and its moment is over (an action done, "
                 "a question asked, a shock seen) - never stop a scene in the middle of a thought, a sentence or an "
                 "action; the NEXT scene picks up from exactly that point. "
                 "NEVER SAY A THING TWICE: no sentence, fact or event is repeated; the storyteller never repeats what a "
                 "character has just said (no 'she said she would not go' next to 'I will not go'). "
                 "NO JUMPS: every scene starts where the previous one ended, or with a clear spoken bridge (time and "
                 "place: 'সেই রাতেই...', 'পরদিন সকালে, থানায়...'); no person, place or event appears from nowhere. "
                 + ("Use ONLY the people, places, clues and promises already in the story so far - no new characters "
                    "or new threads now; tie every open thread. " if final else "") +
                 "Also add the key \"chapter_summary\": ENGLISH, 5-7 sentences - exactly what happened in this "
                 "chapter, with names, decisions, clues and open questions.\n")
        length = (f"- LENGTH OF THIS CHAPTER: {sc_lo} to {sc_hi} scenes, about {words_per} spoken words (never much more). Slow-burning, real "
                  "conversations, every moment lived - never rushed. The length comes from living the planned beats "
                  "fully (talk, doubt, small real details) - NEVER from extra events, repeated scenes or changing "
                  "the planned order.")
        try:                                         # a shorter chapter is kept (no costly rewrite) -
            er = extra_rules
            if full_outline and full_outline in er:
                er = er.replace(full_outline, outline_for(k, final))
            if not final:
                er = er.replace("This is the FINAL part: solve the mystery completely.", "")
                rule += ("NOT THE END YET: in this chapter do NOT solve the mystery, do NOT reveal the twist and do "
                         "NOT wrap up the story - that happens only in the last chapter. ")
            s = make_story(lang, theme, history, fmt=fmt, part=0, prev=None, extra_rules=er + rule,
                           length=length, min_w=int(words_per * 0.88))   # ... more chapters make up the length
        except ClassicUnknown:
            raise
        except Exception as e:
            if k == 1:
                raise
            if final:
                final_tries += 1
                if final_tries >= 2:
                    log(f"  the last chapter failed twice ({str(e)[:100]}) - a closing passage will be written")
                    STATE["ending_cut"] = True
                    STATE["short_plan"] = True
                    break
                k -= 1                               # try the ending again
                continue
            if share:                                # same beats once more, then they go with the next chapter
                if STATE.get("ch_retry") != k:
                    STATE["ch_retry"] = k
                    log(f"  chapter {k} failed ({str(e)[:100]}) - trying it once more")
                    k -= 1
                else:
                    log(f"  chapter {k} failed again - its beats go into chapter {k + 1}")
                    carry = mine
                continue
            log(f"  chapter {k} failed ({str(e)[:100]}) - the next chapter will end the story")
            force_final = True
            k -= 1
            continue
        carry = []
        s = edit_story(s, lang, classic=classic, brief=STATE.get("brief", ""), outline=outline_for(k, final),
                       chapter=(k, n_ch, final))
        chapters.append(s)
        summary += f"\nChapter {k}: {s.get('chapter_summary') or s.get('episode_summary') or ''}"
        tail = [f"{ln.get('speaker', '')}: {ln.get('text', '')}" for ln in (s["scenes"][-1].get("lines") or [])][-8:]
        last = (f"[place: {s['scenes'][-1].get('place', '')}] " + " / ".join(tail))    # v89: more of the seam
        words = sum(len(str(ln.get("text", "")).split()) for sc in s["scenes"] for ln in sc.get("lines") or [])
        total += words
        log(f"Chapter {k} written: {len(s['scenes'])} scenes, {words} words (story so far {total} words, "
            f"~{total / wpm:.0f} min)" + (" - the ending" if final else ""))
        if final:
            break
        # (13 Nov 2026: Google's strong models were used up, the weaker ones wrote 550-650 words a chapter -> a 16-minute
        # video) a chapter far too short: the rest of the plan is shared over ONE MORE chapter, so the story still
        # reaches its length by living the planned beats (never by adding new events)
        if (share and k < len(share) and max_ch < n_ch + 2 and total < words_per * 0.72 * k
                and len(share[k]) >= 2 and env("EXTRA_CHAPTER") != "0"):
            h_ = len(share[k]) // 2
            share = share[:k] + [share[k][:h_], share[k][h_:]] + share[k + 1:]
            ends, starts, c_ = [], [], 0
            for s_ in share:
                starts.append(c_)
                c_ += len(s_)
                ends.append(c_)
            max_ch += 1
            n_ch = max_ch
            log(f"  chapter {k} came out short ({words} words) - the rest of the plan now goes over "
                f"{max_ch - k} chapters, so the story still gets its length")
    if not chapters:
        raise RuntimeError("no chapter written")
    story = dict(chapters[0])
    story["scenes"], off, reveal, chars = [], 0, {}, {}
    for s in chapters:
        for c in s.get("characters") or []:
            if isinstance(c, dict) and c.get("name"):
                chars.setdefault(str(c["name"]).split()[0].lower(), c)
        for g, n in (s.get("ghost_reveal") or {}).items():
            try:
                reveal.setdefault(g, int(str(n)[:2].strip() or 0) + off)
            except ValueError:
                pass
        story["scenes"] += s.get("scenes") or []
        off += len(s.get("scenes") or [])
    story["characters"] = list(chars.values())
    story["ghost_reveal"] = reveal
    end = chapters[-1]
    for k in ("ending_line", "next_story", "comment_question", "guess", "mystery_answer", "episode_summary"):
        if end.get(k):
            story[k] = end[k]
    story["summary"] = summary.strip()
    try:
        fix_language(story, lang)
    except Exception as e:
        log("  language check skipped:", str(e)[:120])
    try:
        continuity_bridges(story, lang)
    except Exception as e:
        log("  continuity check skipped:", str(e)[:120])
    try:
        line_flow_check(story, lang)
    except Exception as e:
        log("  line-by-line check skipped:", str(e)[:120])
    if ending == "resolve":
        try:
            ensure_ending(story, lang, cut_short=bool(STATE.pop("ending_cut", False)))
        except Exception as e:
            log("  ending check skipped:", str(e)[:120])
    words = sum(len(str(ln.get("text", "")).split()) for sc in story["scenes"] for ln in sc.get("lines") or [])
    log(f"LONG STORY: {len(chapters)} chapters, {len(story['scenes'])} scenes, {words} words "
        f"(~{words / wpm:.0f} minutes of video)")
    return story


SHORT_LENGTH = ("- LENGTH: a COMPLETE short radio thriller of 5-8 minutes: 10 to 14 scenes, 650-950 spoken words. "
                "3-4 characters, one place, one tight frightening event, a twist and a clear explanation at the end - "
                "short but complete, never rushed.")


class ClassicUnknown(Exception):
    pass


class _Saved(Exception):
    pass


SCRIPTS = {}                 # the next parts of today's series, written today, posted on the next days


def prewrite_parts(story1, lang, theme, history, fmt, total, extra_rules, special):
    """A long story: write ALL its parts now, in one go, so they fit together exactly; parts 2-3 are saved and
    posted on the next days unchanged."""
    out, prev = {}, {"title": story1.get("title"), "summary": story1.get("summary", ""),
                     "part2_plan": story1.get("part2_plan", ""), "characters": story1.get("characters"),
                     "setting": story1.get("setting", "")}
    for p in range(2, total + 1):
        try:
            log(f"Writing part {p} of {total} now (it will be posted on day {p}) ...")
            s = make_story(lang, theme, history, fmt=fmt, part=p, prev=dict(prev), extra_rules=extra_rules,
                           total=total)
            s = edit_story(s, lang, brief=STATE.get("brief", ""), outline=STATE.get("outline", ""))
            s.pop("choice", None)
            s["characters"], s["setting"] = prev["characters"], prev["setting"]
            out[str(p)] = s
            prev["summary"] = s.get("summary") or (prev["summary"] + " " + str(s.get("episode_summary", "")))
            prev["part2_plan"] = s.get("part2_plan", "")
        except Exception as e:
            log(f"  part {p} could not be written now ({str(e)[:120]}) - it will be written on its day")
            break
    return out


def pick_classic_any(history, lang):
    """the next famous-writer story not told yet in this language"""
    used = {h.get("classic_id") for h in history if h.get("lang") == lang}
    left = [c for c in CLASSICS if c[0] not in used] or CLASSICS
    return left[0]


def pick_classic(history, lang):
    """the day's first horror video (1 PM) on every day without Karna Pishachini - a famous writer's story"""
    days = [int(x) for x in re.findall(r"\d", env("CLASSIC_DAYS") or "6")]
    now = dt.datetime.now(extras.IST)
    if now.weekday() not in days or env("CLASSICS") == "0":
        return None
    today = now.date().isoformat()
    for h in history[-6:]:
        try:
            if h.get("special") == "classic" and \
                    dt.datetime.fromisoformat(h["date"]).astimezone(extras.IST).date().isoformat() == today:
                return None
        except Exception:
            pass
    used = {h.get("classic_id") for h in history if h.get("lang") == lang}
    left = [c for c in CLASSICS if c[0] not in used] or CLASSICS
    return left[0]


def bn_of(name):
    """Bengali 'of': ঠাকুর -> ঠাকুরের, পো -> পো-র, সাকি -> সাকির"""
    last = name.strip()[-1:]
    if last in "ািীুূেৈোৌ":
        return name + "র"
    if "\u0995" <= last <= "\u09b9" or last in "ড়ঢ়য়":
        return name + "ের"
    return name + "-এর"


def classic_rule(c, lang):
    k = 0 if lang == "bn" else 1
    writer, book, title = c[1][k], c[2][k], c[3][k]
    world = len(c) > 5 and c[5]
    if lang == "bn" and world:
        intro = f"'আজকের গল্প বিশ্ববিখ্যাত লেখক {bn_of(writer)} বিখ্যাত গল্প অবলম্বনে - \"{title}\"।'"
    elif lang == "bn":
        intro = (f"'আজকের গল্প {bn_of(writer)} লেখা " + (f"\"{book}\" বইয়ের " if book else "") + f"গল্প \"{title}\"।'")
    elif world:
        intro = f"'आज की कहानी विश्व-प्रसिद्ध लेखक {writer} की मशहूर कहानी पर आधारित है - \"{title}\"।'"
    else:
        intro = (f"'आज की कहानी {writer} की लिखी " + (f"\"{book}\" से " if book else "") + f"कहानी \"{title}\" है।'")
    return CLASSIC_RULE.format(en=c[4], lang=LANGS[lang]["name"], intro=intro)


CHAPTER_CRAFT = """
CHAPTER CRAFT (you write ONE CHAPTER of a longer story - NOT a whole story):
- Tell ONLY this chapter's beats, in order, fully lived in scenes and dialogue; the story goes on after it.
- Do NOT open with a hook line, a flash-forward or a scene from later; do NOT introduce again the people the
  listeners already know; do NOT sum up or end the story - unless the rules below say this is the first / last
  chapter.
- SHOW, don't tell; every scene has concrete detail of sight, sound, smell, touch; each person keeps their own
  way of talking; real, natural dialogue.
- Scenes flow into each other like a film, time only moves forward, details stay consistent.
"""


def chapter_prompt(prompt, extra_rules):
    """The main story prompt is written for a WHOLE story (a hook first, a full plot, a satisfying ending). For a
    chapter of a long story that made each chapter a little story of its own - it 'ended', and the next chapter
    began again with a hook and an introduction. So for chapters those parts are replaced."""
    mt = re.search(r"LONG STORY - CHAPTER (\d+)", extra_rules or "")
    if not mt:
        return prompt
    k = int(mt.group(1))
    last = "This is the FINAL chapter" in extra_rules or "LAST chapter of THIS PART" in extra_rules
    p = prompt.replace("Write ONE brand-new horror story in", "Write ONE CHAPTER (one part, NOT a whole story) of a "
                       "long brand-new horror story in")
    p = p.replace(extras.STORY_CRAFT, CHAPTER_CRAFT)
    p = p.replace("- Before writing, plan the whole plot (beginning - rising dread - trap - face-to-face - twist), then "
                  "write it\n  scene by scene without shortcuts.", "- Follow the master outline's beats for THIS chapter only.")
    if k > 1:
        p = p.replace(HORROR_HOOK, "")
        p = p.replace("  * the FIRST line is a chilling hook (a strange fact, a warning, or a scream) - no slow introduction;",
                      "  * the FIRST line continues EXACTLY from the previous chapter's last moment - no hook, no new start;")
        p = p.replace("(for scene 1: 'cold open')", "(for scene 1: how it continues from the previous chapter's last moment)")
    if not last:
        p = p.replace("a satisfying ending", "a strong cliffhanger at the end of the chapter")
    return p


def make_story(lang, theme, history, fmt=None, part=0, prev=None, extra_rules="", total=2, length=None, min_w=None):
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
You may use classic Indian folk ghosts (chudail, brahmadaitya, shankchunni - spelt শাঁকচুন্নি, nishi, pishach, vetal, daayan...)
but the plot must be your OWN or built on the SOURCE STORY given below (a legend / folk tale / haunted-place
story / public-domain story). Never copy a copyrighted modern book, film or series; no real people's names.
Must be different from these earlier stories: {json.dumps(old_titles, ensure_ascii=False)}

Story rules:
{length or """- LENGTH: a LONG, slow-burning story: 18 to 24 scenes, 8-10 minutes when spoken - at least 1200 spoken words.
  Take time for real life, real conversations and the slow build of dread. Never rush the
  ending; the story must feel complete."""}
- It must be GENUINELY SCARY and impossible to stop listening:
  * the FIRST line is a chilling hook (a strange fact, a warning, or a scream) - no slow introduction;
  * every scene ends with a small cliffhanger, the fear grows scene by scene;
  * use the five senses - but with FRESH details that belong only to THIS place and THIS story (what this very
    room, river, hostel or village really smells, sounds and feels like), never stock phrases;
  * the ghost is shown little by little (a shadow, then a voice, then a face) - the full reveal comes late;
  * 2-3 real jump scares, and a shocking twist ending that makes people comment.
  Keep the narration moving at a natural pace - short punchy sentences in tense moments.
- TERRIFYING but NOT gory: no blood, no violence details, no harm to children, nothing sexual. The fear can be
  very strong: the ghost's horrifying look described slowly (hollow black eyes, a neck turned the wrong way, feet
  turned backward, long wet hair over the face, nails scraping wood), a ghost that is cunning and getting closer
  every scene, someone who vanishes in the night, a death that is only hinted at (found the next morning, eyes
  open, cold as ice), a real threat to the hero until the very last line.
- EXACT, CORRECT WORDS: every word must be a real, correctly spelled word with exactly the right meaning; no
  made-up words, no word-for-word translation from English, no wrong word just because it sounds similar. Use
  strong, vivid, precise words instead of flat words like 'ভয় লাগল' - show the fear through what the person
  DOES and NOTICES (his hand stops on the latch, he counts the steps, he cannot swallow). NO STOCK PHRASES: never
  use these worn-out lines: {', '.join(CLICHES[lang][:14])} - invent a new, exact image for every moment, and never
  use the same image twice in one story. Before
  answering, re-read every line once and correct any wrong or unnatural word.
- 2 to 5 characters plus a narrator. Real dialogue between characters (short, natural lines). Every "speaker"
  is EXACTLY a name from "characters" (in English letters) or "narrator" - every person who speaks must be in
  "characters" with the right gender, so a woman always gets a woman's voice.
- A CLASSIC BENGALI RADIO THRILLER (the quality of the best Sunday-night audio dramas of Kolkata): the story is
  PERFORMED, not read - most of it is living dialogue between the characters (at least 60% of the words), each
  with their own way of speaking (an old aunt, a college boy, a cunning priest...), real arguments, jokes,
  silences and fear in their own words; the narrator only bridges time and place and sets the mood in a few
  calm, grave lines. Rich sound in every scene. A literary, adult, slow-burning story - intelligent and deeply
  unsettling, never childish or cheap.
- THE LISTENER ALWAYS KNOWS WHO IS SPEAKING (it is heard, not seen): each character has his/her own way of
  speaking; when a new person starts to speak, make it clear naturally - they are called by name ('রতনদা, তুমি
  শুনলে?'), or the narrator names them in a short bridge ('সরলা পিসি ফিসফিস করে বললেন...'). Never a line
  where the listener must guess who said it.
- REALISTIC DECISIONS (very important): every person acts like a real person would. When someone decides
  something (to leave, to call the police, to open the door, to tell nobody), the story must FOLLOW IT UP in its
  own scene: either he does it and we see what happens, or we SEE why he could not (the last bus has gone, his
  mother falls ill, the door will not open, he is tricked) - never a decision that is silently forgotten. Every
  surprising event is prepared earlier (no coincidences that solve or create problems).
- INTRODUCE EVERY CHARACTER: the first time anyone appears, the listener hears their NAME and WHO they are
  (relation, job, age) - naturally, in narration or dialogue ('আমার মামা, নীলকণ্ঠ আচার্য...', 'পাশের বাড়ির
  বউ, সরলা...'). Use the names often so the listener always knows who is speaking and who is in the room.
- ONE UNBROKEN STORY LINE (like a well-made film): plan the whole story first as a chain of cause and effect,
  then write it. Every scene happens BECAUSE of the scene before it and leads to the next; every new person,
  place or event is explained; nothing is forgotten (a clue, a promise, a person who left must come back).
  Tell everything in time order.
- A CLEAR BEGINNING, A FULL MIDDLE AND A CLEAR END (never an abrupt start or an abrupt end):
  * BEGINNING (scenes 1-4): the hook line, then WHO the main person is (name, home, family, situation), WHY and
    HOW he/she came to this place, WHERE and WHEN we are, the other people (each introduced), ordinary life -
    and the first small strange sign.
  * MIDDLE (about scenes 5-12): at least THREE separate events, each stronger than the last (a sign, then a
    sighting, then a real attack/loss); the people react, talk, argue, investigate; a clue is found; a false
    lead; a midpoint discovery that changes everything. Never skip from the first sign straight to the end.
  * END (the last 3-4 scenes): the climax (the confrontation / the trap), the twist, then a RESOLUTION scene
    that clearly explains what really happened and why (the listener must understand the whole mystery), what
    became of every main character, and only then the last chilling line. Never end on a sudden cut.
- TRUE TO THE BELIEF: any ghost, spirit, yogini, ritual or custom must be exactly as the tradition and the
  research brief describe it (its form, how it comes, what it can do, its rules). A spirit that in the tradition
  comes only when called or bound must never just appear without that reason.
- Each scene has 4 to 7 lines. The narrator describes; characters speak only their own words
  (no "he said" inside dialogue). Narrator lines 25-50 words, dialogue lines 4-20 words.
- Telling style for this story: {fmt}
{series_rule}{extra_rules}
- Every picture must show exactly what that scene's lines describe.
- THE STORY STARTS AT ITS REAL BEGINNING, told in order like a real storyteller (never a flash-forward, never
  in the middle). The very first line is ONE short chilling narrator hook (max 14 words) that promises the horror
  to come (e.g. 'সেই হোস্টেলের তেরো নম্বর ঘরে যা ঘটেছিল, আজও কেউ মুখে আনে না...'). Then the narrator
  STRICTLY in this order: (1) WHEN it began - 'ঘটনার শুরু হয়েছিল ... মাসের এক শনিবার সকালে।' (a month, a
  day of the week, a time of day); (2) WHO and WHERE FROM - 'রতন নামে একটি ছেলে বাঁকুড়ার ... গ্রামে থাকত।'
  with the family and situation (poor / alone / a new job...); (3) WHY he/she came to this place; (4) HOW - the
  journey and the search (e.g. 'কলকাতায় পড়তে এসে অনেক খুঁজে, অনেক জায়গায় ঘুরে, শেষে সস্তায় একটা পুরোনো
  হোস্টেলে একটা ঘর পেল...'). Only then the first day there, the people he/she meets (each introduced), and the
  first small strange sign. The listener must always know where we are, who is there, how and why.
- PLANT A CLUE: in the first two scenes show one small, innocent-looking thing (an old key, a scratch on the wall,
  a line of a lullaby, a smell) - at the end it turns out to be the key to the whole horror.
- A SOUND THAT STARTS IN THE MIDDLE OF A SCENE (the rain begins, a bell rings, a storm rises, a dog starts to
  howl) is NEVER "ambience" - it is an "sfx" on the exact word that names it, so it is heard exactly when it is
  said, not before and not after. "ambience" is only what is heard from the first to the last line of the scene.
- BACKGROUND SOUND MUST BE EXACT: each scene's "ambience" is ONLY what can really be heard in that exact place at
  that time (indoors at night with rain outside = 'heavy rain heard from inside a closed room'; a village pond at
  dusk = 'frogs and crickets at a village pond'). Never a sound that is not there. Each sfx only for a real event
  in the words.
- SCENES FLOW INTO EACH OTHER like a film: the end of every scene leads straight into the start of the next (the
  same moment continuing, a sound or a question that the next scene picks up, or a clear time/place bridge such
  as 'that night...', 'the next morning at the station...'). Never jump to an unrelated moment; the listener must
  always know where we are, who is there and why. Keep every detail consistent (names, time, place, who knows what).
- SOUND DESIGN like a radio horror drama: for every line think what the listener should HEAR.
  When a line mentions a door, footsteps, knocking, wind, rain, a scream, bells, a phone, breaking glass,
  put that exact sound in that line's "sfx" with the right timing. 0-3 sfx per line, only real story events.
  SOUND MUST BE IN SYNC: if the words of the line name the sound ("দরজায় টোকা", "নূপুরের শব্দ", "চিৎকার"), give
  that exact word in "word" so the sound plays at that very moment - never a sound before or after the words
  that describe it. A sound the character REACTS to ("কে ওখানে?") comes "before" the line.
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
{extras.STORY_CRAFT}{HORROR_HOOK}{extras.HORROR_DREAD}{extras.WRITING_RULES.get(lang, "")}{extras.VOICE_ACTING}

Return ONLY JSON with exactly these keys:
{{
 "title": "chilling {L['name']} title, max 60 characters, 1 emoji",
 "tagline": "{L['name']} tag line for the thumbnail and Reel, max 8 words: a chilling promise or question under the title (e.g. 'সেই রাতে দরজা খুলেছিল কে?')",
 "title_b": "a SECOND, different {L['name']} title for the same story (another hook, e.g. a question), max 60 characters, 1 emoji - used if the first title gets few clicks",
 "thumbnail_text": "2-4 BIG {L['name']} words that create an unbearable curiosity gap or warning (e.g. 'রাত ১২টায় দরজা খুলো না!', 'ও এখনো ফেরেনি...', 'কে ডাকছে?') - never just the title",
 "description": "3-4 line suspenseful {L['name']} description that makes people want to watch, ending with a question",
 "hashtags": ["10-14 popular hashtags mixing {L['name']} and English, e.g. #HorrorStory #BhootKiKahani"],
 "setting": "ENGLISH: the ONE main place of the story (architecture, objects, era, weather, time of night, colors). Reused in every picture",
 "characters": [{{"name": "name in English letters", "gender": "male or female",
                  "age": "child, young, adult or old", "kind": "human or ghost",
                  "look": "ENGLISH, very specific never-changing look: age, face, hair, skin, clothes with exact colors, one special detail. 20-35 words",
                  "name_local": "the name exactly as spoken in the {L['name']} story",
                  "intro": "{L['name']}: ONE short narrator sentence that introduces this person when they first enter the story - name, who they are (relation / job / age) and one telling detail, e.g. 'পাশের বাড়ির সরলা পিসি - বিধবা, একা থাকেন, পাড়ার সব খবর তাঁর কাছে।' For a ghost: only how people first meet it (e.g. 'a woman in a white saree at the ghat'), never revealing early that it is a ghost",
                  "intro_en": "the same intro in English"}}],
 "episode_name": "2-3 word {L['name']} episode name for the thumbnail, eerie and exact (e.g. 'নিশির ডাক', 'পোড়ো বাড়ির ছায়া')",
 "thumbnail_image": {{"hero": "the main human character's name (big in the foreground)", "hero_action": "ENGLISH: pose, what the hands hold (lantern, torch) and the tense face at the scariest moment, e.g. 'holding a brass lantern, looking up toward the window with tense, focused fear'", "second": "the ghost's name", "ghost": "ENGLISH: exactly how THIS story's ghost looks at its scariest (face, eyes, hair, clothes, skin, special detail like backward feet or red saree) - 25-40 words", "second_action": "ENGLISH: where the ghost is and what it does, e.g. 'standing in the upstairs window behind him, staring down'", "place": "ENGLISH: the exact haunted place with rich authentic Bengal details", "moment": "ENGLISH: one sentence - the visual story of the thumbnail"}},
 "plot_outline": ["ENGLISH: one sentence per scene, in order - the whole cause-and-effect chain, written BEFORE the scenes and followed exactly"],
 "scenes": [{{
    "follows_from": "ENGLISH: one sentence - how this scene follows from the previous scene (for scene 1: 'cold open')",
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
                          "word": "the EXACT word of this line's text (copied letter by letter) at which the sound is heard, e.g. for 'হঠাৎ দরজায় তিনবার টোকা পড়ল' the word is 'টোকা' - the sound plays exactly on that word; '' if the sound is not mentioned in the words",
                          "when": "only when word is '': before (sound first, then the line), during, or after (line first, then the sound)"}}],
                "jump_scare": false,
                "ghost_laugh": "",
                "image": {{"prompt": "ENGLISH picture prompt for THIS line, 30-50 words, like a horror film still: WHO/WHAT is in frame and their exact action, pose and facial expression matching the words of this line, WHERE (which part of the setting), camera (extreme close-up / close-up / wide / over-the-shoulder / low angle), light source (lantern, moonlight, lightning), key objects. Only things that can be SEEN. Every line gets a different picture that matches its words exactly",
                           "people": [{{"name": "a character name exactly as in characters", "pose": "lying / sitting / standing / crouching / hiding / running / frozen / floating ...", "doing": "exactly what the body and HANDS do, e.g. 'gripping the lantern with both hands'", "where": "left / middle / right of the frame, and on or near what (in the doorway, under the bed, behind the tree)", "feeling": "facial expression and emotion, e.g. 'wide eyes, frozen in terror'"}}],
                           "characters": ["names VISIBLE in this picture, in order from LEFT to RIGHT; [] if only a place or object is shown"]}}}}]
 }}],
 "ending_line": "one short {L['name']} line from the narrator that leaves a chill",
 "comment_question": "one short {L['name']} question to viewers that makes them comment (e.g. 'आप होते तो क्या करते?'), with 1 emoji",
 "mystery_answer": "only for a which-suspect mystery: the right number (1, 2 or 3) as asked in the story; otherwise 0",
 "teaser_scene": "number: the scene (1 = first) where the most gripping 50 seconds START - used for the Reel/Short teaser",
 "ghost_reveal": {{"<each ghost's name>": "number: the scene (1 = first) where the LISTENERS first realise this character is a ghost (before that it speaks like a normal person)"}},
 "guess": {{"question": "{L['name']}: ONE short question for the viewers at the middle of the story about what is really going on / who is behind it / what happens next (max 14 words)", "options": ["3 short {L['name']} answers (2-6 words), only one right"], "answer": "1, 2 or 3: the right option (revealed by the ending)"}},
 "next_story": {{"title": "{L['name']} title of a DIFFERENT, brand-new horror story for tomorrow (max 40 characters)", "hook": "ONE chilling {L['name']} sentence that makes people wait for it (max 18 words)", "idea": "ENGLISH, 2-3 sentences: its premise, place and the central horror (it will be written tomorrow exactly from this)"}}
}}
Every scene object also has "chapter": "2-4 word {L['name']} chapter name for YouTube chapters".
"""
    prompt = chapter_prompt(prompt, extra_rules)      # a chapter of a long story is NOT a whole story
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0, "responseMimeType": "application/json",
                                 "maxOutputTokens": 60000}}
    last_err = None
    best, min_words = None, min_w or int(env("MIN_WORDS") or 950)       # ~950+ spoken words = 8+ minutes
    models = gemini_models(key)
    waits = [0, 90, 180, 300, 300, 420]           # Google's servers are sometimes busy for a while: be patient
    for round_no, wait in enumerate(waits):
        if min_w and best and round_no >= 1 and best[0] >= min_words * 0.6:
            log(f"  keeping the longest version ({best[0]} words) - no more rewriting (saves the Gemini limit)")
            return best[1]
        if wait and round_no <= 2:                # Gemini busy: try the backup writer before waiting
            try:
                text = extras.freemodel_text(body["contents"][0]["parts"][0]["text"])
                if text:
                    story = extras.load_json_loose(text)
                    if story.get("unknown"):
                        raise ClassicUnknown()
                    assert story.get("title") and len(story.get("scenes", [])) >= 6
                    assert all(s.get("lines") for s in story["scenes"])
                    words = sum(len(str(ln.get("text", "")).split()) for sc in story["scenes"] for ln in sc["lines"])
                    log(f"  backup story: {len(story['scenes'])} scenes, {words} spoken words")
                    if words >= min_words * 0.8:
                        return story
                    if not best or words > best[0]:
                        best = (words, story)
            except ClassicUnknown:
                raise
            except Exception as e:
                log("  backup writer failed:", (str(e) or type(e).__name__)[:150])
        if models and all(x in TEXT_DAY_OUT for x in models):
            log("  every Gemini writing model has used today's free limit - no point waiting")
            break
        if wait:
            log(f"All Gemini models busy - waiting {wait} s (round {round_no + 1}/{len(waits)})")
            time.sleep(wait)
        for model in list(models):
            if model in TEXT_DAY_OUT:
                continue                              # its free limit is over for today
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
                story = extras.load_json_loose(text)     # small JSON mistakes are repaired, not thrown away
                if story.get("unknown"):
                    raise ClassicUnknown()
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
            except ClassicUnknown:
                raise
            except LookupError as e:
                last_err = e
                models.remove(model)
            except Exception as e:
                last_err = e
                log("  trying next model:", (str(e) or type(e).__name__)[:200])
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
                                 "gender": "female" if is_woman(c) else "male",
                                 "age": str(c.get("age", "adult")).lower(),
                                 "kind": str(c.get("kind", "human")).lower()}
        self.ref = None

    def find(self, name):
        k = ascii_text(name).lower()
        if not k:
            return None
        if k in self.chars:
            return self.chars[k]
        # whole words only: "Ma" must not find "Kumar", "Ram" must not find "Ramola"
        w = lambda a, b: re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", b)
        return next((v for kk, v in self.chars.items() if w(k, kk) or w(kk, k)), None)

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
    """The one Cloudflare account (CF_ACCOUNT_ID / CF_API_TOKEN) - one free account, no extra accounts."""
    out = []
    for suf in ("",):
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
            extras.note("ছবির ফ্রি সীমা শেষ হওয়ায় কিছু ছবি backup দিয়ে হয়েছে")
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


def key_line(grp):
    """of the lines that share one picture: the one most worth showing (the scare, a described action, else the
    first) - so the picture matches what the listener hears most"""
    for ln in grp:
        if ln.get("jump_scare"):
            return ln
    pics = [ln for ln in grp if isinstance(ln.get("image"), dict) and (ln["image"].get("people") or ln["image"].get("prompt"))]
    nar = [ln for ln in pics if str(ln.get("speaker", "")).lower().startswith("narrat")]
    if nar:
        return max(nar, key=lambda ln: len(str(ln.get("en") or ln.get("text", ""))))
    return pics[0] if pics else grp[0]


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
        # Gemini voices: never the same voice for two characters. Our recurring heroes ALWAYS keep their own
        # voice, in every episode (the listeners know them by their voice)
        self.gemini_map, taken = {}, {NARRATOR_GEMINI[0]}
        for c in cast.chars.values():
            fv = SERIES_VOICES.get(c["name"].lower().strip())
            if fv and (fv in GEMINI_ALL["female"]) != c["gender"].startswith("f"):
                fv = None                             # a fixed voice never gives a woman a man's voice (or back)
            if fv and fv not in taken:
                self.gemini_map[c["name"].lower()] = fv
                taken.add(fv)
        for c in cast.chars.values():
            if c["name"].lower() in self.gemini_map:
                continue
            g = "female" if c["gender"].startswith("f") else "male"
            ag = age_group(c["age"])
            if c["kind"].startswith("ghost"):
                pool = GHOST_POOL[ghost_kind(g, ag)]
            else:
                pool = GEMINI_POOL[(g, ag)] + [v for k, vs in GEMINI_POOL.items() if k[0] == g for v in vs]
            pool = pool + GEMINI_ALL[g]                  # if the pool is used up: any other voice of that gender
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
    ("male", "old"): ["Rasalgethi", "Sadaltager", "Algenib"],
    ("female", "child"): ["Leda", "Laomedeia"], ("female", "young"): ["Zephyr", "Aoede", "Despina"],
    ("female", "adult"): ["Kore", "Callirrhoe", "Erinome", "Sulafat"],
    ("female", "old"): ["Gacrux", "Pulcherrima", "Autonoe"],
}
GEMINI_VOICES = {k: v[0] for k, v in GEMINI_POOL.items()}
# the fixed voices of our series characters (the same in every episode; never the storyteller's voice)
SERIES_VOICES = {"bhairab thakur": "Rasalgethi", "bhairab": "Rasalgethi", "paltu": "Fenrir",
                 "taranath": "Sadaltager", "kishori": "Zubenelgenubi", "nilkantha": "Charon", "bapi": "Sadachbia",
                 "madhusundari": "Vindemiatrix", "sadhu": "Algieba", "matu pagli": "Gacrux",
                 "karna pishachini": "Achernar", "the karna pishachini": "Achernar", "pishachini": "Achernar"}
GEMINI_ALL = {"male": ["Orus", "Iapetus", "Alnilam", "Schedar", "Umbriel", "Fenrir", "Zubenelgenubi", "Sadachbia",
                       "Rasalgethi", "Sadaltager", "Puck", "Achird", "Charon", "Algieba", "Enceladus", "Algenib"],
              "female": ["Kore", "Callirrhoe", "Erinome", "Sulafat", "Zephyr", "Aoede", "Despina", "Gacrux",
                         "Pulcherrima", "Autonoe", "Leda", "Laomedeia", "Vindemiatrix", "Achernar"]}
GHOST_POOL = {"female": ["Vindemiatrix", "Achernar"], "old_female": ["Gacrux", "Pulcherrima"],
              "male": ["Enceladus", "Algieba"], "child": ["Laomedeia", "Leda"]}
GHOST_WORDS = {
    "female": "a terrifying FEMALE ghost (a chudail / shankchunni): a cold, shrill, breathy woman's voice that wavers "
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
NARRATOR_GEMINI = ((os.environ.get("NARRATOR_VOICE") or "Algenib").strip(),
                   "the storyteller: a deep, heavy, grave, low male voice with a little gravel - a man in his fifties "
                   "quietly telling a true incident late at night. Natural, conversational speech, steady and a "
                   "little slow, every word clear. NOT theatrical, NOT sing-song, NOT like jatra or stage drama: no "
                   "musical rise and fall, no exaggerated stress, no singing tone")
GHOST_GEMINI = ("Enceladus", "a ghost: a hollow, breathy, cold, slow, otherworldly whispering voice")


def gemini_persona(voices, speaker, revealed=True):
    """(voice, who) for a speaker. A woman ALWAYS gets a woman's voice - checked here once more at the very end."""
    v, who = _gemini_persona(voices, speaker, revealed)
    s = ascii_text(speaker).lower()
    c = voices.cast.find(s) if s and not s.startswith("narrat") else None
    woman = (c is not None and c["gender"].startswith("f")) or (
        c is None and str(speaker or "").strip() and not s.startswith("narrat") and is_woman({"name": str(speaker)}))
    if woman and v not in GEMINI_ALL["female"]:
        ghost = c is not None and c["kind"].startswith("ghost")
        pool = (GHOST_POOL["female"] if ghost else []) + GEMINI_ALL["female"]
        used = set(getattr(voices, "gemini_map", {}).values())
        v = next((x for x in pool if x not in used), pool[0])
        if c is not None:
            voices.gemini_map[c["name"].lower()] = v
        nm = c["name"] if c is not None else str(speaker)
        who = f"{AGE_WORDS[age_group(c['age']) if c is not None else 'adult']} (woman named {nm}), a real person, natural and believable"
        log(f"    voice check: {nm} is a woman - given the woman's voice {v}")
    return v, who


def female_feel(feel):
    """A woman's line never carries a man's direction ('deep, growling, hollow male voice' made a female spirit
    sound like a man): those words are taken out and 'a woman's voice' is said clearly."""
    f = re.sub(r"(?i)\b(?:deep|deeper|growl\w*|baritone|bass|booming|hollow|gravel\w*|husky|male|man's|masculine|"
               r"like a man|low-pitched|low pitched)\b", "", str(feel or ""))
    f = re.sub(r"\s*,\s*(?:,\s*)+", ", ", f).strip(" ,;")
    return (f + ", " if f else "") + "clearly a WOMAN'S voice (female)"


def _gemini_persona(voices, speaker, revealed=True):
    s = ascii_text(speaker).lower()
    c = voices.cast.find(s) if s and not s.startswith("narrat") else None
    if not c:
        return NARRATOR_GEMINI
    if c["kind"].startswith("ghost"):
        g = "female" if c["gender"].startswith("f") else "male"
        ag = age_group(c["age"])
        gk = ghost_kind(g, ag)
        voice = voices.gemini_map.get(c["name"].lower(), GHOST_POOL[gk][0])
        who = f"{AGE_WORDS[ag]} ({'woman' if g == 'female' else 'man'} named {c['name']})"
        if not revealed:                       # nobody knows yet: a completely normal, real person
            return voice, f"{who}, a real person, natural and believable"
        return voice, (f"{who} - the listeners now know this is a ghost: the same natural human voice (never "
                       "robotic, no hissing, no growling), a little lower, slower, heavier and cold, very calm")
    g = "female" if c["gender"].startswith("f") else "male"
    ag = age_group(c["age"])
    voice = voices.gemini_map.get(c["name"].lower(), GEMINI_VOICES[(g, ag)])
    return voice, f"{AGE_WORDS[ag]} ({'woman' if g == 'female' else 'man'} named {c['name']}), a real person, natural and believable"


def gemini_keys():
    """The one free voice key (GEMINI_TTS_KEY)."""
    return [k for k in (env("GEMINI_TTS_KEY"),) if k]


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
    if voice in GEMINI_ALL["female"]:
        how, delivery = female_feel(f"{how}, {delivery}" if delivery else how), ""
    style = f"Character: {who}. Emotion: {how}. " + (f"Delivery: {delivery}. " if delivery else "") + extras.PRONOUNCE[lang]
    return extras.tts_gemini(text, voice, style, LANGS[lang]["name"], out_wav, SR)


def parler_persona(voices, speaker, lang):
    s = ascii_text(speaker).lower()
    c = voices.cast.find(s) if s and not s.startswith("narrat") else None
    if not c:   # storyteller: deep, steady male voice
        return (extras.PARLER_SPK.get(lang, extras.PARLER_SPK["bn"])["male"][0], "a deep, low-pitched", "moderate")
    return voices.parler_map.get(c["name"].lower(), ("Arjun", "a moderate-pitched", "moderate"))


def prepare_free_voices(todo, voices, lang, max_minutes=None, keep=False):
    """Whole story with the free voice model (runs on GitHub, no daily limit). All lines or none."""
    global GEMINI_READY
    if MOCK:
        return False
    if not (extras.parler_ok() and extras.ensure_parler()):
        if keep:
            log("  free voice model not available - the last lines get the plain Google backup voice")
            return False
        return no_voice()
    max_minutes = min(max_minutes or int(env("FREE_VOICE_MINUTES") or 200), max(10, job_minutes_left() - 75))
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
    if keep and env("ALLOW_MICROSOFT") != "1":
        # some lines are still without a good voice: rather post on time with the plain backup voice for those.
        # A character the free model did not finish gets the plain voice for ALL its lines (no change mid-story).
        spk = lambda ln: str(ln.get("speaker", "narrator")).lower()
        unfinished = {spk(ln) for (i, j, ln) in todo if (i, j) not in GEMINI_CACHE}
        for (i, j, ln) in todo:
            if spk(ln) in unfinished:
                GEMINI_CACHE.pop((i, j), None)
        log(f"  {', '.join(sorted(unfinished))}: the plain Google backup voice for all their lines (no Microsoft)")
        return False
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


class NoGoodVoice(Exception):
    """A teaser / the Amavasya special could not get a good voice for every character: it is skipped - a horror
    story is never told in the robotic free voice."""


VOICE_CONTEXT = ["main"]      # "main" (the 2 PM / 8 PM story), "teaser" or "amavasya"
HIDDEN_PICS = []              # pictures of this story with its ghost hidden in them (weekly 'spot the ghost')
NOON_NEED = [0]               # Gemini voice requests today's 2 PM story will need (known once it is written)
VOICE_SAMPLES = os.path.join(HERE, "assets", "voice_samples")    # v72: a few raw Gemini recordings + their text


def estimate_requests(story):
    """About how many Gemini voice requests a written story needs: one character per request, up to 16 lines /
    1900 letters each (+1 for the opening and ending lines)."""
    per = {}
    for sc in story.get("scenes") or []:
        for ln in sc.get("lines") or []:
            s = str(ln.get("speaker", "narrator")).lower()
            s = "narrator" if s.startswith("narrat") else s
            c, n = per.get(s, (0, 0))
            per[s] = (c + len(extras.strip_tags(str(ln.get("text", "")))), n + 1)
    return sum(max(-(-c // 1700), -(-n // 9), 1) for c, n in per.values()) + 3    # (+ lines asked again)


THEME_PL_EN = {"gram": "Village Ghost Stories", "shohor": "City Horror Stories", "jayga": "Haunted Places",
               "sotti": "Horror Experiences", "classic": "Classic Horror Stories"}


def theme_playlist(lang, cat, special, festival, true_story):
    """YouTube: stories grouped by theme, so people play one after another (a binge, not one video)."""
    if true_story:
        return ("আপনাদের পাঠানো সত্য ঘটনা | True Stories from Viewers" if lang == "bn"
                else "आपकी भेजी सच्ची घटनाएँ | True Stories from Viewers")
    if special == "amavasya":
        return "অমাবস্যার রাতের গল্প | Amavasya Night Horror" if lang == "bn" else "अमावस्या की रात | Amavasya Night Horror"
    if festival:
        return "উৎসবের রাতের ভূতের গল্প | Festival Horror Specials" if lang == "bn" else "त्योहार स्पेशल | Festival Horror"
    if special in SERIES_IDS or cat not in THEME_PL_EN:
        return ""                                     # (these series already have their own playlist)
    name = HORROR_CATS.get(cat, {}).get(lang, "")
    return f"{name} | {THEME_PL_EN[cat]}" if name else ""


def voice_reserve():
    """Gemini's free day starts again at about 1:30 PM. The MAIN stories come first: a teaser or the Amavasya
    special may only use what is left after the share kept for the next 2 PM story (the rest of a teaser /
    special then gets the Chirp voice) - so the 2 PM story is not late every day."""
    ctx = VOICE_CONTEXT[0]
    if ctx not in ("teaser", "amavasya"):
        # THE 8 PM STORY (10 Nov 2026): Gemini's day runs from 1:30 PM to 1:30 PM - the same day must still voice
        # tomorrow morning's teasers and tomorrow's 2 PM story (made in the morning, before the next reset). So the
        # night story keeps an explicit share for them instead of a guess.
        try:
            night = (ctx == "main" and STATE.get("slot_hour") == EVENING and env("MODE") != "amavasya"
                     and extras.seconds_until_reset() > 12 * 3600)
        except Exception:
            night = False
        if night:
            try:
                return max(0, int(env("TTS_KEEP_FOR_NOON") or 19))
            except ValueError:
                return 18
        return 0
    if env("TTS_RESERVE"):
        try:
            return int(env("TTS_RESERVE"))
        except ValueError:
            pass
    if ctx == "teaser" and NOON_NEED[0]:
        return NOON_NEED[0] + 1
    return 18                                         # the next 2 PM story (~14) + its morning teasers


def split_sentences(text):
    """'আমি জানি। তুমি যাও!' -> ['আমি জানি।', 'তুমি যাও!'] (very short pieces stay with their neighbour)."""
    parts = [x.strip() for x in re.split(r"(?<=[।!?])\s+(?=\S)", str(text).strip()) if x.strip()]
    out = []
    for x in parts:
        if out and (len(extras.strip_tags(x)) < 8 or len(extras.strip_tags(out[-1])) < 8):
            out[-1] = out[-1] + " " + x
        else:
            out.append(x)
    return out or [str(text)]


def sentence_items(items):
    """EVERY SENTENCE IS ITS OWN TURN in a multi-line recording (8 Nov 2026): the pause between two sentences of
    one line was as long as the pause between two lines, so a cut could land between them - the line ended
    half-way and its last sentence was heard in the next scene. Now every long pause in a recording is a real
    turn end; the sentences of a line are joined again afterwards. Returns (turn items, {line out: its turns})."""
    out, parts = [], {}
    for it in items:
        sents = split_sentences(it["text"])
        it["line"] = it["out"]                        # (v69: the batch keeps whole lines; see extras.tts_gemini_batch)
        if len(sents) <= 1:
            out.append(it)
            continue
        subs = []
        for k, s in enumerate(sents):
            sub = dict(it)
            sub.update(text=s, plain=extras.strip_tags(s), out=f"{it['out']}.s{k}.wav", line=it["out"])
            subs.append(sub)
        parts[it["out"]] = subs
        out += subs
    return out, parts


def join_sentences(parts, gap=0.22):
    """The sentences of a line back into the line's own voice file (a short natural breath between them)."""
    np = _np()
    for line_out, subs in parts.items():
        if os.path.exists(line_out) and os.path.getsize(line_out) > 2000:
            continue
        if not all(os.path.exists(s["out"]) and os.path.getsize(s["out"]) > 2000 for s in subs):
            continue
        try:
            waves = [read_wav(s["out"]) for s in subs]
            pause = np.zeros(int(SR * gap), dtype=waves[0].dtype)
            whole = waves[0]
            for w in waves[1:]:
                whole = np.concatenate([whole, pause, w])
            write_wav(line_out, whole)
        except Exception as e:
            log("    a line could not be joined:", str(e)[:100])
        for s in subs:
            if os.path.exists(s["out"]):
                os.remove(s["out"])


def prepare_gemini_voices(scenes, voices, lang, max_minutes=45):
    """Voice the WHOLE story with Gemini before the video is made. If Gemini cannot finish every line
    (time or daily limit), the lines it made are kept and only the rest get a backup voice."""
    global GEMINI_READY
    if MOCK:
        return False
    todo = [(i, j, ln) for i, s in enumerate(scenes) for j, ln in enumerate(s.get("lines") or [])
            if str(ln.get("text", "")).strip()]
    if not extras.tts_keys() or env("USE_GEMINI_VOICE") == "0":
        extras.TTS_STATE["off"] = True
        return prepare_free_voices(todo, voices, lang)
    # ONE VOICE PER CHARACTER, ALWAYS: the voices are made character by character (the storyteller first, then
    # the people with the most lines). If Gemini's free limit ends part-way, every character it finished keeps
    # the Gemini voice for the WHOLE story and the remaining characters get the backup voice for ALL their lines -
    # a person's voice never changes in the middle of the story.
    def _who(ln):
        s = str(ln.get("speaker", "narrator")).lower()
        return "narrator" if s.startswith("narrat") else s
    count = {}
    for (_i, _j, ln) in todo:
        count[_who(ln)] = count.get(_who(ln), 0) + 1
    order = sorted(count, key=lambda s: (s != "narrator", -count[s]))
    todo = sorted(todo, key=lambda t: (order.index(_who(t[2])), t[0], t[1]))
    log(f"Expressive voices for all {len(todo)} lines, character by character: "
        + ", ".join(f"{s} {count[s]}" for s in order))
    items = []
    for (i, j, ln) in todo:
        voice, who = gemini_persona(voices, ln.get("speaker", "narrator"), ln.get("_revealed", True))
        feel = EMOTION_WORDS.get(str(ln.get("emotion", "normal")).lower(), "naturally") + (
            f", {ln.get('delivery')}" if ln.get("delivery") else "")
        if voice in GEMINI_ALL["female"]:
            feel = female_feel(feel)
        items.append({"text": extras.performed(ln), "plain": extras.strip_tags(str(ln["text"])), "voice": voice,
                      "who": who, "feel": feel, "spk": voice, "out": os.path.join(WORK, f"g_{i:02d}_{j:02d}.wav"),
                      "lang": lang})
    try:                                              # who speaks with which voice (to check women / men at a glance)
        vv = {}
        for (_i, _j, ln), it in zip(todo, items):
            vv.setdefault(_who(ln), (it["voice"], "woman" if it["voice"] in GEMINI_ALL["female"] else "man"))
        log("  voices: " + ", ".join(f"{k} = {v} ({g})" for k, (v, g) in vv.items()))
    except Exception:
        pass
    # ONLY GEMINI VOICES IN HORROR (no free / backup voice - it kills the feel). Planned by today's free limit:
    # as many WHOLE characters as fit go now (storyteller first); if some do not fit, the run waits for Google's
    # daily reset (about 1:30 PM India time) when that is near, and voices them then.
    made = lambda it: os.path.exists(it["out"]) and os.path.getsize(it["out"]) > 2000
    pairs_of = lambda chars: [((i, j, ln), it) for (i, j, ln), it in zip(todo, items) if _who(ln) in chars]
    done_chars = set()

    def gemini_round(chars):
        keep = voice_reserve()
        left = max(0, extras.tts_budget_left(TTS_USAGE) - keep)
        if keep:
            log(f"  {keep} voice requests are kept for the next 2 PM story (and its teasers) - this "
                f"{'story' if VOICE_CONTEXT[0] == 'main' else VOICE_CONTEXT[0]} uses only the rest")
        # HOW FULL each request is made (11 Nov 2026). Google gives ~36 free requests a day for two stories and two
        # teasers, and EVERY recording is used now (nothing is thrown away for an uncertain line end - that cost so
        # many requests that whole stories fell back to the Chirp voice). Small recordings are cut apart most surely,
        # so: the SMALLEST size with which the whole cast fits into 4/5 of today's share; the rest is kept for a
        # broken recording and for making doubtful lines again one by one.
        need_of = lambda: {s: len(extras.tts_groups(sentence_items([it for _t, it in pairs_of({s})])[0])) for s in chars}
        for n_, c_ in ((6, 700), (8, 900), (10, 1100), (12, 1300), (16, 1500), (20, 1700), (26, 1900)):
            extras.TTS_PLAN.update(pieces=n_, chars=c_)
            need = need_of()
            if sum(need.values()) <= int(left * 0.8):
                break
        total_need = sum(need.values())
        extras.TTS_SPARE[0] = max(0, left - total_need)
        del extras.SUSPECT[:]
        if VOICE_CONTEXT[0] == "main" and env("VOICE_SAMPLES") != "0":   # a few raw recordings for tuning the cutting
            extras.SAMPLE["dir"] = VOICE_SAMPLES
        log(f"  today's free voice requests left: {left}; the whole cast needs {total_need} "
            f"(up to {extras.TTS_PLAN['pieces']} sentences / {extras.TTS_PLAN['chars']} letters per request)")
        gem = []
        for s in [x for x in order if x in chars]:    # one character after the other (the storyteller first)
            if extras.TTS_USED[0] + need[s] > left:
                continue                              # (a character is only begun when it can also be finished)
            gem.append(s)
            mine = [it for _t, it in pairs_of({s})]
            turns, parts = sentence_items(mine)
            try:
                extras.tts_gemini_batch(turns, LANGS[lang]["name"], SR, max_requests=left)
            except Exception as e:                    # never lose the video over the voices
                log("  expressive voices stopped:", str(e)[:150])
            join_sentences(parts)
            for it in [it for it in mine if not made(it)]:   # a line still open: alone, while the share lasts
                if extras.TTS_USED[0] >= left or not extras.gemini_quota_left():
                    break
                extras.TTS_USED[0] += 1
                extras.tts_gemini(it["text"], it["voice"], f"{it['who']}. {it['feel']}. "
                                  + extras.PRONOUNCE.get(lang, ""), LANGS[lang]["name"], it["out"], SR)
            miss = sum(1 for it in mine if not made(it))
            log(f"  {s}: {len(mine) - miss}/{len(mine)} lines in the Gemini voice ({extras.TTS_USED[0]} of {left} requests used)")
        if len(gem) < len(chars):
            log("  no request left today for: " + ", ".join(s for s in order if s in chars and s not in gem))
        # the requests still left: the most doubtful lines (their length does not fit their words - maybe a sentence
        # of the neighbouring line got into them) are made again ALONE, the worst first. A line alone needs no cutting.
        by_out = {it["out"]: it for _t, it in pairs_of(set(gem))}
        fixed_n, seen_ = 0, set()
        for _dev, ln_ in sorted(extras.SUSPECT, key=lambda z: -z[0]):
            if extras.TTS_USED[0] >= left or not extras.gemini_quota_left() or extras.TTS_STATE["off"]:
                break
            it = by_out.get(ln_)
            if not it or ln_ in seen_:
                continue
            seen_.add(ln_)
            tmp_ = it["out"] + ".alone.wav"
            extras.TTS_USED[0] += 1
            try:
                if extras.tts_gemini(it["text"], it["voice"], f"{it['who']}. {it['feel']}. "
                                     + extras.PRONOUNCE.get(lang, ""), LANGS[lang]["name"], tmp_, SR) \
                        and os.path.exists(tmp_) and os.path.getsize(tmp_) > 2000:
                    os.replace(tmp_, it["out"])
                    fixed_n += 1
            except Exception as e:
                log("  a doubtful line could not be made again:", str(e)[:100])
            finally:
                if os.path.exists(tmp_):
                    os.remove(tmp_)
        log(f"  recordings cut with the machine reading: {extras.CUT_STATS[0]}, by the length of the words only: "
            f"{extras.CUT_STATS[1]}; doubtful lines: {len({l_ for _d, l_ in extras.SUSPECT})}, made again alone: {fixed_n}")
        if extras.SAMPLE.get("dir") and os.path.isdir(VOICE_SAMPLES):
            try:
                push_now([VOICE_SAMPLES], "voice samples for tuning")
            except Exception:
                pass
            extras.SAMPLE["dir"] = None
        try:
            extras.tts_budget_use(TTS_USAGE)
            push_now([TTS_USAGE], "voice limit used today")
        except Exception as e:
            log("  voice usage not saved:", str(e)[:100])
        full = {s for s in gem if all(made(it) for _t, it in pairs_of({s}))}
        for (i, j, ln), it in pairs_of(full):
            GEMINI_CACHE[(i, j)] = it["out"]
        return full

    done_chars |= gemini_round(set(order))
    waiting = [s for s in order if s not in done_chars]
    if waiting:
        wait_s = extras.seconds_until_reset()
        room = job_minutes_left() * 60 - 75 * 60      # time still needed after the voices for the video itself
        if 0 < wait_s <= min(room, float(env("RESET_WAIT_MAX_MIN") or 240) * 60):
            log(f"  {', '.join(waiting)}: no free Gemini voice left today - waiting {wait_s / 60:.0f} min for Google's "
                "daily reset, so EVERY character gets the Gemini voice (the post may be a little late)")
            time.sleep(wait_s + 120)
            extras.DAY_OUT.clear()
            extras.HITS.clear()
            extras.TTS_STATE["off"] = False
            done_chars |= gemini_round(set(waiting))
            waiting = [s for s in order if s not in done_chars]
    extras.TTS_STATE["off"] = True
    log(f"  Gemini voiced {len(done_chars)} characters completely ({', '.join(sorted(done_chars)) or '-'})")
    if waiting and extras.chirp_ok(TTS_USAGE):         # Google's Chirp 3 HD voice of the SAME name (1 line = 1 request)
        used0 = extras.chirp_used(TTS_USAGE)
        for s in [x for x in order if x in waiting]:
            mine = pairs_of({s})
            # (10 Nov 2026) Gemini made nearly all of this character and only 1-2 lines are open: ONLY those lines get
            # the Chirp voice of the same name - before, 20 good Gemini lines were thrown away for one open line
            gap = [x for x in mine if not made(x[1])]
            few = 0 < len(gap) < len(mine) and len(gap) <= max(2, len(mine) // 7)
            part = gap if few else mine
            ok = all(extras.chirp_tts(it["plain"], it["voice"], it["out"], SR, TTS_USAGE, lang) for _t, it in part)
            if ok:                                     # (else the whole character, so one person keeps one voice)
                for (i, j, _ln), it in mine:
                    GEMINI_CACHE[(i, j)] = it["out"]
                done_chars.add(s)
                log(f"  {s}: {'only ' + str(len(part)) + ' of' if few else 'all'} {len(mine)} lines in the Chirp voice "
                    f"({mine[0][1]['voice']})" + (" - the rest is Gemini" if few else ""))
            else:
                for _t, it in mine:
                    if os.path.exists(it["out"]):
                        os.remove(it["out"])
                break                                  # Chirp stopped: the rest is decided below
        waiting = [s for s in order if s not in done_chars]
        spent = extras.chirp_used(TTS_USAGE) - used0
        if spent:
            STATE["chirp_used"] = True                 # (the length is learned from Gemini-only videos)
            extras.note(f"Gemini-র দিনের গলা শেষ হওয়ায় Chirp গলা নিল: {spent} অক্ষর "
                        f"(এই মাসে মোট {extras.chirp_used(TTS_USAGE)} / {env('CHIRP_MONTH_CAP') or 900000})")
            try:
                push_now([TTS_USAGE], "chirp voice used")
            except Exception:
                pass
    if waiting and VOICE_CONTEXT[0] in ("teaser", "amavasya"):
        raise NoGoodVoice(", ".join(waiting))         # never the robotic free voice in a teaser / special
    if waiting:
        rest = [(i, j, ln) for (i, j, ln) in todo if _who(ln) in waiting]
        extras.note(f"Gemini গলা না পাওয়ায় ফ্রি গলা পেয়েছে: {', '.join(waiting)}")
        log(f"  EMERGENCY: {', '.join(waiting)} could not get a Gemini voice today - the free voice for them, so the "
            "video is not lost")
        extras.telegram(f"⚠️ Daily Horror Story: Gemini's free voice limit was not enough today - {', '.join(waiting)} "
                        "got the free voice in this video.")
        prepare_free_voices(rest, voices, lang, keep=True)
    GEMINI_READY = all((i, j) in GEMINI_CACHE for (i, j, _ln) in todo)
    STATE["all_gemini"] = GEMINI_READY and not waiting    # every line in the Gemini voice (the length can be learned)
    return GEMINI_READY


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


GHOST_DEPTH = {"male": 0.93, "female": 0.96, "old_female": 0.95, "child": 0.97}


def ghost_fx(src, out_wav, kind, af="anull"):
    """A revealed ghost: the SAME natural voice (never robotic), only a little deeper and heavier, with the cold
    echo of an empty room. The formants are kept, so it still sounds like a real person."""
    k = GHOST_DEPTH.get(kind, 0.95)
    g = (f"{af},rubberband=pitch={k:.3f}:formant=preserved,"
         "aecho=0.8:0.55:70|160:0.22|0.12,bass=g=3:f=140,lowpass=f=9000,volume=1.05")
    try:
        run(["ffmpeg", "-y", "-i", src, "-af", g, "-ac", "1", "-ar", str(SR), out_wav])
    except RuntimeError:                       # ffmpeg without rubberband: a plain echo only
        run(["ffmpeg", "-y", "-i", src, "-af", f"{af},aecho=0.8:0.55:70|160:0.22|0.12,bass=g=3:f=140",
             "-ac", "1", "-ar", str(SR), out_wav])


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
    if env("ALLOW_MICROSOFT") != "1":
        tries = []                      # Microsoft voices are switched off: straight to the Google backup
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
        # (the Google voice comes at 24000 Hz: first make it 44100 Hz, THEN change its pitch - without this every
        # line came out ~1.8x too high and too fast, like a cartoon child)
        af = f"aresample=44100,asetrate=44100*{f:.3f},aresample=44100,atempo={min(2.0, max(0.5, 1 / f)):.3f}"
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
        # only the exact sound: no single loose words (they bring unrelated sounds), and every recording must
        # really be about this sound (its name / tags contain the important words of what the story says)
        tries = [" ".join(words), " ".join(core)] + pairs + ([g] if g else [])
        adj = {"slow", "fast", "loud", "soft", "quiet", "distant", "heavy", "light", "big", "small", "long", "short",
               "eerie", "creepy", "scary", "dark", "night", "close", "faint", "deep", "low", "high", "sudden"}
        keyw = [w for w in core if len(w) > 2 and w not in adj]

        def stem(w):
            for suf in ("ing", "es", "s", "ed"):
                if w.endswith(suf) and len(w) - len(suf) >= 3:
                    return w[:-len(suf)]
            return w

        def want_of(q):
            return [stem(w) for w in (q.split() if q == g else keyw)]

        def name_hits(x, q):
            nm = str(x.get("name", "")).lower()
            return sum(1 for w in want_of(q) if w in nm)

        def relevant(x, q):
            hay = (str(x.get("name", "")) + " " + " ".join(x.get("tags") or [])).lower()
            want = want_of(q)
            hits = sum(1 for w in want if w in hay)
            # the recording's own NAME must say what it is (tags alone brought 'heavy swallow' for rushing water)
            return name_hits(x, q) >= 1 and hits >= max(1, min(2, len(want)))
        res = []
        for q in dict.fromkeys(t for t in tries if t):
            r = requests.get("https://freesound.org/apiv2/search/", timeout=30, params={
                "query": q, "token": key, "fields": "id,name,tags,duration,previews,avg_rating,num_downloads",
                "filter": f'license:"Creative Commons 0" duration:{dur}', "sort": "score", "page_size": 12})
            res = [x for x in (r.json().get("results", []) if r.ok else []) if relevant(x, q)]
            if res:
                # among the most relevant, prefer well-liked, much-used recordings (better quality)
                res = sorted(res[:6], key=lambda x: (name_hits(x, q), (x.get("avg_rating") or 0) * 10
                                                     + min(x.get("num_downloads") or 0, 5000) / 500), reverse=True)
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


def mark_reveals(story):
    """When do the listeners learn that a character is a ghost? Before that its voice is a plain human voice;
    from then on the same voice, a little deeper, with a cold echo. From the story's "ghost_reveal" (scene number),
    else the ghost's first laugh / jump scare, else its first line."""
    ghosts = [str(c.get("name", "")) for c in story.get("characters", []) if str(c.get("kind", "")).startswith("ghost")]
    given = story.get("ghost_reveal") if isinstance(story.get("ghost_reveal"), dict) else {}
    given = {ascii_text(k).lower(): v for k, v in given.items()}
    scenes = story.get("scenes", [])
    for gname in ghosts:
        key = ascii_text(gname).lower()
        rev = None
        try:
            rev = max(0, int(str(given.get(key, "")).strip()[:2]) - 1)
        except ValueError:
            pass
        if rev is None:
            for i, s in enumerate(scenes):
                if any(ascii_text(str(ln.get("ghost_laugh", ""))).lower() == key or
                       (ln.get("jump_scare") and key in ascii_text(str(ln.get("speaker", ""))).lower())
                       for ln in s.get("lines") or []):
                    rev = i
                    break
        if rev is None:
            rev = 0
        for i, s in enumerate(scenes):
            for ln in s.get("lines") or []:
                if ascii_text(str(ln.get("speaker", ""))).lower() == key:
                    ln["_revealed"] = i >= rev
        log(f"  {gname}: a normal voice until scene {rev + 1}, then the ghost's voice")


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


PLACE_SOUNDS = [   # (words that show where we are, the real background sound of such a place at night)
    (("cremation", "burning ghat", "shoshan", "শ্মশান", "chita"), "river at night with crackling funeral pyre fire"),
    (("ghat", "river", "boat", "ferry", "ঘাট", "নদী"), "river water lapping at a ghat at night"),
    (("rain", "storm", "monsoon", "বৃষ্টি", "ঝড়"), "heavy rain on a tin roof at night"),
    (("railway", "station", "platform", "train", "স্টেশন"), "empty railway platform at night with distant train"),
    (("hospital", "ward", "হাসপাতাল"), "quiet hospital corridor at night with distant beeping"),
    (("metro", "underground"), "empty metro station hum"),
    (("hill", "fog", "pine", "kurseong", "darjeeling", "পাহাড়", "কুয়াশা"), "cold wind in pine trees on a foggy hill"),
    (("forest", "jungle", "জঙ্গল", "বন"), "night forest insects and a distant owl"),
    (("pond", "paddy", "field", "village", "bamboo", "পুকুর", "গ্রাম", "ধানখেত"), "crickets and frogs at a village pond at night"),
    (("hostel", "flat", "apartment", "kolkata", "city", "street", "office", "lane", "শহর", "কলকাতা"),
     "distant city traffic at night with a dog barking far away"),
    (("rajbari", "zamindar", "palace", "mansion", "old house", "haveli", "জমিদার", "রাজবাড়ি"),
     "old empty mansion at night with a clock ticking and wind in the corridors"),
    (("temple", "মন্দির"), "quiet temple courtyard at night with a soft wind"),
]


def authentic_ambience(place, wanted, lines=None):
    """The background must be the REAL sound of this very place: the writer's choice is kept only when it fits the
    place; otherwise (or when missing) the real sound of such a place is used. Never a sound from elsewhere."""
    where = " ".join([str(place or "")] + [str(x.get("en", "")) for x in (lines or [])[:3]]).lower()
    real = [snd for words, snd in PLACE_SOUNDS if any(w in where for w in words)]
    keep = []
    for w in wanted or []:
        wl = str(w).lower()
        if not real or any(set(re.findall(r"[a-z]{4,}", wl)) & set(re.findall(r"[a-z]{4,}", r_)) for r_ in real):
            keep.append(str(w))
    if re.search(r"\b(morning|daytime|day|noon|afternoon|sunlight|sunny|dawn)\b|সকাল|দুপুর", where) and \
            not re.search(r"\b(night|midnight|dark|evening|dusk)\b|রাত|সন্ধ্যা", where):   # a daytime scene
        day = {"crickets and frogs at a village pond at night": "birds, a distant cow and village life in the day",
               "night forest insects and a distant owl": "forest birds and rustling leaves in the day",
               "distant city traffic at night with a dog barking far away": "city traffic and street sounds in the day"}
        real = [day.get(r_, r_.replace(" at night", "")) for r_ in real]
    out = keep[:1] + [r_ for r_ in real if r_ not in keep]
    return out or list(wanted or [])


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


MOOD_MUSIC = {"creepy": "dark ambient horror music loop", "tense": "suspense tension music loop",
              "scare": "horror suspense music", "sad": "sad dark piano ambient", "calm": "calm dark ambient pad music"}


def mood_music(mood, n, rnd):
    """Background score for the scene's mood: a real CC0 recording from freesound (the same one for every scene of
    that mood in a video, like a show's own score). None if none is found - the synthetic drone stays."""
    if env("MOOD_MUSIC") == "0":
        return None
    q = MOOD_MUSIC.get(str(mood).lower(), MOOD_MUSIC["creepy"])
    try:
        p = freesound(q, loop=True)                   # only a real recording - never a synthetic stand-in
        if not p:
            return None
        np = _np()
        a = _decode(p, 120)
        if len(a) < SR * 5:
            return None
        a = np.tile(a, int(np.ceil(n / len(a))) + 1)[:n]
        fade = min(n // 6, int(SR * 1.5))
        a[:fade] *= np.linspace(0, 1, fade)
        a[-fade:] *= np.linspace(1, 0, fade)
        return a * 0.5
    except Exception:
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


def word_time(a, text, word):
    """When (seconds into the spoken line) is this word said? The words are spread over the time the voice
    is really sounding (pauses skipped), so a knock lands exactly on 'knock', not before or after the line."""
    np = _np()
    w = str(word or "").strip(" .,!?।\"'")
    if not w:
        return None
    k = text.find(w)
    if k < 0:                                     # small spelling differences: try the first part of the word
        k = text.find(w[:max(2, len(w) * 2 // 3)])
    if k < 0:
        return None
    frac = k / max(1, len(text))
    hop = int(SR * 0.02)
    m = len(a) // hop
    if m < 3:
        return frac * len(a) / SR
    rms = np.sqrt(np.mean(a[:m * hop].reshape(m, hop) ** 2, axis=1))
    voiced = rms > max(0.02, 0.12 * np.percentile(rms, 95))
    cum = np.cumsum(voiced)
    if cum[-1] == 0:
        return frac * len(a) / SR
    i = int(np.searchsorted(cum, frac * cum[-1]))
    return min(i, m - 1) * hop / SR


SHOW_STING = True
STORY_PART = [1]             # where the story itself starts in the video (after the hook and the title)
STING_AT = [0]               # which part of the video gets the opening sound (the title, after the cold open)
HOOK_TEXT = [""]             # big words on screen in the first seconds (the thumbnail's hook)


def signature_sting():
    """The show's sound signature (always identical): a cold breath, two slow heartbeats, a deep hit."""
    np = _np()
    r = np.random.default_rng(4242)
    n = int(SR * 3.2)
    out = np.zeros(n)
    w = synth("whisper", int(SR * 1.6), r) * np.linspace(0, 1, int(SR * 1.6)) ** 2 * 0.6
    out[:len(w)] += w
    hb = synth("heartbeat", int(SR * 1.2), r) * 0.8
    out[int(SR * 0.9):int(SR * 0.9) + len(hb)] += hb[:n - int(SR * 0.9)]
    hit = synth("scare_hit", int(SR * 1.2), r)
    s = int(SR * 2.0)
    out[s:s + len(hit)] += hit[:n - s]
    return out / (np.abs(out).max() + 1e-9) * 0.85


def make_scene_audio(lines, voices, lang, idx, sounds, mood, out_wav, ambience=None, place=""):
    """Like a radio drama: every line is spoken with its own voice + emotion, and each sound
    effect is placed exactly where the story says it happens (before / during / after the line).
    Ambience (rain, crickets...) and music run underneath and get quieter while people talk.
    Returns (seconds, [(start, dur, speaker_is_narrator, text)])."""
    np = _np()
    rnd = np.random.default_rng(1000 + idx)
    gap, lead, tail = 0.35, 0.5, 1.0
    pieces, subs, cues, silences, t = [], [], [], [], lead
    if idx == STING_AT[0] and SHOW_STING:             # our show's own opening sound - the same every day
        cues.append((0.05, signature_sting(), 0.7, "sting"))
        t += 0.9                                      # the voice comes in over the sound (no silent gap)
    for j, ln in enumerate(lines):
        text = str(ln.get("text", "")).strip()
        if not text:
            continue
        sfx = [x for x in (ln.get("sfx") or []) if isinstance(x, dict) and x.get("sound")]
        # a sound tied to a word of the line plays exactly on that word (in sync with the voice)
        on_word = [x for x in sfx if str(x.get("word", "")).strip() and str(x["word"]).strip(" .,!?।") in text]
        sfx = [x for x in sfx if x not in on_word]
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
            # a real jump scare: a long, held silence (only a slow heartbeat) ... then the sudden hit
            t += 1.4
            silences.append((max(0.0, t - 2.4), t))
            cues.append((t - 1.35, synth("heartbeat", int(SR * 1.3), rnd) * 0.45, 0.8, "heartbeat"))
            cues.append((t, synth("scare_hit", int(SR * 2.5), rnd), 1.0, "scare_hit"))
            t += 0.45
        spec = voices.for_speaker(ln.get("speaker", "narrator"))
        if spec[3] and not ln.get("_revealed", True):  # the ghost is not known yet: a plain human voice
            spec = (spec[0], spec[1], spec[2], False)
        p = os.path.join(WORK, f"v_{idx:02d}_{j:02d}.wav")
        from_gemini = True
        if (idx, j) in GEMINI_CACHE:
            shutil.copy(GEMINI_CACHE[(idx, j)], p)
        elif not gemini_line(extras.performed(ln), gemini_persona(voices, ln.get("speaker", "narrator"),
                                                                 ln.get("_revealed", True)),
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
        if spec[3]:                                   # the revealed ghost: a cold swell just before it speaks
            m = int(SR * 1.2)
            swell = _filt(_noise(m, rnd), "bandpass", [300, 3000]) * np.linspace(0, 1, m) ** 2 * 0.25
            cues.append((max(0.0, t - 1.1), swell, 1.0, "ghost_swell"))
        pieces.append((t, a, bool(spec[3])))
        sp = ascii_text(ln.get("speaker", "")).lower()
        is_nar = (not sp) or sp.startswith("narrat") or voices.cast.find(sp) is None
        subs.append((t, len(a) / SR, is_nar, text))
        if not is_nar:                               # the speaker's name shown in the subtitles
            c_ = voices.cast.find(sp)
            SUB_NAME[text] = NAME_LOCAL.get(c_["name"].lower(), c_["name"]) if c_ else ""
        extras.remember_voice(text, a, SR)
        for x in on_word[:3]:
            wt = word_time(a, text, x.get("word"))
            snd = get_oneshot(x["sound"], rnd, max_sec=6.0)
            if snd is not None and wt is not None:
                cues.append((t + max(0.0, wt - 0.05), snd, 0.75, x["sound"]))
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
    total = math.ceil(total * FPS - 1e-6) / FPS   # a whole number of video frames: picture and sound never drift
    n = int(total * SR)

    # voices: people in the middle; a ghost's voice drifts around the listener's head
    vL, vR = np.zeros(n), np.zeros(n)
    for start, a, is_ghost in pieces:
        if is_ghost and SPATIAL:                      # in front of us, clear - only the cold room around it
            l, r = extras.reverb_stereo(a, a, "room", SR, seed=idx + 7)
        else:
            l, r = a, a
        _place(vL, l, start)
        _place(vR, r, start)

    # background: music + place ambience (from the story) + any old-style tags
    bed = drone(n, rnd, mood)
    music = mood_music(mood, n, rnd)                  # a real (free CC0) score under the scene, by its mood
    if music is not None:
        bed = bed * 0.55 + music * 0.45
    for name in authentic_ambience(place, ambience, lines)[:1]:      # ONE place sound, not a pile of them
        amb = get_ambience(str(name), n, rnd)
        if amb is not None:
            bed += amb * 0.5
    for tag in (sounds or [])[:1]:
        if tag in SOUND_TAGS and tag != "scare_hit":
            bed += synth(tag, n, rnd) * 0.35

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
    talk = np.clip(_filt(talk, "lowpass", 4, 1) * 1.15, 0, 1)    # starts a moment before, ends a moment after
    quiet = np.ones(n)
    for s0, s1 in silences:
        quiet[int(s0 * SR):int(s1 * SR)] = 0.08
    quiet = _filt(quiet, "lowpass", 6, 1)
    # between the lines the place's sound is BIG (rain, wind, the house creaking); while someone speaks it
    # drops well down so every word is clear, and it swells back up as soon as the words end
    # the background is set by the VOICE's loudness (never by chance): while someone speaks it is far below the
    # words (about -24 dB), between the lines it comes up softly, and only the first seconds of a scene let the
    # place be heard clearly (where are we?) - so the conversation is always clear
    vmask = talk > 0.5
    v_rms = float(np.sqrt(np.mean(vL[vmask] ** 2))) if vmask.any() else 0.1
    b_rms = float(np.sqrt(np.mean(np.concatenate([bedL, bedR]) ** 2))) or 1.0
    level = float(env("BG_LEVEL") or 0.30) * v_rms / b_rms
    bedL, bedR = bedL * level, bedR * level
    opening = np.ones(n)
    k0 = min(n, int(SR * 3.0))
    opening[:k0] = np.linspace(1.8, 1.0, k0)
    duck = (1.0 - 0.8 * talk) * quiet * opening
    mixL = vL * 0.95 + bedL * duck + fxL * (1 - 0.45 * talk)
    mixR = vR * 0.95 + bedR * duck + fxR * (1 - 0.45 * talk)
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
    from PIL import features                 # Bengali/Hindi shaping needs Raqm; without it, still never crash
    eng = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    return ImageFont.truetype(FONT, size, layout_engine=eng)


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
    n = max(1, int(round(dur * FPS)))
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


def write_ass(segments, path, family, size=None, fs=(52, 54), margin_v=38, max_len=44):
    """segments: (start, dur, is_narrator, text). Narration white, dialogue yellow with the speaker's name."""
    w_, h_ = size or (W, H)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w_}
PlayResY: {h_}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Nar,{family},{fs[0]},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin_v},1
Style: Talk,{family},{fs[1]},&H0000E6FF,&H0000E6FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = []
    for start, dur, is_nar, text in segments:
        chunks = split_subs(text, max_len)
        who = "" if is_nar else SUB_NAME.get(text, "")
        for c, (s0, s1) in zip(chunks, extras.sub_times(text, dur, chunks)):   # in step with the real voice
            label = ("{\\c&H00FFC060&}" + who + ":{\\c&H0000E6FF&} ") if who else ""
            rows.append(f"Dialogue: 0,{ass_time(start + s0)},{ass_time(start + s1)},"
                        f"{'Nar' if is_nar else 'Talk'},,0,0,0,,{label}{c}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(rows) + "\n")


TIMELINE = ([], [])          # (start second of every part, every spoken line) of the last video
METERS = []                  # v70: the heartbeat films of this video and when each one shows
SUB_NAME, NAME_LOCAL = {}, {}  # line text -> speaker's name for the subtitles; english name -> name in the story
PORTRAIT = [None]            # the 9:16 Facebook version of the video
BADGE_COLORS = ((200, 0, 20), (255, 255, 255))


def hook_png(text, path):
    """the hook in big words at the top for the first seconds - most people watch the feed WITHOUT sound"""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if text:
        d = ImageDraw.Draw(img)
        rows, f, sz = extras._fit_text(d, text, FONT, W - 120, 78, lines_max=2)
        band = int(len(rows) * sz * 1.35 + 40)
        for y in range(band):                         # dark band fading down
            d.line([(0, y), (W, y)], fill=(0, 0, 0, int(190 * (1 - y / band) ** 0.6)))
        y = 20
        for r in rows:
            tw = d.textlength(r, font=f)
            d.text(((W - tw) / 2, y), r, font=f, fill=(255, 225, 0, 255), stroke_width=max(4, sz // 12),
                   stroke_fill=(120, 0, 0, 255))
            y += int(sz * 1.35)
    img.save(path)
    return path


def _clip_job(job):
    return scene_clip(*job)


def render_clips(jobs):
    """All scene pictures moved into film clips - several at once (GitHub's machine has several processor cores):
    about 3x faster than one after the other. If the video is running late, the simpler (faster) motion is used."""
    at = extras.PUBLISH.get("at")
    left = (at - dt.datetime.now(extras.IST)).total_seconds() / 60 if at else 999
    if (left < 25 + len(jobs) * 0.8 or job_minutes_left() < 40 + len(jobs) * 0.6) and env("SIMPLE_MOTION") != "1":
        log(f"  only {left:.0f} minutes left - simpler picture motion today, so the video is on time")
        os.environ["SIMPLE_MOTION"] = "1"
    workers = max(1, min(int(env("CLIP_WORKERS") or 4), os.cpu_count() or 2))
    t0 = time.time()
    if workers > 1 and len(jobs) > 1:
        try:
            import multiprocessing as mp
            from concurrent.futures import ProcessPoolExecutor
            pool = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork"))
            futs = [pool.submit(_clip_job, j) for j in jobs]
            for k, f in enumerate(futs):
                f.result(timeout=900)                 # one clip never takes 15 minutes - if it does, it is stuck
                if (k + 1) % 5 == 0 or k + 1 == len(jobs):
                    log(f"  clips: {k + 1}/{len(jobs)} ({(time.time() - t0) / 60:.1f} min, {workers} at once)")
            pool.shutdown(wait=True)
            return
        except Exception as e:
            log("  parallel clips failed - the rest one by one with simple motion:", str(e)[:150] or type(e).__name__)
            try:
                for pr in list(getattr(pool, "_processes", {}).values()):
                    pr.kill()
                pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            os.environ["SIMPLE_MOTION"] = "1"
    for k, job in enumerate(jobs):
        if not os.path.exists(job[2]) or os.path.getsize(job[2]) < 1000:
            scene_clip(*job)
        log(f"  clip {k + 1}/{len(jobs)}")


def build_video(scene_parts, lang, out):
    """scene_parts: list of dict(image, lines, sounds, mood). Returns mp4 path."""
    global TIMELINE
    clips, segs, t, wavs, part_times, jobs = [], [], 0.0, [], [], []
    voices = scene_parts[0]["voices"]
    prepare_gemini_voices(scene_parts, voices, lang)       # all lines (intro + story + ending) or none
    extras.parler_unload()                           # (frees ~4 GB before the video is put together)
    for i, sp in enumerate(scene_parts):
        log(f"Voices + sound {i + 1}/{len(scene_parts)}" + extras.machine_room())
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
        jobs.append((segments, a, c, i, sp.get("mood", "creepy"), talk))
        segs += [(t + s, du, nar, tx) for s, du, nar, tx in subs]
        clips.append(c)
        t += duration(a)
    render_clips(jobs)
    lst = os.path.join(WORK, "clips.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", os.path.join(WORK, "joined.mp4")])
    alst = os.path.join(WORK, "audio.txt")
    with open(alst, "w") as f:
        f.writelines(f"file '{os.path.basename(a)}'\n" for a in wavs)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", alst, "-c", "pcm_s16le", os.path.join(WORK, "full.wav")])
    extras.normalize_loudness(os.path.join(WORK, "full.wav"))    # as loud as big channels, quiet parts kept
    write_ass(segs, os.path.join(WORK, "subs.ass"), LANGS[lang]["font_family"])
    vf = f"ass=subs.ass:fontsdir={os.path.dirname(FONT)}:shaping=complex,tpad=stop_mode=clone:stop_duration=3"
    total = duration(os.path.join(WORK, "full.wav"))
    TIMELINE = (part_times, segs)
    try:                                   # small "Like - Share - Follow" pill, top right, at the start and the end
        extras.make_badge(FONT, LANGS[lang]["badge"], os.path.join(WORK, "badge.png"), BADGE_COLORS)
        extras.headphone_hint(FONT, LANGS[lang]["hp"], os.path.join(WORK, "hp.png"))
        hook_png(HOOK_TEXT[0], os.path.join(WORK, "hook.png"))
        try:                                         # v70: the heartbeat line (top left), faster in the dark scenes
            METERS[:] = fear_meter(part_times, [sp.get("mood", "creepy") for sp in scene_parts], total)
        except Exception as e:
            METERS[:] = []
            log("  fear meter skipped:", str(e)[:120])
        m_in, m_fc, m_lab = _meter_args(METERS, 5, "h", 24, 20)
        pic = ["-i", "badge.png", "-i", "hp.png", "-i", "hook.png"] + m_in + ["-filter_complex",
               f"[0:v]{vf}[b];[b][2:v]overlay=W-w-24:22:enable='{extras.badge_filter(total)}'[c];"
               f"[c][3:v]overlay=(W-w)/2:H-h-110:enable='between(t,0.5,7)'[d];"
               f"[d][4:v]overlay=0:0:enable='between(t,0,4.5)'[h]" + m_fc, "-map", f"[{m_lab}]"]
    except Exception as e:
        log("  badge skipped:", str(e)[:120])
        pic = ["-vf", vf, "-map", "0:v"]
    r = subprocess.run(["ffmpeg", "-y", "-i", "joined.mp4", "-i", "full.wav"] + pic + ["-map", "1:a",
                        "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast" if total > 900 else "medium",
                        "-crf", "23", "-maxrate", "3500k", "-bufsize", "7000k", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart",
                        os.path.abspath(out)], capture_output=True, text=True, cwd=WORK)
    if r.returncode != 0:
        raise RuntimeError("final render failed:\n" + r.stderr[-2000:])
    PORTRAIT[0] = None
    if env("FB_PORTRAIT") != "0":
        try:
            PORTRAIT[0] = make_portrait(segs, lang, total)
        except Exception as e:
            log("  9:16 version failed - Facebook gets the normal one:", str(e)[:200])
    return out


def next_card(text, bg):
    """16:9 card for the 'next story' preview: the title big on a dark picture"""
    try:
        from PIL import ImageEnhance, ImageFilter
        img = Image.open(bg).convert("RGB").resize((W, H)) if bg and os.path.exists(bg) else Image.new("RGB", (W, H))
        img = ImageEnhance.Brightness(img.filter(ImageFilter.GaussianBlur(6))).enhance(0.3)
        d = ImageDraw.Draw(img)
        mt = re.search(r"['‘’\"]([^'‘’\"]{2,60})['‘’\"]", text)
        head = text.split("...")[0].strip(" .।") + "..."
        lines = [(head, 46, (255, 255, 255)), ((mt.group(1) if mt else ""), 78, (255, 215, 0))]
        y = H // 2 - 110
        for t_, size, col in lines:
            if not t_:
                continue
            rows, f, sz = extras._fit_text(d, extras.no_tofu(t_), FONT, W - 120, size, lines_max=2)
            for r_ in rows:
                tw = d.textlength(r_, font=f)
                d.text(((W - tw) / 2, y), r_, font=f, fill=col, stroke_width=max(3, sz // 14), stroke_fill=(0, 0, 0))
                y += int(sz * 1.3)
            y += 20
        out = os.path.join(WORK, "next_card.jpg")
        img.save(out, quality=92)
        return out
    except Exception as e:
        log("  next-story card skipped:", str(e)[:120])
        return None


def top_png(path, show, title):
    """the show and the story's title at the top of the 9:16 video"""
    VW, VH = 720, 1280
    img = Image.new("RGBA", (VW, 290), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 40
    for text, size, col in ((show, 40, (230, 230, 230, 255)), (title, 54, (255, 215, 0, 255))):
        if not text:
            continue
        rows, f, sz = extras._fit_text(d, extras.no_tofu(text), FONT, VW - 70, size, lines_max=1 if text == show else 2)
        for r_ in rows:
            tw = d.textlength(r_, font=f)
            d.text(((VW - tw) / 2, y), r_, font=f, fill=col, stroke_width=max(3, sz // 14), stroke_fill=(0, 0, 0, 255))
            y += int(sz * 1.3)
        y += 12
    img.save(path)
    return path


# ===================== v70: the fear meter - a heartbeat line that runs faster as the story gets more frightening
METER = {"calm": (72, (90, 235, 130)), "sad": (72, (90, 235, 130)), "creepy": (92, (255, 215, 60)),
         "tense": (116, (255, 140, 40)), "scare": (142, (255, 50, 50)), "scary": (142, (255, 50, 50))}


def _ecg(ph):
    """one heartbeat (ph 0..1): a small wave, the sharp spike, a round wave"""
    g = lambda c, w, a: a * math.exp(-((ph - c) / w) ** 2)
    return g(0.18, 0.035, 0.12) - g(0.335, 0.012, 0.18) + g(0.36, 0.014, 1.0) - g(0.39, 0.014, 0.28) + g(0.6, 0.06, 0.22)


def fear_meter(part_times, moods, total, start=6.0):
    """Small looping heartbeat films (one per mood that occurs) + when each is shown: [(file, enable-expression)].
    The line, the little heart and the number beat faster and turn from green to red as the scenes get darker."""
    if env("FEAR_METER") == "0" or not part_times:
        return []
    mw, mh = 300, 80
    ends = list(part_times[1:]) + [total]
    spans = {}
    for st, en, mood in zip(part_times, ends, moods):
        bpm = METER.get(str(mood).lower(), METER["creepy"])[0]
        st = max(st, start)
        if en - st > 0.5:
            spans.setdefault(bpm, []).append((st, en))
    out = []
    digits = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
    for bpm, sp in sorted(spans.items()):
        col = next(c for b, c in METER.values() if b == bpm)
        beat = 60.0 / bpm
        beats = max(2, round(3.2 / beat))
        frames = max(8, round(beats * beat * FPS))
        d_ = os.path.join(WORK, f"meter_{bpm}")
        os.makedirs(d_, exist_ok=True)
        try:
            f_num = extras._font(FONT, 34)
        except Exception:
            f_num = None
        for k in range(frames):
            now = k / frames * beats                  # in beats
            img = Image.new("RGBA", (mw, mh), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([0, 0, mw - 1, mh - 1], radius=18, fill=(8, 8, 12, 150))
            x0, x1, mid = 70, mw - 78, mh // 2 + 10
            pts = []
            for x in range(x0, x1):                   # the newest moment is at the right end
                ph = (now - (x1 - x) / (x1 - x0) * 2.4) % 1.0
                pts.append((x, mid - _ecg(ph) * 34))
            d.line(pts, fill=col + (255,), width=3, joint="curve")
            d.ellipse([x1 - 4, pts[-1][1] - 4, x1 + 4, pts[-1][1] + 4], fill=(255, 255, 255, 255))
            pulse = 1.0 + 0.28 * max(0.0, _ecg(now % 1.0))            # the heart swells on every beat
            r = 12 * pulse
            cx, cy = 36, mh // 2 - 2
            d.ellipse([cx - r * 1.05, cy - r, cx, cy + r * 0.2], fill=col + (255,))
            d.ellipse([cx, cy - r, cx + r * 1.05, cy + r * 0.2], fill=col + (255,))
            d.polygon([(cx - r * 1.02, cy - r * 0.25), (cx + r * 1.02, cy - r * 0.25), (cx, cy + r * 1.25)],
                      fill=col + (255,))
            if f_num:
                num = str(bpm).translate(digits) if FONT and "Bengali" in os.path.basename(FONT) else str(bpm)
                try:
                    d.text((x1 + 10, mh // 2 - 26), extras.fit_glyphs(num, FONT), font=f_num, fill=(255, 255, 255, 235))
                except Exception:
                    pass
            img.save(os.path.join(d_, f"f_{k:03d}.png"))
        mov = os.path.join(WORK, f"meter_{bpm}.mov")
        run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(d_, "f_%03d.png"),
             "-c:v", "qtrle", "-pix_fmt", "argb", mov])
        shutil.rmtree(d_, ignore_errors=True)
        merged = []
        for st, en in sp:                             # neighbouring scenes of one mood = one stretch
            if merged and st - merged[-1][1] < 0.05:
                merged[-1][1] = en
            else:
                merged.append([st, en])
        out.append((os.path.basename(mov), "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in merged)))
    return out


def _meter_args(meters, first_index, last_label, x, y):
    """ffmpeg inputs + filter steps that lay the heartbeat films over [last_label]; returns (inputs, filter, label)"""
    inp, fc, lab = [], "", last_label
    for k, (mov, when) in enumerate(meters):
        inp += ["-stream_loop", "-1", "-i", mov]
        fc += f";[{lab}][{first_index + k}:v]overlay={x}:{y}:enable='{when}'[mt{k}]"
        lab = f"mt{k}"
    return inp, fc, lab


def make_portrait(segs, lang, total):
    """Facebook: the same film in 9:16 - the picture big in the middle (gently panning, so nothing stays hidden),
    a dark blurred copy behind it, the show + title at the top and big subtitles (with the speaker's name) below."""
    VW, VH, FHh, FY = 720, 1280, 560, 300
    fw = int(FHh * 16 / 9) // 2 * 2
    write_ass(segs, os.path.join(WORK, "subs_v.ass"), LANGS[lang]["font_family"], size=(VW, VH), fs=(44, 46),
              margin_v=150, max_len=30)
    show, title = STATE.get("top_text") or ("", "")
    top_png(os.path.join(WORK, "top_v.png"), show, title)
    fc = (f"[0:v]split[a][b];[a]scale=180:320:force_original_aspect_ratio=increase,crop=180:320,boxblur=8:2,"
          f"scale={VW}:{VH},eq=brightness=-0.28[bg];"
          f"[b]scale={fw}:{FHh},crop={VW}:{FHh}:'({fw}-{VW})/2+({fw}-{VW})*0.45*sin(2*PI*t/18)':0[fg];"
          f"[bg][fg]overlay=0:{FY}[m];[m][2:v]overlay=0:0[t];"
          f"[t]ass=subs_v.ass:fontsdir={os.path.dirname(FONT)}:shaping=complex[s]")
    m_in, m_fc, m_lab = _meter_args(METERS, 3, "s", 20, FY + 14)       # v70: the heartbeat line on the picture
    fc += m_fc + f";[{m_lab}]format=yuv420p[v]"
    out_v = os.path.join(WORK, "facebook_9x16.mp4")
    r = subprocess.run(["ffmpeg", "-y", "-i", "joined.mp4", "-i", "full.wav", "-i", "top_v.png"] + m_in + ["-filter_complex", fc,
                        "-map", "[v]", "-map", "1:a", "-t", f"{total:.2f}", "-r", str(FPS), "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k", "-ac", "2",
                        "-movflags", "+faststart", out_v], capture_output=True, text=True, cwd=WORK)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    log("  Facebook: 9:16 version made")
    return out_v


def portrait_thumb(thumb):
    """9:16 thumbnail: the whole poster in the middle, a blurred copy behind"""
    from PIL import ImageEnhance, ImageFilter
    VW, VH = 1080, 1920
    own = os.path.join(WORK, "thumbnail_portrait.jpg")
    if os.path.exists(own):                          # the poster made for phones (words on top, ghost below)
        return own
    t = Image.open(thumb).convert("RGB")
    s = max(VW / t.width, VH / t.height)
    bg = t.resize((int(t.width * s) + 1, int(t.height * s) + 1))
    bg = bg.crop(((bg.width - VW) // 2, (bg.height - VH) // 2, (bg.width - VW) // 2 + VW, (bg.height - VH) // 2 + VH))
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(30))).enhance(0.6)
    fg = t.resize((VW, VW * t.height // t.width))
    bg.paste(fg, (0, (VH - fg.height) // 2))
    out = os.path.join(WORK, "thumbnail_9x16.jpg")
    bg.save(out, quality=93)
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
    if PORTRAIT[0] and os.path.exists(PORTRAIT[0]):           # 9:16 - fills the whole phone screen
        video = PORTRAIT[0]
        try:
            thumb = portrait_thumb(thumb) if thumb and os.path.exists(thumb) else thumb
        except Exception as e:
            log("  9:16 thumbnail skipped:", str(e)[:120])
    else:
        video, thumb = extras.fb_square(video, thumb, WORK)   # 1:1 ranks better on phones
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


def post_to_youtube(video, thumb, title, description, tags, lang, localizations=None):
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
    if localizations:                                 # the title and summary in English / Hindi too (search reach)
        meta["localizations"] = localizations
    for attempt in range(2):
        parts = "snippet,status" + (",localizations" if meta.get("localizations") else "")
        r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=" + parts,
                          headers={**hdr, "Content-Type": "application/json; charset=UTF-8",
                                   "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
                          data=json.dumps(meta), timeout=60)
        if r.ok or not meta.get("localizations"):
            break
        log("  YouTube did not take the translated titles - uploading without them:", r.text[:150])
        meta.pop("localizations", None)
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
PLANS_FILE = os.path.join(HERE, "assets", "today_scripts.json")    # stories written in the morning
TEASERS_FILE = os.path.join(HERE, "assets", "teasers.json")       # which morning teasers are out


def _jload(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _jsave(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


GIT_ME = ["-c", "user.name=story-bot", "-c", "user.email=story-bot@users.noreply.github.com"]


def _git(*args, timeout=300):
    """git, ALWAYS with the bot's name. 9 Nov 2026: new files had been uploaded to GitHub during the 8 PM run, so
    'git pull --rebase' had to make a new commit - but GitHub's computer has no git name, the save stopped half-way
    ('You are not currently on a branch') and every later save of the night failed: the history entry and the
    series memory (part 2 on Thursday) were lost although the video was posted."""
    return subprocess.run(["git"] + GIT_ME + [str(a) for a in args], cwd=HERE, capture_output=True, text=True,
                          timeout=timeout)


def _git_note(r):
    lines = [x.strip() for x in ((r.stderr or "") + "\n" + (r.stdout or "")).splitlines()
             if x.strip() and not x.startswith(("hint:", " ", "\t"))]
    return (lines[-1] if lines else f"git exit {r.returncode}")[:160]


def _git_branch():
    r = _git("symbolic-ref", "-q", "--short", "HEAD")
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else (env("GITHUB_REF_NAME") or "main")


def git_unstick(keep_files=True):
    """A save that stopped half-way is put right, so the bot is never left 'not on a branch' for the rest of the run.
    keep_files=False: straight after a failed pull (nothing was written since) - it is undone exactly.
    keep_files=True: files may have been written since - every file stays as it is now (the newest), then what
    waited in the stash, then the saves that had not reached GitHub yet. Returns True when something was put right."""
    gd = os.path.join(HERE, ".git")
    rebasing = [d for d in ("rebase-merge", "rebase-apply") if os.path.isdir(os.path.join(gd, d))]
    merging = os.path.exists(os.path.join(gd, "MERGE_HEAD"))
    if not rebasing and not merging and _git("symbolic-ref", "-q", "HEAD").returncode == 0:
        return False
    br = env("GITHUB_REF_NAME") or "main"
    if not keep_files:
        if rebasing and _git("rebase", "--abort").returncode == 0:
            rebasing = []
        if merging and _git("merge", "--abort").returncode == 0:
            merging = False
    if rebasing or merging or _git("symbolic-ref", "-q", "HEAD").returncode != 0:
        oh = ""
        for d in rebasing:
            try:
                with open(os.path.join(gd, d, "orig-head")) as f:
                    oh = f.read().strip() or oh
            except OSError:
                pass
        _git("rebase", "--quit")
        _git("merge", "--quit")
        _git("checkout", "-B", br)
        _git("branch", f"--set-upstream-to=origin/{br}")
        _git("reset", "-q")
        same = lambda f: _git("diff", "--quiet", "HEAD", "--", f).returncode == 0
        for f in _git("diff", "--name-only").stdout.split():
            try:
                with open(os.path.join(HERE, f), encoding="utf-8", errors="ignore") as fh:
                    if any(ln.startswith("<<<<<<< ") for ln in fh):
                        _git("checkout", "--", f)
            except OSError:
                pass
        if _git("rev-parse", "-q", "--verify", "refs/stash").returncode == 0:
            for f in _git("stash", "show", "--name-only", "stash@{0}").stdout.split():
                if same(f):
                    _git("checkout", "stash@{0}", "--", f)
        mb = _git("merge-base", "HEAD", oh).stdout.strip() if oh else ""
        for f in (_git("diff", "--name-only", mb, oh).stdout.split() if mb else []):
            if same(f):
                _git("checkout", oh, "--", f)
            _git("add", "-A", "-f", "--", f)         # these were saved already: they go with this save again
    log("  git: a save that had stopped half-way was put right (nothing lost)")
    return True


def _git_ahead():
    r = _git("rev-list", "--count", f"origin/{_git_branch()}..HEAD")
    return r.returncode == 0 and r.stdout.strip() not in ("", "0")


def git_sync(tries=3):
    """Sends this run's saved commits to GitHub - first taking in whatever else changed there meanwhile (your own
    uploads during the run). Never stops half-way. Returns (ok, reason)."""
    note = ""
    for k in range(tries):
        br = _git_branch()
        try:
            r = _git("pull", "--rebase", "--autostash", "-q", "origin", br)
            if r.returncode != 0:                    # could not put our commits on top: undo, then MERGE instead
                note = _git_note(r)
                git_unstick(keep_files=False)
                r = _git("pull", "--no-rebase", "--no-edit", "--autostash", "-X", "ours", "-q", "origin", br)
                if r.returncode != 0:
                    note = _git_note(r)
                    git_unstick(keep_files=False)
                    time.sleep(5 * (k + 1))
                    continue
            p = _git("push", "-q", "origin", f"HEAD:{br}")
        except subprocess.TimeoutExpired:
            note = "GitHub did not answer in time"
            lock = os.path.join(HERE, ".git", "index.lock")
            if os.path.exists(lock):                 # (left behind by the stopped git)
                os.remove(lock)
            git_unstick(keep_files=False)
            continue
        if p.returncode == 0:
            return True, ""
        note = _git_note(p)
        time.sleep(5 * (k + 1))
    return False, note


def push_now(paths, why):
    """Saves files to GitHub RIGHT AWAY (not only at the end of the run), so the later runs surely find them -
    e.g. this morning's stories for the afternoon and night videos."""
    if MOCK or DRY_RUN or env("GITHUB_ACTIONS") != "true":
        return
    try:
        git_unstick()
        subprocess.run(["git", "add", "-f"] + [p for p in paths if os.path.exists(p)], cwd=HERE, check=True,
                       capture_output=True)
        c = _git("commit", "-q", "-m", why)
        if c.returncode != 0 and not _git_ahead():
            return                                   # nothing new to save
        ok, note = git_sync()
        log("  saved to GitHub:", why if ok else f"NOT yet - {note} (it goes with the next save)")
    except Exception as e:
        log("  could not save to GitHub now:", str(e)[:150])


def load_plan(slot):
    """The story the morning run already wrote for this time slot (and promised in its teaser)."""
    if not slot or env("USE_MORNING_SCRIPT") == "0":
        return None
    p = _jload(PLANS_FILE, {}).get(str(slot))
    return p if isinstance(p, dict) and isinstance(p.get("story"), dict) and p["story"].get("scenes") else None


def save_plan(slot, plan):
    plans = _jload(PLANS_FILE, {})
    today = dt.datetime.now(extras.IST).date()
    keep = {}
    for k, v in plans.items():                       # only today's and yesterday's - the file stays small
        try:
            if (today - dt.date.fromisoformat(k.split("@")[0])).days <= 1:
                keep[k] = v
        except Exception:
            pass
    keep[str(slot)] = plan
    _jsave(PLANS_FILE, keep)


def right_answers(history):
    """Who answered the last video's question right (for the shout-out)."""
    lastp = extras.last_post(history)
    if lastp and not MOCK and not lastp.get("continues", lastp.get("part") == 1) and \
            (lastp.get("mystery_answer") or lastp.get("hidden")):
        try:
            digit = lastp.get("mystery_answer") or lastp.get("hidden")
            names, ids = extras.winners(extras.post_comments(lastp.get("facebook"), lastp.get("youtube")), digit=digit)
            log(f"Right answers to the last video: {len(names)}")
            return names, ids
        except Exception as e:
            log("  right-answer check skipped:", str(e)[:120])
    return [], []


def pick_moments(scenes, story, n=4):
    """The 3-4 most gripping moments for a teaser: from different scenes, never from the ending."""
    ghosts = {str(c.get("name", "")).lower() for c in story.get("characters", [])
              if str(c.get("kind", "")).startswith("ghost")}
    cand = []
    last = max(2, int(len(scenes) * 0.8))
    first = 0 if len(scenes) < 8 else 1               # a short story: any scene may give a teaser moment
    for i in range(first, max(last, min(len(scenes), 3))):
        best, bs = None, -9
        lines = scenes[i].get("lines") or []
        for j, ln in enumerate(lines):
            tx = extras.strip_tags(str(ln.get("text", ""))).strip()
            if not 10 <= len(tx) <= 110:
                continue
            spk = str(ln.get("speaker", "narrator")).lower()
            sc = ((3 if ln.get("jump_scare") or ln.get("ghost_laugh") else 0) + (2 if spk in ghosts else 0)
                  + (0 if spk.startswith("narrat") else 2) + (1 if any(ch in tx for ch in "!?") else 0)
                  + (1 if str(ln.get("emotion", "")).lower() in ("terrified", "scream", "fear", "panic", "whisper",
                                                                    "eerie", "shocked") else 0))
            if sc > bs:
                best, bs = j, sc
        if best is not None:
            cand.append((bs, i, best))
    top = sorted(cand, reverse=True)[:n]
    pick = top[:1] + sorted(top[1:], key=lambda c: c[1])    # the scariest moment opens the teaser
    out = []
    for _s, i, j in pick:
        ln = dict(scenes[i]["lines"][j])
        for k in ("guess", "jump_scare", "_revealed"):
            ln.pop(k, None)
        out.append((i, [ln]))
    return out


def make_plan_teaser(plan, slot_hour, out_portrait):
    """A teaser (under a minute) for a story written this morning: its most gripping moments with pictures and
    voices, then the title and only the time of day ('আজ রাতে') - never a clock time."""
    global FONT
    import copy
    story = copy.deepcopy(plan["story"])
    lang, special = plan["lang"], plan.get("special") or ""
    L = LANGS[lang]
    FONT = find_font(lang)
    clean_story_text(story)
    sync_sounds(story)
    fix_speakers(story)
    NAME_LOCAL.update({str(c["name"]).lower(): str(c.get("name_local") or c["name"]) for c in story["characters"]})
    mark_reveals(story)
    if special in SERIES_IDS:
        fixed = series_cast(special, plan.get("theme"), (plan.get("state") or {}).get("crossover"))
        have = {str(c.get("name", "")).lower() for c in story.get("characters", [])}
        story["characters"] += [b for b in fixed if b["name"].lower() not in have]
    moments = pick_moments(story["scenes"], story, n=3)   # short and sharp: ~25-35 seconds
    if len(moments) < 2:
        raise RuntimeError("not enough gripping moments for a teaser")
    cast = Cast(story)
    voices = Voices(lang, cast)
    seed = random.randint(1, 1_000_000)
    make_cast_sheet(cast, os.path.join(WORK, "cast.jpg"), seed)
    parts, last_img = [], None
    for k, (i, lines) in enumerate(moments):
        s = story["scenes"][i]
        pic = lines[0].get("image") if isinstance(lines[0].get("image"), dict) else {}
        action = pic.get("prompt") or lines[0].get("shot") or s.get("action", "")
        if lines[0].get("en"):
            action = f"{action}. It must show exactly this moment: \"{lines[0]['en']}\""
        names = pic.get("characters") if isinstance(pic.get("characters"), list) else s.get("characters")
        p = os.path.join(WORK, f"tz_{k:02d}.jpg")
        if not make_image(cast, action, s.get("place", ""), names, p, seed + k):
            p = last_img
        if not p:
            continue
        last_img = p
        parts.append({"image": p, "lines": lines, "sounds": [], "mood": "scary", "voices": voices,
                      "place": f"{s.get('place', '')} {story.get('setting', '')}"})
    if len(parts) < 2:
        raise RuntimeError("no pictures for the teaser")
    title = re.sub(r"\s*\|.*$", "", str(story.get("title", ""))).strip()
    when = when_words(lang, slot_hour, 0)
    parts.append({"image": last_img, "lines": [{"speaker": "narrator", "emotion": "eerie",
                  "text": (f"{when}... " + (extras.TRUE_LABEL[lang] + "... " if story.get("true_label") else "")
                           + (f"{title}। পুরো গল্প শুনতে পেজটা ফলো করে রাখুন।" if lang == "bn" else
                              f"{title}। पूरी कहानी सुनने के लिए पेज फ़ॉलो कीजिए।"))}],
                  "sounds": ["wind"], "mood": "creepy", "voices": voices})
    STING_AT[0] = len(parts) - 1                    # the show's sound with the title, at the end
    STORY_PART[0] = 0
    HOOK_TEXT[0] = str(story.get("tagline") or story.get("thumbnail_text") or "").strip()
    cat = plan.get("cat") or category_of(slot_hour)
    STATE["top_text"] = (f"{SHOW_NAME[lang].get(slot_hour, SHOW_NAME[lang][EVENING])} · {HORROR_CATS[cat][lang]}", title)
    wide = os.path.join(WORK, "teaser_wide.mp4")
    os.environ["TTS_SPEAKERS_PER_REQUEST"] = "2"      # a teaser has only a few short lines: fewer voice requests
    VOICE_CONTEXT[0] = "teaser"
    try:
        build_video(parts, lang, wide)
    finally:
        os.environ.pop("TTS_SPEAKERS_PER_REQUEST", None)
        VOICE_CONTEXT[0] = "main"
    extras.make_teaser(wide, 0.0, duration(wide), out_portrait, FONT, title, when, WORK,
                       tagline=str(story.get("tagline") or story.get("thumbnail_text") or ""),
                       colors=((255, 230, 0), (200, 0, 20)))
    return title, when, story


def _teaser_short(reel, title, story, desc, tags, lang, at):
    """A morning teaser as a YouTube Short, published at its time."""
    try:
        extras.PUBLISH["at"], extras.PUBLISH["used"] = at, False
        loc = extras.shorts_localizations(
            extras.yt_localizations(title, story.get("description") or desc, lang, env("GEMINI_API_KEY")), desc)
        log("YouTube teaser Short:", post_to_youtube(reel, None, f"{title[:80]} #Shorts", desc, tags, lang, loc))
    except Exception as e:
        log("  teaser Short skipped:", str(e)[:200])


def morning_teasers(history):
    """MORNING RUN (no morning story any more): writes today's afternoon and night stories, and posts a teaser
    for each, one hour apart. The afternoon and night runs then make their videos from exactly these stories."""
    global WORK
    done = _jload(TEASERS_FILE, {})
    if done.get(str(SLOT)) and not MOCK and env("FORCE_TEASERS") != "1":
        log("This morning's teasers are already out - nothing to do.")
        return
    day = dt.datetime.now(extras.IST).date().isoformat()
    first = dt.datetime.now(extras.IST).replace(hour=int(env("TEASER_HOUR") or 9), minute=0, second=0, microsecond=0)
    hist2, base_work, out = list(history), WORK, []
    gd_due, held_short = None, None
    try:
        gd_due = ghost_dict_due()                    # v63: is today the ghost dictionary's day?
        if gd_due:
            log(f"Today's ghost dictionary: no. {gd_due[1]} - {gd_due[0][2]} (after the teasers)")
    except Exception as e:
        log("  ghost dictionary check skipped:", str(e)[:100])
    try:                                             # v68: stories (if last night failed), today's thumbnail
        morning_prepare(day, history)                # pictures FIRST, the title list, your Telegram pictures
    except Exception as e:
        log("  morning preparation skipped:", str(e)[:150])
    for n, h in enumerate((NOON, EVENING)):
        key = f"{day}@{h}"
        plan = load_plan(key)
        if not plan:
            log(f"=== Writing the story for {when_words('bn', h, 0)} ({key}) ===")
            STATE.clear()
            SCRIPTS.clear()
            try:
                plan = choose_and_write(h, hist2)
                plan = json.loads(json.dumps(plan, ensure_ascii=False, default=list))
                save_plan(key, plan)
                push_now([PLANS_FILE, MY_STORIES], f"story written for {key}")
            except Exception as e:
                log(f"  the story for {key} could not be written now ({str(e)[:200]}) - its own run will write it")
                continue
        if h == NOON:                                # how much of Gemini's day the 2 PM story will need
            try:
                NOON_NEED[0] = estimate_requests(plan["story"])
                log(f"  the 2 PM story will need about {NOON_NEED[0]} voice requests - kept for it")
            except Exception:
                NOON_NEED[0] = 0
        hist2.append({"theme": plan.get("theme"), "title": plan["story"].get("title"), "lang": plan.get("lang"),
                      "category": plan.get("cat"), "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                      "viewer_names": [p[0] for p in ((plan.get("state") or {}).get("viewer_names") or [])]})
        if env("TEASER_VOICE") != "1":
            # (13 Nov 2026) NO separate teaser with its own voice any more: the teaser is cut from the FINISHED video
            # itself (made 3 hours before its time) and posted right away - no extra voice needed
            continue
        try:
            WORK = os.path.join(base_work, f"teaser_{h}")
            shutil.rmtree(WORK, ignore_errors=True)
            os.makedirs(WORK)
            GEMINI_CACHE.clear()
            reel = os.path.join(WORK, "teaser.mp4")
            title, when, story = make_plan_teaser(plan, h, reel)
            log(f"Teaser for {when}: {title} ({duration(reel):.0f} s)")
            out.append(reel)
            if DRY_RUN or MOCK:
                continue
            at = max(first + dt.timedelta(hours=n), dt.datetime.now(extras.IST) + dt.timedelta(minutes=15))
            L = LANGS[plan["lang"]]
            page = env(f"PAGE_NAME_{plan['lang'].upper()}") or env("PAGE_NAME") or L["page_default"]
            tags = [t if str(t).startswith("#") else "#" + str(t).replace(" ", "") for t in story.get("hashtags", [])[:5]]
            desc = (f"{title}\n\n{when} পুরো গল্প - {page} ফলো করে রাখুন।" if plan["lang"] == "bn" else
                    f"{title}\n\n{when} पूरी कहानी - {page} को फ़ॉलो कीजिए।") + "\n\n" + " ".join(tags)
            if env("FB_REELS") != "0":
                try:
                    log("Facebook teaser Reel:", extras.fb_post_reel(reel, desc, at=at))
                    if env("MORNING_STORY") != "0":   # and on the page Story (24 hours at the top of the feed)
                        try:
                            sid = extras.fb_post_story(reel)
                            if sid:
                                log("  teaser on the Facebook Story:", sid)
                        except Exception as e:
                            log("  Facebook Story skipped:", str(e)[:150])
                except Exception as e:
                    log("  teaser Reel skipped:", str(e)[:200])
            if extras.yt_extra_ok() and env("YT_SHORTS") != "0":
                if gd_due and h == EVENING:            # v63: today the ghost dictionary takes this Short's place
                    held_short = (reel, title, story, desc, tags, plan["lang"], at)    # (YouTube's daily limit)
                    log("  YouTube: today the ghost dictionary Short takes this teaser's place (Facebook as always)")
                else:
                    _teaser_short(reel, title, story, desc, tags, plan["lang"], at)
        except Exception as e:
            log(f"  teaser for {key} skipped: {str(e)[:200]} (the story itself is saved for its run)")
        finally:
            WORK = base_work
    if gd_due:                                       # v63: Thursday - the ghost dictionary (11 AM)
        yt_done = False
        try:
            yt_done = make_ghost_dictionary(gd_due)
        except Exception as e:
            log("  ghost dictionary skipped this week:", str(e)[:200])
        finally:
            WORK = base_work
        if held_short and not yt_done:               # the ghost film did not reach YouTube: the teaser after all
            r_, t_, s_, d_, tg_, l_, at_ = held_short
            _teaser_short(r_, t_, s_, d_, tg_, l_, max(at_, dt.datetime.now(extras.IST) + dt.timedelta(minutes=15)))
    done[str(SLOT)] = dt.datetime.now(extras.IST).isoformat(timespec="minutes")
    _jsave(TEASERS_FILE, {k: v for k, v in done.items() if k >= (dt.date.today() - dt.timedelta(days=7)).isoformat()})
    for job_ in (daily_text_short, weekly_ambience):   # v83: no voice needed for either
        try:
            WORK = os.path.join(base_work, job_.__name__)
            shutil.rmtree(WORK, ignore_errors=True)
            os.makedirs(WORK)
            if job_(history):
                save_history(history)
        except Exception as e:
            log(f"  {job_.__name__} skipped:", str(e)[:200])
        finally:
            WORK = base_work
    push_now([PLANS_FILE, TEASERS_FILE, MY_STORIES], "morning teasers posted")
    log(f"Morning done: {len(out)} teaser(s); the afternoon and night videos will use these stories")


BIBLE_FILE = os.path.join(HERE, "assets", "series_bible.json")    # what our series heroes have lived through
SERIES_BIBLE = {   # how our recurring people speak and behave - the same in every episode
    "bhairab": ("BHAIRAB THAKUR speaks slowly, in few words, calm even in the worst moment; dry humour; calls Paltu "
                "'ওরে পল্টু'; never shouts; explains the old beliefs simply. PALTU talks fast when scared, makes "
                "jokes to hide his fear, loves food, calls him 'ঠাকুরমশাই' (only now and then - never line after line "
                "starting with the same call); in the end he is always brave once."),
    "taranath": ("TARANATH speaks like a tired old man who has seen too much: slow, honest about his fear and his "
                 "mistakes, never boasting, sometimes stops and stares at the rain. KISHORI is curious, polite, "
                 "asks short hushed questions, calls him 'তারানাথবাবু'."),
    "karna": ("NILKANTHA ACHARYA speaks softly, carefully, like a man carrying a guilt; he is afraid of the "
              "Pishachini but never shows it to Bapi. BAPI is sharp, a little cheeky, modern, does not believe at "
              "first, calls him 'মামা'."),
}


ARC_WHO = ("THE SHADOW BEHIND THE CASES (our own invention - the thread that runs through the whole series): somewhere "
           "in Bengal an unseen tantrik, known only as 'কালো সাধু' (the Black Sadhu), wakes old spirits on purpose. "
           "Nobody has seen his face. His sign: a small trident drawn in black ash ('কালো ছাইয়ের ত্রিশূল') left at the "
           "haunted place. Bhairab Thakur has been following this sign for years and does not talk about it.\n")


def arc_rule(special, part, total, prev):
    """v70: the Bhairab Thakur cases share one hidden enemy. In a normal case only his sign is found (one quiet
    moment); the month's LAST case is the meeting with him. Returns the rule for the writer ('' for other series)."""
    if special != "bhairab" or env("SERIES_ARC") == "0":
        return ""
    now = dt.datetime.now(extras.IST)
    last = ((now.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)).day
    later = sum(1 for d in range(now.day + 1, last + 1) if category_of(EVENING, now.replace(day=d)) == "rohoshyo")
    need = max(1, int(total or 1))
    # the last case that still ENDS in this month (a case begun on the month's last evening belongs to the next one)
    finale = ((prev or {}).get("arc") == "finale" if part and part >= 2 else
              later >= need - 1 and later - (need - 1) < need)
    STATE["arc"] = "finale" if finale else "sign"
    if finale:
        log("Bhairab Thakur: the month's last case - he meets the Black Sadhu")
        return ("\n" + ARC_WHO + "THIS IS THE MONTH'S LAST CASE - THE MEETING: the haunting of this case leads Bhairab to the "
                "Black Sadhu's own ritual place. They meet at last - a calm, cold voice and a figure whose face stays in "
                "shadow (give him 2-5 spoken lines; speaker name 'Kalo Sadhu'). Bhairab breaks his ritual and frees the "
                "spirits he woke; the Sadhu slips away into the dark with one quiet promise to return. The case itself is "
                "fully solved - only he stays unknown" + (" (the meeting comes in the LAST part)." if need > 1 else ".")
                + "\n")
    return ("\n" + ARC_WHO + "IN THIS CASE his sign appears ONCE, small, near the end: Bhairab notices the black-ash trident, "
            "goes silent for a moment, and when Paltu asks he only says something like 'আবার সে।' It is never explained and "
            "never the main plot - the case is complete without it. Do not show the Sadhu himself.\n")


def bible_rule(special):
    """The series' character book + the cases already told (so a new episode may remember them and never
    contradicts them)."""
    if special not in SERIES_BIBLE:
        return ""
    past = (_jload(BIBLE_FILE, {}).get(special) or [])[-8:]
    txt = "\nSERIES CHARACTER BOOK (keep them exactly like this): " + SERIES_BIBLE[special] + "\n"
    if past:
        txt += ("CASES ALREADY TOLD (they really happened to them - one may be remembered in passing if it fits, "
                "never contradicted, never retold): " + " | ".join(f"{c.get('title')}: {c.get('summary', '')}"
                                                              for c in past) + "\n")
    return txt


def bible_add(special, title, summary):
    if special not in SERIES_BIBLE:
        return
    b = _jload(BIBLE_FILE, {})
    lst = b.setdefault(special, [])
    t = re.sub(r"\s*\|.*$", "", str(title)).strip()
    if any(c.get("title") == t for c in lst):
        return
    lst.append({"title": t, "summary": str(summary or "")[:300],
                "date": dt.datetime.now(extras.IST).date().isoformat()})
    b[special] = lst[-30:]
    _jsave(BIBLE_FILE, b)


MY_STORIES = os.path.join(HERE, "assets", "my_stories.json")      # stories YOU send on Telegram
TTS_USAGE = os.path.join(HERE, "assets", "tts_usage.json")        # free voice requests used today


def creator_inbox(status=None):
    return extras.creator_inbox(MY_STORIES, "horror", status)


THUMB_B = os.path.join(HERE, "assets", "thumb_b")                   # second thumbnails (for weak videos)


def bot_status():
    """What 'অবস্থা' on Telegram answers for this bot."""
    hist = load_history()
    lines = []
    last = next((h for h in reversed(hist) if h.get("facebook") or h.get("youtube")), None)
    if last:
        try:
            when = dt.datetime.fromisoformat(str(last.get("date"))).astimezone(extras.IST).strftime("%d %b %I:%M %p")
        except Exception:
            when = ""
        lines.append(f"শেষ ভিডিও: {re.sub(r'[|].*$', '', str(last.get('title', '')))[:50].strip()} ({when}) "
                     + " ".join(x for x in ("FB ✓" if last.get("facebook") else "FB ✗",
                                            "YT ✓" if last.get("youtube") else "YT ✗")))
    u = _jload(TTS_USAGE, {})
    if isinstance(u, dict):
        used = u.get("used", 0) if u.get("day") == extras._pacific_day() else 0
        lines.append(f"Gemini গলা আজ: {used} / {env('TTS_DAY_BUDGET') or 36} request খরচ (দুপুর দেড়টায় নতুন করে শুরু)")
        if env("GOOGLE_TTS_KEY"):
            lines.append(f"Chirp গলা এই মাসে: {extras.chirp_used(TTS_USAGE)} / {env('CHIRP_MONTH_CAP') or 900000} অক্ষর")
    plans = _jload(PLANS_FILE, {})
    today = dt.datetime.now(extras.IST).date().isoformat()
    ready = [k.split("@")[1] for k in (plans or {}) if str(k).startswith(today)]
    if ready:
        lines.append("আজকের লেখা গল্প তৈরি: " + ", ".join({"14": "দুপুর", "20": "রাত"}.get(h, h) for h in sorted(ready)))
    return lines


def take_creator_story():
    return extras.take_creator_story(MY_STORIES, "horror")


CREATOR_RULE = (
    "\nTHE CREATOR'S OWN STORY - written by our page's creator. THIS is today's story; build the whole video on it:\n"
    "<<<{text}>>>\n"
    "Keep its people, places, events, their ORDER, its twist and its ending exactly as the creator wrote them. "
    "Turn it into our radio drama: living dialogue for its people, the narrator's bridges, sensory detail and "
    "sounds, small connecting moments - so it reaches the planned length by LIVING its own scenes, never by adding "
    "new main events, new main characters or a different ending. If something is unclear or missing (a name, a "
    "reason, the ending), fill it in the creator's own spirit. Keep the creator's best lines.\n")


PLAN_STATE = ("brief", "outline", "outline_saved", "source_name", "idea_used", "own_kind", "trends", "category",
              "trend_used", "crossover", "milestone", "opening", "sequel_of",
              "case_no", "creator_story", "creator_true", "len_scale", "short_plan",
              "district", "district_votes", "viewer_names", "arc")


def length_scale():
    """How many words to write for one minute of video - MEASURED on our own finished videos, not guessed.
    (With a fixed guess of 120 words a minute the slow, grave Gemini storyteller and the long chapters turned a
    22-minute plan into a ~40-minute video - twice the voice limit and far too long.) 1.0 = 120 words a minute."""
    try:
        if env("LENGTH_SCALE"):
            return max(0.3, min(1.3, float(env("LENGTH_SCALE"))))
        s = float(_jload(TTS_USAGE, {}).get("len_scale") or 0)
    except (TypeError, ValueError, AttributeError):
        s = 0
    # (0.6 = 72 words a minute: measured 11 Nov 2026 - the Gemini storyteller with his own pauses. The stories were
    # short because the writer delivered only 1000-1300 of the 1580 words asked for, see the chapters' minimum.)
    return s if 0.3 <= s <= 1.3 else 0.6


def learn_length(video_sec):
    """After a normal story fully in the Gemini voice: compare the real video length with the planned minutes
    and correct the words asked for next time - so the videos really are about LONG_MIN minutes long."""
    try:
        used = float(STATE.get("len_scale") or 0)
        if (not used or MOCK or not STATE.get("all_gemini") or STATE.get("chirp_used") or STATE.get("creator_story")
                or STATE.get("short_plan")
                or video_sec < 300 or LONG_MIN < 8):
            return
        ratio = (video_sec / 60.0) / LONG_MIN          # 1.0 = exactly the planned length
        ideal = used / ratio
        if STATE.get("story_words"):                   # better: the words really spoken per minute of this video
            ideal = float(STATE["story_words"]) / (video_sec / 60.0) / 120.0
        d = _jload(TTS_USAGE, {})
        if not isinstance(d, dict):
            d = {}
        try:
            old = float(d.get("len_scale") or used)
        except (TypeError, ValueError):
            old = used
        new = round(max(0.3, min(1.3, old + 0.7 * (ideal - old))), 3)
        d["len_scale"] = new
        d["len_seen"] = (list(d.get("len_seen") or []) + [round(ratio, 2)])[-8:]
        _jsave(TTS_USAGE, d)
        log(f"  video length {video_sec / 60:.1f} min for a {LONG_MIN:.0f}-minute plan -> next stories are written "
            f"with length factor {new} (was {old})")
        push_now([TTS_USAGE], "story length learned")
    except Exception as e:
        log("  length not learned:", str(e)[:100])


def choose_and_write(slot_hour, history):
    """Chooses today's story for this time (category, series part, idea, language ...) and writes it.
    Returns everything the video needs - so the story can also be written hours EARLIER (the morning run
    writes the afternoon and the night story, makes their teasers, and the later runs use these scripts)."""
    global FONT, VHS, LONG_MIN
    STATE["slot_hour"] = slot_hour
    if not os.environ.get("HORROR_MINUTES"):
        LONG_MIN = SLOT_MINUTES.get(slot_hour, LONG_MIN)
        if env("MODE") == "amavasya":                 # the monthly midnight special: a little shorter, so the
            LONG_MIN = 18.0                           # day's Gemini voice limit still covers the next videos
    cat = category_of(slot_hour)
    festival, special, extra_rules, viewer = None, "", "", None
    classic, plain_rules = None, ""
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
    fest = extras.festival_today("horror") if slot_hour == EVENING else None
    if fest and any(h.get("festival") == fest[0] and
                    (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(h["date"])).total_seconds() < 20 * 3600
                    for h in history[-4:] if h.get("date")):
        fest = None
    # THE AMAVASYA SPECIAL IS THE 8 PM STORY of the new-moon night (no separate midnight video any more - your
    # wish of 8 Nov 2026: nobody needs it that late, and Gemini's voice is enough for the whole day)
    amavasya_tonight = False
    if slot_hour == EVENING and env("MODE") != "amavasya" and env("AMAVASYA_AT_8") != "0":
        try:
            amavasya_tonight = extras.is_amavasya_night(
                dt.datetime.now(extras.IST).replace(hour=23, minute=59, second=0, microsecond=0))
        except Exception:
            amavasya_tonight = False
    prev = None if (env("MODE") == "amavasya" or fest or amavasya_tonight) else extras.series_get(NEXT_PART, cat)
    info = HORROR_CATS[cat]
    lang = prev["lang"] if prev else pick_language(history)
    fmt = (prev or {}).get("fmt") or extras.weighted_choice(FORMATS, extras.weights(history, "format", FORMATS))
    part, total = 0, 1
    theme = ""
    if prev:                                         # the next part of this category's unfinished story
        part, total = int(prev.get("done", 1)) + 1, int(prev.get("total", 2))
        theme, special = prev.get("theme", ""), prev.get("special", "")
        log(f"Category {cat}: part {part} of {total} of '{prev.get('title')}' (part {part - 1} came on "
            f"{prev.get('updated', '')[:10]})")
    elif fest:
        festival, theme = fest[0], fest[1]
        log(f"Festival special: {festival}")
        if amavasya_tonight:                          # (Kali Puja falls on the Amavasya night itself)
            extra_rules += ("\nTONIGHT IS ALSO THE AMAVASYA (new-moon) NIGHT - the darkest night of the month: the "
                            "story happens on it.\n")
    elif env("MODE") == "amavasya" or amavasya_tonight:
        special = "amavasya"
        theme = random.choice(["the darkest Amavasya night in a village where no lamp may be lit",
                               "an Amavasya midnight ritual at the cremation ground that goes wrong",
                               "the Amavasya night when the dead come back to their old house",
                               "a lonely road on Amavasya night and the woman with a lantern"])
        log("Tonight is Amavasya: the 8 PM story is the Amavasya special")
        extra_rules += ("\nSPECIAL: this is our AMAVASYA NIGHT SPECIAL - tonight is the new-moon night. The story "
                        "happens on an Amavasya night and must be the scariest of the month.\n")
    else:
        special = info.get("special", "")
        if special == "notun":                       # v80: tonight one of our new series (they take turns)
            special = pick_new_series(history)
            log(f"Tonight's series: {NEW_SERIES[special]['bn']}")
        total = int(info.get("parts", 1))
        part = 1 if total > 1 else 0
        if special in NEW_SERIES:
            used_ = {str(h.get("theme", "")) for h in history}
            theme = trend_theme(special, lang, history) or random.choice(
                [x for x in NEW_SERIES[special]["themes"] if x not in used_] or NEW_SERIES[special]["themes"])
            fmt = NEW_SERIES[special]["fmt"]
        elif special == "classic":
            classic = pick_classic_any(history, lang)
            theme = f"the classic: {classic[4]}"
            plain_rules = extra_rules
            log(f"Famous writer's story: {classic[4]}")
        elif special == "karna":
            theme = "a new Karna Pishachini case"
            tr_ = trend_theme(cat, lang, history)     # v79: this week's most watched topic of this kind
            if tr_:
                theme = f"a new Karna Pishachini case - its topic: {tr_}"
            fmt = "Bapi tells his uncle Nilkantha's case, with real dialogue between the characters"
        elif special == "taranath":
            theme = random.choice(HORROR_CATS["gram"]["themes"] + HORROR_CATS["jayga"]["themes"])
            theme = trend_theme(cat, lang, history) or theme
            if env("MADHUSUNDARI") != "0" and not any(h.get("theme") == "madhusundari" for h in history):
                theme, total, part = "madhusundari", 2, 1    # the Madhusundari Devi special (2 parts), once
                log("Taranath special: Madhusundari Devi (part 1 of 2)")
            fmt = "Taranath Tantrik telling his own true experience to Kishori, in first person"
        elif special == "bhairab":
            theme = random.choice(HORROR_CATS["gram"]["themes"] + HORROR_CATS["shohor"]["themes"])
            theme = trend_theme(cat, lang, history) or theme
        else:
            mine = take_creator_story() if cat in ("gram", "shohor", "jayga", "sotti") else None
            if mine:
                STATE["creator_story"] = True
                STATE["creator_true"] = bool(mine.get("true", True))
                log(f"YOUR OWN STORY from Telegram is today's story ({len(mine['text'])} characters)")
            used = {str(h.get("theme", "")) for h in history[-80:]}
            pool = [t for t in info["themes"] if t not in used] or info["themes"]
            theme = random.choice(pool)
            idea = next_idea(history) if not mine and slot_hour == EVENING and cat in ("gram", "shohor", "jayga") else None
            if idea:                                 # our idea list comes first (used once each)
                theme = idea[0]
                STATE["idea_used"] = idea[0]
                log(f"Idea from the list: {theme}")
            # TREND STORY (v79: EVERY story): built on what is MOST WATCHED on YouTube this week in exactly this
            # story's kind (real YouTube search of the category, sorted by views) - our own new story, never a copy
            seq_ = None if (mine or idea or cat == "sotti") else hit_for_sequel(history, lang)
            if seq_:                                 # v82: a story people loved comes back ('... ফিরে এল')
                theme = f"the SEQUEL of our hit story '{seq_.get('title')}'"
                STATE["sequel_of"] = seq_.get("slot") or seq_.get("title")
                extra_rules += sequel_rule(seq_, lang)
            if not mine and not idea and not seq_:
                theme = trend_theme(cat, lang, history) or theme
            if cat == "sotti" and not mine:
                vs = []
                try:                                 # v76: the stories viewers TOLD us by voice on Telegram first
                    vs = extras.viewer_voice_stories(ASSETS, {h.get("viewer_story_id") for h in history})
                except Exception as e:
                    log("  viewer voice stories skipped:", str(e)[:120])
                try:
                    vs = vs or extras.viewer_stories(history, {h.get("viewer_story_id") for h in history})
                except Exception as e:
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
            STATE["own_kind"] = not mine
            if mine:
                theme = "the creator's own story"
                extra_rules += CREATOR_RULE.format(text=mine["text"])
    if env("RETENTION_RULE") != "0":                 # v86: people left in the first minute - keep them
        extra_rules += RETENTION_RULE
    try:                                             # v63: this week's district + viewers who asked to be in it
        extra_rules += weekly_district(cat, slot_hour, prev, fest, amavasya_tonight, special, history, lang)
        extra_rules += viewer_names_rule(cat, special, part, festival, history, lang)
    except Exception as e:
        log("  district / viewer names skipped:", str(e)[:120])
    if not MOCK:
        try:                                         # what people watch this week (also hashtags + search words)
            STATE["trends"] = STATE.get("trends") or extras.trending_topics("horror", lang, os.path.join(HERE, "assets"), cat)
        except Exception as e:
            log("  trends skipped:", str(e)[:100])
        try:                                         # title + thumbnail words in this week's winning style
            extra_rules += extras.trend_style_rule("horror", lang, os.path.join(HERE, "assets"))
        except Exception:
            pass
        try:                                         # v76: a subscriber milestone - the storyteller says thank you
            extra_rules += milestone_rule()
        except Exception:
            pass
        try:                                         # v77: what the growth monitor learned + the opening style
            coach = extras.coach_load(COACH_FILE)
            extra_rules += extras.coach_rule(coach, "horror")
            if not (part and part >= 2) and env("OPENING_TEST") != "0":
                op = extras.pick_opening(coach)
                STATE["opening"] = op
                extra_rules += "\nOPENING OF THIS STORY (we measure which opening keeps listeners) - " + extras.OPENINGS[op] + "\n"
                log(f"Opening style of this story: {op}")
        except Exception as e:
            log("  opening / coach rules skipped:", str(e)[:100])
        if STATE.get("own_kind") and STATE.get("trends"):
            extra_rules += ("\nTRENDING THIS WEEK (Bengali / Indian viewers are watching these - if one fits "
                            "today's category, build on it): " + " | ".join(STATE["trends"]) + "\n")
        try:                                         # what worked on our own page, and what viewers asked for
            extra_rules += extras.lessons_rule(extras.learn_lessons(history, "horror", lang, os.path.join(HERE, "assets")))
        except Exception as e:
            log("  lessons skipped:", str(e)[:100])
    extra_rules += bible_rule(special)                 # the series' character book and its past cases
    try:
        extra_rules += arc_rule(special, part, total, prev)
    except Exception as e:
        log("  series thread skipped:", str(e)[:100])
    if special == "karna":
        extra_rules += "\n" + karna_rule(history, lang)
    elif special == "taranath" and theme == "madhusundari":
        extra_rules += "\n" + MADHU_RULE.format(looks=json.dumps(TARANATH + MADHU_CAST, ensure_ascii=False)) + "\n"
    elif special == "taranath":
        extra_rules += "\n" + TARANATH_RULE.format(looks=json.dumps(TARANATH)) + "\n"
    elif special in NEW_SERIES:
        extra_rules += new_series_rule(special, history, lang)
    elif special == "bhairab":
        extra_rules += "\n" + BHAIRAB_RULE.format(looks=json.dumps(BHAIRAB)) + "\n"
        try:                                         # v76: once a month the two series meet - the 'মহা-কেস'
            extra_rules += crossover_rule(history, part, prev)
        except Exception as e:
            log("  crossover check skipped:", str(e)[:100])
    elif special == "classic" and classic:
        extra_rules += classic_rule(classic, lang)
    if not festival and special not in ("classic", "amavasya"):
        extra_rules += (f"\nTODAY'S PROGRAMME ({info['bn']}): {info['about']}. The story must clearly be this kind of "
                        "story - our listeners come at this time for exactly this.\n")
    if part >= 1 and total > 1:                      # a story told in parts, one part on each of its days
        extra_rules += (f"\nTHIS IS PART {part} OF {total} of ONE story (each part about {int(LONG_MIN)} minutes; the "
                        "next part comes on this category's next day). ")
        if part == 1:
            extra_rules += ("Tell only the FIRST part of the master outline's beats - the beginning and the rising "
                            "mystery - and stop at a big cliffhanger. Plant every clue now.\n")
        else:
            extra_rules += (f"Continue the SAME story - never a new case, never a restart. Begin with the narrator's "
                            f"short recap (3-4 lines, e.g. 'গত পর্বে আমরা দেখেছিলাম...') of exactly where part {part - 1} "
                            f"ended, then go on from that very moment. Story so far: {prev.get('summary', '')}\n"
                            f"The last lines of part {part - 1} were: {prev.get('last_lines', '')}\n"
                            f"Use EXACTLY these people (names, looks): {json.dumps(prev.get('characters'), ensure_ascii=False)[:3000]} "
                            f"and this place: {prev.get('setting', '')}. Keep every clue, promise and fact consistent. "
                            + ("This is the FINAL part: the mystery is solved completely - but ONLY in its last "
                               "chapter (the climax and the explanation come at the end, never at the start).\n"
                               if part >= total else
                               "End again on a cliffhanger.\n"))
    if prev and prev.get("outline"):
        STATE["outline_saved"] = prev["outline"]
    day, month, moon, belief = tonight()
    if moon.startswith("AMAVASYA") and not special and not festival and not part and slot_hour == EVENING:
        theme = random.choice(["the darkest Amavasya night in a village where no lamp may be lit",
                               "an Amavasya midnight ritual at the cremation ground that goes wrong",
                               "the Amavasya night when the dead come back to their old house",
                               "a lonely road on Amavasya night and the woman with a lantern"])
        log("Tonight is Amavasya: the story is an Amavasya story")
    if special != "classic":                         # the story fits TODAY
        extra_rules += (f"\nTODAY (let the story fit this very day / night): "
                        f"{dt.datetime.now(extras.IST).strftime('%d %B')}, {belief}; the Bengali month of "
                        f"{month}{'; ' + moon if moon else ''}. The story happens in this season and uses the beliefs "
                        "that belong to it (naturally, never forced).\n")
        log(f"Today: {belief} | {month}" + (f" | {moon}" if moon else ""))
    wx = extras.weather_now(lang) if not MOCK else None
    if wx and special != "classic":
        extra_rules += f"\nTODAY'S REAL WEATHER: {wx}. Set the story in this weather and let the listener feel it.\n"
        log("Weather:", wx)
    STATE["category"] = cat
    log(f"Programme: {SHOW_NAME['bn'][slot_hour] if slot_hour in SLOTS else ''} - {info['bn']}")
    L = LANGS[lang]
    FONT = find_font(lang)
    VHS = "first person" in str(fmt) and special not in ("taranath", "classic")   # found-footage look for modern "I lived it" stories
    log(f"Language: {L['name']} | Idea: {theme} | Style: {fmt}" + (f" | SERIES part {part}" if part else ""))

    if special != "classic":
        extra_rules += MASTER_STYLE
    if special == "karna":
        subject, ck = ("Karna Pishachini (কর্ণপিশাচিনী) in Bengali and Indian tantric belief: the yogini, her sadhana, "
                       "her nature, look and rules"), "karna_pishachini"
    elif special == "classic" and classic:
        subject, ck = f"the published story {classic[4]}", f"classic_{classic[0]}"
    else:
        subject, ck = f"{theme} (with the folk ghost or belief it is about)", None
    if theme == "madhusundari":
        subject, ck = ("the yogini (যোগিনী) in Bengali tantric belief: what yoginis are, how they are said to appear to a "
                       "sadhak, their nature, their dangers and the old warnings about them"), "yogini"
    # (old versions saved part 2 pre-written in ONE go - it did not follow the chapter plan: never used now)
    has_script = env("USE_SAVED_PARTS") == "1" and bool(((prev or {}).get("scripts") or {}).get(str(part)))
    brief = ""
    if not has_script and part <= 1 and special in ("", "taranath", "bhairab", "amavasya", None) and not viewer \
            and theme != "madhusundari" and not STATE.get("creator_story"):
        src_name, src = find_source_story(theme, history)   # a big frightening story from the internet as the base
        if src:
            STATE["source_name"] = src_name
            brief = src
            extra_rules += ("\nSOURCE STORY (found on the internet - BUILD TODAY'S STORY ON IT): keep its core people, "
                            "events, horror and ending, but make it MORE REALISTIC (a believable Bengal / India setting, "
                            "real everyday detail, people who act like real people, every event with a cause) and "
                            "SCARIER; fill every gap so the story is complete from its real beginning to its end. "
                            "Tell it in your own words (never copy sentences).\n" + src + "\n")
    if not has_script and not brief:
        brief = research_brief(subject, ck)
    STATE["brief"] = brief
    if brief and not STATE.get("source_name"):
        extra_rules += ("\nRESEARCH BRIEF (true facts we looked up before writing - FOLLOW THEM EXACTLY; never "
                        "contradict them):\n" + brief + "\n")
    saved = ((prev or {}).get("scripts") or {}).get(str(part)) if part >= 2 and has_script else None
    if saved:                                        # this part was written together with part 1: use it as is
        SCRIPTS.update({k: v for k, v in (prev.get("scripts") or {}).items() if int(k) > part})
        log(f"Series part {part}: using the script written with part 1")
    outline = STATE.get("outline_saved", "") if part >= 2 else ""
    if outline:                                      # the plan of the WHOLE series, made on part 1's day
        extra_rules += ("\nMASTER OUTLINE of the whole series (this part tells its own share of the beats, in order, "
                        "continuing exactly where the last part stopped):\n" + outline + "\n")
    if not saved and special != "classic" and part <= 1:
        outline = plan_story(lang, theme, extra_rules, fmt, parts=total)
        if outline:
            extra_rules += ("\nMASTER OUTLINE (planned and checked by our script doctor - FOLLOW IT EXACTLY, beat by "
                            "beat; every beat becomes one scene or more; keep every name, decision and follow-up. In a series of 2-3 "
                            "parts each part tells only its own share of the beats in order - part 1 up to the big "
                            "cliffhanger):\n"
                            + outline + "\n")
    STATE["outline"] = outline
    try:
        if saved:
            raise _Saved()
        story = write_long_story(lang, theme, history, fmt, extra_rules, classic=special == "classic",
                                 ending="cliffhanger" if part and part < total else "resolve",
                                 opening="recap" if part >= 2 else "start", part=part)
        saved = story                                # already checked chapter by chapter by the editor
    except _Saved:
        story = saved
    except ClassicUnknown:                           # the model does not know that classic well: our own story
        log("  the classic is not remembered well enough - writing our own story instead")
        special, classic, theme = None, None, pick_theme(history)
        extra_rules = plain_rules + MASTER_STYLE
        story = write_long_story(lang, theme, history, fmt, extra_rules)
        saved = story
    if not saved:
        story = edit_story(story, lang, classic=special == "classic", brief=STATE.get("brief", ""),
                           outline=STATE.get("outline", ""))
    if STATE.get("creator_true"):                      # 'সত্য ঘটনা অবলম্বনে' everywhere
        extras.mark_true_story(story, lang)
    plan = {k: v for k, v in locals().items() if k in ('cat', 'classic', 'festival', 'fmt', 'lang', 'outline', 'part', 'prev', 'shout_ids', 'shout_names', 'special', 'story', 'theme', 'total', 'viewer')}
    plan["state"] = {k: STATE[k] for k in PLAN_STATE if k in STATE}
    plan["scripts"], plan["vhs"], plan["long_min"], plan["slot_hour"] = dict(SCRIPTS), VHS, LONG_MIN, slot_hour
    return plan



# ===================== v63: SIX NEW FEATURES (9 Nov 2026) =====================
# 1) "ভূতের অভিধান": every Thursday a short video about ONE ghost of Bengali folk belief (Reel + Short)
# 2) "আপনাদের ভোটে এ সপ্তাহের জেলা": Tuesday's 2 PM village story happens in the district our viewers named most
# 3) "বাংলার ভূতের মানচিত্র": every story becomes a pin on a free map website (docs/ folder; the workflow publishes it
#    on GitHub Pages at .../map/ - the main address stays the privacy page)
# 4) "রাতভর ভূতের গল্প": first Sunday of the month - the month's best stories as one 2-3 hour video
# 5) viewers who ASK for it (#আমার_নাম) get a small, kind side character with their first name
# 6) the storyteller's own sign-off at the end of every story (L["outro"])
UNIQ = {
    "bn": {"district_vote": "আপনাদের ভোটে এ সপ্তাহের জেলা: {d}।",
           "district_week": "এ সপ্তাহের জেলা: {d}।",
           "district_top": "📍 {line}",
           "district_invite": ("📍 আপনার জেলায় কোন ভূতের লোককথা শোনা যায়? জেলার নাম আর লোককথাটা লিখে জানান - "
                               "যে জেলার নাম সবচেয়ে বেশি আসবে, পরের {day} দুপুরের গ্রামের গল্প হবে সেই জেলায়।"),
           "names_thanks": "💐 এই গল্পে আমাদের দর্শকদের নামে চরিত্র: {names}",
           "names_invite": ("✍️ গল্পে নিজের নাম চান? কমেন্টে লিখুন #আমার_নাম - পরের কোনো গল্পে একটা ভালো "
                            "চরিত্র হবে আপনার নামে (শুধু নামের প্রথম অংশ)।"),
           "names_reply": "💐 আজকের গল্পে আপনার নামে একটা চরিত্র আছে! শুনে দেখুন:",
           "map_line": "🗺️ বাংলার ভূতের মানচিত্র - আপনার জেলার গল্প খুঁজুন: {url}",
           "dict_title": "ভূতের অভিধান পর্ব {n}: {name} কে? 👻",
           "dict_band": "ভূতের অভিধান · পর্ব {n}",
           "dict_tagline": "বাংলার লোকবিশ্বাস",
           "dict_hook": "{name} কে?",
           "dict_playlist": "ভূতের অভিধান | Bengali Ghost Encyclopedia",
           "dict_desc": "লোকবিশ্বাসে {name}: {summary}\n\nবাংলার প্রতিটা ভূতের কথা - প্রতি বৃহস্পতিবার একটা করে। 👻",
           "marathon_title": "রাতভর ভূতের গল্প 🌙 মাসের সেরা {n}টা গল্প একসাথে | {h}",
           "marathon_thumb": "রাতভর ভূতের গল্প",
           "marathon_intro": "মাসের সবচেয়ে বেশি শোনা গল্পগুলো একটানা - আলো নিভিয়ে, হেডফোনে শুনুন। 🌙",
           "marathon_playlist": "রাতভর ভূতের গল্প | Bengali Horror Marathon",
           "hours": "{h} ঘণ্টা", "hours_min": "{h} ঘণ্টা {m} মিনিট"},
    "hi": {"district_vote": "आपके वोट से इस हफ़्ते का ज़िला: {d}।",
           "district_week": "इस हफ़्ते का ज़िला: {d}।",
           "district_top": "📍 {line}",
           "district_invite": ("📍 बंगाल के किस ज़िले की भूतिया लोककथा सुननी है? ज़िले का नाम और वहाँ की लोककथा "
                               "लिखकर बताइए - जिस ज़िले का नाम सबसे ज़्यादा आएगा, अगले {day} दोपहर की गाँव की कहानी "
                               "वहीं की होगी।"),
           "names_thanks": "💐 इस कहानी में हमारे दर्शकों के नाम के किरदार: {names}",
           "names_invite": ("✍️ कहानी में अपना नाम चाहिए? कमेंट में लिखिए #मेरा_नाम - अगली किसी कहानी में एक "
                            "अच्छा किरदार आपके नाम का होगा (सिर्फ़ पहला नाम)।"),
           "names_reply": "💐 आज की कहानी में आपके नाम का एक किरदार है! सुनिए:",
           "map_line": "🗺️ भूतिया कहानियों का नक्शा: {url}",
           "dict_title": "भूतों का शब्दकोश भाग {n}: {name} कौन है? 👻",
           "dict_band": "भूतों का शब्दकोश · भाग {n}",
           "dict_tagline": "बंगाल की लोक-मान्यता",
           "dict_hook": "{name} कौन है?",
           "dict_playlist": "भूतों का शब्दकोश | Ghost Encyclopedia",
           "dict_desc": "लोक-मान्यता में {name}: {summary}\n\nहर गुरुवार एक भूत की कहानी। 👻",
           "marathon_title": "रात भर भूतिया कहानियाँ 🌙 महीने की {n} सबसे अच्छी कहानियाँ | {h}",
           "marathon_thumb": "रात भर डर",
           "marathon_intro": "महीने की सबसे ज़्यादा सुनी गई कहानियाँ एक साथ - बत्ती बुझाइए, हेडफ़ोन लगाइए। 🌙",
           "marathon_playlist": "रात भर भूतिया कहानियाँ | Horror Marathon",
           "hours": "{h} घंटे", "hours_min": "{h} घंटे {m} मिनट"},
}

# the 23 districts of West Bengal: key, Bengali, English, latitude, longitude (district town), other names
# (no short or everyday words as other names - 'বেহালা' is also a violin, 'আমতা আমতা' means hesitating)
WB_DISTRICTS = [
    ("kolkata", "কলকাতা", "Kolkata", 22.5726, 88.3639, ["calcutta", "শ্যামবাজার", "টালিগঞ্জ", "tollygunge", "কলেজ স্ট্রিট",
                                                        "college street", "বাগবাজার", "bagbazar", "ধর্মতলা", "esplanade"]),
    ("howrah", "হাওড়া", "Howrah", 22.5958, 88.2636, ["উলুবেড়িয়া", "uluberia", "বাগনান", "bagnan", "শিবপুর", "shibpur"]),
    ("n24", "উত্তর ২৪ পরগনা", "North 24 Parganas", 22.7248, 88.4789,
     ["উত্তর চব্বিশ পরগনা", "north 24 parganas", "north 24 pgs", "বারাসত", "barasat", "সল্টলেক", "salt lake", "বনগাঁ",
      "bongaon", "বারাকপুর", "barrackpore", "বসিরহাট", "basirhat", "দমদম", "dum dum", "dumdum", "নিউটাউন", "new town",
      "হাবড়া", "habra", "ব্যারাকপুর"]),
    ("s24", "দক্ষিণ ২৪ পরগনা", "South 24 Parganas", 22.1600, 88.4300,
     ["দক্ষিণ চব্বিশ পরগনা", "south 24 parganas", "south 24 pgs", "সুন্দরবন", "sundarban", "ডায়মন্ড হারবার",
      "diamond harbour", "diamond harbor", "কাকদ্বীপ", "kakdwip", "সাগরদ্বীপ", "sagar island", "গঙ্গাসাগর", "gangasagar",
      "গোসাবা", "gosaba", "ক্যানিং", "বারুইপুর", "baruipur", "বকখালি", "bakkhali"]),
    ("hooghly", "হুগলি", "Hooghly", 22.8960, 88.2460, ["হুগলী", "hugli", "চুঁচুড়া", "chinsurah", "চন্দননগর", "chandannagar",
                                                      "শ্রীরামপুর", "serampore", "ব্যান্ডেল", "bandel", "আরামবাগ", "arambagh",
                                                      "তারকেশ্বর", "tarakeswar"]),
    ("bardhaman_p", "পূর্ব বর্ধমান", "Purba Bardhaman", 23.2324, 87.8615,
     ["purba bardhaman", "purba burdwan", "বর্ধমান", "burdwan", "bardhaman", "কালনা", "kalna", "কাটোয়া", "katwa",
      "মেমারি", "memari"]),
    ("bardhaman_w", "পশ্চিম বর্ধমান", "Paschim Bardhaman", 23.6739, 86.9524,
     ["paschim bardhaman", "paschim burdwan", "আসানসোল", "asansol", "দুর্গাপুর", "durgapur", "রানিগঞ্জ", "raniganj"]),
    ("nadia", "নদিয়া", "Nadia", 23.4058, 88.4900, ["নদীয়া", "কৃষ্ণনগর", "krishnanagar", "নবদ্বীপ", "nabadwip", "মায়াপুর",
                                                "mayapur", "রানাঘাট", "ranaghat", "শান্তিপুর", "shantipur", "কল্যাণী",
                                                "kalyani", "জলঙ্গি", "jalangi"]),
    ("murshidabad", "মুর্শিদাবাদ", "Murshidabad", 24.1000, 88.2500,
     ["বহরমপুর", "baharampur", "berhampore", "লালবাগ", "lalbag", "জিয়াগঞ্জ", "jiaganj", "জঙ্গিপুর", "jangipur"]),
    ("birbhum", "বীরভূম", "Birbhum", 23.9000, 87.5300, ["সিউড়ি", "siuri", "শান্তিনিকেতন", "santiniketan", "shantiniketan",
                                                     "বোলপুর", "bolpur", "তারাপীঠ", "tarapith", "রামপুরহাট", "rampurhat"]),
    ("bankura", "বাঁকুড়া", "Bankura", 23.2324, 87.0716, ["বিষ্ণুপুর", "bishnupur", "মুকুটমণিপুর", "mukutmanipur",
                                                       "শুশুনিয়া", "susunia"]),
    ("purulia", "পুরুলিয়া", "Purulia", 23.3320, 86.3650, ["অযোধ্যা পাহাড়", "ajodhya hill", "ayodhya hill", "বেগুনকোদর",
                                                        "begunkodor", "জয়চণ্ডী", "joychandi", "বাঘমুন্ডি", "baghmundi"]),
    ("medinipur_w", "পশ্চিম মেদিনীপুর", "Paschim Medinipur", 22.4250, 87.3199,
     ["paschim medinipur", "west midnapore", "মেদিনীপুর", "midnapore", "medinipur", "খড়গপুর", "kharagpur", "ঘাটাল",
      "ghatal", "গড়বেতা", "garbeta"]),
    ("medinipur_e", "পূর্ব মেদিনীপুর", "Purba Medinipur", 22.3000, 87.9200,
     ["purba medinipur", "east midnapore", "তমলুক", "tamluk", "দিঘা", "digha", "কাঁথি", "contai", "হলদিয়া", "haldia",
      "মন্দারমণি", "mandarmani"]),
    ("jhargram", "ঝাড়গ্রাম", "Jhargram", 22.4550, 86.9974, ["বেলপাহাড়ি", "belpahari", "কাঁকড়াঝোর", "kankrajhore"]),
    ("malda", "মালদা", "Malda", 25.0108, 88.1411, ["মালদহ", "maldah", "ইংরেজবাজার", "english bazar", "পাণ্ডুয়া",
                                                "pandua"]),
    ("dinajpur_n", "উত্তর দিনাজপুর", "Uttar Dinajpur", 25.6200, 88.1200, ["uttar dinajpur", "north dinajpur", "রায়গঞ্জ",
                                                                         "raiganj", "ইসলামপুর", "islampur"]),
    ("dinajpur_s", "দক্ষিণ দিনাজপুর", "Dakshin Dinajpur", 25.2200, 88.7700, ["dakshin dinajpur", "south dinajpur",
                                                                            "বালুরঘাট", "balurghat", "গঙ্গারামপুর",
                                                                            "gangarampur"]),
    ("jalpaiguri", "জলপাইগুড়ি", "Jalpaiguri", 26.5167, 88.7333, ["ডুয়ার্স", "dooars", "duars", "মালবাজার", "malbazar",
                                                              "লাটাগুড়ি", "lataguri", "গরুমারা", "gorumara"]),
    ("alipurduar", "আলিপুরদুয়ার", "Alipurduar", 26.4830, 89.5220, ["জলদাপাড়া", "jaldapara", "বক্সা", "buxa"]),
    ("coochbehar", "কোচবিহার", "Cooch Behar", 26.3240, 89.4510, ["koch bihar", "coochbehar", "দিনহাটা", "dinhata"]),
    ("darjeeling", "দার্জিলিং", "Darjeeling", 27.0410, 88.2663, ["শিলিগুড়ি", "siliguri", "কার্শিয়াং", "kurseong",
                                                             "মিরিক", "mirik", "ডাওহিল", "dow hill"]),
    ("kalimpong", "কালিম্পং", "Kalimpong", 27.0594, 88.4695, ["লোলেগাঁও", "lolegaon"]),
]
DISTRICT = {d[0]: d for d in WB_DISTRICTS}
DISTRICT_HI = {"kolkata": "कोलकाता", "howrah": "हावड़ा", "n24": "उत्तर 24 परगना", "s24": "दक्षिण 24 परगना",
               "hooghly": "हुगली", "bardhaman_p": "पूर्व बर्धमान", "bardhaman_w": "पश्चिम बर्धमान", "nadia": "नदिया",
               "murshidabad": "मुर्शिदाबाद", "birbhum": "बीरभूम", "bankura": "बांकुड़ा", "purulia": "पुरुलिया",
               "medinipur_w": "पश्चिम मेदिनीपुर", "medinipur_e": "पूर्व मेदिनीपुर", "jhargram": "झाड़ग्राम",
               "malda": "मालदा", "dinajpur_n": "उत्तर दिनाजपुर", "dinajpur_s": "दक्षिण दिनाजपुर",
               "jalpaiguri": "जलपाईगुड़ी", "alipurduar": "अलीपुरद्वार", "coochbehar": "कूचबिहार",
               "darjeeling": "दार्जिलिंग", "kalimpong": "कालिम्पोंग"}
_BN_DIG = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def district_name(key, lang):
    return DISTRICT_HI.get(key, DISTRICT[key][2]) if lang == "hi" else DISTRICT[key][1]


def district_day():
    try:
        return max(0, min(6, int(env("DISTRICT_DAY") or 1)))     # 1 = Tuesday (2 PM: the village story)
    except ValueError:
        return 1


def district_hits(text):
    """{district key: how often it is named} in a text - Bengali, Hindi or English, towns included. Longer names
    are found first and taken out, so 'পশ্চিম বর্ধমান' is never also counted as 'বর্ধমান'."""
    t = " " + str(text or "").lower().translate(_BN_DIG) + " "
    pairs = []
    for key, bn, en, _la, _lo, aka in WB_DISTRICTS:
        for w in [bn, en.lower(), DISTRICT_HI.get(key, "")] + [a.lower() for a in aka]:
            if w:
                pairs.append((w.translate(_BN_DIG), key))
    pairs.sort(key=lambda p: -len(p[0]))
    out = {}
    for w, key in pairs:
        if w.isascii():                              # English: whole words only ('suri' is not in 'surinder'),
            end = r"(?:r|er|e|te|y|ey|tei|rei)?" if len(w) >= 5 else ""     # Banglish endings: 'puruliar'
            rx = re.compile(r"(?<![a-z])" + re.escape(w) + end + r"(?![a-z])")
        else:                                        # Bengali / Hindi: the word may carry an ending ('পুরুলিয়ার')
            rx = re.compile(r"(?<![ঀ-৿ऀ-ॿ])" + re.escape(w))
        n = len(rx.findall(t))
        if n:
            out[key] = out.get(key, 0) + n
            t = rx.sub(" ", t)
    return out


def story_district(story):
    """Which district of West Bengal this story happens in (for its pin on the map), or None."""
    text = " ".join([str(story.get("setting", "")), str(story.get("title", "")), str(story.get("description", ""))]
                    + [str(sc.get("place", "")) for sc in story.get("scenes") or [] if isinstance(sc, dict)])
    hits = district_hits(text)
    if hits:
        return max(hits, key=hits.get)
    key = env("GEMINI_API_KEY")
    if not key or MOCK:
        return None
    ask = ("In which district of West Bengal (India) does this story happen? Answer with ONLY one of these keys, "
           "or the word none if it is not clearly in West Bengal: " + ", ".join(d[0] for d in WB_DISTRICTS)
           + "\nSTORY: " + text[:1500])
    for model in extras.helper_models(key)[:3]:
        try:
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json={"contents": [{"parts": [{"text": ask}]}],
                                    "generationConfig": {"temperature": 0}}, timeout=60)
            if r.ok:
                ans = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip().lower().strip(" .'\"`")
                return ans if ans in DISTRICT else None
        except Exception:
            continue
    return None


def _age_days(h):
    try:
        t = dt.datetime.fromisoformat(str(h.get("date")))
        return (dt.datetime.now(dt.timezone.utc) - t.replace(tzinfo=t.tzinfo or dt.timezone.utc)).total_seconds() / 86400
    except Exception:
        return 999


def voted_district(history):
    """This week's district: the one our viewers named most in the last week's comments (one vote per person
    and district; not one of the last four weeks' districts; Kolkata has the city stories). No votes yet: the
    next district in turn, said honestly ('এ সপ্তাহের জেলা'). Returns (key, votes)."""
    recent = [h.get("district_week") for h in history if h.get("district_week")][-4:]
    votes, seen = {}, set()
    if not MOCK:
        for h in history[-24:]:
            if not (h.get("facebook") or h.get("youtube")) or _age_days(h) > 8:
                continue
            try:
                for c in extras.post_comments(h.get("facebook"), h.get("youtube")):
                    who = str(c.get("name") or c.get("id") or "").lower()
                    for k in district_hits(c.get("text", "")):
                        if (who, k) not in seen:
                            seen.add((who, k))
                            votes[k] = votes.get(k, 0) + 1
            except Exception:
                pass
    ranked = sorted((k for k in votes if k not in recent and k != "kolkata"), key=lambda k: -votes[k])
    if ranked:
        return ranked[0], votes[ranked[0]]
    order = [d[0] for d in WB_DISTRICTS if d[0] != "kolkata"]
    used = [h.get("district_week") for h in history if h.get("district_week")]
    left = [k for k in order if k not in used[-(len(order) - 1):]] or order
    return left[0], 0


def weekly_district(cat, slot_hour, prev, fest, amavasya, special, history, lang):
    """Tuesday 2 PM (the village story): the story happens in this week's district. Returns the writer's rule."""
    if (env("DISTRICT_VOTE") == "0" or lang != "bn" or cat != "gram" or slot_hour != NOON or prev or fest
            or amavasya or special or STATE.get("creator_story")
            or dt.datetime.now(extras.IST).weekday() != district_day()):
        return ""
    key, votes = voted_district(history)
    STATE["district"], STATE["district_votes"] = key, votes
    d = DISTRICT[key]
    log(f"This week's district: {d[2]} ({votes} viewers asked for it)" if votes else
        f"This week's district (in turn - no viewer named one yet): {d[2]}")
    return (f"\nTHIS WEEK'S DISTRICT ({'chosen by our viewers' if votes else 'our district of the week'}): the "
            f"story happens in a village of {d[2]} district, West Bengal ({d[1]}) - even if a source story below "
            "is set elsewhere, move it there. Give it that district's real character: its land and rivers, crops and "
            "trades, local food and festivals, a touch of the local way of speaking and the folk beliefs told there "
            "(only true facts, never invented ones). The village and every person in it are invented - no real "
            "person's name or address. Name the district early in the story, naturally.\n")


def district_line(lang):
    """Said right after the story's name in the video, e.g. 'আপনাদের ভোটে এ সপ্তাহের জেলা: পুরুলিয়া।'"""
    key = STATE.get("district")
    if not key or key not in DISTRICT:
        return ""
    U = UNIQ.get(lang, UNIQ["bn"])
    return (U["district_vote"] if STATE.get("district_votes") else U["district_week"]).format(d=district_name(key, lang))


# ----------------------------------------------------------------- 5) viewers who asked to be in a story
NAME_TAGS = ("#আমার_নাম", "#আমারনাম", "#আমার নাম", "#amar_naam", "#amarnaam", "#amar_nam", "#मेरा_नाम", "#मेरानाम",
             "#mera_naam", "#meranaam")
_SCRIPT = {"bn": "ঀ-৿", "hi": "ऀ-ॿ"}


def optin_names(history, n=2):
    """First names of viewers who ASKED to be in a story (a comment with #আমার_নাম in the last days) - never
    anyone else, and nobody twice within about two weeks. [(first name, comment id, 'fb'/'yt')]"""
    used = {str(x[0] if isinstance(x, (list, tuple)) else x).lower()
            for h in history[-30:] for x in (h.get("viewer_names") or [])}
    if MOCK:                                         # (tests: names from TEST_VIEWER_NAMES)
        return [(x.strip(), "", "") for x in env("TEST_VIEWER_NAMES").split(",")
                if x.strip() and x.strip().lower() not in used][:n]
    page = " ".join(env(k) for k in ("PAGE_NAME_BN", "PAGE_NAME_HI", "PAGE_NAME")).lower()
    out = []
    for h in reversed(history[-8:]):
        if not (h.get("facebook") or h.get("youtube")) or _age_days(h) > 5:
            continue
        try:
            for c in extras.post_comments(h.get("facebook"), h.get("youtube")):
                low = str(c.get("text", "")).lower()
                if not any(tg in low for tg in NAME_TAGS) or "পরের কোনো গল্পে" in low or "अगली किसी कहानी" in low:
                    continue                          # (never our own invitation text)
                first = re.sub(r"[^A-Za-zঀ-৿ऀ-ॿ]", "", str(c.get("name") or ""))
                if re.match(r"(?i)^user", first) and re.search(r"\d", str(c.get("name") or "")):
                    continue                          # (YouTube's automatic '@user-1a2b3c' names)
                if (2 <= len(first) <= 14 and first.lower() not in page and first.lower() not in used
                        and first.lower() not in {o[0].lower() for o in out}):
                    out.append((first, str(c.get("id") or ""), str(c.get("src") or "")))
        except Exception:
            pass
        if len(out) >= n:
            break
    return out[:n]


def local_names(names, lang):
    """The names written in the story's own script (Bengali / Devanagari), as the writer must use them:
    [[name as the viewer wrote it, name in the story, comment id, src]]"""
    rng = _SCRIPT.get(lang, _SCRIPT["bn"])
    done, todo = [], []
    for nm, cid, src in names:
        if re.fullmatch(f"[{rng}]+", nm):
            done.append([nm, nm, cid, src])
        else:
            todo.append((nm, cid, src))
    key = env("GEMINI_API_KEY")
    if todo and key and not MOCK:
        ask = (f"These are viewers' names from YouTube / Facebook. For each one: if it is a real person's first name, "
               f"write that first name in {'Bengali' if lang == 'bn' else 'Hindi (Devanagari)'} script exactly as it "
               "is pronounced (a first name joined to a surname, like 'sumonkumar', gives only the first name). If it is "
               "NOT a real first name (a nickname, a handle, a brand, a word, random letters, anything rude), give an "
               "empty string. Answer ONLY a JSON list of strings, same order: "
               + json.dumps([t[0] for t in todo], ensure_ascii=False))
        for model in extras.helper_models(key)[:3]:
            try:
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                                  json={"contents": [{"parts": [{"text": ask}]}],
                                        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
                                  timeout=60)
                if r.ok:
                    got = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                    if isinstance(got, list) and len(got) == len(todo):
                        for (nm, cid, src), loc in zip(todo, got):
                            loc = str(loc).strip()
                            if loc and re.fullmatch(f"[{rng}]+", loc) and len(loc) <= 14:
                                done.append([nm, loc, cid, src])
                            elif not loc:
                                log(f"  '{nm}' does not look like a first name - left out")
                        break
            except Exception:
                continue
    elif todo and MOCK:
        done += [[nm, nm, cid, src] for nm, cid, src in todo]
    return done


def viewer_names_rule(cat, special, part, festival, history, lang):
    """The writer's rule that gives viewers who asked for it a small, kind part in today's story."""
    if (env("VIEWER_NAMES") == "0" or not STATE.get("own_kind") or special or festival or part > 1
            or cat not in ("gram", "shohor", "jayga")):
        return ""
    pairs = local_names(optin_names(history), lang)
    if not pairs:
        return ""
    STATE["viewer_names"] = pairs
    log("Viewers who asked to be in a story: " + ", ".join(f"{p[0]} ({p[1]})" for p in pairs))
    shown = ", ".join(p[1] for p in pairs)
    return (f"\nOUR VIEWERS IN THE STORY: these viewers asked to be in one of our stories - use exactly these first "
            f"names, written exactly like this: {shown}. Give each ONE small, KIND side role (a helpful neighbour, the "
            "tea-stall owner who warns the hero, a ferryman, a friend who comes with a torch, the doctor who "
            "helps...). Never the ghost, a villain or a victim; never someone who dies, is hurt, possessed or made "
            "fun of. The story stays the same story - they are small parts of it.\n")


def names_in_story(story):
    """The viewers' names that really made it into the story (only they are thanked)."""
    pairs = STATE.get("viewer_names") or []
    if not pairs:
        return []
    text = " ".join([str(story.get("title", ""))] + [str(c.get("name_local") or "") + " " + str(c.get("name") or "")
                                                     for c in story.get("characters") or [] if isinstance(c, dict)]
                    + [str(ln.get("text", "")) for sc in story.get("scenes") or [] if isinstance(sc, dict)
                       for ln in sc.get("lines") or [] if isinstance(ln, dict)])
    return [p for p in pairs if p[1] and p[1] in text]


def uniq_top_lines(lang, used_names):
    """Short lines right under the title of the description (Facebook keeps them - they come first)."""
    U = UNIQ.get(lang, UNIQ["bn"])
    rows = []
    dl = district_line(lang)
    if dl:
        rows.append(U["district_top"].format(line=dl))
    if used_names:
        rows.append(U["names_thanks"].format(names=", ".join(p[1] for p in used_names)))
    return "\n".join(rows)


def uniq_invites(lang, youtube=False):
    """The invitations at the end of the YouTube description and in the first comment."""
    U = UNIQ.get(lang, UNIQ["bn"])
    rows = []
    if env("DISTRICT_VOTE") != "0" and lang == "bn" and not NO_BAIT:
        rows.append(U["district_invite"].format(day=BN_DAYS[district_day()]))
    if youtube and env("VIEWER_NAMES") != "0" and not NO_BAIT:       # (only on YouTube: Facebook dislikes 'comment X' asks)
        rows.append(U["names_invite"])
    url = map_url()
    if url:
        rows.append(U["map_line"].format(url=url))
    return rows


def thank_named_viewers(used_names, results, lang):
    """A reply under each Facebook comment that asked for it: 'your name is in today's story' + the link."""
    if not used_names or not results.get("facebook") or DRY_RUN:
        return
    U = UNIQ.get(lang, UNIQ["bn"])
    for p in used_names:
        if len(p) >= 4 and p[3] == "fb" and p[2]:
            try:
                extras.fb_comment(p[2], f"{U['names_reply']} https://www.facebook.com/{results['facebook']}")
            except Exception as e:
                log("  thank-you reply not posted:", str(e)[:100])


# ----------------------------------------------------------------- 3) the ghost map (GitHub Pages)
MAP_DIR = os.path.join(HERE, "docs")
MAP_JSON = os.path.join(MAP_DIR, "stories.json")
MAP_HTML = os.path.join(MAP_DIR, "index.html")
MAP_VERSION = "ghost-map-v2"
MAP_PAGE = """<!doctype html>
<html lang="bn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<!-- ghost-map-v2 -->
<title>বাংলার ভূতের মানচিত্র</title>
<meta name="description" content="বাংলার প্রতিটা জেলার ভূতের গল্প - মানচিত্রে। Bengali horror stories on a map.">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{--bg:#0b0b10;--card:#16161f;--text:#f2efe9;--muted:#a9a3b5;--red:#e23b3b;--gold:#ffcf4a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font-family:"Noto Sans Bengali","Hind Siliguri",system-ui,sans-serif}
header{padding:18px 16px 8px;text-align:center}h1{margin:0;font-size:1.6rem;color:var(--gold)}
header p{margin:6px 0 0;color:var(--muted)}#map{height:60vh;margin:10px 12px;border-radius:14px;border:1px solid #2a2a38}
main{max-width:860px;margin:0 auto;padding:6px 16px 40px}.d{margin:18px 0 6px;font-size:1.15rem;color:var(--gold)}
.s{background:var(--card);border-radius:12px;padding:12px 14px;margin:8px 0;border-left:4px solid var(--red)}
.s b{display:block;margin-bottom:6px}.s a{color:#ffd9d9;margin-right:14px;text-decoration:none}
.s small{color:var(--muted)}.leaflet-popup-content a{margin-right:10px}
footer{color:var(--muted);text-align:center;font-size:.85rem;padding:20px}
</style></head><body>
<header><h1>👻 বাংলার ভূতের মানচিত্র</h1><p>প্রতিটা লাল বিন্দু একটা গল্প - নিজের জেলায় চাপ দিন</p>
<p><a href="cases.html" style="color:#ffcf4a;font-weight:700;text-decoration:none">📁 ভৈরব ঠাকুর, তারানাথ ও কর্ণপিশাচিনীর কেস ফাইল →</a></p></header>
<div id="map"></div><main id="list"><p>লোড হচ্ছে...</p></main>
<footer>প্রতিটা নতুন গল্পের সাথে মানচিত্র নিজে থেকেই বাড়ে · গল্পগুলো লোককথা অবলম্বনে / কাল্পনিক, যদি না অন্য কিছু লেখা থাকে</footer>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var map=L.map('map',{scrollWheelZoom:false});map.fitBounds([[21.6,85.8],[27.3,89.9]]);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:12,attribution:'&copy; OpenStreetMap'}).addTo(map);
function esc(s){return String(s||'').replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function links(x){var o='';if(x.fb)o+='<a href="'+esc(x.fb)+'" target="_blank" rel="noopener">▶ Facebook</a>';
if(x.yt)o+='<a href="'+esc(x.yt)+'" target="_blank" rel="noopener">▶ YouTube</a>';return o}
fetch('stories.json?'+Date.now()).then(function(r){return r.json()}).then(function(all){
 all.sort(function(a,b){return (b.date||'').localeCompare(a.date||'')});var by={};
 all.forEach(function(x){if(x.lat&&x.lon){L.circleMarker([x.lat,x.lon],{radius:8,color:'#ffcf4a',weight:2,
  fillColor:'#e23b3b',fillOpacity:.9}).addTo(map).bindPopup('<b>'+esc(x.t)+'</b><br><small>'+esc(x.dn)+' · '
  +esc(x.date)+'</small><br>'+links(x))}(by[x.dn]=by[x.dn]||[]).push(x)});
 var h='';Object.keys(by).sort(function(a,b){return by[b].length-by[a].length}).forEach(function(d){
  h+='<div class="d">'+esc(d)+' ('+by[d].length+')</div>';by[d].forEach(function(x){
  h+='<div class="s"><b>'+esc(x.t)+'</b><small>'+esc(x.date)+'</small><br>'+links(x)+'</div>'})});
 document.getElementById('list').innerHTML=h||'<p>প্রথম গল্পের অপেক্ষা...</p>';
}).catch(function(){document.getElementById('list').innerHTML='<p>এখনো কোনো গল্প যোগ হয়নি।</p>'});
</script></body></html>
"""
MAP_LIVE = {}


def map_url():
    """The map's address - only once GitHub Pages really shows it (no dead link is ever posted)."""
    if "url" in MAP_LIVE:
        return MAP_LIVE["url"]
    url = env("MAP_URL")
    if not url:                                      # (the main address keeps the privacy page; the map is /map/)
        repo = env("GITHUB_REPOSITORY")
        if "/" in repo:
            owner, name = repo.split("/", 1)
            url = f"https://{owner.lower()}.github.io/{name}/map/"
    ok = ""
    flag = os.path.join(MAP_DIR, "live.txt")
    if url and not MOCK and env("GHOST_MAP") != "0":
        for _try in range(3):                         # v87: one slow answer from GitHub Pages no longer turns off
            try:                                      # the story page and the podcast episode for the whole run
                r = requests.get(url, timeout=25)
                ok = url if r.ok and "ভূতের মানচিত্র" in r.content.decode("utf-8", "ignore") else ""
            except Exception:
                ok = ""
            if ok:
                break
            time.sleep(5)
        if not ok and os.path.exists(flag):           # it was live before: a short hiccup, keep using it
            ok = url
            log("  ghost map did not answer just now - it was live before, so its address is used")
    MAP_LIVE["url"] = ok
    if ok and not os.path.exists(flag) and not DRY_RUN:     # the first time it works: tell you on Telegram
        try:
            with open(flag, "w") as f:
                f.write(ok)
            push_now([flag], "ghost map is live")
            extras.telegram(f"🗺️ আপনার 'বাংলার ভূতের মানচিত্র' চালু হয়ে গেছে: {ok}\n"
                            "এখন থেকে প্রতিটা গল্পের প্রথম comment-এ এই link যাবে।")
        except Exception as e:
            log("  map notice skipped:", str(e)[:100])
    return ok


def _pin(title, key, lang, fb_id, yt_id, date, cat_name=""):
    d = DISTRICT[key]
    rnd = random.Random(str(fb_id or yt_id or title))     # the same story always gets the same spot
    return {"t": re.sub(r"\s*\|.*$", "", str(title)).strip()[:90], "d": key, "dn": f"{d[1]} ({d[2]})",
            "lat": round(d[3] + rnd.uniform(-0.12, 0.12), 4), "lon": round(d[4] + rnd.uniform(-0.12, 0.12), 4),
            "fb": f"https://www.facebook.com/watch/?v={fb_id}" if fb_id else "",
            "yt": f"https://youtu.be/{yt_id}" if yt_id else "", "cat": cat_name, "lang": lang, "date": date}


def ensure_map_page(history):
    """Makes the map website (docs/ folder) once - with the pins of the old stories whose place we can tell -
    so GitHub Pages can show it as soon as you switch Pages on."""
    if MOCK or DRY_RUN or env("GHOST_MAP") == "0" or env("GITHUB_ACTIONS") != "true":
        return
    try:
        cur = open(MAP_HTML, encoding="utf-8").read() if os.path.exists(MAP_HTML) else ""
    except Exception:
        cur = ""
    if MAP_VERSION in cur and os.path.exists(MAP_JSON):
        return
    os.makedirs(MAP_DIR, exist_ok=True)
    with open(MAP_HTML, "w", encoding="utf-8") as f:
        f.write(MAP_PAGE)
    with open(os.path.join(MAP_DIR, ".nojekyll"), "w") as f:
        f.write("")
    items = _jload(MAP_JSON, None)
    if not isinstance(items, list):
        items = []
        for h in history:
            if h.get("kind") or not (h.get("facebook") or h.get("youtube")):
                continue
            hits = district_hits(" ".join(str(h.get(k) or "") for k in ("title", "theme", "idea_used", "source")))
            key = h.get("district") or (max(hits, key=hits.get) if hits else None)
            if key in DISTRICT:
                items.append(_pin(h.get("title", ""), key, h.get("lang", "bn"), h.get("facebook"), h.get("youtube"),
                                  str(h.get("date", ""))[:10], h.get("category") or ""))
        _jsave(MAP_JSON, items)
    log(f"Ghost map website made (docs/ folder, {len(items)} old stories on it)")
    try:
        cases_page(history)
    except Exception as e:
        log("  case files skipped:", str(e)[:120])
    push_now([MAP_DIR], "ghost map website")


# ----------------------------------------------------------------- v70: the case files of our series (website)
CASES_HTML = os.path.join(MAP_DIR, "cases.html")
CASE_SERIES = [("bhairab", "🕵️ ভৈরব ঠাকুরের কেস ফাইল", "অলৌকিক রহস্যের সন্ধানী ভৈরব ঠাকুর আর তার সঙ্গী পল্টু"),
               ("taranath", "🕯️ তারানাথ তান্ত্রিকের খাতা", "বৃদ্ধ তারানাথ নিজের মুখে শোনান তাঁর জীবনের অভিজ্ঞতা"),
               ("karna", "👂 কর্ণপিশাচিনী", "নীলকণ্ঠ আচার্য, ভাগ্নে বাপি আর কানে-কানে কথা বলা সেই পিশাচিনী")]

# ===================================================================================================== v80: new series
# Five ORIGINAL horror series (13 Nov 2026), shaped after the KINDS of shows that are most heard in Bengali horror on
# YouTube and podcasts right now - late-night call-in shows, hospital / morgue night duty, railway nights, ghost-hunting
# teams, a lonely bungalow's register - with our own people, names and stories (nothing taken from any show).
# They take turns on Thursday and Saturday night; every episode is one complete case.
NEW_SERIES = {
    "nishi": {
        "bn": "নিশি-রেডিও", "hi": "निशि रेडियो", "icon": "📻",
        "about": "NISHI RADIO - a late-night Kolkata FM show at 1 AM where listeners phone in their own true ghost experience",
        "fmt": "RJ Mohona takes a listener's call live at night; the caller's experience is acted out in full, then back to the studio",
        "cast": [{"name": "Mohona", "name_local": "মোহনা", "gender": "female", "age": "adult", "kind": "human",
                  "look": "RJ Mohona, a Bengali woman of about thirty-five, shoulder-length wavy black hair, big silver "
                          "headphones round her neck, a dark kurta, a small red bindi, sitting at a radio desk with a "
                          "glowing ON AIR sign and a microphone, warm calm eyes"}],
        "voices": {"mohona": "Aoede"},
        "rule": ("Every episode is ONE complete call: RJ MOHONA opens the 1 AM show warmly, a listener (a NEW person "
                 "every time, with a name and a town) calls in and tells what happened to them - this is the main story, "
                 "acted out fully with its own people and scenes; Mohona comes back between the parts with one or two "
                 "short, gentle questions. The last scene is back in the studio, with ONE quiet chill that ties the call "
                 "to Mohona herself (never the same chill twice). The caller's story must have a clear start: who, where, "
                 "when, why they were there."),
        "bible": ("RJ MOHONA speaks softly and warmly, like a friend at night; never mocks a caller; says 'আপনি বলুন, "
                  "আমি শুনছি' kind of things; a little afraid herself but steady on air."),
        "themes": ["a call from a night-shift security guard of a closed cinema hall", "a call from a nurse in a rural "
                   "health centre", "a call from a truck driver on NH-19 at night", "a call from a girl alone in a PG in Salt Lake"],
        "q": {"bn": ["ভূতের অভিজ্ঞতা রেডিও", "সত্যি ভৌতিক অভিজ্ঞতা শ্রোতার", "bhoot fm style golpo"], "hi": ["real horror call radio", "listener horror experience hindi"]},
    },
    "morg": {
        "bn": "মর্গের খাতা", "hi": "मुर्दाघर की डायरी", "icon": "🏥",
        "about": "THE MORGUE REGISTER - night duty in the morgue of an old Kolkata hospital, one body and one night each time",
        "fmt": "old night-guard Haradhan tells young doctor Ritam about one body and one night from his register",
        "cast": [{"name": "Haradhan", "name_local": "হারাধন", "gender": "male", "age": "old", "kind": "human",
                  "look": "Haradhan, the morgue's night guard, a lean Bengali man of about sixty-two, grey stubble, deep "
                          "lines on his face, a faded khaki uniform shirt, a bunch of old keys at his waist, an old torch "
                          "and a thick register book"},
                 {"name": "Ritam", "name_local": "ঋতম", "gender": "male", "age": "young", "kind": "human",
                  "look": "Dr Ritam, a young Bengali intern of about twenty-six, neat short hair, thin glasses, a white "
                          "doctor's coat over a blue shirt, a stethoscope round his neck, tired curious eyes"}],
        "voices": {"haradhan": "Schedar", "ritam": "Umbriel"},
        "rule": ("Every episode is ONE complete case from HARADHAN's old morgue register (a different body, a different "
                 "year): young DR RITAM, new on night duty, asks; Haradhan tells - and the night of that case is acted "
                 "out in full. Real hospital detail (cold room, tags, the lift, the long corridor, the night staff), "
                 "respectful to the dead, no gore. End: back in the present night, one small sign that the case is not "
                 "over."),
        "bible": ("HARADHAN speaks slowly, plainly, like an old worker who has seen everything; calls Ritam 'ডাক্তারবাবু'; "
                  "never boasts, respects the dead. RITAM is rational, polite, slowly shaken."),
        "themes": ["the body that came back to bed number nine", "a tag with a name that was never written",
                   "the night the cold-room door would not stay shut"],
        "q": {"bn": ["হাসপাতালের ভূতের গল্প", "মর্গের ভূতের গল্প", "hospital horror story bangla"], "hi": ["hospital horror story hindi", "मुर्दाघर की कहानी"]},
    },
    "local": {
        "bn": "শেষ লোকাল", "hi": "आख़िरी लोकल", "icon": "🚆",
        "about": "THE LAST LOCAL - the last local train of the night on a Kolkata suburban line, one passenger each time",
        "fmt": "old guard Anadi Bose remembers one passenger from one last-local night",
        "cast": [{"name": "Anadi", "name_local": "অনাদি", "gender": "male", "age": "old", "kind": "human",
                  "look": "Guard Anadi Bose, a Bengali railway guard of about fifty-six, grey moustache, a black railway "
                          "coat with brass buttons, a guard's cap, a green-and-red signal lamp in his hand, kind tired eyes"}],
        "voices": {"anadi": "Alnilam"},
        "rule": ("Every episode is ONE passenger on the last local of the night (a different line and station each time - "
                 "Sealdah south, Howrah main, Bandel, Canning ...): GUARD ANADI BOSE remembers; the passenger's night is "
                 "acted out in full - the empty compartment, the dark platforms, the station that should not be there. "
                 "Clear start: who boarded, where, why so late. End: Anadi's last line about that train."),
        "bible": ("ANADI speaks like a gentle old railwayman: short sentences, railway words (প্ল্যাটফর্ম, সিগন্যাল, "
                  "গার্ডের কামরা), a little sad, never laughs at the dead."),
        "themes": ["the woman who got down at a station that closed in 1971", "the compartment where the fan turned by itself",
                   "the child who asked for the last stop every night"],
        "q": {"bn": ["ট্রেনের ভূতের গল্প", "লোকাল ট্রেনের ভূত", "railway station bhuter golpo"], "hi": ["train horror story hindi", "रेलवे स्टेशन भूत"]},
    },
    "tadanta": {
        "bn": "রাত-তদন্ত", "hi": "रात की तहक़ीक़ात", "icon": "🔦",
        "about": "NIGHT INVESTIGATION - a young ghost-hunting team with a camera and a sound recorder spends one night in a haunted place",
        "fmt": "Riya and Tanmoy's team spends one night in a haunted place with their camera and recorder",
        "cast": [{"name": "Riya", "name_local": "রিয়া", "gender": "female", "age": "young", "kind": "human",
                  "look": "Riya Sen, the team leader, a Bengali woman of about twenty-six, hair in a high ponytail, a dark "
                          "green jacket, cargo trousers, a small digital sound recorder in her hand, a headlamp, brave sharp eyes"},
                 {"name": "Tanmoy", "name_local": "তন্ময়", "gender": "male", "age": "young", "kind": "human",
                  "look": "Tanmoy, the cameraman, a stocky Bengali man of about twenty-eight, short beard, a black hoodie, "
                          "a camera with a night-vision light on his shoulder, a backpack of cables"}],
        "voices": {"riya": "Zephyr", "tanmoy": "Orus"},
        "rule": ("Every episode is ONE night in ONE real-sounding haunted place of Bengal (a different place every time): "
                 "RIYA (believes, careful) and TANMOY (does not believe, jokes) arrive at dusk, set up the camera and "
                 "recorder, talk to one local person, and the night goes wrong step by step; the recorder catches a "
                 "voice. Clear start (why this place, who told them about it). End: the next morning, what the "
                 "recording really says."),
        "bible": ("RIYA is calm, brave, respectful to the place, speaks quickly when excited. TANMOY makes jokes to hide "
                  "fear, calls her 'রিয়াদি', is the first to run and the first to come back for her."),
        "themes": ["a closed jute mill by the Hooghly", "an abandoned TB sanatorium in the hills", "a rajbari with one locked room"],
        "q": {"bn": ["প্যারানর্মাল ইনভেস্টিগেশন বাংলা", "ভূতুড়ে জায়গায় এক রাত", "ghost hunting bangla"], "hi": ["paranormal investigation hindi", "haunted place one night hindi"]},
    },
    "bungalow": {
        "bn": "ডাকবাংলোর খাতা", "hi": "डाक बंगले का रजिस्टर", "icon": "🏚️",
        "about": "THE BUNGALOW REGISTER - an old forest dak bungalow in Purulia; one guest's night from its visitors' book each time",
        "fmt": "old chowkidar Mahadeb reads one old entry from the visitors' book and that guest's night is told",
        "cast": [{"name": "Mahadeb", "name_local": "মহাদেব", "gender": "male", "age": "old", "kind": "human",
                  "look": "Mahadeb Mahato, the chowkidar of an old forest dak bungalow, a dark thin Bengali man of about "
                          "sixty-five, white stubble, a checked gamchha on his shoulder, a brown shawl, a hurricane lantern, "
                          "an old cloth-bound visitors' book under his arm"}],
        "voices": {"mahadeb": "Iapetus"},
        "rule": ("Every episode is ONE entry of the bungalow's old visitors' book (a different year and guest each time): "
                 "CHOWKIDAR MAHADEB opens the book by lantern light and the guest's night is acted out in full - the "
                 "forest, the generator going off, the room at the end of the verandah. Clear start (who came, from where, "
                 "why). End: Mahadeb closes the book - and the last line in it is new."),
        "bible": ("MAHADEB speaks in plain Purulia-touched Bengali, slowly, kind but full of warnings he never fully explains; "
                  "calls guests 'বাবু' / 'দিদিমণি'."),
        "themes": ["a young couple on their honeymoon in 1984", "a forest officer in the monsoon of 1962", "three college friends in the winter of 1998"],
        "q": {"bn": ["ডাকবাংলোর ভূতের গল্প", "জঙ্গলের বাংলোর ভূত", "purulia bhuter golpo"], "hi": ["dak bungalow horror story", "jungle bungalow bhoot"]},
    },
}
SERIES_IDS = ("bhairab", "taranath", "karna") + tuple(NEW_SERIES)
for _k, _s in NEW_SERIES.items():
    LANGS["bn"][_k] = f"{_s['bn']} #{{n}}"
    LANGS["bn"][_k + "_pl"] = f"{_s['bn']} - {_k.title()} Horror Series"
    LANGS["hi"][_k] = f"{_s['hi']} #{{n}}"
    LANGS["hi"][_k + "_pl"] = f"{_s['hi']} - {_k.title()} Horror Series"
    SERIES_RX[_k] = re.escape(_s["bn"]) + "|" + re.escape(_s["hi"])
    SERIES_BIBLE[_k] = _s["bible"]
    SERIES_VOICES.update(_s["voices"])
    CASE_SERIES.append((_k, f"{_s['icon']} {_s['bn']}", _s["about"].split(" - ", 1)[-1]))
    extras.CAT_QUERIES[("horror", _k)] = _s["q"]       # (its own YouTube search for this week's trend)


def series_cast(special, theme="", crossover=False):
    """the fixed people of a series (old and new)"""
    if special in NEW_SERIES:
        return [dict(c) for c in NEW_SERIES[special]["cast"]]
    return {"bhairab": BHAIRAB + (KARNA if crossover else []),
            "taranath": TARANATH + (MADHU_CAST if theme == "madhusundari" else []), "karna": KARNA}.get(special, [])


def series_label(special, L):
    if special in NEW_SERIES or special in ("taranath", "karna"):
        return L[special].split(" #")[0]
    if special == "bhairab":
        return L["bhairab"].split(" #")[0].replace("ের কেস", "").replace(" का केस", "")
    return None


def pick_new_series(history):
    """the next of our new series: the one not heard for the longest time (a series that people clearly watch
    less is given fewer turns once there are numbers)"""
    last = {k: "" for k in NEW_SERIES}
    sc = {k: [] for k in NEW_SERIES}
    for h in history:
        if h.get("special") in NEW_SERIES:
            last[h["special"]] = max(last[h["special"]], str(h.get("date", "")))
            if h.get("stats"):
                sc[h["special"]].append(extras.score(h["stats"]))
    avg = {k: (sum(v) / len(v)) for k, v in sc.items() if len(v) >= 3}
    weak = {k for k, a in avg.items() if avg and a < 0.5 * (sum(avg.values()) / len(avg))}
    order = sorted(NEW_SERIES, key=lambda k: (k in weak, last[k]))
    return order[0]


def new_series_rule(special, history, lang):
    s = NEW_SERIES[special]
    n = 1 + sum(1 for h in history if h.get("special") == special)
    return (f"\nOUR OWN ORIGINAL SERIES '{s['bn']}' ({s['about']}), episode {n} - never copy any existing show, "
            f"podcast, book or film; our own people and stories only.\n{s['rule']}\nThe fixed people and their looks "
            f"(use EXACTLY these names and looks): {json.dumps(s['cast'], ensure_ascii=False)}. Every other person is "
            "new in this episode. Women are always played as women.\n")


def cases_page(history):
    """docs/cases.html: every case of our three series in order - where it happened, whether it is solved, what
    happened (once it is over) and the links to every part. New viewers can watch a series from its first case.
    Returns True when the page changed."""
    import html
    if MOCK or DRY_RUN or env("GHOST_MAP") == "0" or env("CASE_FILES") == "0":
        return False
    bible = _jload(BIBLE_FILE, {})
    e = lambda s: html.escape(str(s or ""))
    body, total = "", 0
    for sp, head, about in CASE_SERIES:
        cases = {}
        for h in history:
            if h.get("special") != sp or h.get("kind") or not (h.get("facebook") or h.get("youtube")):
                continue
            base = re.sub(r"\s*\|.*$", "", str(h.get("title") or "")).strip()
            if base:
                cases.setdefault(h.get("series_id") or base, {"t": base, "parts": []})["parts"].append(h)
        if not cases:
            continue
        body += f'<h2>{e(head)}</h2><p class="a">{e(about)}</p>'
        for c in sorted(cases.values(), key=lambda c: str(c["parts"][0].get("date") or ""), reverse=True):
            parts = sorted(c["parts"], key=lambda h: (int(h.get("part") or 0), str(h.get("date") or "")))
            last = parts[-1]
            open_ = bool(last.get("continues"))
            dk = next((h.get("district") for h in parts if h.get("district") in DISTRICT), None)
            summ = next((b.get("summary") for b in bible.get(sp) or [] if b.get("title") == c["t"]), "")
            tag = next((h.get("tagline") for h in parts if h.get("tagline")), "")
            links = ""
            for h in parts:
                lab = f"পর্ব {str(h.get('part')).translate(str.maketrans('0123456789', '০১২৩৪৫৬৭৮৯'))}" if h.get("part") else "গল্প"
                links += f'<span class="p">{lab}: '
                if h.get("facebook"):
                    links += f'<a href="https://www.facebook.com/watch/?v={e(h["facebook"])}" target="_blank" rel="noopener">▶ Facebook</a>'
                if h.get("youtube"):
                    links += f'<a href="https://youtu.be/{e(h["youtube"])}" target="_blank" rel="noopener">▶ YouTube</a>'
                links += "</span>"
            body += (f'<div class="c{" o" if open_ else ""}"><b>{e(c["t"])}</b>'
                     f'<small>{e(str(parts[0].get("date") or "")[:10])}'
                     + (f' · {e(DISTRICT[dk][1])}' if dk else "")
                     + (" · ⏳ চলছে - পরের পর্ব আসছে" if open_ else " · ✅ শেষ হয়েছে") + "</small>"
                     + (f"<p>{e(tag)}</p>" if tag else "")
                     + (f"<p>{e(summ)}</p>" if summ and not open_ and re.search(r"[\u0980-\u09FF]", str(summ)) else "")
                     + links + "</div>")
            total += 1
    if not total:
        return False
    page = ("""<!doctype html>
<html lang="bn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>কেস ফাইল - ভূতের গল্পের সিরিজ</title>
<meta name="description" content="ভৈরব ঠাকুর, তারানাথ তান্ত্রিক আর কর্ণপিশাচিনীর সব গল্প - প্রথম থেকে পরপর।">
<style>
:root{--bg:#0b0b10;--card:#16161f;--text:#f2efe9;--muted:#a9a3b5;--red:#e23b3b;--gold:#ffcf4a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font-family:"Noto Sans Bengali","Hind Siliguri",system-ui,sans-serif}
header{padding:18px 16px 4px;text-align:center}h1{margin:0;font-size:1.5rem;color:var(--gold)}
header a{color:var(--gold);text-decoration:none;font-weight:700}main{max-width:860px;margin:0 auto;padding:6px 16px 40px}
h2{margin:26px 0 2px;font-size:1.25rem;color:var(--gold)}.a{margin:0 0 8px;color:var(--muted)}
.c{background:var(--card);border-radius:12px;padding:12px 14px;margin:10px 0;border-left:4px solid #3c8f5a}
.c.o{border-left-color:var(--red)}.c b{display:block;font-size:1.05rem}.c small{color:var(--muted)}
.c p{margin:8px 0;line-height:1.55}.p{display:inline-block;margin:8px 14px 0 0}.p a{color:#ffd9d9;margin-left:8px;text-decoration:none}
footer{color:var(--muted);text-align:center;font-size:.85rem;padding:20px}
</style></head><body>
<header><h1>📁 কেস ফাইল</h1><p><a href="./">← ভূতের মানচিত্রে ফিরুন</a></p></header><main>"""
            + body + "</main><footer>নতুন পর্ব এলেই এই পাতা নিজে থেকে বদলায় · গল্পগুলো কাল্পনিক</footer></body></html>\n")
    try:
        if os.path.exists(CASES_HTML) and open(CASES_HTML, encoding="utf-8").read() == page:
            return False
    except Exception:
        pass
    os.makedirs(MAP_DIR, exist_ok=True)
    with open(CASES_HTML, "w", encoding="utf-8") as f:
        f.write(page)
    log(f"  case files website: {total} cases")
    return True


def map_add(story, title, results, lang, cat_name=""):
    """The new story's pin on the ghost map (docs/stories.json), saved to GitHub at once. Returns its district."""
    if env("GHOST_MAP") == "0" or not (results.get("facebook") or results.get("youtube")):
        return None
    key = STATE.get("district") or story_district(story)
    if not key or key not in DISTRICT:
        log("  ghost map: this story is not set in a district of West Bengal - no pin")
        return None
    if MOCK or DRY_RUN:
        return key
    os.makedirs(MAP_DIR, exist_ok=True)
    items = _jload(MAP_JSON, [])
    items = items if isinstance(items, list) else []
    pin = _pin(title, key, lang, results.get("facebook"), results.get("youtube"),
               dt.datetime.now(extras.IST).date().isoformat(), cat_name)
    if not any((pin["fb"] and x.get("fb") == pin["fb"]) or (pin["yt"] and x.get("yt") == pin["yt"]) for x in items):
        items.append(pin)
        _jsave(MAP_JSON, items[-3000:])
    if not os.path.exists(MAP_HTML):
        with open(MAP_HTML, "w", encoding="utf-8") as f:
            f.write(MAP_PAGE)
    log(f"  ghost map: pin in {DISTRICT[key][2]} ({len(items)} stories on the map)")
    push_now([MAP_DIR], "ghost map: new story")
    return key


# ----------------------------------------------------------------- 1) the ghost dictionary (weekly)
GHOST_FILE = os.path.join(HERE, "assets", "ghost_dict.json")      # which ghosts were already told
GHOST_DICT = [   # Bengali folk belief (public domain), in the order they are told: bn, hi, English, gender, look
    ("শাঁকচুন্নি", "शाँकचुन्नी", "Shakchunni", "female",
     "the ghost of a married woman in a white sari with red-bordered conch-shell bangles, sitting in a tree beside a "
     "village pond at night"),
    ("ব্রহ্মদৈত্য", "ब्रह्मदैत्य", "Brahmadaitya", "male",
     "the tall pale ghost of an old Brahmin with a sacred thread and a white dhoti, sitting in an ancient bel tree"),
    ("নিশি", "निशि", "Nishi", "female",
     "a dark night spirit standing outside a village hut's door at midnight, calling a sleeping person's name"),
    ("মেছোভূত", "मेछो भूत", "Mechho Bhoot", "male",
     "a thin hungry ghost by a village pond at night, reaching for a basket of fresh fish"),
    ("পেত্নী", "पेत्नी", "Petni", "female",
     "a female ghost with long loose black hair and backward-turned feet, standing under a tamarind tree"),
    ("স্কন্ধকাটা", "स्कंधकाटा", "Skondhokata", "male",
     "a headless figure walking along a railway line between foggy paddy fields at night"),
    ("গেছোভূত", "गेछो भूत", "Gechho Bhoot", "male",
     "a ghost crouching high in the branches of a giant banyan tree above a dark village path"),
    ("আলেয়া", "आलेया", "Aleya", "male",
     "eerie floating ghost lights glowing over a dark marsh at night, luring a lone traveller"),
    ("কানাভুলো", "कानाभुलो", "Kanabhulo", "male",
     "a lone villager with a lantern lost in endless foggy fields at night, a shadowy spirit leading him in circles"),
    ("বেঘোভূত", "बेघो भूत", "Begho Bhoot", "male",
     "the restless spirit of a man taken by a tiger, in the dark mangrove forest of the Sundarbans"),
    ("চোরাচুন্নি", "चोराचुन्नी", "Chorachunni", "female",
     "a shadowy female ghost slipping into a village house through a window on a moonless night"),
    ("পেঁচাপেঁচি", "पेंचापेंची", "Penchapechi", "male",
     "an owl-like ghost with glowing eyes following a traveller through a dark forest"),
    ("যক্ষ", "यक्ष", "Jokkho", "male",
     "a guardian spirit of hidden treasure in the dark cellar of an old abandoned zamindar house"),
    ("একানড়ে", "एकानड़े", "Ekanore", "male",
     "a very tall thin one-legged spirit standing among palm trees at dusk"),
    ("পিশাচ", "पिशाच", "Pishach", "male",
     "a gaunt pishach spirit at a riverside cremation ground at midnight, eyes glowing"),
    ("চুড়েল", "चुड़ैल", "Churel", "female",
     "a churel spirit of north Indian folklore, a woman in white on a lonely village road at night"),
    ("বেতাল", "बेताल", "Vetal", "male",
     "a vetal spirit hanging upside down from a tree at a cremation ground, as in the old Vetal tales"),
    ("ব্রহ্মরাক্ষস", "ब्रह्मराक्षस", "Brahmarakshas", "male",
     "a fierce scholar-demon with a sacred thread in an old ruined temple at night"),
]


def ghost_dict_due():
    """Today's ghost for the dictionary, or None (only on its day, once a week). Returns (entry, number)."""
    if env("GHOST_DICT") == "0":
        return None
    try:
        day = int(env("GHOST_DICT_DAY") or 3)                    # 3 = Thursday
    except ValueError:
        day = 3
    if dt.datetime.now(extras.IST).weekday() != day:
        return None
    done = (_jload(GHOST_FILE, {}) or {}).get("done") or []
    if done and _age_days(done[-1]) < 6:
        return None
    told = {str(d.get("ghost")) for d in done}
    entry = next((g for g in GHOST_DICT if g[2] not in told), None)
    if not entry:
        log("Ghost dictionary: every ghost on our list has been told")
        return None
    return entry, len(done) + 1


def make_ghost_dictionary(due):
    """A ~40-second film about ONE ghost of Bengali folk belief - who it is, where it is said to live, its signs
    and its rule - told as folk belief. Facebook Reel + YouTube Short at 11 AM. Returns True if YouTube got it."""
    global WORK, FONT
    (bn, hi, en, gender, look), n = due
    chan = (env("CHANNEL_LANG") or "bn").lower()
    lang = chan if chan in LANGS else "bn"
    name = bn if lang == "bn" else hi
    U = UNIQ[lang]
    key = env("GEMINI_API_KEY")
    script = None
    if MOCK:
        script = {"lines": [{"speaker": "narrator", "emotion": "eerie", "text": f"লোকবিশ্বাস বলে, {name} থাকে পুকুরপাড়ের গাছে।"},
                            {"speaker": "narrator", "emotion": "whisper", "text": "অমাবস্যার রাতে সে নেমে আসে।"},
                            {"speaker": "narrator", "emotion": "tense", "text": "তার পায়ের পাতা থাকে উল্টো দিকে।"},
                            {"speaker": "narrator", "emotion": "whisper", "text": "আপনার গ্রামে কি কেউ তাকে দেখেছে?"}],
                  "pic1": look, "pic2": f"close view of {look}", "summary": f"{name} - বাংলার লোকবিশ্বাসের ভূত।"}
    else:
        ask = (f"Write a short {'Bengali (Kolkata cholit bhasha)' if lang == 'bn' else 'Hindi'} narration about "
               f"'{name}' ({en}) of Bengali / Indian FOLK BELIEF: {look}. 4 or 5 short lines, 50-65 words in all: "
               "who or what it is, where folk belief says it is found, its signs, its rule, and how people "
               f"traditionally keep safe. Tell it as folk belief ('{'লোকবিশ্বাস বলে' if lang == 'bn' else 'लोग कहते हैं'}"
               "...'), never as a proven fact; eerie but never gory; no clock times. The last line is a chilling "
               "question to the listener. Answer ONLY JSON: {\"lines\": [{\"speaker\": \"narrator\", \"emotion\": "
               "\"eerie|whisper|tense\", \"text\": \"\"}], \"pic1\": \"English picture prompt: the spirit in its place "
               "at night, cinematic\", \"pic2\": \"English picture prompt: a closer, frightening view of it\", "
               "\"summary\": \"1-2 sentences in the same language\"}")
        for model in extras.text_models(key)[:3] if key else []:
            try:
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                                  json={"contents": [{"parts": [{"text": ask}]}],
                                        "generationConfig": {"temperature": 0.8, "responseMimeType": "application/json"}},
                                  timeout=120)
                if r.ok:
                    js = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                    if isinstance(js, dict) and isinstance(js.get("lines"), list) and len(js["lines"]) >= 3:
                        script = js
                        break
            except Exception:
                continue
    if not script:
        raise RuntimeError("the narration could not be written")
    lines = [{"speaker": "narrator", "emotion": str(ln.get("emotion") or "eerie"), "text": str(ln.get("text")).strip()}
             for ln in script["lines"][:6] if isinstance(ln, dict) and str(ln.get("text", "")).strip()]
    base_work = WORK
    WORK = os.path.join(base_work, "ghost_dict")
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    try:
        FONT = find_font(lang)
        story = {"title": name, "setting": "a Bengal village at night",
                 "characters": [{"name": en, "gender": gender, "age": "adult", "kind": "ghost", "look": look}]}
        cast = Cast(story)
        voices = Voices(lang, cast)
        seed = random.randint(1, 1_000_000)
        pics = []
        for k, prm in enumerate((script.get("pic1") or look, script.get("pic2") or f"close view of {look}")):
            p = os.path.join(WORK, f"gd_{k}.jpg")
            if make_image(cast, str(prm)[:600], "a Bengal village at night", [en], p, seed + k):
                pics.append(p)
        if not pics:
            raise RuntimeError("no pictures")
        half = max(1, (len(lines) + 1) // 2)
        parts = [{"image": pics[0], "lines": lines[:half], "sounds": ["wind"], "mood": "creepy", "voices": voices},
                 {"image": pics[-1], "lines": lines[half:] or lines[-1:], "sounds": [], "mood": "scary",
                  "voices": voices}]
        STING_AT[0], STORY_PART[0], HOOK_TEXT[0] = 0, 0, ""
        nn = str(n).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) if lang == "bn" else str(n)
        # the 9:16 film (big picture, the words on top, big subtitles below) IS the Short
        STATE["top_text"] = (U["dict_band"].format(n=nn), U["dict_hook"].format(name=name))
        GEMINI_CACHE.clear()
        wide = os.path.join(WORK, "gd_wide.mp4")
        PORTRAIT[0] = None
        VOICE_CONTEXT[0] = "teaser"                      # the 2 PM story keeps its share of Gemini's voice
        try:
            build_video(parts, lang, wide)
        finally:
            VOICE_CONTEXT[0] = "main"
        short = os.path.join(WORK, "gd_short.mp4")
        if PORTRAIT[0] and os.path.exists(PORTRAIT[0]):
            run(["ffmpeg", "-y", "-i", PORTRAIT[0], "-t", "88", "-c", "copy", "-movflags", "+faststart", short])
        else:
            extras.make_teaser(wide, 0.0, min(88.0, duration(wide)), short, FONT, U["dict_hook"].format(name=name),
                               U["dict_band"].format(n=nn), WORK, tagline=U["dict_tagline"],
                               colors=((255, 230, 0), (200, 0, 20)))
        PORTRAIT[0] = None
        title = U["dict_title"].format(n=nn, name=name)
        page = env(f"PAGE_NAME_{lang.upper()}") or env("PAGE_NAME") or LANGS[lang]["page_default"]
        desc = (U["dict_desc"].format(name=name, summary=str(script.get("summary") or "").strip()) + "\n\n"
                + f"{page} · {LANGS[lang]['ai_note']}")
        tags = (["#ভূতেরঅভিধান", "#" + name.replace(" ", ""), "#বাংলারভূত", "#ভূতেরগল্প", "#BengaliFolklore"]
                if lang == "bn" else ["#भूतोंकाशब्दकोश", "#" + name.replace(" ", ""), "#भूत", "#Folklore", "#Shorts"])
        log(f"Ghost dictionary film ready: {title} ({duration(short):.0f} s)")
        if DRY_RUN or MOCK:
            return False
        at = dt.datetime.now(extras.IST).replace(hour=int(env("GHOST_DICT_HOUR") or 11), minute=0, second=0,
                                                  microsecond=0)
        at = max(at, dt.datetime.now(extras.IST) + dt.timedelta(minutes=15))
        rec = {"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "ghost": en, "n": n,
               "title": title, "lang": lang}
        if env("FB_REELS") != "0":
            try:
                rec["fb_reel"] = extras.fb_post_reel(short, f"{title}\n\n{desc}\n\n{' '.join(tags)}", at=at)
                log("Ghost dictionary Facebook Reel:", rec["fb_reel"])
            except Exception as e:
                log("  ghost dictionary Reel skipped:", str(e)[:200])
        if extras.yt_extra_ok() and env("YT_SHORTS") != "0":
            try:
                extras.PUBLISH["at"], extras.PUBLISH["used"] = at, False
                yd = extras.search_head("horror", lang, "", [f"{name} কে" if lang == "bn" else f"{name} कौन",
                                                             f"{en} ghost", "Bengali ghost"]) + "\n\n" + desc
                loc = extras.shorts_localizations(extras.yt_localizations(title, yd, lang, key), yd)
                rec["yt_short"] = post_to_youtube(short, None, f"{title} #Shorts"[:100], yd, tags, lang, loc)
                log("Ghost dictionary YouTube Short:", rec["yt_short"])
                try:
                    extras.yt_add_to_playlist(rec["yt_short"], U["dict_playlist"], lang)
                except Exception as e:
                    log("  ghost dictionary playlist skipped:", str(e)[:120])
            except Exception as e:
                log("  ghost dictionary Short skipped:", str(e)[:200])
        if rec.get("fb_reel") or rec.get("yt_short"):
            gd = _jload(GHOST_FILE, {}) or {}
            gd["done"] = (gd.get("done") or []) + [rec]
            _jsave(GHOST_FILE, gd)
            push_now([GHOST_FILE], "ghost dictionary posted")
            extras.telegram(f"👻 {title} - বেলা {at.strftime('%I:%M').lstrip('0')}-এ Facebook Reel"
                            + (" আর YouTube Short" if rec.get("yt_short") else "") + " হিসেবে আসবে।")
        return bool(rec.get("yt_short"))
    finally:
        WORK = base_work
        STING_AT[0], HOOK_TEXT[0] = 0, ""
        PORTRAIT[0] = None


# ----------------------------------------------------------------- 4) the monthly night-long marathon
def marathon_items(history, lang, max_n=12):
    """The month's most-watched stories (one language) for the night-long video, best first."""
    pool = []
    for h in history[-160:]:
        whole = (not h.get("kind") and not h.get("part")) or h.get("kind") == "series_full"   # never half a series
        if _age_days(h) <= 31 and h.get("facebook") and h.get("lang") == lang and whole:
            st = h.get("stats") or {}
            pool.append((extras.score(st) if st else 0, h))
    pool.sort(key=lambda x: -x[0])
    return [h for _s, h in pool[:max_n]]


def _probe_wh(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
               "-of", "csv=p=0:s=x", path]).strip().splitlines()[0]
    w, h = out.split("x")[:2]
    return int(w), int(h)


def _fill_clip(src, dst, W, H):
    """Any video into W x H: the whole picture in the middle, a dark blurred copy of it filling the rest
    (no black bars). Same codec settings for every piece, so the pieces join without a new encode."""
    fc = (f"[0:v]split[a][b];[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,"
          f"crop={W // 4}:{H // 4},boxblur=6:1,scale={W}:{H},eq=brightness=-0.25[bg];"
          f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=25,format=yuv420p[v]")
    run(["ffmpeg", "-y", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "0:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-maxrate", "3000k", "-bufsize", "6000k",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", dst])
    return dst


def _hours_text(sec, lang):
    U = UNIQ.get(lang, UNIQ["bn"])
    m = int(round(sec / 60.0))
    h, mm = divmod(m, 60)
    if mm >= 50:
        h, mm = h + 1, 0
    elif mm < 10:
        mm = 0
    else:
        mm = int(round(mm / 5.0)) * 5
    txt = U["hours_min"].format(h=h, m=mm) if mm else U["hours"].format(h=h)
    return txt.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) if lang == "bn" else txt


def make_marathon(history):
    """FIRST SUNDAY OF THE MONTH (instead of the weekly compilation): 'রাতভর ভূতের গল্প' - the month's best
    stories in one 2-3 hour video, to listen to at night. Facebook gets it in 9:16 like our stories, YouTube in
    16:9. Returns True when it is done (or was already done this month)."""
    global FONT
    month = dt.datetime.now(extras.IST).strftime("%Y-%m")
    if any(h.get("marathon") and h.get("month") == month for h in history):
        log("Night marathon: already out this month")
        return True
    langs = [h.get("lang") for h in history[-160:] if h.get("facebook") and not h.get("kind")]
    lang = env("LANGUAGE") if env("LANGUAGE") in LANGS else (max(set(langs), key=langs.count) if langs else "bn")
    items = marathon_items(history, lang, max_n=int(env("MARATHON_MAX") or 12))
    if len(items) < 4:
        log(f"Night marathon: only {len(items)} stories this month - the weekly compilation instead")
        return False
    L, U = LANGS[lang], UNIQ[lang]
    FONT = find_font(lang)
    limit = float(env("MARATHON_MIN") or 180) * 60
    raws, t = [], 0.0
    for k, h in enumerate(items):
        if t >= limit - 600:                          # (within 10 minutes of the limit: long enough)
            break
        try:
            src, length = extras.fb_video_source(h["facebook"])
            if not src:
                raise RuntimeError("no video link")
            if length and t + length > limit + 300 and len(raws) >= 4:
                continue                              # too long for what is left - perhaps a shorter one fits
            raw = extras.download(src, os.path.join(WORK, f"mraw_{k:02d}.mp4"))
            d = duration(raw)
            raws.append((raw, d, h, _probe_wh(raw)))
            t += d
            log(f"  marathon: {str(h.get('title', ''))[:50]} ({d / 60:.0f} min)")
        except Exception as e:
            log(f"  marathon: one story left out ({str(e)[:150]})")
    if len(raws) < 4:
        log("Night marathon: not enough videos could be downloaded - the weekly compilation instead")
        for r in raws:
            if os.path.exists(r[0]):
                os.remove(r[0])
        return False
    portrait = sum(1 for r in raws if r[3][1] > r[3][0]) * 2 > len(raws)
    W, H = (720, 1280) if portrait else (1280, 720)
    clips, chapters, frames, t = [], [], [], 0.0
    for k, (raw, d, h, _wh) in enumerate(raws):
        try:
            c = _fill_clip(raw, os.path.join(WORK, f"m_{k:02d}.mp4"), W, H)
            fr = os.path.join(WORK, f"mfr_{k}.jpg")
            run(["ffmpeg", "-y", "-ss", f"{min(40, d / 3):.1f}", "-i", c, "-frames:v", "1", fr])
            chapters.append((t, re.sub(r"\s*\|.*$", "", str(h.get("title") or f"{k + 1}")).strip()))
            frames.append(fr)
            clips.append(c)
            t += duration(c)
        except Exception as e:
            log(f"  marathon: one story left out ({str(e)[:150]})")
        finally:
            if os.path.exists(raw):
                os.remove(raw)
    if len(clips) < 4:
        log("Night marathon: not enough videos - the weekly compilation instead")
        return False
    lst = os.path.join(WORK, "marathon.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
    video = os.path.join(WORK, "marathon.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", video])
    for c in clips:
        os.remove(c)
    nn = str(len(clips))
    title = U["marathon_title"].format(n=nn.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) if lang == "bn"
                                       else nn, h=_hours_text(t, lang))[:99]
    base = extras.collage(frames, os.path.join(WORK, "m_thumb_base.jpg"))
    thumb = os.path.join(WORK, "m_thumbnail.jpg")
    make_thumbnail(base, U["marathon_thumb"], thumb, _hours_text(t, lang))
    chap = L["chapters"] + "\n" + "\n".join(f"{extras.fmt_time(s)} {n[:60]}" for s, n in chapters)
    tags = (["#ভূতেরগল্প", "#রাতভরভূতেরগল্প", "#BengaliHorrorStory", "#BhuterGolpo", "#HorrorMarathon"]
            if lang == "bn" else ["#BhootKiKahani", "#HorrorStories", "#HindiHorrorStories", "#HorrorMarathon"])
    description = f"{title}\n\n{U['marathon_intro']}\n\n{chap}\n\n{L['ai_note']}\n\n{' '.join(tags)}"
    log(f"Night marathon ready: {t / 60:.0f} minutes, {len(clips)} stories ({'9:16' if portrait else '16:9'})")
    if DRY_RUN:
        return True
    results = {}
    PORTRAIT[0] = video if portrait else None          # Facebook: the way our stories look there
    try:
        results["facebook"] = post_to_facebook(video, thumb, title, description)
        log("Night marathon on Facebook:", results["facebook"])
    except Exception as e:
        log("FACEBOOK FAILED (marathon):", e)
    finally:
        PORTRAIT[0] = None
    if youtube_ready() and extras.yt_extra_ok():
        try:
            yv = _fill_clip(video, os.path.join(WORK, "marathon_yt.mp4"), 1280, 720) if portrait else video
            if portrait:
                os.remove(video)
            results["youtube"] = post_to_youtube(yv, thumb, title, description, tags, lang)
            log("Night marathon on YouTube:", results["youtube"])
            try:
                extras.yt_add_to_playlist(results["youtube"], U["marathon_playlist"], lang)
            except Exception as e:
                log("  marathon playlist skipped:", str(e)[:120])
        except Exception as e:
            log("YouTube marathon skipped:", str(e)[:200])
    if not results:
        return False
    # kept as a 'compilation' (+ marathon), so nothing ever takes it for a normal story
    history.append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "lang": lang,
                    "kind": "compilation", "marathon": True, "month": month, "title": title, **results})
    save_history(history)
    extras.telegram(f"🌙 {title} - পোস্ট হয়েছে ({len(clips)}টা গল্প)")
    return True


# ===================== v67: a video that WAS posted, but whose saving failed (9 Nov 2026)
# That night's log (GitHub hides every '1' in a log as '***'): the exact YouTube ids, and the Facebook id with its
# hidden 1s - the bot finds the real Facebook id itself (by the title, or by trying what the hidden 1s can be).
LOST_HINTS = {"2026-11-09@20": {"youtube": "TuWwZbD23Kc", "yt_short": "7hquKevToz8",
                                "facebook_masked": "224***668***93229704"}}


def _letters(t):
    """only the letters of a title (no emoji, spaces, '|', ':' or '#'), to find one title inside another"""
    return re.sub(r"[^\wঀ-৿ऀ-ॿ]", "", str(t or "")).lower()


def _story_keys(story):
    out = []
    for t in (story.get("title"), story.get("title_b")):
        k = _letters(re.sub(r"\s*\|.*$", "", str(t or "")))
        if len(k) >= 6 and k not in out:
            out.append(k)
    return out


def _not_a_story_video(t):
    return any(w in str(t) for w in ("সম্পূর্ণ গল্প", "पूरी कहानी", "#Shorts", "#shorts", "ম্যারাথন", "मैराथन"))


def _fb_find_posted(keys, at, masked=""):
    """the posted story video on the Facebook page -> (id, title): searched by its title among the page's latest
    videos (the longest one, uploaded around that time); else every id the hidden 1s ('***') can stand for"""
    page, token = env("FB_PAGE_ID"), env("FB_PAGE_TOKEN")
    if not (page and token and keys):
        return None, None
    try:
        r = requests.get(f"{extras.GRAPH}/{page}/videos", timeout=60, params={
            "fields": "id,title,created_time,length", "limit": 60, "access_token": token}).json()
        hits = []
        for v in r.get("data") or []:
            t = str(v.get("title") or "")
            if not t or _not_a_story_video(t) or not any(k in _letters(t) for k in keys):
                continue
            try:
                made = dt.datetime.fromisoformat(str(v.get("created_time"))[:19]).replace(tzinfo=dt.timezone.utc)
                if not (-dt.timedelta(hours=20) <= made - at <= dt.timedelta(hours=8)):
                    continue
            except ValueError:
                pass
            hits.append((float(v.get("length") or 0), str(v["id"]), t))
        if hits:
            _l, vid, t = max(hits)
            return vid, t
        if "error" in r:
            log("  repair: Facebook search -", str(r["error"].get("message"))[:120])
    except Exception as e:
        log("  repair: Facebook search skipped:", str(e)[:120])
    if masked and "***" in masked:
        import itertools
        bits = masked.split("***")
        for fill in itertools.product(("1", "11", "111"), repeat=len(bits) - 1):
            cand = bits[0] + "".join(f + b for f, b in zip(fill, bits[1:]))
            try:
                v = requests.get(f"{extras.GRAPH}/{cand}", params={"fields": "id,title", "access_token": token},
                                 timeout=30).json()
            except Exception:
                continue
            if v.get("id") and any(k in _letters(v.get("title")) for k in keys):
                return str(v["id"]), str(v.get("title") or "")
    return None, None


def _yt_find_posted(keys, hint):
    """(main video id, its title, the Short's id) on our YouTube channel"""
    if not youtube_ready():
        return hint.get("youtube"), None, hint.get("yt_short")
    try:
        hdr = extras.yt_token()
        if hint.get("youtube"):
            r = requests.get(f"{extras.YT}/videos", headers=hdr, timeout=30,
                             params={"part": "snippet", "id": hint["youtube"]}).json()
            t = next((str(x["snippet"].get("title") or "") for x in r.get("items") or []), None)
            return hint["youtube"], t, hint.get("yt_short")
        ch = requests.get(f"{extras.YT}/channels", headers=hdr, timeout=30,
                          params={"part": "contentDetails", "mine": "true"}).json()
        up = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        r = requests.get(f"{extras.YT}/playlistItems", headers=hdr, timeout=30,
                         params={"part": "snippet", "playlistId": up, "maxResults": 40}).json()
        main_id = title = short_id = None
        for x in r.get("items") or []:
            sn = x.get("snippet") or {}
            t, vid = str(sn.get("title") or ""), (sn.get("resourceId") or {}).get("videoId")
            if not vid or not any(k in _letters(t) for k in keys):
                continue
            if "#shorts" in t.lower():
                short_id = short_id or vid
            elif not main_id and not _not_a_story_video(t):
                main_id, title = vid, t
        return main_id, title, short_id
    except Exception as e:
        log("  repair: YouTube search skipped:", str(e)[:120])
        return hint.get("youtube"), None, hint.get("yt_short")


def _series_cast(story, special, theme, part, prev):
    """the same people main() keeps in the series memory (our fixed heroes; part 2+ = part 1's people + new)"""
    chars = [dict(c) for c in story.get("characters") or [] if isinstance(c, dict)]
    if special in SERIES_IDS:
        fixed = series_cast(special, theme, STATE.get("crossover") or (prev or {}).get("crossover"))
        names = {c["name"].lower(): c for c in fixed}
        chars = [names.get(str(c.get("name", "")).lower(), c) for c in chars]
        for b in fixed:
            if b["name"].lower() not in [str(c.get("name", "")).lower() for c in chars]:
                chars.append(b)
    setting = story.get("setting", "")
    if part >= 2 and prev:
        old = {str(c.get("name", "")).lower() for c in prev.get("characters") or []}
        chars = list(prev.get("characters") or []) + [c for c in chars if str(c.get("name", "")).lower() not in old]
        setting = prev.get("setting") or setting
    return chars, setting


def repair_lost_posts(history, now=None):
    """9 Nov 2026: the 8 PM video WAS posted, but saving to GitHub failed - its history entry, its map pin and its
    series memory (part 2 promised for Thursday) were lost. Every run first checks the stories written for the last
    days: a time that is over, with no history entry, but whose video IS on Facebook / YouTube -> its history entry
    and its series memory are written again and saved. Returns the repaired time slots."""
    if MOCK or DRY_RUN or env("REPAIR_LOST") == "0":
        return []
    plans = _jload(PLANS_FILE, {})
    if not isinstance(plans, dict):
        return []
    now = now or dt.datetime.now(extras.IST)
    saved = {h.get("slot") for h in history if h.get("slot") and not h.get("kind")}
    fixed = []
    for key in sorted(plans):
        plan = plans.get(key)
        if key in saved or "@" not in str(key) or not isinstance(plan, dict) or not isinstance(plan.get("story"), dict):
            continue
        try:
            d_, h_ = str(key).split("@")
            at = dt.datetime.fromisoformat(d_).replace(hour=int(h_), tzinfo=extras.IST)
        except ValueError:
            continue
        if not dt.timedelta(minutes=40) <= now - at <= dt.timedelta(days=4):
            continue                                 # its own run may still be going / too old
        story, hint = plan["story"], LOST_HINTS.get(key, {})
        keys = _story_keys(story)
        if not keys:
            continue
        at_utc = at.astimezone(dt.timezone.utc)
        fb_id, fb_title = _fb_find_posted(keys, at_utc, hint.get("facebook_masked", ""))
        yt_id, yt_title, yt_short = _yt_find_posted(keys, hint)
        if not fb_id and not yt_id:
            log(f"  {key}: no history entry and no video online - that story was not posted (nothing to repair)")
            continue
        st = plan.get("state") or {}
        lang = plan.get("lang") if plan.get("lang") in LANGS else "bn"
        L = LANGS[lang]
        part, total = int(plan.get("part") or 0), int(plan.get("total") or 0)
        prev = plan.get("prev") if isinstance(plan.get("prev"), dict) else None
        special, theme, fmt = plan.get("special"), plan.get("theme"), plan.get("fmt")
        cat = st.get("category") or plan.get("cat") or "gram"
        continues = bool(part) and part < total
        title = fb_title or yt_title or str(story.get("title", ""))
        when = at_utc.isoformat(timespec="minutes")
        series_id = (((prev or {}).get("series_id") or (prev or {}).get("created")) if part >= 2 else
                     (when if part == 1 else None))
        pn = str(part).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) if lang == "bn" else str(part)
        tb = re.sub(r"\s*\|\s*(?:পর্ব|भाग).*$", "", str(story.get("title_b") or "")).strip()[:85]
        ma = str(story.get("mystery_answer", 0) or 0)[:1]
        rec = {"date": when, "lang": lang, "slot": key, "pending_comments": [],
               "source": st.get("source_name") or (prev or {}).get("source") or None,
               "idea_used": st.get("idea_used"), "trend_used": st.get("trend_used"), "category": cat, "question_post": None,
               "title_b": (tb + (f" | {L['part'].format(n=pn)}" if part else "")) if tb else None,
               "theme": theme, "format": fmt, "part": part, "continues": continues, "series_id": series_id,
               "title": title, "festival": plan.get("festival"), "special": special,
               "viewer_story_id": (plan.get("viewer") or {}).get("id") if isinstance(plan.get("viewer"), dict) else None,
               "classic_id": (plan.get("classic") or [None])[0] if special == "classic" and plan.get("classic") else None,
               "episode_summary": str(story.get("episode_summary", ""))[:400] if special == "karna" else None,
               "karna_origin": True if special == "karna" else None, "hidden": False,
               "mystery_answer": int(ma) if ma.isdigit() else 0, "repaired": True}
        for k_, v_ in (("facebook", fb_id), ("youtube", yt_id), ("yt_short", yt_short)):
            if v_:
                rec[k_] = v_
        try:                                         # its pin on the ghost map
            dk = story_district(story)
            if dk in DISTRICT and os.path.exists(MAP_JSON) and env("GHOST_MAP") != "0":
                items = _jload(MAP_JSON, [])
                items = items if isinstance(items, list) else []
                pin = _pin(title, dk, lang, fb_id, yt_id, at.date().isoformat(), HORROR_CATS.get(cat, {}).get("bn", ""))
                if not any((pin["fb"] and x.get("fb") == pin["fb"]) or (pin["yt"] and x.get("yt") == pin["yt"])
                           for x in items):
                    items.append(pin)
                    _jsave(MAP_JSON, items[-3000:])
                rec["district"] = dk
        except Exception as e:
            log("  repair: map pin skipped:", str(e)[:100])
        later = [h for h in history if str(h.get("date") or "") > when and not h.get("kind")
                 and (h.get("category") == cat)]
        if continues or part >= 2:                   # the series memory - unless this category has gone on since
            cur = extras.series_all(NEXT_PART).get(str(cat))
            if later:
                log(f"  repair: '{cat}' has had a newer story since - its series memory is left as it is")
            elif continues and (not cur or str(cur.get("updated") or cur.get("created") or "") < when or
                                (cur.get("series_id") == series_id and int(cur.get("done") or 0) < part)):
                m = re.search(r"#\s*([০-৯0-9]+)", title)
                case_no = (int(m.group(1).translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))) if m and special in
                           SERIES_IDS else (prev or {}).get("case_no"))
                chars, setting = _series_cast(story, special, theme, part, prev)
                last_sc = story["scenes"][-1] if story.get("scenes") else {}
                extras.series_put(NEXT_PART, cat, {
                    "created": (prev or {}).get("created") or at_utc.isoformat(),
                    "category": cat, "lang": lang, "theme": theme, "fmt": fmt, "special": special,
                    "title": (prev or {}).get("title") or re.sub(r"\s*\|.*$", "", title).strip(),
                    "done": part, "total": total, "series_id": series_id, "case_no": case_no,
                    "summary": (((prev or {}).get("summary") or "") + f"\nPart {part}: " + str(story.get("summary", "")))[-4000:],
                    "last_lines": " / ".join(str(ln.get("text", "")) for ln in (last_sc.get("lines") or [])[-4:]),
                    "outline": st.get("outline") or plan.get("outline") or (prev or {}).get("outline", ""),
                    "characters": chars, "setting": setting,
                    "source": st.get("source_name", "") or (prev or {}).get("source", "")})
                data = extras.series_all(NEXT_PART)  # 'updated' = when it was really posted, so the next part
                data[str(cat)]["updated"] = at_utc.isoformat()   # comes on the category's next day as promised
                with open(NEXT_PART, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=1)
                log(f"  repair: series memory back - part {part + 1} of {total} comes on '{cat}' day")
            elif not continues and cur and cur.get("series_id") == series_id:
                extras.series_put(NEXT_PART, cat, None)
        if not continues and special in SERIES_BIBLE:
            try:
                bible_add(special, title, story.get("episode_summary") or str(story.get("summary", ""))[:300])
            except Exception as e:
                log("  repair: series bible skipped:", str(e)[:100])
        pos = len(history)
        while pos > 0 and str(history[pos - 1].get("date") or "") > when:
            pos -= 1
        history.insert(pos, rec)
        saved.add(key)
        fixed.append(key)
        log(f"REPAIRED {key}: '{title}' was posted (Facebook {fb_id or '-'}, YouTube {yt_id or '-'}) but not saved "
            f"- its history entry is back")
    if fixed:
        save_history(history)
        try:
            cases_page(history)
        except Exception:
            pass
        push_now([HISTORY, NEXT_PART, MAP_DIR, BIBLE_FILE], "lost save repaired: " + ", ".join(fixed))
        try:
            extras.telegram("🛠️ আগের run-এর হারানো হিসেব ঠিক করা হয়েছে: " + ", ".join(fixed) +
                            " (ভিডিও পোস্ট হয়েছিল, শুধু GitHub-এ লেখা হয়নি)")
        except Exception:
            pass
    return fixed


# ===================== v68: tomorrow's stories at night, YOUR thumbnail from Telegram, better thumbnails,
# ===================== the Sunday report and the YouTube podcast (your wishes of 9 Nov 2026)
from contextlib import contextmanager

TITLE_LIST = os.path.join(HERE, "assets", "title_list.json")       # which days' titles were sent to you, when
USER_THUMBS = os.path.join(HERE, "assets", "user_thumbs")           # the thumbnails you sent on Telegram
UT_INDEX = os.path.join(USER_THUMBS, "index.json")
THUMB_PRE = os.path.join(HERE, "assets", "thumb_base")              # today's thumbnail pictures, made in the morning
WEEKLY_FILE = os.path.join(HERE, "assets", "weekly_report.json")
PODCAST_FILE = os.path.join(HERE, "assets", "podcast.json")
SLOT_NO = {NOON: "1", EVENING: "2"}
SLOT_BN = {NOON: "দুপুর ২টো", EVENING: "রাত ৮টা"}
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


@contextmanager
def pretend_now(at):
    """While TOMORROW's stories are written at night: every 'what day is it' in main.py and extras.py (all ask with a
    time zone) answers as if it were `at` - so tomorrow's programme, festival, moon and series part are chosen.
    The log clock (asked without a time zone) stays real."""
    real = dt.datetime
    shift = at - real.now(dt.timezone.utc)

    class _Now(real):
        @classmethod
        def now(cls, tz=None):
            return real.now(tz) if tz is None else real.now(tz) + shift

    dt.datetime = _Now
    try:
        yield
    finally:
        dt.datetime = real


def _slot_time(key):
    d_, h_ = str(key).split("@")
    return dt.datetime.fromisoformat(d_).replace(hour=int(h_), tzinfo=extras.IST)


def _plan_title(plan):
    """the title as you will see it (series name + part)"""
    story = plan.get("story") or {}
    lang = plan.get("lang") if plan.get("lang") in LANGS else "bn"
    L = LANGS[lang]
    t = re.sub(r"\s*\|.*$", "", str(story.get("title", ""))).strip()
    sp = plan.get("special")
    if sp in SERIES_IDS:                           # the case number exactly as the video will count it
        prev = plan.get("prev") if isinstance(plan.get("prev"), dict) else {}
        try:
            n = prev.get("case_no") or 1 + sum(1 for h in load_history() if h.get("special") == sp
                                               and not (h.get("part") or 0) > 1
                                               and (sp != "karna" or h.get("lang") == lang))
            t = f"{L[sp].format(n=n)}: {no_series_name(t, sp)}"
        except Exception:
            t = f"{L[sp].split(' #')[0]}: {no_series_name(t, sp)}"
    part = int(plan.get("part") or 0)
    if part:
        t += f" | {L['part'].format(n=str(part).translate(BN_DIGITS) if lang == 'bn' else part)}"
    return t


def _story_cast(plan):
    """the people as the video will show them (our heroes always with their fixed looks)"""
    story = dict(plan.get("story") or {})
    chars, setting = _series_cast(story, plan.get("special"), plan.get("theme"), int(plan.get("part") or 0),
                                  plan.get("prev") if isinstance(plan.get("prev"), dict) else None)
    story["characters"], story["setting"] = chars, setting
    return story


def thumb_plan(story, cast, special, cat):
    """The thumbnail picture of a story - YOUR formula (7 Nov 2026) filled with this story's ghost, place and
    moment. Returns (prompt, formula, hero, ghost's name, the story's thumbnail idea)."""
    ti = story.get("thumbnail_image") or {}
    if isinstance(ti, str):
        ti = {"action": ti}
    ghost = ascii_text(ti.get("ghost", ""))
    ghost_names = [c["name"] for c in cast.chars.values() if c["kind"].startswith("ghost")]
    hero = ti.get("hero") or next((n for n in (ti.get("characters") or []) if n not in ghost_names), "")
    gname = ti.get("second") or (ghost_names[0] if ghost_names else "")

    def describe(n):
        c = cast.find(n) if n else None
        if c and c["kind"].startswith("ghost"):
            return f"{ghost or c['look']} ghost"
        return f"{c['name']} ({c['look']})" if c else n
    t_prompt = extras.poster_prompt("horror", {**ti, "hero": hero, "second": gname}, describe, "", cast.setting)
    tkind = extras.thumb_kind("horror", special if special in ("karna",) else cat, bool(story.get("true_label")))
    if env("POSTER_STYLE") not in ("old", "words"):   # YOUR thumbnail formula (7 Nov 2026)
        subj = describe(gname) if gname else (ghost or "a terrifying ghost")
        if tkind == "h_closeup":
            subj = f"the face of {subj}"
        t_prompt = extras.user_thumb_prompt(tkind, subj, ti.get("place") or cast.setting,
                                            ti.get("moment") or ti.get("action") or "")
    return t_prompt, tkind, hero, gname, ti


def _thumb_small(plan_or_story, part, special, lang, true_label):
    L = LANGS[lang]
    series_bn = series_label(special, L)
    pn = str(part).translate(BN_DIGITS) if lang == "bn" else str(part)
    return " · ".join(x for x in (extras.TRUE_LABEL.get(lang, extras.TRUE_LABEL["bn"]) if true_label else "",
                                  series_bn or "", L["part"].format(n=pn) if part else "") if x)


# ----------------------------------------------------------------- Telegram helpers
def tg_photo(path, caption):
    tok = env("TELEGRAM_BOT_TOKEN")
    cid = extras.tg_chat_id(tok) if tok else None
    if MOCK or not (tok and cid and os.path.exists(path)):
        return False
    try:
        with open(path, "rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto", timeout=60,
                              data={"chat_id": cid, "caption": caption[:1000]}, files={"photo": f})
        return r.ok
    except Exception as e:
        log("  Telegram picture not sent:", str(e)[:100])
        return False


def _tg_text(text):
    if MOCK:
        log("  [Telegram] " + text.replace("\n", " / ")[:300])
        return True
    return extras.telegram(text)


# ----------------------------------------------------------------- 1) tomorrow's stories at night + the title list
def write_tomorrow(history):
    """YOUR WISH (9 Nov 2026): right after the 8 PM video, TOMORROW's 2 PM and 8 PM stories are written (as if it
    were tomorrow morning - tomorrow's programme, festival, moon and series part) and their titles come to you on
    Telegram by 9 PM:  1 = 2 PM, 2 = 8 PM. A picture you send with '1' / '2' becomes that video's thumbnail.
    (If this fails, the morning run writes them as before and sends the list then.)"""
    if DRY_RUN or env("NIGHT_WRITE") == "0":
        return []
    now = dt.datetime.now(extras.IST)
    day = (now + dt.timedelta(days=1)).date()
    at = dt.datetime(day.year, day.month, day.day, 6, 30, tzinfo=extras.IST)
    if not MOCK:
        try:                                         # stories you sent on Telegram until now
            creator_inbox(bot_status)
        except Exception as e:
            log("  Telegram stories not read:", str(e)[:120])
    hist2, done = list(history), []
    for h in (NOON, EVENING):
        key = f"{day.isoformat()}@{h}"
        plan = load_plan(key)
        if not plan:
            log(f"=== Writing TOMORROW's story for {SLOT_BN[h]} ({key}) ===")
            STATE.clear()
            SCRIPTS.clear()
            try:
                with pretend_now(at):
                    plan = choose_and_write(h, hist2)
                plan = json.loads(json.dumps(plan, ensure_ascii=False, default=list))
                save_plan(key, plan)
                push_now([PLANS_FILE, MY_STORIES], f"story written for {key}")
            except Exception as e:
                log(f"  tomorrow's story for {key} not written now ({str(e)[:200]}) - the morning run writes it")
                continue
        done.append(key)
        hist2.append({"theme": plan.get("theme"), "title": plan["story"].get("title"), "lang": plan.get("lang"),
                      "category": plan.get("cat"), "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                      "viewer_names": [p[0] for p in ((plan.get("state") or {}).get("viewer_names") or [])]})
    send_title_list(day.isoformat())
    return done


def chatgpt_prompt(plan):
    """what you paste into ChatGPT for this story's thumbnail picture (your formula, this story's ghost and place)"""
    story = _story_cast(plan)
    t_prompt = thumb_plan(story, Cast(story), plan.get("special"), plan.get("cat"))[0]
    return (t_prompt + " Make it ONE photorealistic image in wide landscape format (16:9). Keep the faces away from "
            "the very top and bottom edges.")


def send_title_list(day):
    """The day's titles on Telegram:  1 = 2 PM, 2 = 8 PM  (+ for each, what to paste into ChatGPT)."""
    plans = _jload(PLANS_FILE, {})
    items = [(h, plans.get(f"{day}@{h}")) for h in (NOON, EVENING)]
    items = [(h, p) for h, p in items if isinstance(p, dict) and isinstance(p.get("story"), dict)]
    if not items or env("TITLE_LIST") == "0":
        return False
    sent = _jload(TITLE_LIST, {})
    sent = sent if isinstance(sent, dict) else {}
    have = set(((sent.get(day) or {}).get("slots")) or [])
    if all(str(h) in have for h, _p in items):
        return False                                 # already sent
    d = dt.date.fromisoformat(day)
    today = dt.datetime.now(extras.IST).date()
    when = "আজকের" if d == today else ("কালকের" if (d - today).days == 1 else d.strftime("%d %b"))
    wd = BN_DAYS[d.weekday()]
    lines = [f"🎬 {when} ভিডিও ({wd}, {str(d.day).translate(BN_DIGITS)} {BN_MONTH_NAMES[d.month - 1]}):", ""]
    for h, p in items:
        lines.append(f"{SLOT_NO[h]}️⃣ {SLOT_BN[h]}: {_plan_title(p)}")
        if (p.get("state") or {}).get("trend_used"):
            lines.append("   🔥 YouTube-এ এই সপ্তাহে সবচেয়ে বেশি দেখা বিষয় নিয়ে নতুন গল্প")
    lines += ["", "নিজের thumbnail দিতে চাইলে: নিচের message-এর লেখাটা ChatGPT-তে paste করে ছবি বানান, তারপর ছবিটা "
              "এখানে পাঠান - ছবির নিচে লিখুন 1 (দুপুরের) বা 2 (রাতের)। বাংলা লেখাটা bot নিজেই বসিয়ে দেবে।",
              "⏰ 1-এর ছবি সকাল ৮টার মধ্যে, 2-এর ছবি বিকেল ৪টের মধ্যে (রাতেই পাঠানো সবচেয়ে ভালো)। কিছু না পাঠালে "
              "bot নিজের thumbnail দেবে।"]
    ok = _tg_text("\n".join(lines))
    for h, p in items:
        try:
            _tg_text(f"{SLOT_NO[h]}️⃣ {SLOT_BN[h]} - ChatGPT-তে এটা paste করুন:\n\n{chatgpt_prompt(p)}")
        except Exception as e:
            log("  ChatGPT idea not sent:", str(e)[:100])
    if ok:
        sent[day] = {"slots": sorted({str(h) for h, _p in items} | have),
                     "at": dt.datetime.now(extras.IST).isoformat(timespec="minutes")}
        keep = (today - dt.timedelta(days=7)).isoformat()
        _jsave(TITLE_LIST, {k: v for k, v in sent.items() if k >= keep})
        push_now([TITLE_LIST], f"titles of {day} sent on Telegram")
        log(f"Titles of {day} sent to you on Telegram ({len(items)})")
    return ok


BN_MONTH_NAMES = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর",
                  "নভেম্বর", "ডিসেম্বর"]


# ----------------------------------------------------------------- 2) YOUR thumbnail from Telegram
def _ut_index():
    idx = _jload(UT_INDEX, {})
    idx = idx if isinstance(idx, dict) else {}
    idx.setdefault("items", [])
    idx.setdefault("seen", [])
    idx.setdefault("made", {})
    return idx


def _ut_save(idx):
    now = time.time()
    keep = []
    for it in idx["items"]:                          # pictures older than 4 days are deleted (the repo stays small)
        if now - float(it.get("sent") or 0) > 4 * 86400:
            try:
                os.remove(os.path.join(USER_THUMBS, it["file"]))
            except OSError:
                pass
        else:
            keep.append(it)
    idx["items"] = keep
    old = (dt.datetime.now(extras.IST).date() - dt.timedelta(days=7)).isoformat()
    idx["made"] = {k: v for k, v in idx["made"].items() if k >= old}
    idx["seen"] = idx["seen"][-400:]
    _jsave(UT_INDEX, idx)


def _which_slot(text):
    """'1' / '১' / 'দুপুর' = the 2 PM video, '2' / '২' / 'রাত' = the 8 PM video"""
    t = str(text or "").strip().lower()
    if not t:
        return None
    if any(w in t for w in ("দুপুর", "dupur", "noon")):
        return NOON
    if any(w in t for w in ("রাত", "raat", "night", "ratre", "rate")):
        return EVENING
    one = re.search(r"(?<![0-9০-৯])[1১](?![0-9০-৯])", t)
    two = re.search(r"(?<![0-9০-৯])[2২](?![0-9০-৯])", t)
    if one and not two:
        return NOON
    if two and not one:
        return EVENING
    return None


def _thumb_target(h, sent_at, idx):
    """which video a picture sent at `sent_at` is for: the next video of that time whose title you ALREADY had
    (a picture is never put on a story you had not seen yet). None = no such video."""
    lists = _jload(TITLE_LIST, {})
    lists = lists if isinstance(lists, dict) else {}
    for add in (0, 1):
        day = (sent_at + dt.timedelta(days=add)).date().isoformat()
        key = f"{day}@{h}"
        if _slot_time(key) <= sent_at:
            continue
        ann = (lists.get(day) or {}).get("at")
        try:
            if ann and dt.datetime.fromisoformat(ann) <= sent_at + dt.timedelta(minutes=1):
                return key
        except ValueError:
            pass
    return None


def _tg_download(tok, fid, path):
    from io import BytesIO
    try:
        info = requests.get(f"https://api.telegram.org/bot{tok}/getFile", params={"file_id": fid}, timeout=30).json()
        fp = (info.get("result") or {}).get("file_path")
        if not fp:
            return False
        data = requests.get(f"https://api.telegram.org/file/bot{tok}/{fp}", timeout=120).content
        img = Image.open(BytesIO(data)).convert("RGB")
        if img.width < 480 or img.height < 270:
            log(f"  your picture is too small ({img.width}x{img.height}) - not used")
            return False
        img.thumbnail((1920, 1920))
        os.makedirs(USER_THUMBS, exist_ok=True)
        img.save(path, quality=93)
        return True
    except Exception as e:
        log("  your picture could not be downloaded:", str(e)[:120])
        return False


def thumb_inbox():
    """Pictures YOU send to the bot on Telegram for a thumbnail - with '1' (2 PM video) or '2' (8 PM video) written
    under it, or as a reply to the bot's '1️⃣ / 2️⃣' message. Each is saved in the repo and confirmed on Telegram.
    Returns how many new pictures were taken."""
    tok, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if MOCK or DRY_RUN or not tok or not chat or env("USER_THUMBS") == "0":
        return 0
    try:
        r = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates",
                         params={"allowed_updates": json.dumps(extras.TG_UPDATES)}, timeout=30).json()
    except Exception as e:
        log("  your Telegram pictures: could not read -", str(e)[:100])
        return 0
    idx = _ut_index()
    seen = set(idx["seen"])
    msgs = [u for u in r.get("result") or [] if isinstance(u.get("message"), dict)]
    groups = {}
    for u in msgs:                                   # several pictures sent together: the caption of one counts
        m = u["message"]
        if m.get("media_group_id") and _which_slot(m.get("caption")):
            groups[m["media_group_id"]] = _which_slot(m.get("caption"))
    plans, got, changed = _jload(PLANS_FILE, {}), 0, False
    for u in msgs:
        uid, m = u.get("update_id"), u["message"]
        if uid in seen or str((m.get("chat") or {}).get("id")) != str(chat):
            continue
        doc = m.get("document") or {}
        if m.get("photo"):
            fid = max(m["photo"], key=lambda p: (p.get("width", 0) * p.get("height", 0), p.get("file_size", 0)))["file_id"]
        elif str(doc.get("mime_type", "")).startswith("image/"):
            fid = doc["file_id"]
        else:
            continue
        rep = m.get("reply_to_message") or {}
        h = (_which_slot(m.get("caption")) or groups.get(m.get("media_group_id"))
             or _which_slot(str(rep.get("text") or rep.get("caption") or "")[:25]))
        seen.add(uid)
        changed = True
        if h is None:
            _tg_text("🖼️ একটা ছবি পেয়েছি, কিন্তু কোন ভিডিওর জন্য বুঝতে পারিনি। ছবিটা আবার পাঠান, নিচে লিখে দিন: "
                     "1 (দুপুর ২টো) বা 2 (রাত ৮টা)।")
            continue
        sent_at = dt.datetime.fromtimestamp(int(m.get("date") or time.time()), extras.IST)
        target = _thumb_target(h, sent_at, idx)
        if not target:
            _tg_text(f"🖼️ ছবিটা পেয়েছি, কিন্তু {SLOT_BN[h]}-র পরের গল্পের নাম তখনও আপনাকে পাঠানো হয়নি - তাই এটা কোনো "
                     "ভিডিওতে বসানো হলো না। রাত ৮টার পরে নতুন নামের তালিকা পেলে তবেই ছবি পাঠাবেন।")
            continue
        if target in idx["made"]:
            p = plans.get(target) or {}
            _tg_text(f"⌛ ছবিটা দেরিতে এসেছে - {SLOT_BN[h]}-র ভিডিও ('{_plan_title(p) if p.get('story') else target}')-র thumbnail "
                     "আগেই তৈরি হয়ে গিয়েছিল, তাই এটা ব্যবহার হলো না। পরের বার একটু আগে পাঠাবেন।")
            continue
        path = os.path.join(USER_THUMBS, f"u{uid}_{h}.jpg")
        if not _tg_download(tok, fid, path):
            seen.discard(uid)                        # (tried again next time)
            continue
        idx["items"].append({"id": uid, "h": h, "sent": int(sent_at.timestamp()), "slot": target,
                             "file": os.path.basename(path), "used": None})
        p = plans.get(target) or {}
        d = target.split("@")[0]
        day_w = "আজ" if d == dt.datetime.now(extras.IST).date().isoformat() else "কাল"
        _tg_text(f"✅ ছবি পেয়েছি - {day_w} {SLOT_BN[h]}-র ভিডিও" + (f" '{_plan_title(p)}'" if p.get("story") else "")
                 + "-র thumbnail এটাই হবে। (আরেকটা পাঠালে নতুনটাই নেওয়া হবে)")
        log(f"  your thumbnail from Telegram for {target}")
        got += 1
    idx["seen"] = sorted(seen)
    if changed:
        _ut_save(idx)
        push_now([USER_THUMBS], "your thumbnail from Telegram")
    return got


def user_thumb_for(slot):
    """your newest picture for this video (or None)"""
    idx = _ut_index()
    cands = [it for it in idx["items"] if it.get("slot") == slot and not it.get("used")
             and os.path.exists(os.path.join(USER_THUMBS, str(it.get("file"))))]
    if not cands:
        return None
    best = max(cands, key=lambda it: it.get("sent") or 0)
    for it in cands:
        it["used"] = slot if it is best else "a newer picture came"
    _ut_save(idx)
    return os.path.join(USER_THUMBS, best["file"])


def mark_thumb_made(slot):
    idx = _ut_index()
    idx["made"][str(slot)] = dt.datetime.now(extras.IST).isoformat(timespec="minutes")
    _ut_save(idx)


def fit_16x9(src, out, W=1280, H=720):
    """any picture -> 1280x720: nearly 16:9 is cut a little; square / tall is shown whole on a blurred copy"""
    from PIL import ImageEnhance
    img = Image.open(src).convert("RGB")
    r = img.width / img.height
    s = max(W / img.width, H / img.height)
    big = img.resize((max(W, int(img.width * s + 0.5)), max(H, int(img.height * s + 0.5))), Image.LANCZOS)
    x, y = (big.width - W) // 2, (big.height - H) // 2
    if 1.45 <= r <= 2.0:
        big.crop((x, y, x + W, y + H)).save(out, quality=95)
        return out
    bg = ImageEnhance.Brightness(big.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(28))).enhance(0.55)
    f = min(W / img.width, H / img.height)
    fg = img.resize((int(img.width * f), int(img.height * f)), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    bg.save(out, quality=95)
    return out


def _vision(prompt, images, max_side=768):
    """Gemini (a free text model) LOOKS at pictures and answers in JSON"""
    from io import BytesIO
    key = env("GEMINI_API_KEY")
    if MOCK or not key or not images:
        return None
    parts = [{"text": prompt}]
    for k, p in enumerate(images):
        im = Image.open(p).convert("RGB")
        im.thumbnail((max_side, max_side))
        b = BytesIO()
        im.save(b, "JPEG", quality=85)
        if len(images) > 1:
            parts.append({"text": f"Picture {k + 1}:"})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}})
    for model in extras.helper_models(key)[:4]:
        try:
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json={"contents": [{"parts": parts}],
                                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}},
                              timeout=120)
            if not r.ok:
                continue
            return extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as e:
            log(f"  picture check ({model}): {str(e)[:100]}")
    return None


def image_has_text(path):
    js = _vision("Does this picture contain any written words, letters or numbers (in any language, Bengali too)? "
                 'Answer ONLY JSON: {"text": true or false}', [path])
    return bool(js.get("text")) if isinstance(js, dict) else False


def apply_user_thumb(slot, thumb, words, small, kind):
    """YOUR picture from Telegram becomes the video's thumbnail. Without words on it, the bot puts the Bengali words
    on it in the channel's style; with words, it is used as it is. The bot's own thumbnail becomes the second one
    (used only if the video gets few views)."""
    src = user_thumb_for(slot) if slot else None
    if not src:
        return False
    fitted = fit_16x9(src, os.path.join(WORK, "user_thumb_16x9.jpg"))
    if os.path.exists(thumb):
        shutil.copy(thumb, os.path.join(WORK, "thumbnail_b.jpg"))
    port = os.path.join(WORK, "thumbnail_portrait.jpg")
    if image_has_text(src):
        shutil.copy(fitted, thumb)
        if os.path.exists(port):
            os.remove(port)                          # (the 9:16 one is then made from your picture)
        log("YOUR thumbnail from Telegram (with its own words) is used")
    else:
        extras.title_poster(fitted, words, thumb, kind, small=small, fallback_font=FONT)
        extras.title_poster(fitted, words, port, kind, small=small, portrait=True, fallback_font=FONT)
        log(f"YOUR thumbnail from Telegram is used, with the words '{words}'")
    return True


# ----------------------------------------------------------------- 3) the bot's own thumbnail: best model, early
JUDGE_PROMPT = (
    "You choose the YouTube thumbnail picture for a Bengali horror story channel. Which picture would get the most "
    "clicks on a phone screen AND has no defects? Look for: one clear, frightening focal point (a face or a "
    "figure) that reads even when small; sharp, detailed, photorealistic; dramatic cinematic lighting and strong "
    "contrast; the LEFT side darker and simpler (the title goes there); no deformed face, eyes or hands; no "
    "letters, text or watermark; not gory. Answer ONLY JSON: {\"best\": <picture number>, \"why\": \"one short "
    "sentence\"}")


def judge_pictures(paths):
    """the number (0-based) of the best thumbnail picture - Gemini looks at them; the first one if it cannot"""
    if len(paths) < 2:
        return 0
    js = _vision(JUDGE_PROMPT, paths)
    try:
        k = int(js.get("best")) - 1
        if 0 <= k < len(paths):
            log(f"  Gemini picked thumbnail picture {k + 1} of {len(paths)}: {str(js.get('why', ''))[:100]}")
            return k
    except (AttributeError, TypeError, ValueError):
        pass
    return 0


def premade_thumb(slot, out):
    """the thumbnail picture made this morning for this video (best model + Gemini's pick)"""
    p = os.path.join(THUMB_PRE, f"{str(slot).replace('@', '_')}.jpg")
    if slot and os.path.exists(p):
        shutil.copy(p, out)
        log("  thumbnail picture made this morning with the high-quality model")
        return True
    return False


def premake_thumbs(day):
    """MORNING, before anything else uses pictures: the thumbnail pictures of today's 2 PM and 8 PM videos with the
    best free model (Leonardo Lucid Origin) + 2 quick alternatives - Gemini picks the best. (Cloudflare's free
    pictures are refilled at 5:30 AM; by evening they are used up - 9 Nov the 8 PM thumbnail had to fall back.)
    A preview of each goes to you on Telegram."""
    if DRY_RUN or env("PREMAKE_THUMBS") == "0":
        return []
    plans, made = _jload(PLANS_FILE, {}), []
    os.makedirs(THUMB_PRE, exist_ok=True)
    for h in (NOON, EVENING):
        key = f"{day}@{h}"
        plan = plans.get(key)
        out = os.path.join(THUMB_PRE, f"{key.replace('@', '_')}.jpg")
        if not isinstance(plan, dict) or not isinstance(plan.get("story"), dict) or os.path.exists(out):
            continue
        story = _story_cast(plan)
        cast = Cast(story)
        t_prompt, tkind, hero, gname, _ti = thumb_plan(story, cast, plan.get("special"), plan.get("cat"))
        seed = random.randint(1, 1_000_000)
        cands = []
        if not MOCK:
            p0 = os.path.join(WORK, f"tcand_{h}_0.jpg")
            if extras.hq_image(t_prompt, p0, seed, w=int(env("HQ_W") or 1024), h=int(env("HQ_H") or 576)):
                cands.append(p0)
            for k in range(1, 1 + int(env("THUMB_ALTERNATIVES") or 2)):
                pk = os.path.join(WORK, f"tcand_{h}_{k}.jpg")
                try:
                    save_picture(cf_request(CF_MODEL, t_prompt, None, seed=seed + 101 * k), pk)
                    cands.append(pk)
                except Exception as e:
                    log(f"  thumbnail alternative {k}: {str(e)[:120]}")
                    break
        else:
            pk = os.path.join(WORK, f"tcand_{h}_0.jpg")
            Image.new("RGB", (1024, 576), (40, 10, 10)).save(pk)
            cands.append(pk)
        if not cands:
            continue
        best = cands[judge_pictures(cands)]
        from PIL import ImageEnhance
        im = Image.open(best).convert("RGB").resize((1280, 720), Image.LANCZOS)
        ImageEnhance.Sharpness(im).enhance(1.25).save(out, quality=95)
        made.append(key)
        log(f"Thumbnail picture for {SLOT_BN[h]} made this morning ({len(cands)} tried, the best kept)")
        try:                                         # a preview on Telegram, with the words it will carry
            pv = os.path.join(WORK, f"preview_{h}.jpg")
            lang = plan.get("lang") if plan.get("lang") in LANGS else "bn"
            small = _thumb_small(plan, int(plan.get("part") or 0), plan.get("special"), lang,
                                 bool(story.get("true_label")))
            extras.title_poster(out, extras.thumb_words(story, _plan_title(plan)), pv, tkind, small=small,
                                fallback_font=FONT or find_font(lang))
            tg_photo(pv, f"{SLOT_NO[h]}️⃣ {SLOT_BN[h]}: {_plan_title(plan)}\nbot-এর thumbnail এরকম হবে। নিজেরটা দিতে "
                         f"চাইলে ছবিটা পাঠান, নিচে {SLOT_NO[h]} লিখে।")
        except Exception as e:
            log("  thumbnail preview not sent:", str(e)[:120])
    if made and not MOCK:
        push_now([THUMB_PRE], "today's thumbnail pictures")
    try:                                             # older days' pictures go (the repo stays small)
        for f in os.listdir(THUMB_PRE):
            if f[:10] < (dt.date.fromisoformat(day) - dt.timedelta(days=2)).isoformat():
                os.remove(os.path.join(THUMB_PRE, f))
    except (OSError, ValueError):
        pass
    return made


def morning_prepare(day, history):
    """v68 morning: any story not yet written (the night run failed) is written now, then today's thumbnail
    pictures FIRST, then the title list (only if it did not go out last night)."""
    hist2 = list(history)
    for h in (NOON, EVENING):
        key = f"{day}@{h}"
        plan = load_plan(key)
        if not plan:
            log(f"=== Writing the story for {when_words('bn', h, 0)} ({key}) ===")
            STATE.clear()
            SCRIPTS.clear()
            try:
                plan = choose_and_write(h, hist2)
                plan = json.loads(json.dumps(plan, ensure_ascii=False, default=list))
                save_plan(key, plan)
                push_now([PLANS_FILE, MY_STORIES], f"story written for {key}")
            except Exception as e:
                log(f"  the story for {key} could not be written now ({str(e)[:200]}) - its own run will write it")
                continue
        hist2.append({"theme": plan.get("theme"), "title": plan["story"].get("title"), "lang": plan.get("lang"),
                      "category": plan.get("cat"), "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                      "viewer_names": [p[0] for p in ((plan.get("state") or {}).get("viewer_names") or [])]})
    send_title_list(day)
    try:
        premake_thumbs(day)
    except Exception as e:
        log("  morning thumbnails skipped:", str(e)[:150])
    try:
        thumb_inbox()                                # your pictures sent during the night
    except Exception as e:
        log("  your Telegram pictures skipped:", str(e)[:120])


# ----------------------------------------------------------------- 4) the Sunday report on Telegram
def weekly_report(history, force=False):
    """SUNDAY NIGHT (with the weekly compilation): the week in numbers on Telegram - views, the best stories, which
    time and which kind of story worked, your thumbnails vs the bot's, how much people watched and where they
    left, and what the bot changes next week."""
    if env("WEEKLY_REPORT") == "0":
        return False
    now = dt.datetime.now(extras.IST)
    wk = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
    st_ = _jload(WEEKLY_FILE, {})
    st_ = st_ if isinstance(st_, dict) else {}
    if st_.get("last") == wk and not force:
        return False
    if not MOCK:
        try:
            extras.refresh_stats(history, max_items=40)
            save_history(history)
        except Exception as e:
            log("  weekly report: stats not refreshed:", str(e)[:120])
    week = []
    for h in history:
        if h.get("kind") or not (h.get("facebook") or h.get("youtube")):
            continue
        try:
            t = dt.datetime.fromisoformat(str(h.get("date")))
        except ValueError:
            continue
        if (now - t.replace(tzinfo=t.tzinfo or dt.timezone.utc)).days < 7:
            week.append(h)
    if not week:
        return False
    S = lambda h: h.get("stats") or {}
    tot = {k: sum(int(S(h).get(k) or 0) for h in week) for k in ("views", "likes", "comments")}
    d0 = now - dt.timedelta(days=6)
    lines = [f"📊 সাপ্তাহিক হিসেব ({str(d0.day).translate(BN_DIGITS)} {BN_MONTH_NAMES[d0.month - 1]} - "
             f"{str(now.day).translate(BN_DIGITS)} {BN_MONTH_NAMES[now.month - 1]})",
             f"ভিডিও: {len(week)}টা | 👁 {tot['views']} | 👍 {tot['likes']} | 💬 {tot['comments']}"]
    scored = sorted([h for h in week if S(h)], key=lambda h: extras.score(S(h)), reverse=True)
    if scored:
        lines.append("\n🏆 সেরা গল্প:")
        for k, h in enumerate(scored[:3]):
            lines.append(f"{k + 1}) {re.sub(r'[|].*$', '', str(h.get('title', '')))[:55].strip()} - 👁 {S(h).get('views', 0)}"
                         f" 👍 {S(h).get('likes', 0)} 💬 {S(h).get('comments', 0)}")

    def avg(rows, k="views"):
        v = [float(S(h).get(k) or 0) for h in rows if S(h)]
        return sum(v) / len(v) if v else None
    by_t = {w: avg([h for h in week if str(h.get("slot", "")).endswith(f"@{hh}")]) for hh, w in ((NOON, "দুপুর ২টো"),
                                                                                           (EVENING, "রাত ৮টা"))}
    by_t = {k: v for k, v in by_t.items() if v is not None}
    if len(by_t) == 2:
        lines.append("\n⏰ গড় view: " + " | ".join(f"{k}: {v:.0f}" for k, v in by_t.items()))
    cats = {}
    for h in week:
        if S(h) and h.get("category") in HORROR_CATS:
            cats.setdefault(h["category"], []).append(h)
    ca = sorted(((avg(v), HORROR_CATS[c]["bn"]) for c, v in cats.items() if avg(v) is not None), reverse=True)
    if len(ca) >= 2:
        lines.append(f"🗂️ সবচেয়ে ভালো চলেছে: {ca[0][1]} (গড় {ca[0][0]:.0f}), সবচেয়ে কম: {ca[-1][1]} (গড় {ca[-1][0]:.0f})")
    ut = avg([h for h in week if h.get("thumb_src") == "user"])
    bt = avg([h for h in week if h.get("thumb_src") and h.get("thumb_src") != "user"])
    if ut is not None and bt is not None:
        lines.append(f"🖼️ thumbnail: আপনার পাঠানো ছবিতে গড় view {ut:.0f}, bot-এর ছবিতে {bt:.0f}")
    yp = [float(S(h)["yt_avg_pct"]) for h in week if S(h).get("yt_avg_pct") is not None]
    fp = [float(S(h)["watched_pct"]) for h in week if S(h).get("watched_pct") is not None]
    if yp or fp:
        lines.append("⏱️ গড়ে দেখা হয়েছে: " + " | ".join(x for x in (
            f"YouTube {sum(yp) / len(yp):.0f}%" if yp else "", f"Facebook {sum(fp) / len(fp):.0f}%" if fp else "") if x))
    leave = []
    for h in week:
        tl, d = h.get("timeline") or {}, S(h).get("yt_drop_at")
        if d is not None and tl.get("len") and tl.get("parts"):
            sec = float(tl["len"]) * float(d) / 100
            lab = next((l_ for t_, l_ in reversed(tl["parts"]) if t_ <= sec), None)
            if lab:
                leave.append(f"'{lab}' ({int(sec // 60)}:{int(sec % 60):02d})")
    if leave:
        lines.append("📉 বেশিরভাগ দর্শক যেখানে ছেড়ে গেছেন: " + ", ".join(leave[:3]))
    les = (_jload(os.path.join(HERE, "assets", "lessons.json"), {}).get("horror_bn") or {})
    tips = [str(x) for x in (les.get("lessons") or [])[:3]]
    if tips:
        bn = _bn_lines(tips)
        lines.append("\n🧠 পরের সপ্তাহে bot যা মাথায় রাখবে:")
        lines += [f"• {x}" for x in bn]
    ok = _tg_text("\n".join(lines))
    if ok:
        st_["last"] = wk
        _jsave(WEEKLY_FILE, st_)
        push_now([WEEKLY_FILE, HISTORY], "weekly report sent")
        log("Weekly report sent on Telegram")
    return ok


def _bn_lines(lines):
    """the lessons in Bengali for you (one small Gemini request; English if it cannot)"""
    key = env("GEMINI_API_KEY")
    if MOCK or not key:
        return lines
    prompt = ("Translate each line into simple, natural Bengali for a non-technical reader. Answer ONLY a JSON list "
              "of strings in the same order.\n" + json.dumps(lines, ensure_ascii=False))
    for model in extras.helper_models(key)[:3]:
        try:
            r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key},
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}},
                              timeout=90)
            if r.ok:
                out = extras.load_json_loose(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                if isinstance(out, list) and len(out) == len(lines):
                    return [str(x)[:220] for x in out]
        except Exception:
            pass
    return lines


# ----------------------------------------------------------------- 5) the stories as a YouTube podcast
def podcast_cover(name, out, lang="bn"):
    """a square cover (YouTube needs one before a playlist can be a podcast): our newest thumbnail picture, darker,
    with the playlist's name"""
    from PIL import ImageEnhance
    S_ = 1280
    src = None
    for p in sorted(glob.glob(os.path.join(THUMB_PRE, "*.jpg")) + glob.glob(os.path.join(WORK, "thumb_base.jpg")),
                    key=os.path.getmtime, reverse=True):
        src = p
        break
    if src:
        im = Image.open(src).convert("RGB")
        s = S_ / min(im.width, im.height)
        im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
        x = max(0, int(im.width * 0.62) - S_ // 2)
        im = im.crop((min(x, im.width - S_), 0, min(x, im.width - S_) + S_, S_))
        im = ImageEnhance.Brightness(im).enhance(0.6)
    else:
        im = Image.new("RGB", (S_, S_), (12, 4, 6))
    d = ImageDraw.Draw(im)
    try:
        f = extras._title_font("horror", 120, FONT or find_font(lang))[0]
    except Exception:
        f = ImageFont.load_default()
    words = str(name).split()
    rows, cur = [], ""
    for w in words:
        if cur and d.textlength(cur + " " + w, font=f) > S_ - 140:
            rows.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    rows.append(cur)
    y = S_ - 120 - 140 * len(rows)
    for r_ in rows:
        w_ = d.textlength(r_, font=f)
        d.text(((S_ - w_) / 2, y), r_, font=f, fill=(255, 235, 220), stroke_width=8, stroke_fill=(120, 0, 0))
        y += 140
    im.save(out, quality=88)
    return out


def yt_podcast(pid, name, lang="bn"):
    """YouTube: our story playlist becomes a PODCAST (listed on YouTube and YouTube Music as a show) - free and
    automatic: a square cover once, then the playlist marked as a podcast. Tried once a week until it works."""
    if MOCK or DRY_RUN or not pid or env("YT_PODCAST") == "0":
        return False
    st_ = _jload(PODCAST_FILE, {})
    st_ = st_ if isinstance(st_, dict) else {}
    s = st_.get(pid) or {}
    if s.get("ok"):
        return True
    try:
        if s.get("tried") and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(s["tried"])).days < 7:
            return False
    except ValueError:
        pass
    note = ""
    try:
        hdr = extras.yt_token()
        cover = podcast_cover(name, os.path.join(WORK, "podcast_cover.jpg"), lang)
        meta = json.dumps({"snippet": {"playlistId": pid, "type": "hero"}})
        bnd = "storybot" + str(random.randint(10 ** 8, 10 ** 9))
        body = (f"--{bnd}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n--{bnd}\r\n"
                f"Content-Type: image/jpeg\r\n\r\n").encode() + open(cover, "rb").read() + f"\r\n--{bnd}--".encode()
        r = requests.post("https://www.googleapis.com/upload/youtube/v3/playlistImages", timeout=120,
                          params={"part": "snippet", "uploadType": "multipart"},
                          headers={**hdr, "Content-Type": f"multipart/related; boundary={bnd}"}, data=body)
        if not r.ok:
            note = f"cover: {extras._yt_err(r)}"
        r = requests.put(f"{extras.YT}/playlists", params={"part": "status"}, timeout=60, headers=hdr,
                         json={"id": pid, "status": {"privacyStatus": "public", "podcastStatus": "enabled"}})
        if r.ok:
            st_[pid] = {"ok": True, "name": name, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
            log(f"  YouTube: the playlist '{name}' is now a PODCAST (YouTube + YouTube Music)")
            _tg_text(f"🎧 নতুন: '{name}' এখন YouTube / YouTube Music-এ পডকাস্ট হিসেবেও আছে - আলাদা কিছু করতে হবে না।")
        else:
            note = (note + " | " if note else "") + f"podcast: {extras._yt_err(r)}"
    except Exception as e:
        note = str(e)[:200]
    if note:
        log("  YouTube podcast not set yet:", note[:250])
        st_[pid] = {**s, "tried": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "why": note[:300]}
    _jsave(PODCAST_FILE, st_)
    push_now([PODCAST_FILE], "youtube podcast")
    return bool((st_.get(pid) or {}).get("ok"))



def recap_frames(history, series_id, part, lang, n=3):
    """v70 'আগের পর্বে...': real pictures from the LAST PART's film - grey, like a memory - for the opening of this
    part, while the storyteller tells what happened. (No new pictures are needed for them either.)"""
    if MOCK or DRY_RUN or env("RECAP_FRAMES") == "0" or not part or int(part) < 2 or not series_id:
        return []
    ph = next((h for h in reversed(history) if h.get("series_id") == series_id and not h.get("kind")
               and int(h.get("part") or 0) == int(part) - 1 and h.get("facebook")), None)
    if not ph:
        return []
    from PIL import ImageEnhance, ImageFilter, ImageOps
    src, length = extras.fb_video_source(ph["facebook"])
    if not src or length < 120:
        return []
    out = []
    label = "আগের পর্বে" if lang == "bn" else "पिछले भाग में"
    for k, fr in enumerate((0.36, 0.62, 0.9)[:n]):
        raw = os.path.join(WORK, f"recap_raw_{k}.jpg")
        try:
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{length * fr:.1f}", "-i", src,
                                "-frames:v", "1", "-q:v", "2", raw], capture_output=True, timeout=150)
            if r.returncode != 0 or not os.path.exists(raw) or os.path.getsize(raw) < 5000:
                continue
            im = Image.open(raw).convert("RGB")
            w, h = im.size
            if h > w:                                 # Facebook's 9:16 film: the picture is the band in the middle
                im = im.crop((0, int(h * 300 / 1280), w, int(h * 860 / 1280)))
            else:                                     # 16:9: without the badge at the top and the subtitles below
                im = im.crop((int(w * 0.1), int(h * 0.15), int(w * 0.9), int(h * 0.76)))
            im = ImageOps.fit(im, (W, H), Image.LANCZOS, centering=(0.5, 0.7))   # (below the heartbeat line)
            g = ImageOps.grayscale(im)                # a memory: grey with a touch of cold blue, soft, dark edges
            im = ImageOps.colorize(g, (6, 8, 14), (214, 222, 235)).filter(ImageFilter.GaussianBlur(1.1))
            im = ImageEnhance.Contrast(im).enhance(1.15)
            vg = Image.new("L", (W, H), 0)
            ImageDraw.Draw(vg).ellipse([-W * 0.18, -H * 0.3, W * 1.18, H * 1.3], fill=255)
            im = Image.composite(im, Image.new("RGB", (W, H), (0, 0, 0)), vg.filter(ImageFilter.GaussianBlur(120)))
            d = ImageDraw.Draw(im, "RGBA")
            f_ = extras._font(FONT, 34)
            txt = extras.fit_glyphs(label, FONT)
            tw = d.textlength(txt, font=f_)
            d.rounded_rectangle([40, 96, 40 + tw + 44, 96 + 56], radius=14, fill=(0, 0, 0, 170))
            d.text((62, 102), txt, font=f_, fill=(255, 215, 80, 255))
            p_ = os.path.join(WORK, f"recap_{k}.jpg")
            im.save(p_, quality=92)
            out.append(p_)
        except Exception as e:
            log("  recap picture skipped:", str(e)[:100])
        finally:
            if os.path.exists(raw):
                os.remove(raw)
    if out:
        log(f"  the recap opens with {len(out)} real pictures from part {int(part) - 1}")
    return out


# ===================================================================================================== v76: growth
ASSETS = os.path.join(HERE, "assets")
MILESTONE_FILE = os.path.join(ASSETS, "milestones.json")
COACH_FILE = os.path.join(ASSETS, "coach.json")
GROWTH_FILES = [os.path.join(ASSETS, f) for f in ("promos.json", "milestones.json", "tg_channel.json", "viewer_voice.json", "coach.json",
                                                   "messenger.json", "tg_requests.json")]


def video_len(h):
    tl = h.get("timeline") or {}
    if tl.get("len"):
        return float(tl["len"])
    if h.get("facebook"):
        try:
            return float(extras.fb_video_source(h["facebook"])[1] or 0) or None
        except Exception:
            return None
    return None


def daily_monitor(history):
    """v77: ONCE A DAY - the health of every key, the channel's numbers, the first 30 seconds, clicks, how long people
    watch: what the bot changes by itself, and (only if needed) what YOU must do. One message on Telegram."""
    coach, lines, did = extras.growth_monitor(history, COACH_FILE, "horror", "bn", video_len)
    if lines is None or (not lines and not did and not (coach.get("last_report") or {}).get("todo")):
        return False
    todo = (coach.get("last_report") or {}).get("todo") or []
    msg = ["📈 ভূতের চ্যানেল - আজকের খবর"] + lines
    if did:
        msg += ["", "🤖 bot নিজে যা বদলাল:"] + [f"• {x}" for x in did]
    msg += ["", "⚠️ আপনাকে যা করতে হবে:"] + [f"• {x}" for x in todo] if todo else ["", "✅ সব চাবি ঠিক আছে - আপনার কিছু করার নেই।"]
    extras.telegram("\n".join(msg))
    save_history(history)
    return True


def story_slug():
    s = str(SLOT or dt.datetime.now(extras.IST).strftime("%Y-%m-%d@%H"))
    return re.sub(r"[^0-9A-Za-z-]", "-", s)


def trend_theme(cat, lang, history):
    """v79: this week's most watched topic on YouTube for THIS category (searched by its own words) that we have not
    used yet - or None (then the story keeps its normal theme)"""
    if MOCK or env("TREND_STORY") == "0" or cat in ("classic",):
        return None
    try:
        tr_ = extras.trending_topics("horror", lang, os.path.join(HERE, "assets"), cat)
    except Exception as e:
        log("  trend story skipped:", str(e)[:100])
        return None
    done_ = {str(h.get("theme", "")).strip() for h in history} | {str(h.get("trend_used", "")).strip() for h in history}
    tr_ = [x.strip() for x in tr_ if x.strip() and x.strip() not in done_ and not any(x.strip() in d for d in done_ if d)]
    if not tr_:
        return None
    STATE["trend_used"] = tr_[0]
    STATE["trends"] = tr_[:6]
    log(f"TREND STORY ({cat}) - what is most watched on YouTube this week in this kind: {tr_[0][:120]}")
    return tr_[0]


def hit_for_sequel(history, lang):
    """a normal story (not a series) of the last 3-12 days that people watched at least twice as much as usual and
    that has no sequel yet - at most one sequel a week"""
    if env("SEQUELS") == "0":
        return None
    now = dt.datetime.now(dt.timezone.utc)

    def age(h):
        try:
            return (now - dt.datetime.fromisoformat(str(h.get("date")))).days
        except Exception:
            return 999
    if any(h.get("sequel_of") and age(h) < 7 for h in history[-20:]):
        return None
    recent = [h for h in history[-40:] if not h.get("kind") and h.get("stats") and h.get("lang", "bn") == lang]
    scores = sorted(extras.score(h["stats"]) for h in recent)
    if len(scores) < 6:
        return None
    med = max(scores[len(scores) // 2], 1)
    done = {h.get("sequel_of") for h in history if h.get("sequel_of")}
    for h in sorted(recent, key=lambda h: -extras.score(h["stats"])):
        if (3 <= age(h) <= 12 and not h.get("special") and not h.get("part") and not h.get("sequel_of")
                and (h.get("slot") or h.get("title")) not in done and extras.score(h["stats"]) >= 2 * med):
            log(f"SEQUEL: '{h.get('title')}' was watched {extras.score(h['stats']) / med:.1f}x more than usual")
            return h
    return None


def sequel_rule(h, lang):
    t = re.sub(r"\s*\|.*$", "", str(h.get("title", ""))).strip()
    return (f"\nSEQUEL OF OUR HIT STORY '{t}' (our listeners loved it): {h.get('summary') or h.get('theme') or ''}\n"
            "Write its second story: the same place and the same surviving people some time later, a NEW mystery that "
            "grows out of what was left unexplained; in the first minute the storyteller reminds the listener in two "
            "or three sentences what happened last time. The TITLE says that it is back (for example '"
            + t[:30] + " ফিরে এল ...'). A complete story of its own.\n")


BEST_COMMENT_FILE = os.path.join(HERE, "assets", "best_comment.json")


def add_best_comment(story, history, lang, slot_hour):
    """SUNDAY 8 PM: before the story, the storyteller reads the week's best viewer comment with the viewer's name"""
    if env("BEST_COMMENT") == "0" or slot_hour != EVENING or dt.datetime.now(extras.IST).weekday() != 6:
        return
    wk = dt.datetime.now(extras.IST).strftime("%G-W%V")
    if (_jload(BEST_COMMENT_FILE, {}) or {}).get("week") == wk:
        return
    bc = extras.best_comment(history, "horror")
    if not bc:
        return
    line = (f"গল্প শুরুর আগে... এ সপ্তাহে আপনাদের সবচেয়ে সুন্দর মন্তব্যটি লিখেছেন {bc['name']}। তিনি লিখেছেন: "
            f"“{bc['text']}”... ধন্যবাদ {bc['name']}। আর এবার, আজকের গল্প।" if lang == "bn" else
            f"कहानी से पहले... इस हफ़्ते की सबसे सुंदर टिप्पणी {bc['name']} ने लिखी: “{bc['text']}”... धन्यवाद "
            f"{bc['name']}। और अब, आज की कहानी।")
    (story.get("scenes") or [{}])[0].setdefault("lines", []).insert(0, {"speaker": "narrator", "emotion": "calm",
                                                                         "text": line})
    STATE["best_comment_id"] = bc["id"]
    _jsave(BEST_COMMENT_FILE, {"week": wk, "id": bc["id"]})
    try:
        push_now([BEST_COMMENT_FILE], "best comment of the week")
    except Exception:
        pass
    log(f"  the week's best comment (by {bc['name']}) is read before the story")


def make_web_story(story, title, video, results, base, lang, names):
    """8 vertical pictures from the finished video + 8 short lines of the story -> a Google Web Story"""
    dur_ = duration(video)
    lines = [extras.strip_tags(str(ln.get("text", ""))).strip() for sc in story.get("scenes") or []
             for ln in sc.get("lines") or [] if str(ln.get("speaker", "narrator")).lower().startswith("narrat")]
    lines = [l for l in lines if len(l) >= 20]
    if len(lines) < 8 or dur_ < 60:
        return None
    pick = [lines[int(i * (len(lines) - 1) / 7)] for i in range(8)]
    pick = [re.split(r"(?<=[।!?])\s+", p)[0][:120] for p in pick]
    urls = []
    for i in range(8):
        tsec = dur_ * (0.08 + 0.84 * i / 7)
        fr = os.path.join(WORK, f"ws_{i}.jpg")
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{tsec:.1f}", "-i", video, "-frames:v", "1", "-vf",
             "crop=ih*9/16:ih,scale=720:1280", "-q:v", "4", fr])
        urls.append(extras.gh_release_upload(fr, f"{story_slug()}_{i}.jpg", tag="webstory", ctype="image/jpeg",
                                             title="Web Story pictures"))
    if not all(urls):
        return None
    link = (f"https://youtu.be/{results['youtube']}" if results.get("youtube") else
            f"https://www.facebook.com/{results.get('facebook', '')}")
    u = extras.web_story(MAP_DIR, story_slug(), re.sub(r"\s*\|.*$", "", title).strip(), urls, pick, base, link, lang)
    log(f"  web story: {u}")
    return u


def _today_done(history, kind, days=0):
    today = dt.datetime.now(extras.IST).date()
    for h in reversed(history[-80:]):
        if h.get("kind") == kind:
            try:
                d = dt.datetime.fromisoformat(str(h["date"])).astimezone(extras.IST).date()
            except Exception:
                continue
            if (today - d).days <= days:
                return True
    return False


def _dark_bg(w, h, seed=0):
    """a dark, misty, original background when no picture can be made"""
    np = _np()
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype("float32")
    v = 1 - np.clip(np.hypot((x - w / 2) / w, (y - h * 0.45) / h) * 1.6, 0, 1)
    img = np.stack([v * 30 + 6, v * 38 + 8, v * 52 + 12], -1)
    fog = np.zeros((h // 8 + 1, w // 8 + 1), "float32")
    for _ in range(40):
        cx, cy, r = rng.uniform(0, w // 8), rng.uniform(0, h // 8), rng.uniform(4, 20)
        fog += np.exp(-(((np.arange(w // 8 + 1)[None, :] - cx) ** 2 + (np.arange(h // 8 + 1)[:, None] - cy) ** 2) / (2 * r * r)))
    fog = np.array(Image.fromarray(np.clip(fog / fog.max() * 255, 0, 255).astype("uint8")).resize((w, h))).astype("float32")
    img += fog[..., None] * np.array([0.10, 0.12, 0.16])
    return Image.fromarray(np.clip(img, 0, 255).astype("uint8"))


def _picture(prompt, w, h, path, seed=0):
    """one picture from the picture model (no people, no text) - or the misty dark background"""
    try:
        if not MOCK and not CF_QUOTA_OUT:
            save_picture(cf_request(CF_MODEL, prompt + ". Dark, atmospheric, cinematic, eerie Bengal night, no people, "
                                    "no text, no letters, no watermark", w=w, h=h, seed=seed), path)
            if os.path.exists(path) and os.path.getsize(path) > 5000:
                im = Image.open(path).convert("RGB").resize((w, h))
                im.save(path, quality=92)
                return path
    except Exception as e:
        log("  picture not made, misty background instead:", str(e)[:100])
    _dark_bg(w, h, seed).save(path, quality=92)
    return path


def _drone(secs, seed=0, heart_at=None):
    """a low, uneasy drone (and a heartbeat near the end) - our own sound, no copyright"""
    np = _np()
    rnd = np.random.default_rng(seed)
    n = int(secs * SR)
    t_ = np.arange(n) / SR
    a = 0.10 * np.sin(2 * np.pi * 55 * t_) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t_))
    a += 0.05 * np.sin(2 * np.pi * 82.4 * t_ + 0.5 * np.sin(2 * np.pi * 0.2 * t_))
    a += _filt(rnd.standard_normal(n), "lowpass", 400) * 0.06
    try:
        a += synth("wind", n, rnd) * 0.25
    except Exception:
        pass
    if heart_at is not None:
        k = int(heart_at * SR)
        hb = synth("heartbeat", n - k, rnd) * 0.6
        a[k:k + len(hb)] += hb[:n - k]
    fade = int(SR * 1.0)
    a[:fade] *= np.linspace(0, 1, fade)
    a[-fade:] *= np.linspace(1, 0, fade)
    return a / (np.abs(a).max() + 1e-9) * 0.7


def daily_text_short(history):
    """v83 - EVERY DAY: a tiny written ghost story (3-4 sentences) appearing line by line on a dark picture, with our
    own uneasy sound - a YouTube Short and a Facebook Reel at 10 AM. No voice at all."""
    global FONT
    if env("TEXT_SHORTS") == "0" or _today_done(history, "text_short"):
        return False
    lang = "bn"
    FONT = FONT or find_font(lang)
    avoid = [h.get("title") for h in history if h.get("kind") == "text_short"][-60:]
    ms = extras.micro_story(lang, avoid) if not MOCK else {
        "title": "শেষ বাসের যাত্রী", "lines": ["রাত সাড়ে এগারোটার শেষ বাসে আমি একাই ছিলাম।", "কন্ডাক্টর দুটো টিকিট কাটল।",
                                             "জিজ্ঞেস করতেই বলল, আপনার পাশের দিদিরটা।", "আমার পাশের সিট ফাঁকা ছিল।"],
        "picture": "an empty night bus interior"}
    if not ms:
        log("  text Short: no tiny story today (Gemini busy)")
        return False
    Wv, Hv = 720, 1280
    bg = _picture(ms["picture"], Wv, Hv, os.path.join(WORK, "ts_bg.jpg"), seed=len(avoid))
    lines = ms["lines"]
    per = [max(3.2, min(6.0, len(l) / 11.0)) for l in lines]
    t0, starts = 2.6, []
    for d_ in per:
        starts.append(t0)
        t0 += d_
    total = t0 + 3.0
    pngs = []

    def text_png(txt, size, color, y, path, box=True):
        im = Image.new("RGBA", (Wv, Hv), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        f = font(size)
        words, rows, cur = extras.fit_glyphs(txt, FONT).split(), [], ""
        for w_ in words:
            if cur and d.textlength(cur + " " + w_, font=f) > Wv * 0.84:
                rows.append(cur)
                cur = w_
            else:
                cur = (cur + " " + w_).strip()
        rows.append(cur)
        hh = int(size * 1.45)
        if box:
            d.rounded_rectangle([Wv * 0.05, y - 18, Wv * 0.95, y + hh * len(rows) + 10], radius=22, fill=(0, 0, 0, 120))
        for k, r_ in enumerate(rows):
            d.text(((Wv - d.textlength(r_, font=f)) / 2, y + k * hh), r_, font=f, fill=color, stroke_width=3,
                   stroke_fill=(0, 0, 0))
        im.save(path)
        return path, hh * len(rows) + 40
    title_png, _h = text_png("👻 " + ms["title"], 58, (255, 207, 74), 140, os.path.join(WORK, "ts_t.png"), box=False)
    y = 360
    for k, l in enumerate(lines):
        p_, hh = text_png(l, 40, (240, 240, 240) if k < len(lines) - 1 else (255, 90, 90), y, os.path.join(WORK, f"ts_{k}.png"))
        pngs.append(p_)
        y += hh
    end_png, _h = text_png("পুরো গল্প শুনুন আমাদের চ্যানেলে 🕯️", 36, (255, 207, 74), Hv - 220,
                           os.path.join(WORK, "ts_end.png"), box=False)
    wav = os.path.join(WORK, "ts.wav")
    write_wav(wav, _drone(total, len(avoid), heart_at=starts[-1] - 1.0))
    out = os.path.join(WORK, "text_short.mp4")
    lp = ["-loop", "1", "-framerate", "25", "-t", f"{total:.2f}"]     # (each picture as a running video)
    inputs = lp + ["-i", bg] + lp + ["-i", title_png] + sum((lp + ["-i", p_] for p_ in pngs), []) + \
        lp + ["-i", end_png] + ["-i", wav]
    fl = [f"[0:v]scale={Wv * 2}:{Hv * 2},zoompan=z='min(1+0.0009*on,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          f"d={int(total * 25)}:s={Wv}x{Hv}:fps=25,eq=brightness=-0.12:saturation=0.85[b0]",
          "[1:v]format=rgba,fade=t=in:st=0.3:d=0.8:alpha=1[t]", "[b0][t]overlay=0:0[b1]"]
    cur = "b1"
    for k, st in enumerate(starts):
        fl.append(f"[{k + 2}:v]format=rgba,fade=t=in:st={st:.2f}:d=0.9:alpha=1[l{k}]")
        fl.append(f"[{cur}][l{k}]overlay=0:0:enable='gte(t,{st:.2f})'[c{k}]")
        cur = f"c{k}"
    ei = len(starts) + 2
    fl.append(f"[{ei}:v]format=rgba,fade=t=in:st={total - 2.8:.2f}:d=0.6:alpha=1[e]")
    fl.append(f"[{cur}][e]overlay=0:0:enable='gte(t,{total - 2.8:.2f})',format=yuv420p[v]")
    run(["ffmpeg", "-y", "-loglevel", "error"] + inputs + ["-filter_complex", ";".join(fl), "-map", "[v]",
                                                            "-map", f"{ei + 1}:a", "-t", f"{total:.2f}", "-c:v", "libx264",
                                                            "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a",
                                                            "128k", out])
    log(f"Text Short ready: {ms['title']} ({total:.0f} s)")
    rec = {"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "lang": lang, "kind": "text_short",
           "title": ms["title"]}
    if MOCK or DRY_RUN:
        return False
    tags = ["#ভূতের_গল্প", "#BhuterGolpo", "#HorrorShorts", "#ছোট_গল্প", "#shorts"]
    last_long = next((h.get("youtube") for h in reversed(_hist_safe()) if h.get("youtube") and not h.get("kind")), "")
    desc = (f"{ms['title']}\n\n" + (f"▶ আগের পুরো ভূতের গল্পটা শুনুন: https://youtu.be/{last_long}\n\n" if last_long else "")
            + " ".join(ms["lines"]) + "\n\n🕯️ রোজ পুরো ভূতের গল্প দুপুর ২টো আর রাত ৮টায়।\n\n" + " ".join(tags))
    if youtube_ready() and extras.yt_extra_ok():
        try:
            rec["youtube"] = post_to_youtube(out, None, f"{ms['title']} 👻 #Shorts", desc, ["shorts", "bhuter golpo",
                                                                                           "horror story bangla"], lang)
            log("  text Short on YouTube:", rec["youtube"])
        except Exception as e:
            log("  text Short (YouTube) skipped:", str(e)[:150])
    if env("FB_PAGE_TOKEN"):
        try:
            rec["facebook"] = extras.fb_post_reel(out, desc)
            log("  text Reel on Facebook:", rec["facebook"])
        except Exception as e:
            log("  text Reel skipped:", str(e)[:150])
    if rec.get("youtube") or rec.get("facebook"):
        history.append(rec)
        return True
    return False


AMBIENCE_SCENES = [
    ("ভূতুড়ে বৃষ্টির রাত", "a lonely old Bengal zamindar house at night in heavy rain, one dim lantern in a window, "
                          "wet banana trees, dark sky"),
    ("শ্মশানঘাটের কুয়াশা-রাত", "a misty river ghat at night with an old temple and burning lamps far away, fog over water"),
    ("জঙ্গলের ডাকবাংলো", "an old forest dak bungalow at night in the monsoon, a hurricane lantern on the verandah, rain"),
    ("পুরনো কলকাতার গলি", "a narrow old north Kolkata lane at night in the rain, a flickering street lamp, closed doors"),
]


def weekly_ambience(history):
    """v83 - EVERY WEDNESDAY: a long 'sleep / study' video (2 hours) - a dark rainy scene with our own rain, wind,
    crickets and far-away night sounds, softly moving. No voice. YouTube + Facebook."""
    global FONT
    if (env("AMBIENCE") == "0" or dt.datetime.now(extras.IST).weekday() != int(env("AMBIENCE_DAY") or 2)
            or _today_done(history, "ambience", days=5)):
        return False
    np = _np()
    lang = "bn"
    FONT = FONT or find_font(lang)
    n_done = sum(1 for h in history if h.get("kind") == "ambience")
    name, scene = AMBIENCE_SCENES[n_done % len(AMBIENCE_SCENES)]
    hours = float(env("AMBIENCE_HOURS") or 2)
    secs = int(hours * 3600) if not MOCK else 30
    img = _picture(scene, 1280, 720, os.path.join(WORK, "amb.jpg"), seed=n_done + 77)
    # 1) 20 seconds of picture that loops without a seam: falling rain + a breathing lantern light
    base = np.asarray(Image.open(img).convert("RGB").resize((1280, 720))).astype("float32")
    rng = np.random.default_rng(n_done)
    LOOP, FPSA = 20, 25
    drops = np.c_[rng.uniform(0, 1280, 260), rng.uniform(0, 720, 260), rng.uniform(1, 3, 260)]   # x, y, speed (screens / loop)
    loop_mp4 = os.path.join(WORK, "amb_loop.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1280x720",
                           "-r", str(FPSA), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                           "-g", str(FPSA * 2), "-pix_fmt", "yuv420p", loop_mp4], stdin=subprocess.PIPE)
    import cv2
    for f in range(LOOP * FPSA):
        u = f / (LOOP * FPSA)
        fr = base * (0.86 + 0.06 * math.sin(2 * math.pi * 3 * u))
        layer = np.zeros((720, 1280), "float32")
        for x_, y_, sp in drops:
            yy = (y_ + sp * 720 * u * 4) % 720
            cv2.line(layer, (int(x_), int(yy)), (int(x_ - 3), int(yy + 18)), 1.0, 1)
        fr = fr + cv2.GaussianBlur(layer, (0, 0), 0.8)[..., None] * 70
        ff.stdin.write(np.clip(fr, 0, 255).astype("uint8").tobytes())
    ff.stdin.close()
    ff.wait()
    # 2) ten minutes of sound that loops: rain + wind + crickets + now and then a far-away night sound
    n = SR * 600 if not MOCK else SR * 30
    rnd = np.random.default_rng(n_done + 5)
    a = synth("rain", n, rnd) * 0.55 + synth("wind", n, rnd) * 0.25 + synth("crickets", n, rnd) * 0.18
    real = freesound("heavy rain on roof night", True)
    if real:
        r_ = _decode(real, 600)
        if len(r_) > SR * 20:
            a += np.resize(r_, n) * 0.6
    for k in range(int(n / SR / 75)):
        at = int(rnd.uniform(20, n / SR - 10) * SR)
        snd = synth(rnd.choice(["owl", "thunder", "creak", "drip", "clock"]), int(SR * 4), rnd) * 0.35
        a[at:at + len(snd)] += snd[:max(0, n - at)]
    xf = SR * 3                                        # the end fades into the start - the loop has no seam
    a[:xf] = a[:xf] * np.linspace(0, 1, xf) + a[-xf:] * np.linspace(1, 0, xf)
    a = a[:-xf]
    wav = os.path.join(WORK, "amb.wav")
    write_wav(wav, a / (np.abs(a).max() + 1e-9) * 0.6)
    out = os.path.join(WORK, "ambience.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", loop_mp4, "-stream_loop", "-1", "-i", wav,
         "-t", str(secs), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", out])
    hrs_bn = str(int(hours)).translate(BN_DIGITS)
    title = f"{name} 🌧️ {hrs_bn} ঘণ্টা | ঘুম আর পড়ার জন্য গা ছমছমে বৃষ্টির আবহ | Horror Rain Ambience for Sleep"[:100]
    thumb = extras.text_card(img, [name, f"{hrs_bn} ঘণ্টা ঘুমের আবহ", "কোনো কথা নেই, শুধু রাত"], os.path.join(WORK, "amb_thumb.jpg"), FONT)
    log(f"Ambience video ready: {name} ({secs / 3600:.1f} h)")
    if MOCK or DRY_RUN:
        return False
    desc = (f"{name} - {hrs_bn} ঘণ্টা একটানা বৃষ্টি, হাওয়া, ঝিঁঝিঁ আর দূরের রাতের শব্দ। ঘুমোনোর, পড়ার বা ভূতের গল্প পড়ার "
            "সময় চালিয়ে রাখুন। কোনো কথা নেই, কোনো হঠাৎ জোরে শব্দ নেই।\n\n🕯️ রোজ নতুন ভূতের গল্প দুপুর ২টো আর রাত ৮টায়।\n\n"
            "#ভূতের_গল্প #RainSounds #SleepSounds #HorrorAmbience #BhuterGolpo")
    rec = {"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "lang": lang, "kind": "ambience",
           "title": title}
    if youtube_ready() and extras.yt_extra_ok():
        try:
            rec["youtube"] = post_to_youtube(out, thumb, title, desc, ["rain sounds", "sleep sounds", "horror ambience",
                                                                       "ভূতের গল্প", "bhuter golpo"], lang)
            log("  ambience on YouTube:", rec["youtube"])
        except Exception as e:
            log("  ambience (YouTube) skipped:", str(e)[:150])
    if env("FB_PAGE_TOKEN"):
        try:
            rec["facebook"] = post_to_facebook(out, thumb, title, desc)
            log("  ambience on Facebook:", rec["facebook"])
        except Exception as e:
            log("  ambience (Facebook) skipped:", str(e)[:150])
    if rec.get("youtube") or rec.get("facebook"):
        history.append(rec)
        return True
    return False


def crossover_rule(history, part, prev):
    """ONCE A MONTH (a Bhairab case that starts in the month's last 8 days): Nilkantha Acharya and Bapi of the
    Karna Pishachini series join Bhairab Thakur and Paltu - both series' listeners meet. Both parts of the case."""
    if env("CROSSOVER") == "0":
        return ""
    if part >= 2:
        if not (prev or {}).get("crossover"):
            return ""
    else:
        now = dt.datetime.now(extras.IST) + dt.timedelta(days=1)          # (written the night before)
        last = (now.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        month = now.strftime("%Y-%m")
        if (last.day - now.day) > 7 or any(h.get("crossover") and str(h.get("date", ""))[:7] == month for h in history):
            return ""
    STATE["crossover"] = True
    log("CROSSOVER - this month's 'মহা-কেস': Bhairab Thakur and Paltu meet Nilkantha Acharya and Bapi")
    return ("\nCROSSOVER - THIS MONTH'S 'মহা-কেস': in this case our two series meet. NILKANTHA ACHARYA and his nephew BAPI "
            "(of the Karna Pishachini series; the Karna Pishachini whispers hidden truths into Nilkantha's ear, at a "
            "terrible price) come to BHAIRAB THAKUR and PALTU with a case neither can solve alone. Their looks: "
            + json.dumps(KARNA, ensure_ascii=False)[:1500] + ". Bhairab's calm tantrik method and Nilkantha's dangerous "
            "gift clash and then work together; each keeps his own way of speaking. The TITLE starts with 'মহা-কেস: '.\n")


PROMO_FILE = os.path.join(ASSETS, "promos.json")


def _clean_url(u):
    """a link without the tracking part (?si=...&utm_source=...)"""
    return str(u or "").strip().split("?")[0].split("#")[0].rstrip("/")


def _short_url(u):
    return re.sub(r"^https?://", "", _clean_url(u))


def promo_list(lang):
    """v84: our features that can be advertised RIGHT NOW (only the ones that really work - no dead links)"""
    if lang != "bn" or env("PROMOS") == "0":
        return {}
    base = map_url() if not MOCK else (env("MAP_URL") or "https://sumonsham.github.io/horror-story-bot/map/")
    bot = extras.tg_bot_link()
    ch = channel_link()
    out = {}
    if base:
        out["map"] = {"icon": "map", "head": "বাংলার ভূতের মানচিত্র", "sub": "আপনার জেলার ভূতের গল্প এক জায়গায়",
                      "sub2": "প্রতিটা নতুন গল্পের সাথে মানচিত্র নিজেই বাড়ে", "link": _short_url(base), "url": base}
    if bot and env("TG_REQUESTS") != "0":
        out["golpo_chai"] = {"icon": "bot", "head": "Telegram-এ লিখুন: গল্প চাই",
                             "sub": "সাথে সাথে একটা ছোট ভূতের গল্প আপনার কাছে", "sub2": "দিনে তিনটে পর্যন্ত, একদম বিনামূল্যে",
                             "link": _short_url(bot), "url": bot}
    if bot and env("VIEWER_VOICE") != "0":
        out["voice"] = {"icon": "voice", "head": "আপনার নিজের ভৌতিক অভিজ্ঞতা",
                        "sub": "Telegram-এ গলায় বলে পাঠান - সেটা নিয়েই গল্প হবে", "sub2": "ভয়েস মেসেজ পাঠালেই হবে",
                        "link": _short_url(bot), "url": bot}
    if ch:
        out["channel"] = {"icon": "channel", "head": "আমাদের Telegram চ্যানেল", "sub": "নতুন গল্পের খবর সবার আগে",
                          "sub2": "কোন গল্প কখন আসছে - সব এখানে", "link": _short_url(ch), "url": ch}
    if base and (MOCK or os.path.exists(os.path.join(MAP_DIR, "podcast.xml"))):
        sp = _clean_url(env("SPOTIFY_URL"))
        out["podcast"] = {"icon": "podcast", "head": "এখন Spotify-তেও শুনুন",
                          "sub": "সব ভূতের গল্প পডকাস্টে - হাঁটতে চলতে শুনুন", "sub2": "Spotify-তে আমাদের নাম লিখে খুঁজুন",
                          "link": _short_url(sp), "url": sp}
    if env("YT_LIVE") != "0":
        out["live"] = {"icon": "live", "head": "প্রতি শনিবার রাতে লাইভ: ভূতের রাত",
                       "sub": "সপ্তাহের সেরা গল্প একটানা - YouTube-এ", "sub2": "লাইভ চ্যাটে আপনার নাম পর্দায় আসবে"}
    if base and env("STORY_PAGES") != "0":
        out["web"] = {"icon": "web", "head": "গল্পগুলো পড়তেও পারেন", "sub": "প্রতিটা গল্প লেখা আকারে আমাদের ওয়েবসাইটে",
                      "sub2": "রাতে শোনার আগে বা পরে - পড়ে নিন", "link": _short_url(base + "golpo/"), "url": base + "golpo/"}
    if env("AMBIENCE") != "0":
        out["ambience"] = {"icon": "moon", "head": "প্রতি বুধবার: ২ ঘণ্টার রাতের আওয়াজ",
                           "sub": "বৃষ্টি, হাওয়া, দূরের ঝিঁঝিঁ - ঘুম বা পড়ার জন্য", "sub2": "আমাদের YouTube চ্যানেলে"}
    out["series"] = {"icon": "star", "head": "বৃহস্পতি আর শনিবার রাত ৮টা: নতুন সিরিজ",
                     "sub": "নিশি-রেডিও, মর্গের খাতা, শেষ লোকাল, রাত-তদন্ত, ডাকবাংলোর খাতা",
                     "sub2": "প্রতি সপ্তাহে নতুন পর্ব"}
    if env("TEXT_SHORT") != "0":
        out["text_short"] = {"icon": "clock", "head": "রোজ সকাল ১০টা: এক মিনিটের ভূতের গল্প",
                             "sub": "ছোট্ট, কিন্তু রাতে মনে পড়বেই", "sub2": "YouTube Shorts আর Facebook Reels-এ"}
    return out


def promo_card_for(lang, secs):
    """(png, start, seconds) of this video's feature card - or None (every 2nd video, each feature every month)"""
    feats = promo_list(lang)
    if not feats or secs < (30 if MOCK else 120):
        return None
    pid = extras.promo_pick(PROMO_FILE, list(feats), every=int(env("PROMO_EVERY") or 2))
    if not pid:
        return None
    png = extras.promo_card_png((W, H), feats[pid], os.path.join(WORK, "promo_card.png"), FONT)
    log(f"  feature card in the video: {pid}")
    return (png, round(secs * 0.45, 1), 7.0)


def promo_monthly_post(thumb):
    """v84: one Facebook poster a day at most, every feature once a month, at least 3 days apart"""
    feats = promo_list(env("LANGUAGE") or "bn")
    if not feats or not env("FB_PAGE_TOKEN") or env("PROMO_POSTS") == "0":
        return False
    pid = extras.promo_post_due(PROMO_FILE, list(feats), gap_days=3)
    if not pid:
        return False
    f = feats[pid]
    img = extras.promo_poster(thumb, f, os.path.join(WORK, "promo_poster.jpg"), FONT)
    msg = "\n".join(x for x in [f"✨ {f['head']}", f.get("sub", ""), f.get("sub2", ""),
                                (f"👉 {f['url']}" if f.get("url") else "")] if x)
    now = dt.datetime.now(extras.IST)
    when = now.replace(hour=12, minute=15, second=0, microsecond=0)        # a quiet hour, far from the videos
    if when < now + dt.timedelta(minutes=30):
        when += dt.timedelta(days=1)
    extras.fb_schedule_photo(img, msg, when)
    extras.promo_post_done(PROMO_FILE, pid)
    log(f"  monthly feature poster scheduled on Facebook: {pid}")
    return True


def channel_link():
    """our Telegram fan channel: the one the bot found itself, else the address you gave (13 Nov 2026)"""
    return extras.tg_channel_link(ASSETS) or env("TG_CHANNEL_URL") or "https://t.me/dailyhorrorstory"


def growth_links(lang):
    """the lines under every video: read the story, tell us your own experience by voice, our fan channel"""
    if lang != "bn":
        return ""
    out = []
    base = map_url()
    if base and env("STORY_PAGES") != "0":
        out.append(f"📖 গল্পটা পড়ুন: {base}golpo/{story_slug()}.html")
    bot = extras.tg_bot_link()
    if bot and env("VIEWER_VOICE") != "0":
        out.append(f"🎙️ আপনার নিজের ভৌতিক অভিজ্ঞতা গলায় বলে পাঠান (Telegram-এ voice message) - সেটা নিয়েই গল্প হবে: {bot}")
    ch = channel_link()
    if ch:
        out.append(f"📢 নতুন গল্পের খবর সবার আগে: {ch}")
    sp = _clean_url(env("SPOTIFY_URL"))              # v87: the Spotify page itself (the feed file is for apps only)
    if sp:
        out.append(f"🎧 Spotify-তে শুনুন: {sp}")
    return "\n".join(out)


def growth_start(history):
    """every run: answers under YouTube comments, the fan channel's waiting messages, viewers' voice stories,
    and (once a day) the subscriber / follower milestones"""
    lang = env("LANGUAGE") or "bn"
    try:
        if extras.yt_reply_fans(history, lang, "horror"):
            save_history(history)
    except Exception as e:
        log("  YouTube replies skipped:", str(e)[:120])
    try:
        extras.tg_channel_flush(ASSETS)
    except Exception as e:
        log("  fan channel skipped:", str(e)[:100])
    try:
        extras.viewer_voice_process(ASSETS)
    except Exception as e:
        log("  viewer voices skipped:", str(e)[:100])
    try:                                             # v82: people who wrote to the Page on Messenger
        last_ = [h for h in history if not h.get("kind") and (h.get("youtube") or h.get("facebook"))][-2:]
        links_ = [f"{re.sub(r'[|].*$', '', str(h.get('title', ''))).strip()}: " +
                  (f"https://youtu.be/{h['youtube']}" if h.get("youtube") else f"https://www.facebook.com/{h['facebook']}")
                  for h in reversed(last_)]
        extras.messenger_replies("horror", links_, extras.tg_bot_link())
    except Exception as e:
        log("  Messenger skipped:", str(e)[:100])
    try:                                             # v83: 'গল্প চাই' on Telegram
        last1 = next((h for h in reversed(history) if not h.get("kind") and h.get("youtube")), None)
        extras.tg_requests_answer(ASSETS, f"https://youtu.be/{last1['youtube']}" if last1 else "")
    except Exception as e:
        log("  Telegram story requests skipped:", str(e)[:100])
    try:
        got = extras.milestone_check(MILESTONE_FILE)
        if got:
            celebrate_milestone(got, lang)
    except Exception as e:
        log("  milestones skipped:", str(e)[:100])
    if env("MONITOR") != "0":
        try:
            daily_monitor(history)
        except Exception as e:
            log("  daily monitor skipped:", str(e)[:150])
    try:
        push_now([f for f in GROWTH_FILES if os.path.exists(f)], "growth notes")
    except Exception:
        pass


def celebrate_milestone(got, lang):
    global FONT
    FONT = FONT or find_font(lang)
    pf = {"yt": "YouTube", "fb": "Facebook"}[got["platform"]]
    log(f"MILESTONE: {got['n']:,} on {pf} ({got['count']:,} now) - a thank-you")
    bg = next((os.path.join(THUMB_B, f) for f in sorted(os.listdir(THUMB_B)) if f.endswith(".jpg")), None) \
        if os.path.isdir(THUMB_B) else None
    card = extras.milestone_card(bg, got["n"], got["platform"], lang, os.path.join(WORK, "milestone.jpg"), FONT)
    num = str(got['n']).translate(extras.BN_DIG)
    word = "সাবস্ক্রাইবার" if got["platform"] == "yt" else "ফলোয়ার"
    text = (f"🕯️ আজ আমরা {num} জন {word}-এর পরিবার! প্রতিটা রাতে আমাদের গল্প শোনার জন্য আপনাদের সবাইকে অন্তর থেকে "
            "ধন্যবাদ। আরও গভীর, আরও অন্ধকার গল্প আসছে...")
    try:
        if env("FB_PAGE_TOKEN"):
            extras.fb_photo(card, text)
    except Exception as e:
        log("  milestone photo skipped:", str(e)[:100])
    extras.tg_channel_post(ASSETS, text, card)
    extras.telegram(f"🎉 মাইলফলক: {pf}-এ {num} জন {word} পার হলো ({got['count']:,})! পরের গল্পে গল্পকার সবাইকে "
                    "ধন্যবাদ জানাবেন।")


def milestone_rule():
    got = extras.milestone_take(MILESTONE_FILE)
    if not got:
        return ""
    STATE["milestone"] = got
    word = "subscribers on YouTube" if got["platform"] == "yt" else "followers on Facebook"
    return (f"\nMILESTONE THANKS: our channel has just passed {got['n']} {word}. The narrator's VERY FIRST line (before "
            "the story begins) warmly thanks this family of listeners in one or two sentences - grateful and grave, "
            "never asking for likes, shares or subscriptions - then the story starts.\n")


def growth_after_post(story, title, results, history, lang, video, thumb, slot_hour, special, viewer):
    """after a story is posted: the Facebook countdown story, the fan channel, the story as Facebook text (2 PM),
    the story's own web page, the podcast episode, an old video's best moment as a Short (Tue / Thu night)"""
    log(f"After-post steps: map={'yes' if map_url() else 'NO'}, token={'yes' if env('GITHUB_TOKEN') else 'NO'}")
    at = extras.publish_time()
    when_bn = SLOT_BN.get(slot_hour, "") if isinstance(SLOT_BN, dict) else ""
    fb_link = f"https://www.facebook.com/{results['facebook']}" if results.get("facebook") else ""
    yt_link = f"https://youtu.be/{results['youtube']}" if results.get("youtube") else ""
    clean = re.sub(r"\s*[|].*$", "", title).strip()
    changed = []
    # v84: once in a while (each feature once a month) a Facebook poster for one of our features
    try:
        if results.get("facebook") and promo_monthly_post(thumb):
            changed.append(PROMO_FILE)
    except Exception as e:
        log("  feature poster skipped:", str(e)[:150])
    # 10) Facebook photo story: countdown
    if at and results.get("facebook") and env("FB_COUNTDOWN") != "0":
        try:
            card = extras.story_card_vertical(thumb, [f"আজ {when_bn}", clean[:40], "👻 নতুন ভূতের গল্প"],
                                              os.path.join(WORK, "countdown.jpg"), FONT)
            extras.fb_photo_story(card)
            log("  Facebook story: countdown picture posted")
        except Exception as e:
            log("  Facebook countdown story skipped:", str(e)[:150])
    # 6) fan channel: now 'coming', at the time 'here it is'
    try:
        if extras.tg_get(ASSETS).get("id"):
            extras.tg_channel_post(ASSETS, f"🕯️ আজ {when_bn}: {clean}\n\nতৈরি থাকুন...", thumb)
            extras.tg_channel_post(ASSETS, f"👻 এসে গেছে: {clean}\n\n▶ YouTube: {yt_link}\n▶ Facebook: {fb_link}".strip(),
                                   at=at or dt.datetime.now(dt.timezone.utc))
            changed.append(os.path.join(ASSETS, "tg_channel.json"))
    except Exception as e:
        log("  fan channel post skipped:", str(e)[:100])
    names = {str(c.get("name", "")).lower(): str(c.get("name_local") or c.get("name")) for c in story.get("characters") or []}
    # 7) the story as Facebook text (the 2 PM story, 3 hours after the video)
    if slot_hour == NOON and fb_link and env("FB_TEXT_STORY") != "0" and lang == "bn":
        try:
            part_text = extras.story_text(story, names, frac=0.45, max_chars=6000)
            msg = (f"📖 {clean}\n\n{part_text}\n\n... তারপর কী হলো? বাকি গল্পটা শুনুন: {fb_link}")
            extras.fb_schedule_photo(thumb, msg, (at or dt.datetime.now(dt.timezone.utc)) + dt.timedelta(hours=3))
            log("  the story as text: scheduled on Facebook 3 hours after the video")
        except Exception as e:
            log("  written story post skipped:", str(e)[:150])
    # 4) a safe copy of the video (GitHub release) - also used by the live and the old-video Shorts
    try:
        bk = extras.backup_video(video, f"{story_slug()}.mp4")
        if bk and history and history[-1].get("title") == title:
            history[-1]["backup"] = bk
            save_history(history)
            log("  video backup kept")
    except Exception as e:
        log("  video backup skipped:", str(e)[:150])
    if results.get("youtube"):
        try:
            extras.VIDEO_SECS[results["youtube"]] = duration(video)
        except Exception:
            pass
    # 3) the story's own web page (+ list + sitemap)
    base = map_url()
    if base and env("STORY_PAGES") != "0":
        try:
            when_d = (at or dt.datetime.now(dt.timezone.utc)).astimezone(extras.IST).date().isoformat()
            extras.story_page(MAP_DIR, story_slug(), title, extras.story_text(story, names), results.get("youtube"),
                              results.get("facebook"), base, lang, when_d)
            changed.append(MAP_DIR)
            log(f"  story web page: {base}golpo/{story_slug()}.html")
        except Exception as e:
            log("  story web page skipped:", str(e)[:150])
    # 2) a Google Web Story (tap-through pictures, shown in Google Discover)
    if base and env("WEB_STORY") != "0" and env("GITHUB_TOKEN"):
        try:
            make_web_story(story, title, video, results, base, lang, names)
            changed.append(MAP_DIR)
        except Exception as e:
            log("  web story skipped:", str(e)[:150])
    # 4) podcast episode (Spotify / Apple read the feed by themselves)
    if not (base and env("GITHUB_TOKEN")):
        log("  story page / podcast skipped: " + ("the ghost-map address is not live" if not base else
                                                  "GITHUB_TOKEN is missing in horror-story.yml"))
    if base and env("PODCAST_FEED") != "0" and env("GITHUB_TOKEN"):
        try:
            mp3 = os.path.join(WORK, f"{story_slug()}.mp3")
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vn", "-ac", "1", "-ar", "44100", "-b:a", "64k", mp3])
            url = extras.gh_release_upload(mp3, os.path.basename(mp3))
            if url:
                pub = (at or dt.datetime.now(dt.timezone.utc))
                extras.podcast_feed(MAP_DIR, base, {
                    "guid": story_slug(), "title": title, "url": url, "bytes": os.path.getsize(mp3),
                    "secs": duration(video), "date": pub.strftime("%a, %d %b %Y %H:%M:%S +0000"),
                    "desc": str(story.get("description", ""))[:600]},
                    env("PODCAST_TITLE") or "Daily Horror Story", thumb, lang)   # v88: the show's name in English
                changed.append(MAP_DIR)
                log("  podcast episode added to the feed")
        except Exception as e:
            log("  podcast episode skipped:", str(e)[:150])
    # 11) the viewer whose voice became this story hears it first
    if viewer and str(viewer.get("id", "")).startswith("tg_"):
        try:
            extras.viewer_voice_done(ASSETS, viewer["id"], [x for x in (yt_link, fb_link) if x])
        except Exception:
            pass
    # 8) an old video's scariest moment as a new Short / Reel (Tuesday and Thursday nights)
    if (slot_hour == EVENING and dt.datetime.now(extras.IST).weekday() in (1, 3) and env("OLD_SHORTS") != "0"):
        try:
            if old_video_short(history, lang):
                save_history(history)
        except Exception as e:
            log("  old-video short skipped:", str(e)[:150])
    if changed:
        try:
            push_now(sorted(set(changed)), "story page, podcast, fan channel")
        except Exception:
            pass


def old_video_short(history, lang):
    """the scariest 45 seconds of one of our best OLDER videos as a new YouTube Short + Facebook Reel, with 'the
    whole story' link - old videos get new viewers (no new voice needed)"""
    global FONT
    FONT = FONT or find_font(lang)
    now = dt.datetime.now(dt.timezone.utc)
    done = {h.get("from_video") for h in history if h.get("kind") == "old_short"}
    cands = []
    for h in history:
        if h.get("kind") or not h.get("facebook") or not h.get("youtube") or h.get("youtube") in done:
            continue
        try:
            age = (now - dt.datetime.fromisoformat(str(h["date"]))).days
        except Exception:
            continue
        if age >= 7:
            cands.append((extras.score(h.get("stats") or {}), h))
    if not cands:
        log("  old-video short: no older video yet")
        return False
    h = max(cands, key=lambda x: x[0])[1]
    src = h.get("backup") or extras.fb_video_source(h["facebook"])[0]
    if not src:
        return False
    raw = extras.download(src, os.path.join(WORK, "old_raw.mp4"))
    st = extras.scariest_window(raw)
    clean = re.sub(r"\s*[|].*$", "", str(h.get("title", ""))).strip()
    top = os.path.join(WORK, "old_top.png")
    im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k, (txt, sz, y) in enumerate(((clean[:34], 74, 210), ("পুরো গল্প চ্যানেলে 👆" if lang == "bn" else "पूरी कहानी चैनल पर 👆", 58, 1600))):
        f = font(sz)
        txt = extras.fit_glyphs(txt, FONT)
        while d.textlength(txt, font=f) > 1000 and sz > 30:
            sz -= 4
            f = font(sz)
        d.text(((1080 - d.textlength(txt, font=f)) / 2, y), txt, font=f, fill=(255, 214, 90) if k == 0 else (255, 255, 255),
               stroke_width=5, stroke_fill=(0, 0, 0))
    im.save(top)
    out = os.path.join(WORK, "old_short.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{st:.1f}", "-t", "45", "-i", raw, "-i", top, "-filter_complex",
         "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2,eq=brightness=-0.15[bg];"
         "[0:v]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v1];[v1][1:v]overlay=0:0,format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac",
         "-b:a", "128k", "-r", "30", out])
    os.remove(raw)
    full = f"https://youtu.be/{h['youtube']}"
    title = f"{clean[:60]} 😱 #shorts"
    desc = f"পুরো গল্প এখানে: {full}\n\n#ভূতের_গল্প #BhuterGolpo #HorrorShorts #shorts"
    rec = {"date": now.isoformat(timespec="minutes"), "lang": lang, "kind": "old_short", "from_video": h["youtube"],
           "title": title}
    if youtube_ready() and extras.yt_extra_ok():
        try:
            fr = os.path.join(WORK, "old_frame.jpg")
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "20", "-i", out, "-frames:v", "1", fr])
            rec["youtube"] = post_to_youtube(out, fr, title, desc, ["shorts", "bhuter golpo", "horror"], lang)
            log(f"  old-video short on YouTube: {rec['youtube']} (from '{clean[:40]}')")
        except Exception as e:
            log("  old-video short (YouTube) skipped:", str(e)[:150])
    if env("FB_PAGE_TOKEN"):
        try:
            rec["facebook"] = extras.fb_post_reel(out, f"{clean} 😱\n\nপুরো গল্প: https://www.facebook.com/{h['facebook']}")
            log("  old-video reel on Facebook:", rec["facebook"])
        except Exception as e:
            log("  old-video reel skipped:", str(e)[:150])
    if rec.get("youtube") or rec.get("facebook"):
        history.append(rec)
        return True
    return False


def weekly_live(history):
    """SATURDAY NIGHT LIVE on YouTube - 'ভূতের রাত': the week's best stories one after another (no new voice),
    with cards between them that greet the people in the live chat by name; the bot also answers in the chat."""
    global FONT
    import threading
    lang = "bn"
    FONT = find_font(lang)
    if MOCK or DRY_RUN or not youtube_ready() or env("YT_LIVE") == "0":
        log("Live: not in this run")
        return
    hours = float(env("LIVE_HOURS") or 2.5)
    now = dt.datetime.now(dt.timezone.utc)
    cands = []
    for h in history:
        if h.get("kind") or not h.get("facebook") or not h.get("youtube"):
            continue
        try:
            age = (now - dt.datetime.fromisoformat(str(h["date"]))).days
        except Exception:
            continue
        if age <= 60:
            cands.append(((age <= 7) * 1000 + extras.score(h.get("stats") or {}), h))
    cands.sort(key=lambda x: -x[0])
    clips, titles, total = [], [], 0.0
    for _s, h in cands:
        if total >= hours * 3600:
            break
        try:
            src = h.get("backup") or extras.fb_video_source(h["facebook"])[0]
            if not src:
                continue
            raw = extras.download(src, os.path.join(WORK, f"lraw_{len(clips)}.mp4"))
            c = extras.live_clip(raw, os.path.join(WORK, f"l_{len(clips):02d}.mp4"))
            os.remove(raw)
            clips.append(c)
            titles.append(re.sub(r"\s*[|].*$", "", str(h.get("title", ""))).strip())
            total += duration(c)
            log(f"  live: {titles[-1][:50]} ({duration(c) / 60:.0f} min)")
        except Exception as e:
            log("  live: a video skipped:", str(e)[:120])
    if len(clips) < 2:
        log("Live: not enough videos - no live tonight")
        return
    bg = os.path.join(WORK, "live_bg.jpg")
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "60", "-i", clips[0], "-frames:v", "1", bg])
    names = []

    def card(k, secs=10.0):
        bn_ = [x for x in names[-8:] if re.search(r"[\u0980-\u09FF]", x)][-4:]
        en_ = [x for x in names[-8:] if not re.search(r"[\u0980-\u09FF]", x)][-4:]
        who = (["লাইভে আছেন"] + ([", ".join(bn_)] if bn_ else []) + ([", ".join(en_)] if en_ else [])) if names \
            else ["আলো নিভিয়ে, হেডফোন লাগিয়ে বসুন"]
        lines = (["ভূতের রাত - লাইভ", "প্রথম গল্প", titles[0][:36]] if k == 0 else
                 ["পরের গল্প", titles[k][:40]]) + who
        sizes_ = [96, 64] + [56] * 4
        img = extras.text_card(bg, lines, os.path.join(WORK, f"card_{k}.jpg"), FONT, sizes=sizes_)
        tmp = os.path.join(WORK, f"c_{k:02d}.tmp.mp4")
        extras.live_card(img, secs, tmp)
        os.replace(tmp, os.path.join(WORK, f"c_{k:02d}.mp4"))
    for k in range(len(clips)):
        card(k)
    lst = os.path.join(WORK, "live.txt")
    with open(lst, "w") as f:
        for k, c in enumerate(clips):
            f.write(f"file 'c_{k:02d}.mp4'\nfile '{os.path.basename(c)}'\n")
    title = "👻 ভূতের রাত - লাইভ | একটানা ভূতের গল্প | Bhuter Golpo Live"
    desc = ("আজ রাতে একটানা সপ্তাহের সেরা ভূতের গল্প। চ্যাটে আপনার নাম লিখুন - পরের গল্পের আগে পর্দায় আপনার নাম "
            "দেখাবে।\n\n" + "\n".join(f"{k + 1}. {t}" for k, t in enumerate(titles)) + "\n\n" + growth_links(lang))
    thumb = extras.text_card(bg, ["👻 ভূতের রাত", "লাইভ", "একটানা ভূতের গল্প"], os.path.join(WORK, "live_thumb.jpg"), FONT)
    try:
        bid, rtmp, chat = extras.yt_live_create(title, desc, thumb)
    except Exception as e:
        msg = str(e)
        log("Live could not start:", msg[:300])
        if "liveStreamingNotEnabled" in msg or "not enabled" in msg.lower():
            extras.telegram("⚠️ শনিবারের লাইভ হলো না: আপনার YouTube চ্যানেলে লাইভ এখনো চালু নয়। একবার YouTube Studio-তে "
                            "'Create → Go live' টিপে ফোন নম্বর দিয়ে যাচাই করুন - ২৪ ঘণ্টা পরে লাইভ চালু হয়ে যাবে, তারপর "
                            "bot নিজেই প্রতি শনিবার লাইভ করবে।")
        return
    link = f"https://www.youtube.com/watch?v={bid}"
    log("LIVE:", link)
    extras.telegram(f"🔴 লাইভ শুরু হচ্ছে: {link}")
    extras.tg_channel_post(ASSETS, f"🔴 এখন লাইভ - ভূতের রাত! একটানা সপ্তাহের সেরা গল্প:\n{link}", thumb)
    try:
        if env("FB_PAGE_TOKEN"):
            extras.fb_photo(thumb, f"🔴 এখন YouTube-এ লাইভ - ভূতের রাত! একটানা সপ্তাহের সেরা ভূতের গল্প, চ্যাটে আপনার নাম "
                                   f"লিখলে পর্দায় দেখাবে 👻\n{link}")
    except Exception:
        pass
    starts, t = [], 0.0
    for c in clips:
        starts.append(t)
        t += 10.0 + duration(c)
    stop = threading.Event()

    def watcher():
        tok, said, t0 = None, 0, time.time()
        while not stop.is_set():
            try:
                if chat:
                    msgs, tok = extras.yt_live_chat(chat, tok)
                    for a, _m in msgs:
                        if a and a not in names:
                            names.append(a)
                            if said < int(env("LIVE_REPLIES") or 8):
                                said += extras.yt_live_say(chat, f"স্বাগতম {a} 🕯️ পরের গল্পের আগে পর্দায় আপনার নাম থাকবে")
                el = time.time() - t0
                for k in range(1, len(clips)):        # the next card: made again with the newest names
                    if starts[k] - 150 <= el < starts[k] - 40:
                        card(k)
            except Exception as e:
                log("  live chat:", str(e)[:80])
            stop.wait(int(env("LIVE_CHAT_SEC") or 120))
    th = threading.Thread(target=watcher, daemon=True)
    th.start()
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-re", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                        "-f", "flv", rtmp], cwd=WORK, timeout=int(hours * 3600 + 3600))
    finally:
        stop.set()
    log(f"Live finished ({t / 60:.0f} min, {len(names)} people in the chat)")
    history.append({"date": now.isoformat(timespec="minutes"), "lang": lang, "kind": "live", "youtube": bid,
                    "title": title, "people": len(names)})
    save_history(history)
    extras.telegram(f"✅ লাইভ শেষ: {t / 60:.0f} মিনিট, চ্যাটে {len(names)} জন। {link}")


def main():
    global FONT, VHS
    if env("MODE") == "voice_demo":
        return voice_demo()
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    history = load_history()
    try:                                             # v67: a video posted earlier whose saving had failed
        repair_lost_posts(history)
    except Exception as e:
        log("  lost-save check skipped:", str(e)[:150])
    if not MOCK and not DRY_RUN:
        try:
            changed = extras.flush_pending(history)    # comments of earlier videos that are live now
            changed = extras.reply_fans(history, env("LANGUAGE") or "bn", kind="horror") or changed   # answer the fans
            if changed:
                save_history(history)
        except Exception as e:
            log("  earlier comments skipped:", str(e)[:120])
    if not MOCK and not DRY_RUN and env("MY_STORIES") != "0":
        try:                                         # every run collects the stories you sent on Telegram
            creator_inbox(bot_status)   # (Telegram keeps a message only 24 hours) + your commands
        except Exception as e:
            log("  Telegram stories not read:", str(e)[:120])
    if not MOCK and not DRY_RUN:
        try:                                         # v76: YouTube replies, fan channel, viewers' voices, milestones
            growth_start(history)
        except Exception as e:
            log("  growth start skipped:", str(e)[:150])
    if env("MODE") == "live":
        return weekly_live(history)
    if extras.bot_paused(MY_STORIES) and not MOCK:
        log("PAUSED from Telegram ('বন্ধ') - no video this time. Send 'চালু' to start again.")
        return
    global SLOT
    SLOT = None if env("MODE") in ("amavasya", "compilation") else extras.current_slot(TRIGGERS)
    extras.plan_publish(SLOT)
    if env("MODE") == "compilation":
        try:                                         # v68: Sunday night - the week in numbers on Telegram
            weekly_report(history)
        except Exception as e:
            log("  weekly report skipped:", str(e)[:150])
        return make_compilation(history)
    # automatic runs (GitHub's clock or the cron-job.org clock) must not post twice for one time slot
    if env("MODE") == "amavasya" and env("AMAVASYA_MIDNIGHT") != "1":
        log("The Amavasya special now comes at 8 PM on the Amavasya night - nothing to do at midnight. "
            "(The 23:55 job on cron-job.org can be deleted.)")
        return
    if env("MODE") == "amavasya" and not extras.is_amavasya_night():
        log("Not an Amavasya night - nothing to do.")
        return
    if env("MODE") != "amavasya" and (env("EVENT") == "schedule" or env("MODE") == "auto") and (extras.slot_done(history, SLOT) or (not SLOT and recently_posted(history, hours=2))):
        log("A video for this time slot was already posted - this backup run has nothing to do.")
        return
    if (env("EVENT") == "schedule" or env("MODE") == "auto") and SLOT and "@" in str(SLOT):
        d_, h_ = str(SLOT).split("@")
        post_at = dt.datetime.fromisoformat(d_).replace(hour=int(h_), tzinfo=extras.IST)
        if dt.datetime.now(extras.IST) - post_at > dt.timedelta(hours=2):
            log(f"This run is for {SLOT}, which is long over - nothing to do (the next story comes at "
                f"{EVENING}:00).")
            return
    try:
        ensure_map_page(history)                     # v63: the ghost map website (made once, in the docs folder)
    except Exception as e:
        log("  ghost map website skipped:", str(e)[:150])
    if not MOCK:
        try:
            extras.refresh_stats(history)            # learn which stories people liked
            if extras.yt_title_test(history, thumb_dir=THUMB_B):   # a weak video: 2nd title + thumbnail (once)
                save_history(history)
        except Exception as e:
            log("  stats skipped:", str(e)[:150])
    slot_hour = int(str(SLOT).split("@")[1]) if SLOT and "@" in str(SLOT) else EVENING
    if slot_hour == MORNING and env("MODE") != "amavasya" and env("MORNING_TEASERS") != "0":
        return morning_teasers(history)              # no morning story: the morning makes the day's two teasers
    STATE["slot_hour"] = slot_hour
    global LONG_MIN
    if not os.environ.get("HORROR_MINUTES"):
        LONG_MIN = SLOT_MINUTES.get(slot_hour, LONG_MIN)
        if env("MODE") == "amavasya":                 # the monthly midnight special: a little shorter, so the
            LONG_MIN = 18.0                           # day's Gemini voice limit still covers the next videos
    log(f"Story length for this time: about {LONG_MIN:.0f} minutes")
    plan = load_plan(SLOT)
    if plan:                                         # written this morning (its teaser is already out)
        log(f"Using the story written this morning for this time: {plan['story'].get('title', '')}")
        STATE.update(plan.get("state") or {})
        SCRIPTS.update(plan.get("scripts") or {})
        VHS, LONG_MIN = bool(plan.get("vhs")), float(plan.get("long_min") or LONG_MIN)
        plan["shout_names"], plan["shout_ids"] = right_answers(history)
    else:
        plan = choose_and_write(slot_hour, history)
        if SLOT and not MOCK:                          # a re-run after a failure uses this story, no new writing
            try:
                save_plan(SLOT, json.loads(json.dumps(plan, ensure_ascii=False, default=list)))
                push_now([PLANS_FILE, MY_STORIES], f"story written for {SLOT}")
            except Exception as e:
                log("  story not saved for a re-run:", str(e)[:120])
    (cat, classic, festival, fmt, lang, outline, part, prev, shout_ids, shout_names, special, story, theme, total, viewer) = (plan.get(k) for k in ('cat', 'classic', 'festival', 'fmt', 'lang', 'outline', 'part', 'prev', 'shout_ids', 'shout_names', 'special', 'story', 'theme', 'total', 'viewer'))
    classic = tuple(classic) if classic else None
    L = LANGS[lang]
    FONT = find_font(lang)
    STATE["special"] = special
    clean_story_text(story)
    sync_sounds(story)
    fix_speakers(story)
    NAME_LOCAL.update({str(c["name"]).lower(): str(c.get("name_local") or c["name"]) for c in story["characters"]})
    ensure_intros(story, cold=env("COLD_OPEN") == "1")
    if not MOCK and not DRY_RUN:
        try:                                         # v82: Sunday night - the week's best viewer comment, read aloud
            add_best_comment(story, history, lang, slot_hour)
        except Exception as e:
            log("  best comment skipped:", str(e)[:120])
    ensure_ghost_laughs(story)
    mark_reveals(story)
    continues = bool(part) and part < total          # this part ends on a cliffhanger, the next part comes on
    story.pop("choice", None)                        # ... this category's next day
    series_id = (((prev or {}).get("series_id") or (prev or {}).get("created")) if part >= 2 else
                 (dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes") if part == 1 else None))
    if special in SERIES_IDS:                        # always the same faces for our recurring heroes
        fixed = series_cast(special, theme, STATE.get("crossover") or (prev or {}).get("crossover"))
        names = {c["name"].lower(): c for c in fixed}
        story["characters"] = [names.get(str(c.get("name", "")).lower(), c) for c in story.get("characters", [])]
        for b in fixed:
            if b["name"].lower() not in [str(c.get("name", "")).lower() for c in story["characters"]]:
                story["characters"].append(b)
    if part >= 2:                                    # same people and place as part 1 (+ anyone new who speaks)
        old = {str(c.get("name", "")).lower() for c in prev["characters"] or []}
        story["characters"] = list(prev["characters"] or []) + [c for c in story.get("characters", [])
                                                                if str(c.get("name", "")).lower() not in old]
        story["setting"] = prev["setting"]
    title = story["title"].strip()[:85]
    if part >= 2 and (prev or {}).get("title"):     # every part of one story carries the same name
        title = str(prev["title"]).strip()[:85]
    if part:                                         # (9 Nov 2026: '... | পর্ব ১ | পর্ব ১' - said twice in the video)
        title = re.sub(r"\s*[|(\[\-–:]?\s*(?:পর্ব|भाग|part|episode)\s*[#নং]*\s*[০-৯0-9]+\s*[)\]]?\s*$", "",
                       title, flags=re.I).strip() or title
    if part:
        pn = str(part).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) if lang == "bn" else str(part)
        title = f"{title} | {L['part'].format(n=pn)}"
    if special == "bhairab":
        case_no = (prev or {}).get("case_no") or 1 + sum(1 for h in history if h.get("special") == "bhairab" and not (h.get("part") or 0) > 1)
        title = f"{L['bhairab'].format(n=case_no)}: {no_series_name(title, 'bhairab')}"[:95]
        STATE["case_no"] = case_no
        story["_playlist"] = L["bhairab_pl"]
    elif special == "taranath":
        case_no = (prev or {}).get("case_no") or 1 + sum(1 for h in history if h.get("special") == "taranath" and not (h.get("part") or 0) > 1)
        title = f"{L['taranath'].format(n=case_no)}: {no_series_name(title, 'taranath')}"[:95]
        STATE["case_no"] = case_no
        story["_playlist"] = L["taranath_pl"]
    elif special == "karna":
        case_no = (prev or {}).get("case_no") or 1 + sum(1 for h in history if h.get("special") == "karna" and h.get("lang") == lang
                                                         and not (h.get("part") or 0) > 1)
        title = f"{L['karna'].format(n=case_no)}: {no_series_name(title, 'karna')}"[:95]
        STATE["case_no"] = case_no
        story["_playlist"] = L["karna_pl"]
    elif special in NEW_SERIES:
        case_no = (prev or {}).get("case_no") or 1 + sum(1 for h in history if h.get("special") == special
                                                         and h.get("lang") == lang)
        title = f"{L[special].format(n=case_no)}: {no_series_name(title, special)}"[:95]
        STATE["case_no"] = case_no
        story["_playlist"] = L[special + "_pl"]
    elif special == "amavasya":
        title = f"{L['amavasya']}: {title}"[:95]
    elif special == "classic" and classic:
        k = 0 if lang == "bn" else 1
        title = f"{classic[3][k]} | {classic[1][k]}"[:95]
    story["_theme_pl"] = theme_playlist(lang, cat, special, festival, bool(story.get("true_label")))
    if story.get("true_label"):
        title = extras.true_title(title, lang)
    log("Title:", title)
    STATE["story_words"] = sum(len(str(ln.get("text", "")).split()) for sc_ in story.get("scenes") or []
                               for ln in sc_.get("lines") or [])
    used_names = names_in_story(story)               # v63: viewers who asked to be in a story
    if STATE.get("viewer_names"):
        log("  viewers' names in the story: " + (", ".join(p[1] for p in used_names) or "none made it in"))
    with open(os.path.join(WORK, "story.json"), "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=1)

    cast = Cast(story)
    voices = Voices(lang, cast)
    for c in cast.chars.values():
        log(f"  {c['name']} ({c['gender']}, {c['age']}, {c['kind']}) -> voice {voices.map[c['name'].lower()][:3]}")
    seed = random.randint(1, 1_000_000)
    scenes = story["scenes"][:120]         # never cut the story short

    log("Cast reference picture")
    if not make_cast_sheet(cast, os.path.join(WORK, "cast.jpg"), seed):
        log("  no cast picture - using text descriptions only")

    # one picture per spoken line (a new "camera shot" every few seconds), within the free budget
    budget = int(env("MAX_IMAGES") or (50 if LONG_MIN > 16 else 36))   # 2 videos + teasers fit the free picture limit
    scene_lines = [[ln for ln in (s.get("lines") or []) if str(ln.get("text", "")).strip()] for s in scenes]
    total_lines = sum(len(x) for x in scene_lines) or 1
    imgs, shots_per_scene, last_ok, count = [], [], None, 0
    try:
        recap_pics = recap_frames(history, series_id, part, lang)
    except Exception as e:
        recap_pics = []
        log("  recap pictures skipped:", str(e)[:120])
    for i, (s, lines) in enumerate(zip(scenes, scene_lines)):
        want = max(1, min(len(lines), round(len(lines) * budget / total_lines))) if lines else 1
        groups = [lines[round(g * len(lines) / want):round((g + 1) * len(lines) / want)] for g in range(want)] or [[]]
        scene_shots = []
        for g, grp in enumerate(groups):
            count += 1
            p = os.path.join(WORK, f"shot_{i:02d}_{g:02d}.jpg")
            first = key_line(grp) if grp else {}           # the line this picture must show
            pic = first.get("image") if isinstance(first.get("image"), dict) else {}
            action = pic.get("prompt") or first.get("shot") or s.get("action", "")
            said = " ".join(str(x.get("en", "")).strip() for x in grp if x.get("en"))[:420]
            if said:                                     # the picture shows exactly what these words tell
                action = (f"{action}. It must show exactly what is being told: \"{said}\". Same place, time of "
                          f"day and light as the story ({s.get('place', '')})")
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
            if i == 0 and g < len(recap_pics) and len(groups) > len(recap_pics):   # v70: the last part's own pictures
                p = recap_pics[g]
            elif make_image(cast, action, s.get("place", ""), names, p, seed):
                last_ok = p
            elif scene_shots:
                p = scene_shots[-1]                      # reuse; the camera move makes it look different
            elif last_ok:
                p = last_ok
            else:
                p = None
            scene_shots += [p] * max(1, len(grp))
        shots_per_scene.append(scene_shots)
        imgs.append(next((x for x in scene_shots if x and x not in recap_pics), None)
                    or next((x for x in scene_shots if x), None))
    first_ok = next((p for p in imgs if p and p not in recap_pics), None) or next((p for p in imgs if p), None)
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
                HIDDEN_PICS.append(hp)
            except Exception as e:
                log("  hide ghost:", str(e)[:100])
        log(f"Ghost face ready; hidden in {hidden} pictures")

    thumb_base = os.path.join(WORK, "thumb_base.jpg")
    # poster-style thumbnail: the same formula every time, only the people, the ghost and the moment change
    t_prompt, tkind, hero, gname, ti = thumb_plan(story, cast, special, cat)
    if env("POSTER_STYLE") not in ("old", "words"):
        log(f"Thumbnail formula: {tkind}")
    STATE["thumb_src"] = "bot"
    if premade_thumb(SLOT, thumb_base):              # v68: made this morning (best model + Gemini's pick)
        STATE["thumb_src"] = "bot_morning"
    elif not extras.hq_image(t_prompt, thumb_base, seed):
        if not make_image(cast, t_prompt, "", [n for n in (hero, gname) if n], thumb_base, seed):
            gf_ = os.path.join(WORK, "ghost_face.jpg")
            shutil.copy(gf_ if os.path.exists(gf_) else first_ok, thumb_base)   # the ghost is always on it
    thumb = os.path.join(WORK, "thumbnail.jpg")
    series_bn = series_label(special, L)
    big = re.sub(r"[^\w\sঀ-৿ऀ-ॿ!?,।'’-]", " ", re.sub(r"\s*\|.*$", "", title))   # the title on the thumbnail
    big = re.sub(r"\s{2,}", " ", re.sub(r"[0-9০-৯०-९]+", " ", big)).strip()   # the poster font has no digits
    sub = str(story.get("tagline") or story.get("thumbnail_text") or story.get("episode_name") or "").strip()   # ... + tag line
    # ONLY the Bengali title on the picture (your formula); a small line only for the part number / true story
    own = re.sub(r"\s*\|.*$", "", title).strip()
    if ":" in own:                                   # 'কর্ণপিশাচিনী #2: নিশির ডাক' -> the story's own name
        own = own.split(":", 1)[1].strip() or own
    bn_part = (str(part).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) if lang == "bn" else str(part))
    small = " · ".join(x for x in (
        extras.TRUE_LABEL.get(lang, extras.TRUE_LABEL["bn"]) if story.get("true_label") else "",
        series_bn or "", L["part"].format(n=bn_part) if part else "") if x)
    title_done = False
    # YouTube's advice (8 Nov 2026): 2-4 BIG words that ADD to the title (a question, a warning) - not the title again
    tw = own if env("THUMB_WORDS") == "title" else extras.thumb_words(story, title)
    if env("POSTER_STYLE") not in ("old", "words"):
        try:
            extras.title_poster(thumb_base, tw, thumb, tkind, small=small, fallback_font=FONT)
            extras.title_poster(thumb_base, tw, os.path.join(WORK, "thumbnail_portrait.jpg"), tkind, small=small,
                                portrait=True, fallback_font=FONT)
            try:                                     # a SECOND thumbnail (used only if the video gets few views):
                mir = os.path.join(WORK, "thumb_base_b.jpg")   # the picture mirrored, the title's own words
                Image.open(thumb_base).convert("RGB").transpose(Image.FLIP_LEFT_RIGHT).save(mir, quality=92)
                tb_title = re.sub(r"\s*\|.*$", "", str(story.get("title_b") or "")).strip() or own
                tb_title = tb_title if tb_title != tw else own
                extras.title_poster(mir, tb_title, os.path.join(WORK, "thumbnail_b.jpg"),
                                    "h_closeup" if tkind != "h_closeup" else "h_cinematic", small=small, fallback_font=FONT)
            except Exception as e:
                log("  second thumbnail skipped:", str(e)[:100])
            title_done = True
            log(f"Thumbnail words: '{tw}'" + (f" + '{small}'" if small else ""))
        except Exception as e:
            log("  thumbnail title failed, the older poster:", str(e)[:120])
    try:                                             # the channel's own poster style (see extras.horror_poster)
        if title_done:
            raise _Saved()
        if env("POSTER_STYLE") == "old":
            raise RuntimeError("old style asked")
        gname_ = next((c["name"] for c in cast.chars.values() if c["kind"].startswith("ghost")), "")
        words = extras.poster_words(title, ti.get("place") or story.get("setting", ""), gname_, lang,
                                    env("GEMINI_API_KEY"), gemini_models(env("GEMINI_API_KEY")) if env("GEMINI_API_KEY") else None)
        if story.get("true_label"):
            banner = extras.TRUE_LABEL.get(lang, extras.TRUE_LABEL["bn"])
        elif part:
            banner = (f"{series_bn} · " if series_bn else "") + L["part"].format(
                n=str(part).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) if lang == "bn" else part)
        else:
            banner = re.sub(r"\s+", " ", sub)[:28]
        extras.horror_poster(thumb_base, words, banner, thumb, FONT)
        extras.horror_poster(thumb_base, words, banner, os.path.join(WORK, "thumbnail_portrait.jpg"), FONT,
                             portrait=True)
        log(f"Poster: {' / '.join(v for v in words.values() if v)} | {banner}")
        try:                                         # a SECOND thumbnail (used only if the video gets few views)
            mir = os.path.join(WORK, "thumb_base_b.jpg")
            Image.open(thumb_base).convert("RGB").transpose(Image.FLIP_LEFT_RIGHT).save(mir, quality=92)
            words_b = extras.poster_words(story.get("title_b") or title, ti.get("place") or story.get("setting", ""),
                                          gname_, lang)            # no extra Gemini call: cut from the 2nd title
            extras.horror_poster(mir, words_b, banner, os.path.join(WORK, "thumbnail_b.jpg"), FONT)
        except Exception as e:
            log("  second thumbnail skipped:", str(e)[:100])
    except _Saved:
        pass
    except Exception as e:
        log("  channel poster failed, the older poster:", str(e)[:120])
        try:
            extras.poster_thumbnail(thumb_base, big, sub, thumb, "horror", FONT)
        except Exception as e2:
            log("  poster thumbnail failed, simple one:", str(e2)[:120])
            make_thumbnail(thumb_base, story.get("thumbnail_text") or title, thumb, L["label"])
    if SLOT and not MOCK:                            # v68: YOUR picture from Telegram ('1' = 2 PM, '2' = 8 PM)
        try:
            thumb_inbox()                            # (the pictures sent until this very minute)
            if apply_user_thumb(SLOT, thumb, tw, small, tkind):
                STATE["thumb_src"] = "user"
            mark_thumb_made(SLOT)
        except Exception as e:
            log("  your Telegram thumbnail skipped:", str(e)[:150])

    clean_title = re.sub(r"[^\w\sऀ-ॿঀ-৿,।!?-]", "", title).strip()
    page = env(f"PAGE_NAME_{lang.upper()}") or env("PAGE_NAME") or L["page_default"]
    g = story.get("guess") if isinstance(story.get("guess"), dict) else {}
    gopts = [str(o).strip() for o in (g.get("options") or []) if str(o).strip()][:3]
    if (not NO_BAIT and not continues and not str(story.get("mystery_answer", "0")).strip()[:1] in "123" and g.get("question")
            and len(gopts) == 3 and str(g.get("answer", "")).strip()[:1] in ("1", "2", "3") and len(scenes) >= 4):
        mid = scenes[len(scenes) // 2 - 1]           # the viewers guess at the middle: comment 1, 2 or 3
        mid.setdefault("lines", []).append({"speaker": "narrator", "emotion": "eerie", "text": L["guess_line"].format(
            q=str(g["question"]).strip(), o1=gopts[0], o2=gopts[1], o3=gopts[2])})
        story["mystery_answer"] = int(str(g["answer"]).strip()[0])
        log(f"Viewers' guess at scene {len(scenes) // 2}: answer {story['mystery_answer']}")
    # COLD OPEN: viewers decide in 3 seconds - the video starts INSIDE the story (its first, most gripping scene);
    # the show's short title with its sound comes right after it, then the rest of the story
    if special == "classic" and classic:
        kk = 0 if lang == "bn" else 1
        tline = L["title_classic"].format(writer=bn_of(classic[1][0]) if lang == "bn" else classic[1][1],
                                          title=classic[3][kk])
    else:
        # short: the show's name and category are written at the top of the screen - no slow spoken intro
        tline = (L["title_karna"].format(title=clean_title) if special == "karna" else f"{clean_title}।")
        if story.get("true_label"):                  # the narrator says it: based on true events
            lab = extras.TRUE_LABEL.get(lang, extras.TRUE_LABEL["bn"])
            base = re.sub(r"[^\w\sऀ-ॿঀ-৿,।!?-]", "", re.sub(r"\s*\|.*$", "", title)).strip()
            tline = f"{lab}... {base}।"
    if district_line(lang):                          # v63: 'আপনাদের ভোটে এ সপ্তাহের জেলা: পুরুলিয়া।'
        tline = f"{tline.rstrip()} {district_line(lang)}"
        log(f"  title line: {tline}")
    parts = [{"image": thumb_base, "lines": [{"speaker": "narrator", "emotion": "eerie", "text": tline}],
              "sounds": ["wind"], "mood": "creepy", "voices": voices, "title_part": True}]
    for img, s, sh in zip(imgs, scenes, shots_per_scene):
        parts.append({"image": img, "shots": sh, "lines": s.get("lines", []), "sounds": s.get("sounds", []),
                      "ambience": s.get("ambience", []), "mood": s.get("mood", "creepy"), "voices": voices,
                      "place": f"{s.get('place', '')} {story.get('setting', '')}"})
    hk = None if env("HOOK_OPEN") == "0" else pick_hook(scenes, story)
    cold = False
    if hk:                                         # 1) the gripping moment, 2) the title, 3) the story from its start
        hi, hlines = hk
        himg = (shots_per_scene[hi][0] if shots_per_scene[hi] else imgs[hi])
        parts.insert(0, {"image": himg, "lines": hlines, "sounds": [], "mood": "scary", "voices": voices,
                         "hook_part": True})
        cold = True
        log(f"Hook at the start (from scene {hi + 1}): {str(hlines[0].get('text', ''))[:80]}")
        if env("TENSION_BRIDGE") == "1":             # (13 Nov 2026: OFF - the same 3 lines came in every story)
            bridges = (["কিন্তু কীভাবে শুরু হয়েছিল এই সব? ফিরে যেতে হবে প্রথম দিনে...",
                        "কে সে? কেন এসেছিল? উত্তর লুকিয়ে আছে প্রথম রাতে...",
                        "অথচ শুরুটা ছিল একেবারে সাধারণ একটা দিন... তারপর?"] if lang == "bn" else
                       ["लेकिन ये सब शुरू कैसे हुआ? लौटते हैं पहले दिन पर...",
                        "वो कौन थी? क्यों आई थी? जवाब छिपा है पहली रात में...",
                        "जबकि शुरुआत एक बिल्कुल आम दिन से हुई थी... फिर?"])
            tl = parts[1]["lines"][0]
            tl["text"] = f"{str(tl['text']).rstrip()} {random.choice(bridges)}"
            log(f"  tension bridge after the hook: {tl['text'][-60:]}")
    STORY_PART[0] = 2 if cold else 1
    end_lines = []
    choice = story.get("choice") if continues and isinstance(story.get("choice"), dict) else None
    vote_text = ""
    if not NO_BAIT and choice and choice.get("question") and choice.get("option1") and choice.get("option2"):
        vote_text = L["vote_line"].format(q=choice["question"], o1=choice["option1"], o2=choice["option2"])
    if story.get("ending_line"):
        end_lines.append({"speaker": "narrator", "text": story["ending_line"]})
    if vote_text:
        end_lines.append({"speaker": "narrator", "text": vote_text})
    if hidden and not NO_BAIT:
        end_lines.append({"speaker": "narrator", "text": L["find_ghost_line"]})
    lang_names = lambda ns: extras.name_list(ns, lang)
    if viewer and viewer.get("name"):
        end_lines.append({"speaker": "narrator", "text": L["viewer_credit"].format(name=viewer["name"])})
    vote_names = (prev or {}).get("vote", {}).get("names") if part >= 2 else None
    if vote_names:
        end_lines.append({"speaker": "narrator", "text": L["vote_thanks"].format(names=lang_names(vote_names))})
    if shout_names:
        end_lines.append({"speaker": "narrator", "text": L["shout_line"].format(names=lang_names(shout_names))})
    nxt = None if env("MODE") == "amavasya" else next_preview(story, history, lang, slot_hour, classic,
                                                                 cat=cat, continues=continues)
    last_img = shots_per_scene[-1][-1] if shots_per_scene[-1] else imgs[-1]
    first_end = end_lines[:1]                        # the story's last chilling line ...
    parts.append({"image": last_img, "lines": first_end or [{"speaker": "narrator", "text": "..."}],
                  "sounds": ["wind"], "mood": "creepy", "voices": voices})
    if nxt:                                          # ... then at once: what comes next, with its own card
        log("Next story preview:", nxt[:120])
        card = next_card(nxt, last_img)
        parts.append({"image": card or last_img, "lines": [{"speaker": "narrator", "emotion": "eerie", "text": nxt}],
                      "sounds": ["wind"], "mood": "creepy", "voices": voices})
    # A SHORT ENDING (YouTube: people leave when the story is over - a long goodbye lowers how much of the video
    # is watched): the 'how to join' talk is in the description and the first comment, not spoken any more
    asked = bool(nxt) and any(w in str(nxt) for w in ("ফলো", "फ़ॉलो", "फॉलो"))     # (never 'follow' twice in a row)
    rest = end_lines[1:] + [{"speaker": "narrator", "text": (L["outro_short"] if asked else L["outro"]).format(page=page)}]
    parts.append({"image": last_img, "lines": rest, "sounds": ["wind"], "mood": "creepy", "voices": voices})

    STING_AT[0] = 1 if cold else 0      # the show's sound with the title, right after the hook
    HOOK_TEXT[0] = str(story.get("thumbnail_text") or "").strip()
    video = os.path.join(WORK, "final.mp4")
    show_top = (series_label(special, L) if special == "karna" or special in NEW_SERIES else
                f"{SHOW_NAME[lang].get(slot_hour, SHOW_NAME[lang][EVENING])} · {HORROR_CATS[cat][lang]}")
    STATE["top_text"] = (show_top, re.sub(r"\s*\|.*$", "", title).strip())
    VOICE_CONTEXT[0] = "amavasya" if env("MODE") == "amavasya" else "main"
    try:
        build_video(parts, lang, video)
    except NoGoodVoice as e:
        log(f"Amavasya special skipped: no good voice left today for {e} (never the free voice in horror)")
        extras.telegram("🌑 আজ অমাবস্যার স্পেশাল বাদ গেল: Gemini-র আজকের গলা শেষ, আর ভূতের গল্প আমরা ফ্রি "
                        "গলায় দিই না। দুপুর ২টো আর রাত ৮টার গল্প আগের মতোই আসবে।")
        return
    log(f"Video ready: {duration(video):.0f} seconds")
    learn_length(duration(video))
    cards_ = []                                      # pictures laid over the video (one re-encode for all)
    if special in NEW_SERIES and env("PREV_CARD") != "0":
        try:                                         # v82: 'আগের পর্বে: ...' over the first seconds (no voice)
            prev_ep = next((h for h in reversed(history) if h.get("special") == special and h.get("title")), None)
            if prev_ep:
                png_ = extras.prev_card_png(f"{series_label(special, L)} - আগের পর্বে" if lang == "bn" else
                                            f"{series_label(special, L)} - पिछले एपिसोड में",
                                            re.sub(r"^.*?:\s*", "", re.sub(r"\s*\|.*$", "", str(prev_ep["title"])))[:60],
                                            (W, H), os.path.join(WORK, "prev_card.png"), FONT)
                cards_.append((png_, 0.0, 5.0))
                log(f"  'last episode' card: {prev_ep['title'][:60]}")
        except Exception as e:
            log("  last-episode card skipped:", str(e)[:150])
    try:                                             # v84: a small card for one of our features (every 2nd video)
        pc_ = promo_card_for(lang, duration(video))
        if pc_:
            cards_.append(pc_)
    except Exception as e:
        log("  feature card skipped:", str(e)[:150])
    if cards_:
        try:
            vw_ = os.path.join(WORK, "final_cards.mp4")
            extras.overlay_cards(video, cards_, vw_)
            os.replace(vw_, video)
        except Exception as e:
            log("  cards over the video skipped:", str(e)[:150])

    own = [t if t.startswith("#") else "#" + t.replace(" ", "") for t in story.get("hashtags", [])[:15]]
    seeds = ([HORROR_CATS[cat]["bn"], "ভূতের গল্প", "bhuter golpo"] if lang == "bn" else
             [HORROR_CATS[cat]["hi"], "bhoot ki kahani", "डरावनी कहानी"])
    trend_tags, seo_words = extras.seo_pack("horror", lang, os.path.join(HERE, "assets"), seeds) if not MOCK else ([], [])
    trend_tags, seo_words = horror_only(trend_tags), horror_only(seo_words)   # v86: no stray trending words
    tags = []                                        # Facebook shows the first 5: 2 of this story + 3 trending tags
    for t in own[:2] + trend_tags[:3] + L.get("core_tags", [])[:3] + own[2:] + trend_tags[3:]:
        if t.lower() not in {x.lower() for x in tags}:
            tags.append(t)
    prev_link = ""
    # never 'everything is fictional' under a 'based on true events' story - the two would contradict each other
    ai_note = (L.get("ai_true") or L["ai_note"]) if story.get("true_label") else L["ai_note"]
    if part >= 2:                                     # part 2: the link to part 1 right at the top
        p1 = next((h for h in reversed(history) if h.get("series_id") and h.get("series_id") == series_id
                   and int(h.get("part") or 0) == part - 1), None)
        if p1 and (p1.get("youtube") or p1.get("facebook")):
            lnk = (f"https://youtu.be/{p1['youtube']}" if p1.get("youtube")
                   else f"https://www.facebook.com/watch/?v={p1['facebook']}")
            prev_link = ("⏮️ আগের পর্ব আগে শুনে নিন: " if lang == "bn" else "⏮️ पिछला भाग पहले सुनिए: ") + lnk + "\n\n"
    description = (f"{title}\n\n{prev_link}{story.get('description', '').strip()}\n\n" + (f"🗳️ {vote_text}\n\n" if vote_text else "")
                   + (f"{L['find_ghost']}\n\n" if hidden and not NO_BAIT else "") + f"{L['your_story']}\n\n{L['share_cta']}\n\n"
                   + f"{ai_note}\n\n{' '.join(tags)}")
    top_lines = uniq_top_lines(lang, used_names)     # v63: this week's district / the viewers in the story
    if top_lines:
        description = description.replace(f"{title}\n\n", f"{title}\n\n{top_lines}\n\n", 1)
    part_times, segs = TIMELINE
    labels = [sc.get("chapter") or f"{k + 1}" for k, sc in enumerate(scenes)]
    labels = (["⚡ " + ("ঝলক" if lang == "bn" else "झलक"), L["ch_intro"]] + labels) if STORY_PART[0] == 2 else \
        ([labels[0], L["ch_intro"]] + labels[1:]) if cold else [L["ch_intro"]] + labels
    chap = extras.chapters_text(part_times, labels + [L["ch_end"]], L["chapters"])
    try:                                             # v68: where each chapter starts (to learn where viewers leave)
        STATE["timeline"] = {"len": round(duration(video)),
                             "parts": [[round(t_), str(l_)[:40]] for t_, l_ in zip(part_times, labels)]}
    except Exception:
        pass
    yt_description = description.replace(f"\n\n{ai_note}", (f"\n\n{chap}" if chap else "") + f"\n\n{ai_note}")
    # YouTube: the first lines are what search shows - a 2-3 sentence summary and the words people search for
    yt_description = extras.search_head("horror", lang, story.get("description", ""), seo_words[:4]) + "\n\n" + \
        yt_description.replace(f"\n\n{story.get('description', '').strip()}\n\n", "\n\n", 1)
    try:                                             # v63: district wish, 'your name in a story', the ghost map
        yt_more = "\n\n".join(uniq_invites(lang, youtube=True))
        if yt_more:
            yt_description = yt_description.replace(f"\n\n{ai_note}", f"\n\n{yt_more}\n\n{ai_note}", 1)
    except Exception as e:
        log("  YouTube invitations skipped:", str(e)[:100])
    try:                                             # v76: read the story, send your own experience, fan channel
        g_links = growth_links(lang)
        if g_links:
            yt_description = yt_description.replace(f"\n\n{ai_note}", f"\n\n{g_links}\n\n{ai_note}", 1)
    except Exception as e:
        log("  growth links skipped:", str(e)[:100])
    yt_title = title
    kw = next((w for w in seo_words if w.lower() not in title.lower() and len(title) + 3 + len(w) <= 100), "")
    if kw:
        yt_title = f"{title} | {kw}"
    yt_tags = [w for w in seo_words] + tags
    try:                                             # v77: the safety check before every upload
        yt_title, yt_description, yt_tags, n1 = extras.safety_check(yt_title, yt_description, yt_tags, "horror")
        title, description, _t, n2 = extras.safety_check(title, description, [], "horror")
        extras.thumb_safe(thumb)
        if n1 or n2:
            log("  safety check: " + "; ".join(dict.fromkeys(n1 + n2)))
            extras.note("নিরাপত্তা-পরীক্ষা: " + "; ".join(dict.fromkeys(n1 + n2))[:300])
    except Exception as e:
        log("  safety check skipped:", str(e)[:120])

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
                loc = extras.yt_localizations(yt_title, yt_description, lang, env("GEMINI_API_KEY"))
                results["youtube"] = post_to_youtube(video, thumb, yt_title, yt_description, yt_tags, lang, loc)
                log("Posted to YouTube:", results["youtube"])
            except Exception as e:
                log("YOUTUBE FAILED:", e)
                results["youtube_error"] = str(e)[:200]
        else:
            log("YouTube secrets not set - skipping YouTube")
        extras.alert_post_errors(results, "ভূতের bot", title)
        if not results.get("facebook") and not results.get("youtube"):
            raise SystemExit("Posting failed everywhere - see messages above.")
        if results.get("youtube"):                   # the second thumbnail, kept for the weak-video test
            try:
                tb = os.path.join(WORK, "thumbnail_b.jpg")
                if os.path.exists(tb):
                    extras.keep_thumb_b(THUMB_B, results["youtube"], tb)
            except Exception as e:
                log("  second thumbnail not kept:", str(e)[:100])

    first = [vote_text or str(story.get("comment_question", "")).strip()]
    if hidden and not NO_BAIT:
        first.append(L["find_ghost"])
    if viewer and viewer.get("name"):
        first.append(L["credit_comment"].format(name=viewer["name"]))
    if vote_names:
        first.append(L["vote_comment"].format(names=extras.name_list(vote_names, lang, 10)))
    if shout_names:
        first.append(L["shout_comment"].format(names=extras.name_list(shout_names, lang, 10)))
    if not NO_BAIT:
        first.append(L["join_comment"])
    if lang == "bn" and env("TG_CHANNEL_COMMENT") != "0":   # v89: the fan channel in every first comment
        first.append(f"📢 নতুন গল্পের খবর সবার আগে পেতে আমাদের Telegram চ্যানেলে যোগ দিন: {channel_link()}")
    try:
        first += uniq_invites(lang)                  # v63: which district next Tuesday? + the ghost map
    except Exception as e:
        log("  first-comment invitations skipped:", str(e)[:100])
    story["comment_question"] = "\n\n".join(x for x in first if x)
    results.update(grow(video, story, title, lang, L, tags, results, history, page))

    history.append({"date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "lang": lang, "slot": SLOT,
                    "pending_comments": list(extras.PENDING),
                    "source": STATE.get("source_name") or (prev or {}).get("source") or None,
                    "idea_used": STATE.get("idea_used"),
                    "trend_used": STATE.get("trend_used"),
                    "crossover": STATE.get("crossover") or None,
                    "opening": STATE.get("opening"),
                    "category": STATE.get("category"),
                    "question_post": extras.fb_question_post(
                        history, "horror", lang, photo=(HIDDEN_PICS[0] if HIDDEN_PICS else None),
                        link=(f"https://www.facebook.com/watch/?v={results['facebook']}" if results.get("facebook") else "")
                    ) if not (MOCK or DRY_RUN) else None,
                    "title_b": (str(story.get("title_b") or "").strip()[:85] + (f" | {L['part'].format(n=part)}" if part else "")) or None,
                    "theme": theme, "format": fmt, "part": part, "continues": continues, "series_id": series_id, "title": title, "festival": festival,
                    "summary": str(story.get("summary") or story.get("description") or "")[:500] or None,
                    "sequel_of": STATE.get("sequel_of"), "best_comment_id": STATE.get("best_comment_id"),
                    "special": special, "viewer_story_id": viewer["id"] if viewer else None,
                    "classic_id": classic[0] if special == "classic" and classic else None,
                    "episode_summary": str(story.get("episode_summary", ""))[:400] if special == "karna" else None,
                    "karna_origin": True if special == "karna" else None,
                    "hidden": hidden, "mystery_answer": int(str(story.get("mystery_answer", 0) or 0)[:1] or 0)
                    if str(story.get("mystery_answer", 0) or 0)[:1].isdigit() else 0, **results})
    try:                                             # v63: district of the week, viewers' names, the ghost map pin
        rec = history[-1]
        for k_ in ("thumb_src", "timeline"):         # v68: whose thumbnail; where each chapter starts
            if STATE.get(k_):
                rec[k_] = STATE[k_]
        if STATE.get("district"):
            rec["district_week"] = STATE["district"]
        if special in SERIES_BIBLE and story.get("tagline"):
            rec["tagline"] = str(story["tagline"])[:160]      # (shown in the case files on the website)
        if used_names:
            rec["viewer_names"] = [p[0] for p in used_names]
        dk = map_add(story, title, results, lang, HORROR_CATS.get(cat, {}).get("bn", ""))
        if dk:
            rec["district"] = dk
        thank_named_viewers(used_names, results, lang)
    except Exception as e:
        log("  ghost map / district note skipped:", str(e)[:150])
    STATE["posted_now"] = True
    if not MOCK and not DRY_RUN:
        save_promise(story, slot_hour, lang, continues)
        try:                                         # v81: its storyteller's sentences are never used again
            remember_said(story)
            push_now([SAID_FILE], "sentences remembered")
        except Exception as e:
            log("  sentences not remembered:", str(e)[:100])
    if not MOCK:
        save_history(history)
        cat_ = STATE.get("category", "gram")
        if continues:                                # the next part comes on this category's next day
            last_sc = story["scenes"][-1] if story.get("scenes") else {}
            extras.series_put(NEXT_PART, cat_, {
                "created": (prev or {}).get("created") or dt.datetime.now(dt.timezone.utc).isoformat(),
                "category": cat_, "lang": lang, "theme": theme, "fmt": fmt, "special": special,
                "title": (prev or {}).get("title") or re.sub(r"\s*\|.*$", "", title).strip(),
                "done": part, "total": total, "series_id": series_id, "case_no": STATE.get("case_no"),
                "summary": (((prev or {}).get("summary") or "") + f"\nPart {part}: " + str(story.get("summary", "")))[-4000:],
                "last_lines": " / ".join(str(ln.get("text", "")) for ln in (last_sc.get("lines") or [])[-4:]),
                "outline": STATE.get("outline") or (prev or {}).get("outline", ""),
                "characters": story.get("characters"), "setting": story.get("setting", ""),
                "arc": STATE.get("arc") or (prev or {}).get("arc"),
                "crossover": STATE.get("crossover") or (prev or {}).get("crossover"),
                "source": STATE.get("source_name", "") or (prev or {}).get("source", "")})
            log(f"Series: part {part + 1} of {total} comes on this category's next day")
        elif part >= 2:
            extras.series_put(NEXT_PART, cat_, None)
        if not continues and special in SERIES_BIBLE:   # the case is over: into the series' memory
            try:
                bible_add(special, title, story.get("episode_summary") or str(story.get("summary", ""))[:300])
            except Exception as e:
                log("  series memory skipped:", str(e)[:100])
        if special in SERIES_BIBLE:                  # v70: the series' case files on the website
            try:
                if cases_page(history):
                    push_now([MAP_DIR], "case files")
            except Exception as e:
                log("  case files skipped:", str(e)[:120])
    if viewer and not DRY_RUN:                       # tell the viewer their story is out
        try:
            if viewer["id"].startswith("fb_") and results.get("facebook"):
                extras.fb_comment(viewer["id"][3:], L["reply_viewer"] + f" https://www.facebook.com/{results['facebook']}")
        except Exception as e:
            log("  reply to viewer skipped:", str(e)[:120])
    if shout_ids and results.get("facebook") and not DRY_RUN:
        n = extras.reply_to(shout_ids, L["congrats_reply"].format(link=f"https://www.facebook.com/{results['facebook']}"))
        log(f"  congratulated {n} viewers under their comments")
    if not MOCK and not DRY_RUN:
        try:                                         # v76: countdown story, fan channel, written story, web page ...
            growth_after_post(story, title, results, history, lang, video, thumb, slot_hour, special, viewer)
        except Exception as e:
            log("  growth steps skipped:", str(e)[:200])
    page_name = env(f"PAGE_NAME_{lang.upper()}") or "Daily Horror Story"
    extras.telegram(extras.report_text(page_name, title, results, history))
    if slot_hour == EVENING and env("MODE") not in ("amavasya", "compilation") and SLOT and \
            str(SLOT).startswith(dt.datetime.now(extras.IST).date().isoformat()):
        try:                                         # v68: tomorrow's two stories now + their titles to you by 9 PM
            write_tomorrow(history)
        except Exception as e:
            log("  tomorrow's stories not written tonight (the morning run will):", str(e)[:200])


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
    if env("MARATHON") != "0" and dt.datetime.now(extras.IST).day <= 7:   # v63: first Sunday of the month
        try:
            if make_marathon(history):
                return
        except Exception as e:
            log("  night marathon skipped - the weekly compilation instead:", str(e)[:200])
        for f in os.listdir(WORK):                   # (room for the weekly compilation)
            if f.startswith(("mraw_", "m_", "marathon")) and f.endswith(".mp4"):
                os.remove(os.path.join(WORK, f))
    now = dt.datetime.now(dt.timezone.utc)
    week = []
    for h in history[-40:]:
        try:
            t = dt.datetime.fromisoformat(str(h.get("date")))
        except Exception:
            continue
        if (now - t.replace(tzinfo=t.tzinfo or dt.timezone.utc)).days <= 7 and h.get("facebook") \
                and not h.get("kind"):
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


# ----------------------------------------------------------------- the Reel: a film trailer
def _card(path, lines, sizes, colors, bg=None):
    """a 9:16 title card: big text on black (or on a dark picture)"""
    from PIL import ImageEnhance
    VW, VH = 720, 1280
    if bg and os.path.exists(bg):
        img = Image.open(bg).convert("RGB")
        s = max(VW / img.width, VH / img.height)
        img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1))
        img = img.crop(((img.width - VW) // 2, (img.height - VH) // 2, (img.width - VW) // 2 + VW, (img.height - VH) // 2 + VH))
        img = ImageEnhance.Brightness(img).enhance(0.35)
    else:
        img = Image.new("RGB", (VW, VH), (0, 0, 0))
    d = ImageDraw.Draw(img)
    blocks = []
    for text, size, col in zip(lines, sizes, colors):
        rows, f, sz = extras._fit_text(d, extras.no_tofu(text), FONT, VW - 80, size, lines_max=3)
        blocks.append((rows, f, sz, col))
    total = sum(len(r) * int(sz * 1.35) for r, f, sz, c in blocks) + 30 * (len(blocks) - 1)
    y = (VH - total) // 2
    for rows, f, sz, col in blocks:
        for r in rows:
            tw = d.textlength(r, font=f)
            d.text(((VW - tw) / 2, y), r, font=f, fill=col, stroke_width=max(3, sz // 14), stroke_fill=(0, 0, 0))
            y += int(sz * 1.35)
        y += 30
    img.save(path, quality=92)
    return path


def _still_clip(img, sound, dur, out, zoom=False):
    VW, VH = 720, 1280
    wav = out + ".wav"
    np = _np()
    a = np.zeros(int(SR * dur))
    if sound is not None:
        a[:min(len(a), len(sound))] += sound[:len(a)]
    write_wav(wav, a)
    z = (f"zoompan=z='min(1+0.0035*on,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(dur * FPS) + 1}"
         f":s={VW}x{VH}:fps={FPS}," if zoom else "")
    run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-i", wav, "-t", f"{dur:.2f}",
         "-vf", f"scale={VW}:{VH},{z}format=yuv420p", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-shortest", out])
    return out


def _video_clip(video, st, dur, out, text=""):
    """a moment of the film, shown big in 9:16 (blurred copy behind), with its own sound and its words as a
    big caption (the picture without the wide video's subtitles, so nothing is cut off)"""
    VW, VH = 720, 1280
    fh = int(VH * 0.62) // 2 * 2
    fw = int(fh * 16 / 9) // 2 * 2
    clean_v = os.path.join(WORK, "joined.mp4")           # the film before the subtitles were burned in
    src_v = clean_v if os.path.exists(clean_v) else video
    src_a = os.path.join(WORK, "full.wav") if src_v == clean_v else video
    cap = os.path.join(WORK, os.path.basename(out) + ".png")
    img = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    top_t, top_s = STATE.get("trailer_top") or ("", "")
    if top_t:                                       # the story's title and tag line at the top, all through
        d0 = ImageDraw.Draw(img)
        y0 = 34
        for t_, sz_, col_ in ((top_t, 56, (255, 215, 0, 255)), (top_s, 38, (255, 255, 255, 255))):
            if not t_:
                continue
            rows_, f_, s_ = extras._fit_text(d0, extras.no_tofu(t_), FONT, VW - 70, sz_, lines_max=2)
            for r_ in rows_:
                tw = d0.textlength(r_, font=f_)
                d0.text(((VW - tw) / 2, y0), r_, font=f_, fill=col_, stroke_width=max(3, s_ // 12), stroke_fill=(0, 0, 0, 255))
                y0 += int(s_ * 1.3)
    if text:
        d = ImageDraw.Draw(img)
        rows, f, sz = extras._fit_text(d, text, FONT, VW - 70, 46, lines_max=3)
        y = int(VH * 0.83) - len(rows) * int(sz * 1.3) // 2
        for r in rows:
            tw = d.textlength(r, font=f)
            d.text(((VW - tw) / 2, y), r, font=f, fill=(255, 230, 0, 255), stroke_width=4, stroke_fill=(0, 0, 0, 255))
            y += int(sz * 1.3)
    img.save(cap)
    fc = (f"[0:v]split[a][b];[a]scale=-2:{VH},crop={VW}:{VH},boxblur=22:2,eq=brightness=-0.3[bg];"
          f"[b]scale={fw}:{fh},crop={VW}:{fh}[fg];[bg][fg]overlay=0:{(VH - fh) // 2}[m];[m][2:v]overlay=0:0,"
          "format=yuv420p[v]")
    run(["ffmpeg", "-y", "-ss", f"{st:.2f}", "-t", f"{dur:.2f}", "-i", src_v, "-ss", f"{st:.2f}", "-t", f"{dur:.2f}",
         "-i", src_a, "-i", cap, "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-af", "afade=t=in:d=0.08",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k",
         "-ar", "44100", "-ac", "2", "-t", f"{dur:.2f}", out])
    return out


def pick_hook(scenes, story):
    """The first 5-8 seconds decide everything (Facebook: most viewers leave in 2-3 seconds). So the video
    opens with ONE gripping moment from the middle of the story - a scream, the ghost's line, a terrified
    question - never the ending (no spoiler). Returns (scene index, [1-2 lines]) or None."""
    n = len(scenes)
    if n < 4:
        return None
    ghosts = {str(c.get("name", "")).lower() for c in story.get("characters", [])
              if str(c.get("kind", "")).startswith("ghost")}
    best, bs = None, -9
    for i in range(max(1, n // 4), max(2, int(n * 0.7))):
        lines = scenes[i].get("lines") or []
        for j, ln in enumerate(lines):
            tx = extras.strip_tags(str(ln.get("text", ""))).strip()
            if not 12 <= len(tx) <= 110:
                continue
            spk = str(ln.get("speaker", "narrator")).lower()
            sc = ((3 if ln.get("jump_scare") or ln.get("ghost_laugh") else 0) + (2 if spk in ghosts else 0)
                  + (0 if spk.startswith("narrat") else 2) + (1 if any(ch in tx for ch in "!?") else 0)
                  + (1 if str(ln.get("emotion", "")).lower() in ("terrified", "scream", "fear", "panic", "whisper",
                                                                    "eerie", "shocked") else 0))
            if sc > bs:
                best, bs = (i, j), sc
    if not best or bs < 3:
        return None
    i, j = best
    lines = scenes[i]["lines"]
    take = [dict(lines[j])]
    if j + 1 < len(lines) and len(str(lines[j + 1].get("text", ""))) <= 70 and \
            not str(lines[j + 1].get("speaker", "narrator")).lower().startswith("narrat"):
        take.append(dict(lines[j + 1]))                 # the answer / scream that follows it
    for ln in take:                                    # straight in: no held silence before the first words
        for k in ("guess", "jump_scare", "_revealed"):
            ln.pop(k, None)
    return i, take


def make_trailer(video, story, title, lang, L, out, slot_hour, special):
    STATE["trailer_top"] = (re.sub(r"\s*\|.*$", "", title).strip(),
                            str(story.get("tagline") or story.get("thumbnail_text") or "").strip())
    """A cinema-trailer Reel (under a minute): a quiet cold open, title cards, quick cuts of the scariest moments
    with hits in between, a held breath ... then the ghost's face, and the show's title card with the time."""
    np = _np()
    part_times, segs = TIMELINE
    if len(part_times) < 3:
        raise RuntimeError("too short for a trailer")
    st0, st1 = part_times[min(STORY_PART[0], len(part_times) - 2)], part_times[-1]   # the story (not hook/title)
    limit = st0 + (st1 - st0) * 0.78                   # never show the ending
    # only WHOLE lines (never cut in the middle of a sentence), short enough to keep the trailer under a minute
    cand = [(s, d, nar, tx) for s, d, nar, tx in segs if st0 <= s < limit and 1.2 < d <= 7.5]
    if len(cand) < 3:
        raise RuntimeError("not enough moments")
    scary = {str(ln.get("text", "")).strip() for sc in story.get("scenes", []) for ln in sc.get("lines", [])
             if ln.get("jump_scare") or ln.get("ghost_laugh") or ln.get("sfx")}
    ghosts = {str(c.get("name", "")).lower() for c in story.get("characters", []) if str(c.get("kind", "")).startswith("ghost")}
    ghost_lines = {str(ln.get("text", "")).strip() for sc in story.get("scenes", []) for ln in sc.get("lines", [])
                   if str(ln.get("speaker", "")).lower() in ghosts}
    score = lambda c: ((0 if c[2] else 2) + (1 if any(ch in c[3] for ch in "!?") else 0)
                       + (3 if c[3].strip() in scary else 0) + (2 if c[3].strip() in ghost_lines else 0)
                       - max(0, c[1] - 5) * 0.5)
    import bisect
    scene_of = lambda c: bisect.bisect_right(part_times, c[0])       # which scene this moment belongs to
    best = {}                                        # never the same scene (picture) or the same words twice
    for c in cand:
        s = scene_of(c)
        if s not in best or score(c) > score(best[s]):
            best[s] = c
    chosen = sorted(best.values(), key=score, reverse=True)
    picks, words = [], set()
    budget = 40.0                                    # seconds of story moments (+ the cards = under a minute)
    for c in chosen:
        w = re.sub(r"[^\wঀ-৿ऀ-ॿ]", "", c[3])[:30]
        if w in words or any(abs(c[0] - p[0]) < 6 for p in picks) or c[1] + 0.4 > budget:
            continue
        words.add(w)
        picks.append(c)
        budget -= c[1] + 0.4
        if len(picks) == 6:
            break
    picks.sort(key=lambda c: c[0])
    if len(picks) < 2:
        raise RuntimeError("not enough different moments")
    rnd = np.random.default_rng(7)
    hit = synth("scare_hit", int(SR * 1.2), rnd) * 0.9
    boom = synth("scare_hit", int(SR * 2.0), rnd)
    parts, k = [], 0

    def nxt(name):
        nonlocal k
        k += 1
        return os.path.join(WORK, f"tr_{k:02d}_{name}.mp4")
    black = os.path.join(WORK, "tr_black.jpg")
    Image.new("RGB", (720, 1280), (0, 0, 0)).save(black)
    hook = str(story.get("thumbnail_text") or "").strip()
    first = picks[0]
    parts.append(_video_clip(video, first[0] - 0.15, first[1] + 0.4, nxt("open"), first[3]))
    if hook:
        parts.append(_still_clip(_card(os.path.join(WORK, "tr_c1.jpg"), [hook], [64], [(255, 255, 255)]),
                     boom, 1.8, nxt("card")))
    for c in picks[1:4]:
        parts.append(_still_clip(black, hit, 0.3, nxt("flash")))
        parts.append(_video_clip(video, c[0] - 0.15, c[1] + 0.4, nxt("cut"), c[3]))
    when = when_words(lang, slot_hour, 0) + (" পুরো গল্প" if lang == "bn" else " पूरी कहानी")
    if extras.PUBLISH.get("at") and extras.PUBLISH["at"] > dt.datetime.now(extras.IST):
        parts.append(_still_clip(_card(os.path.join(WORK, "tr_c2.jpg"), [when], [70], [(255, 40, 40)]),
                     boom, 1.4, nxt("when")))
    for c in picks[4:]:
        parts.append(_still_clip(black, hit, 0.25, nxt("flash")))
        parts.append(_video_clip(video, c[0] - 0.15, c[1] + 0.4, nxt("fast"), c[3]))
    g = story.get("guess") if isinstance(story.get("guess"), dict) else {}
    opts = [str(x) for x in (g.get("options") or [])][:3]
    if g.get("question") and len(opts) == 3 and not NO_BAIT:   # the viewers' puzzle: they comment 1, 2 or 3
        nums = "১২৩" if lang == "bn" else "123"
        qcard = _card(os.path.join(WORK, "tr_cq.jpg"),
                      [str(g["question"])] + [f"{nums[i]}) {o}" for i, o in enumerate(opts)] + [L["guess_card"]],
                      [52, 42, 42, 42, 40], [(255, 255, 255)] + [(255, 225, 0)] * 3 + [(255, 70, 70)])
        parts.append(_still_clip(qcard, hit, 3.2, nxt("guess")))
    # a held breath ... the ghost
    parts.append(_still_clip(black, synth("heartbeat", int(SR * 1.4), rnd) * 0.6, 1.4, nxt("breath")))
    gface = os.path.join(WORK, "ghost_face.jpg")
    ghost_img = gface if os.path.exists(gface) else os.path.join(WORK, "thumb_base.jpg")
    scream = None
    try:
        gl = ghost_laugh_sound("female", rnd)
        if gl is not None:
            scream = gl * 0.9
    except Exception:
        pass
    sc = boom.copy()
    if scream is not None:
        sc = np.concatenate([sc, np.zeros(max(0, len(scream) - len(sc)))])
        sc[:len(scream)] += scream
    parts.append(_still_clip(ghost_img, sc, 2.4, nxt("ghost"), zoom=True))
    show = SHOW_NAME[lang].get(slot_hour, SHOW_NAME[lang][EVENING])
    if special == "karna" or special in NEW_SERIES:
        show = series_label(special, L)
    clean = re.sub(r"[^\w\sऀ-ॿঀ-৿,।!?'-]", "", title).strip()
    final = _card(os.path.join(WORK, "tr_c3.jpg"), [show, clean, when if when else "", L["follow"], L["link_below"]], [50, 66, 46, 40, 40],
                  [(200, 200, 200), (255, 225, 0), (255, 60, 60), (255, 255, 255), (120, 220, 255)], bg=ghost_img)
    parts.append(_still_clip(final, signature_sting(), 3.4, nxt("title")))
    lst = os.path.join(WORK, "trailer.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in parts)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "22", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-movflags", "+faststart", out])
    return out


def grow(video, story, title, lang, L, tags, results, history, page):
    """Extra reach after the main post: Reel + Short teaser, first comment, playlist. Never stops the run."""
    out = {}
    part_times, segs = TIMELINE
    teaser = os.path.join(WORK, "teaser.mp4")
    try:
        try:                                         # a cinema trailer (ghost and the time at the end)
            make_trailer(video, story, title, lang, L, teaser, STATE.get("slot_hour", EVENING), STATE.get("special"))
            log(f"Trailer ready ({duration(teaser):.0f} s)")
        except Exception as e:
            log("  trailer not made, plain teaser:", str(e)[:200])
            st, en = extras.pick_window(segs, part_times, story.get("teaser_scene") or 2)
            extras.make_teaser(video, st, en, teaser, FONT, re.sub(r"\s*\|.*$", "", title).strip(), L["cta"], WORK, tagline=str(story.get("tagline") or story.get("thumbnail_text") or ""),
                               colors=((255, 230, 0), (200, 0, 20)))
            log(f"Teaser ready ({en - st:.0f} s, from {st:.0f} s)")
    except Exception as e:
        log("  teaser skipped:", str(e)[:200])
        teaser = None
    if DRY_RUN:
        return out
    question = str(story.get("comment_question", "")).strip()
    fb_full = f"https://www.facebook.com/watch/?v={results['facebook']}" if results.get("facebook") else page
    short_desc = f"{title}\n\n{L['full_link']} {fb_full}\n\n{' '.join(tags[:5])}"   # the FULL story's own link
    if teaser and env("FB_REELS") != "0":
        try:
            pub = extras.PUBLISH.get("at")
            now_ = dt.datetime.now(extras.IST)
            if pub and (pub - now_).total_seconds() > 40 * 60 and env("FB_TEASER_BEFORE") == "1":
                # v81: the teaser (cut from this finished video - no extra voice) goes out NOW, before the story
                sl_ = STATE.get("slot_hour", EVENING)
                when_ = (SLOT_BN.get(sl_, "") + "য়") if lang == "bn" else ""
                promo = (f"{re.sub(r'[|].*$', '', title).strip()}\n\n👻 পুরো গল্প আজ {when_}, এই পেজেই। "
                         f"আলো নিভিয়ে শুনবেন।\n\n{' '.join(tags[:5])}" if lang == "bn" else short_desc)
                out["fb_reel"] = extras.fb_post_reel(teaser, promo, at=now_ + dt.timedelta(minutes=12))
                log("Teaser Reel (from the finished video) posted BEFORE the story:", out["fb_reel"])
            elif pub and pub > now_ + dt.timedelta(minutes=15):
                # v86: a Reel before the story got ~3 views (nothing to click yet) - now it comes 10 minutes AFTER
                # the story is out, with the full story's link
                out["fb_reel"] = extras.fb_post_reel(teaser, short_desc, at=pub + dt.timedelta(minutes=10))
                log("Facebook Reel scheduled 10 minutes after the story:", out["fb_reel"])
            else:
                out["fb_reel"] = extras.fb_post_reel(teaser, short_desc)
                log("Posted Facebook Reel:", out["fb_reel"])
        except Exception as e:
            log("  Facebook Reel skipped:", str(e)[:200])
        try:                                     # the teaser on the page Story too (24 h, top of the feed)
            out["fb_story"] = extras.fb_post_story(teaser)
            if out["fb_story"]:
                log("Shared to Facebook Story:", out["fb_story"])
        except Exception as e:
            log("  Facebook Story skipped:", str(e)[:200])
        if env("SECOND_REEL") != "0":                # a second Reel from another moment, 2 hours later
            try:
                pt_, sg_ = TIMELINE[0], TIMELINE[1]
                s2, e2 = extras.pick_window(sg_, pt_, max(2, (len(pt_) * 3) // 5))
                reel2 = os.path.join(WORK, "reel2.mp4")
                extras.make_teaser(video, s2, e2, reel2, FONT, re.sub(r"\s*\|.*$", "", title).strip(), L["cta"], WORK,
                                   tagline=str(story.get("tagline") or story.get("thumbnail_text") or ""))
                base = extras.PUBLISH.get("at") or dt.datetime.now(extras.IST)
                out["fb_reel2"] = extras.fb_post_reel(reel2, short_desc, at=max(base, dt.datetime.now(extras.IST))
                                                      + dt.timedelta(hours=2))
                log("Second Facebook Reel scheduled (2 hours later):", out["fb_reel2"])
            except Exception as e:
                log("  second Reel skipped:", str(e)[:200])
    if teaser and env("INSTAGRAM") == "1":           # only if you switch Instagram on (secret INSTAGRAM = 1)
        try:
            out["ig_reel"] = extras.ig_post_reel(teaser, short_desc)
            log("Posted Instagram Reel:", out["ig_reel"])
        except Exception as e:
            log("  Instagram Reel skipped:", str(e)[:200])
    if results.get("youtube"):
        try:
            pl_name = story.get("_playlist") or L["playlist"]
            pid = extras.yt_add_to_playlist(results["youtube"], pl_name, lang)
            log("  added to YouTube playlist")
            try:                                     # v68: the playlist as a podcast (YouTube + YouTube Music)
                yt_podcast(pid, pl_name, lang)
            except Exception as e:
                log("  podcast skipped:", str(e)[:150])
            if story.get("_theme_pl") and story.get("_theme_pl") != story.get("_playlist"):
                extras.yt_add_to_playlist(results["youtube"], story["_theme_pl"], lang)
                log(f"  added to the themed playlist: {story['_theme_pl']}")
        except Exception as e:
            log("  playlist skipped:", str(e)[:200])
        if (teaser and extras.yt_extra_ok() and env("YT_SHORTS") != "0"
                and extras.shorts_today(history) < int(env("YT_SHORTS_PER_DAY") or 2)):
            try:
                desc = f"{L['full_link']} https://youtu.be/{results['youtube']}\n\n{title}\n{' '.join(tags[:5])}"
                loc = extras.shorts_localizations(extras.yt_localizations(title, desc, lang, env("GEMINI_API_KEY")),
                                                  desc)
                out["yt_short"] = post_to_youtube(teaser, None, f"{title[:80]} #Shorts", desc, tags, lang, loc)
                log("Posted YouTube Short:", out["yt_short"])
                try:                                 # v86: the way from the Short to the full story, right under it
                    extras.yt_comment(out["yt_short"], ("▶ পুরো গল্পটা এখানে: " if lang == "bn" else "▶ पूरी कहानी यहाँ: ")
                                      + f"https://youtu.be/{results['youtube']}")
                except Exception as e:
                    log("  Short's link comment skipped:", str(e)[:120])
            except Exception as e:
                log("  YouTube Short skipped:", str(e)[:200])
    if results.get("facebook"):
        try:                                          # closed captions (CC) on the Facebook video
            extras.fb_add_captions(results["facebook"], segs, lang,
                                   {str(ln.get("text", "")).strip(): str(ln.get("en", "")).strip()
                                    for sc in story.get("scenes", []) for ln in sc.get("lines", []) if ln.get("en")})
        except Exception as e:
            log("  Facebook captions skipped:", str(e)[:160])
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
        if lang == "bn" and env("HINDI_SUBS") != "0":
            try:                                      # v82: Hindi subtitles - Hindi-speaking viewers can follow too
                hi_ = extras.translate_lines([s[3] for s in segs], "Hindi")
                srt_hi = extras.write_srt(segs, hi_, os.path.join(WORK, "subs_hi.srt"))
                if srt_hi:
                    extras.yt_upload_captions(results["youtube"], srt_hi, language="hi", name="हिन्दी")
                    log(f"  Hindi subtitles added on YouTube ({len(hi_)} lines)")
            except Exception as e:
                log("  Hindi subtitles skipped:", str(e)[:160])
    if results.get("facebook") and env("ANNOUNCE") != "0" and env("MODE") != "amavasya":
        try:                                          # "coming soon" post 2 hours before the next video
            nxt = extras.next_slot([NOON, EVENING], [EVENING])
            if nxt:
                slot, when, day = nxt
                words = f"{extras.DAY_WORDS[lang][day]} {extras.TIME_WORDS[lang][slot.hour]}"
                card = extras.announcement_card(os.path.join(WORK, "thumb_base.jpg"), FONT, L["ann1"], words,
                                                os.path.join(WORK, "announce.jpg"))
                extras.fb_schedule_photo(card, L["ann_msg"].format(when=words), when)
                log(f"  'coming soon' post scheduled for {when.strftime('%d %b %H:%M')} India time")
        except Exception as e:
            log("  announcement skipped:", str(e)[:160])
    live = extras.wait_for_publish()
    if question and results.get("facebook"):
        try:
            extras.comment_when_live(results["facebook"], question, live)
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


def day_report():
    """After the night video: the day's report on Telegram."""
    try:
        if str(SLOT or "").endswith(f"@{EVENING}") and STATE.get("posted_now"):
            u = _jload(TTS_USAGE, {})
            hist = load_history()
            kinds = extras.best_kinds(hist, {k: v.get("bn", k) for k, v in HORROR_CATS.items()})
            chirp = (f"\nChirp গলা এই মাসে: {extras.chirp_used(TTS_USAGE)} / {env('CHIRP_MONTH_CAP') or 900000} অক্ষর"
                     if env("GOOGLE_TTS_KEY") else "")
            extras.daily_report(hist, "Daily Horror Story",
                                f"Gemini গলা: আজ {u.get('used', 0)} / {env('TTS_DAY_BUDGET') or 36} request খরচ"
                                + chirp + (f"\n{kinds}" if kinds else ""))
    except Exception as e:
        log("  daily report skipped:", str(e)[:120])


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:                          # a stop with a reason -> the reason in Bengali on Telegram
        if e.code not in (None, 0):
            extras.fail_note(HERE, str(e.code), "ভূতের bot")
        raise
    except BaseException as e:
        extras.fail_note(HERE, f"{type(e).__name__}: {e}", "ভূতের bot")
        raise
    day_report()
