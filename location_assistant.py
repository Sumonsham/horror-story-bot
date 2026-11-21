"""LOCATION ASSISTANT (assistant 1 of 3) - role: find WHERE every scene happens and give it the right place from
the Location Library (pond, road, jungle, house interior, railway station, cremation ground, rajbari).

- reads the scene's place text + its narration (what is said happening HERE counts more than places only
  mentioned in dialogue; comparisons like "যেন ... দিঘি" never count)
- Gemini (free) may answer when present; offline keyword scoring otherwise - the report says which
- when the story's place is NOT in the library (a hospital, a boat, a temple inside...), it picks the closest
  place honestly and reports it as SUBSTITUTE with the reason - never silently
- weather (rain, storm, lightning) and time come from the same words
- COLLECTS: every requested place is counted in location_requests.json (missing ones first) so the next
  places to build are the ones the stories really ask for
"""
import json
import os
import re
import unicodedata

_n = lambda s: unicodedata.normalize("NFD", s or "")    # one spelling for য় / ড় / ঢ়

import location_library as L

KEYWORDS = {
    "pond": r"পুকুর|দিঘি|দীঘি|ডোবা|ঝিল|ঘাটে বস|pond|lake",
    "road": r"রাস্তা|সড়ক|রোড|হাইওয়ে|বাইপাস|মোড়|মাঝরাস্তা|দোকান|road|highway|street",
    "jungle": r"জঙ্গল|বন\b|বনের|অরণ্য|বাঁশবন|বাঁশঝাড়|forest|jungle|woods",
    "house_interior": r"ঘরে|ঘরের|কুটির|কামরা|উঠোন|দাওয়া|বাড়ির ভেতর|মেসে|বারান্দা|room|hut|house|inside",
    "railway_station": r"স্টেশন|প্ল্যাটফর্ম|রেললাইন|রেলগাড়ি|ট্রেন|station|platform|railway",
    "cremation_ground": r"শ্মশান|চিতা|শবদাহ|cremation|pyre|burning ghat",
    "rajbari": r"রাজবাড়ি|জমিদারবাড়ি|জমিদার বাড়ি|প্রাসাদ|ভগ্ন অট্টালিকা|palace|mansion|zamindar",
}
# places the library does not have yet -> the honest nearest one
NEAREST = {
    r"হাসপাতাল|hospital": ("house_interior", "হাসপাতাল নেই - ঘরের ভেতর দেখানো হচ্ছে"),
    r"নৌকা|নদীতে|boat": ("cremation_ground", "নৌকা নেই - নদীর পাড় দেখানো হচ্ছে (শ্মশানের নদী)"),
    r"নদী|river": ("cremation_ground", "আলাদা নদীর ঘাট নেই - শ্মশানের নদীর পাড় দেখানো হচ্ছে"),
    r"মন্দির|temple": ("rajbari", "মন্দির নেই - পুরোনো ভাঙা বাড়ি দেখানো হচ্ছে"),
    r"কবরস্থান|graveyard|cemetery": ("cremation_ground", "কবরস্থান নেই - শ্মশান দেখানো হচ্ছে"),
    r"মাঠ|field": ("pond", "খোলা মাঠ নেই - পুকুরপাড়ের খোলা জমি দেখানো হচ্ছে"),
    r"স্কুল|school|অফিস|office": ("house_interior", "স্কুল/অফিস নেই - ঘরের ভেতর দেখানো হচ্ছে"),
    r"ছাদ|roof": ("rajbari", "ছাদ নেই - পুরোনো বাড়ির সামনে দেখানো হচ্ছে"),
    r"গাড়ির ভেতর|বাসে|in the car|bus": ("road", "গাড়ির ভেতর নেই - রাস্তা দেখানো হচ্ছে"),
}
# a road through the jungle looks like the jungle with its path; a room in a palace is still a room
PRIORITY = ["cremation_ground", "railway_station", "rajbari", "house_interior", "jungle", "pond", "road"]


def _clean(text):
    t = re.sub(_n(r"যেন[^।?!,]*"), " ", _n(text))
    return re.sub(_n(r"\S+\s*(মতো|মত)\b"), " ", t)


def weather(text):
    t = _n(text)
    w = {"rain": 0.0, "storm": False, "lightning": False}
    if re.search(_n(r"ঝোড়ো|ঝড়|storm"), t, re.I):
        w.update(rain=0.9, storm=True, lightning=True)
    elif re.search(_n(r"বৃষ্টি|rain"), t, re.I):
        w["rain"] = 0.6
    if re.search(_n(r"বাজ|বিদ্যুৎ|বজ্র|lightning|thunder"), t, re.I):
        w["lightning"] = True
    return w


def offline(place_text, narration, dialogue):
    score = {k: 0.0 for k in KEYWORDS}
    hits = {k: [] for k in KEYWORDS}
    for src, wgt in ((place_text, 3.0), (narration, 2.0), (dialogue, 1.0)):
        s = _clean(src)
        for k, pat in KEYWORDS.items():
            for m in re.finditer(_n(pat), s, re.I):
                score[k] += wgt
                hits[k].append(unicodedata.normalize("NFC", m.group(0)))
    best = max(score.values())
    if best <= 0:
        for pat, (loc, why) in NEAREST.items():
            if re.search(_n(pat), _n(f"{place_text} {narration}"), re.I):
                return loc, "SUBSTITUTE", why, hits
        return "pond", "SUBSTITUTE", "গল্পে জায়গার নাম পাওয়া যায়নি - গ্রামের খোলা রাত (পুকুরপাড়) দেখানো হচ্ছে", hits
    tops = [k for k in PRIORITY if score[k] >= best * 0.6 and score[k] > 0]
    loc = tops[0]
    for pat, (nloc, why) in NEAREST.items():               # a better-named missing place inside the text?
        if re.search(_n(pat), _clean(place_text), re.I) and not re.search(_n(KEYWORDS[loc]), _clean(place_text), re.I):
            return nloc, "SUBSTITUTE", why, hits
    return loc, "MATCH", "গল্পের শব্দ: " + ", ".join(sorted(set(hits[loc]))[:6]), hits


PROMPT = """You are the LOCATION ASSISTANT of a Bengali horror-story animation engine. The library has ONLY these
places: {places}. Read the scene and answer JSON {{"location":"<one id>","status":"MATCH|SUBSTITUTE",
"reason":"<Bengali: which words say so; if SUBSTITUTE, which place the story wanted and why this one is the closest>",
"story_place":"<the place the story names>"}}. A place only mentioned in dialogue (a plan, a memory) or a comparison
("যেন ... দিঘি") is NOT the scene's place.
Scene place: {place}
Narration: {narr}
Dialogue: {dia}"""


def analyse(scene, llm=None, log=print):
    """scene: {"place", "lines": [{"speaker", "text"}]} -> {"location", "status", "reason", "weather", "source"}"""
    place = str(scene.get("place", ""))
    narr = " ".join(str(l.get("text", "")) for l in scene.get("lines", []) if (l.get("speaker") or "narrator") == "narrator")
    dia = " ".join(str(l.get("text", "")) for l in scene.get("lines", []) if (l.get("speaker") or "narrator") != "narrator")
    w = weather(f"{place} {narr}")
    if llm:
        try:
            raw = llm(PROMPT.format(places=", ".join(f"{k} ({v['bn']})" for k, v in L.LOCATIONS.items()),
                                    place=place, narr=narr[:1500], dia=dia[:1500]))
            d = json.loads(raw[raw.find("{"):raw.rfind("}") + 1]) if raw else None
            if d and d.get("location") in L.LOCATIONS:
                return {"location": d["location"], "status": d.get("status", "MATCH"), "reason": d.get("reason", ""),
                        "story_place": d.get("story_place", place), "weather": w, "source": "gemini"}
        except Exception as e:
            log(f"  location assistant: Gemini answer unusable ({str(e)[:100]}) - offline rules used")
    loc, status, why, hits = offline(place, narr, dia)
    return {"location": loc, "status": status, "reason": why, "story_place": place, "weather": w, "source": "offline-rules",
            "candidates": {k: v for k, v in hits.items() if v}}


def collect(ledger_path, results):
    try:
        led = json.load(open(ledger_path, encoding="utf-8"))
    except Exception:
        led = {"used": {}, "wanted_missing": {}}
    for r in results:
        led["used"][r["location"]] = led["used"].get(r["location"], 0) + 1
        if r["status"] == "SUBSTITUTE":
            k = r.get("story_place") or "?"
            led["wanted_missing"][k] = led["wanted_missing"].get(k, 0) + 1
    os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(led, f, ensure_ascii=False, indent=1)
    return led
