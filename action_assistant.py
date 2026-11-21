"""ACTION ASSISTANT (assistant 2 of 3) - role: read every line of the story and write down WHO does WHAT, WHERE,
with which FEELING, towards WHOM, holding WHAT - and whether it really HAPPENS on screen.

For every line it returns:
  {"i", "speaker", "who", "where", "emotion", "target", "objects",
   "doing": [{"act", "who", "mode", "target", "object", "words", "ongoing"}]}
  mode:  happens   - the story says it happens now (narration, or a line that describes what is going on now:
                     "লণ্ঠন দোলাচ্ছেন কেন?", "হাত দুটো কাঠ হয়ে গেছে")
         command   - someone is ASKED to do it ("ওঠ পেছনে!", "আমার দিকে তাকা!") - the story does not say it was done
         mentioned - only talked about (past, a plan, a memory, a comparison) - nothing to show
  ongoing: the state was already there when the line is spoken (it is shown from the start of the scene)

Two ways, both honest:
  1. Gemini (free key, the bot's own helper) reads the lines with the fixed action list below and answers JSON.
  2. Offline rules (Bengali + English verb patterns) when Gemini is not there / busy - the report says which
     one was used for every scene ("source").
It also COLLECTS: every action the stories ask for is counted in a ledger (animation_requests.json) so the most
wanted missing animations can be built first.
"""
import json
import os
import re
import unicodedata


def _n(s):
    """one spelling for য় / ড় / ঢ় (they can be stored two ways in Unicode) - patterns and text alike"""
    return unicodedata.normalize("NFD", s or "")

# the actions this assistant knows how to name (the Match assistant decides what the engine can show)
VOCAB = {
    "sit": "sitting", "sit_down": "sits down", "stand": "standing", "stand_up": "stands up", "walk": "walks",
    "run": "runs / flees", "turn": "turns round", "look": "looks at someone / something", "look_back": "looks behind",
    "talk": "speaks", "whisper": "whispers", "scream": "screams / shouts", "nod": "nods", "point": "points",
    "knock": "knocks on a door", "open_door": "opens a door", "close_door": "closes a door", "enter": "comes in",
    "exit": "goes out / leaves", "tremble": "trembles", "stiff": "frozen stiff, cannot move",
    "hold_lantern": "holds a lantern", "swing_lantern": "swings a lantern", "cry": "cries", "fall": "falls / faints",
    "hug": "hugs", "grab": "grabs / holds someone", "ride_vehicle": "rides / drives a vehicle",
    "wear_helmet": "puts on / ties a helmet", "vehicle_crash": "a vehicle crashes", "train": "a train comes / goes",
    "fire": "a fire burns", "rain": "it rains / a storm", "lightning": "lightning", "breath": "breathing heard",
    "smell": "a smell", "stare": "stares without blinking", "figure_appears": "a ghost / shadow appears",
    "vanish": "vanishes", "eat": "eats / drinks", "climb": "climbs", "pray": "prays", "fight": "fights / hits",
    "write": "writes / reads", "dig": "digs", "light_lamp": "lights a lamp", "die": "dies",
}

# offline rules: (pattern, act, object). Bengali stems first, then English (the story's "en" text).
RULES = [
    (r"বসে পড়(ল|লেন|লাম)|sat down|sits down", "sit_down", None),
    (r"বসে (আছে|আছেন|ছিল|ছিলেন|রইল)|বসেছিল|sitting", "sit", None),
    (r"উঠে দাঁড়া|দাঁড়িয়ে পড়|উঠে পড়(ল|লেন)|stood up|stands up|got up", "stand_up", None),
    (r"দাঁড়িয়ে (আছে|আছেন|ছিল|রইল|রইলেন)|standing", "stand", None),
    (r"দৌড়|ছুট(ে|ল|লাম|ছে)|পালা(ও|ল|লেন|তে|চ্ছে)|\bran\b|\brun|fled|flee", "run", None),
    (r"হাঁট|এগিয়ে (গেল|এল|গেলেন|এলেন|যা)|পা বাড়া|walk", "walk", None),
    (r"পেছন ফির|পিছন ফির|পেছনে তাকা|পিছনে তাকা|ফিরে তাকা|looked back|look behind", "look_back", None),
    (r"ঘুরে দাঁড়া|turned (round|around)", "turn", None),
    (r"তাকা|চেয়ে (দেখ|রইল)|look", "look", None),
    (r"দরজায় (ধাক্কা|কড়া|টোকা)|কড়া নাড়|knock", "knock", "door"),
    (r"দরজা(টা)? (খুল|খোল)|opened the door|open the door", "open_door", "door"),
    (r"দরজা(টা)? (বন্ধ কর|লাগা)|closed the door|shut the door", "close_door", "door"),
    (r"ঢুক(ল|লেন|লাম|ে পড়)|ভেতরে এ(ল|লেন)|প্রবেশ|came in|entered", "enter", None),
    (r"বেরিয়ে (গেল|গেলেন|এল)|চলে (গেল|গেলেন)|went out|left the", "exit", None),
    (r"কাঁপ|থরথর|trembl|shiver", "tremble", None),
    (r"কাঠ হয়ে|জমে (গেছে|গেল)|পাথর হয়ে (গেছে|গেল)|অসাড়|নড়(ছে|ল) না|frozen|stiff|numb", "stiff", None),
    (r"চিৎকার|আর্তনাদ|চেঁচি|scream|shout", "scream", None),
    (r"ফিসফিস|whisper", "whisper", None),
    (r"ইশারা|আঙুল (তুলে|দিয়ে) দেখা|point", "point", None),
    (r"(লণ্ঠন|লন্ঠন|হ্যারিকেন)[^।?!]{0,12}(দোলা|নাড়)|swing(ing)? (a |the )?lantern", "swing_lantern", "lantern"),
    (r"লণ্ঠন|লন্ঠন|হ্যারিকেন|lantern", "hold_lantern", "lantern"),
    (r"কাঁদ|কান্না|\bcr(y|ied|ies)\b|weep", "cry", None),
    (r"পড়ে গেল|লুটিয়ে|অজ্ঞান|মূর্ছা|faint|fell down", "fall", None),
    (r"জড়িয়ে ধর|\bhug", "hug", None),
    (r"হাত (ধর|চেপে)|চেপে ধর|টেনে (নিল|ধর)|grab", "grab", None),
    (r"বাইক|মোটরসাইকেল|স্কুটার|পেছনে ওঠ|ওঠ পেছনে|গাড়ি চালা|স্টার্ট|ইঞ্জিন|সেলফ|bike|motorcycle|drive", "ride_vehicle", "vehicle"),
    (r"হেলমেট|helmet", "wear_helmet", "helmet"),
    (r"ব্রেক|গাড়িগুলো|অ্যাক্সিডেন্ট|দুর্ঘটনা|crash|accident", "vehicle_crash", "vehicle"),
    (r"ট্রেন|train", "train", "train"),
    (r"আগুন|চিতা(র)? (জ্বল|জ্বা)|\bfire\b|pyre", "fire", None),
    (r"বৃষ্টি|ঝোড়ো|ঝড়|rain|storm", "rain", None),
    (r"বাজ পড়|বিদ্যুৎ চমক|বজ্র|lightning|thunder", "lightning", None),
    (r"নিঃশ্বাস|শ্বাস|breath", "breath", None),
    (r"গন্ধ|smell", "smell", None),
    (r"পলক|blink", "stare", None),
    (r"আবির্ভূত|ছায়ামূর্তি|দেখা দিল|appeared|ghost|shadow", "figure_appears", None),
    (r"মিলিয়ে গেল|অদৃশ্য|উধাও|vanish|disappear", "vanish", None),
    (r"খা(চ্ছে|ল|লেন|ওয়া)|পান কর|\beat|drink", "eat", None),
    (r"চড়(ল|লেন)|বেয়ে ওঠ|climb", "climb", None),
    (r"প্রণাম|প্রার্থনা|মন্ত্র|pray", "pray", None),
    (r"মার(ল|লেন)|আঘাত|লড়াই|\bhit\b|fight|attack", "fight", None),
    (r"প্রদীপ (জ্বাল|ধরা)|বাতি জ্বাল|lit the lamp|light the lamp", "light_lamp", "lamp"),
    (r"মারা গেল|মৃত্যু হল|died|dead body|লাশ", "die", None),
]
# words that make a dialogue line describe what is happening NOW (so it can be shown)
PRESENT = r"(চ্ছেন|চ্ছে|চ্ছিস|চ্ছ|ছেন|ছিস|গেছে|গেছেন|হয়েছে|করছে|করছেন|আছে|আছেন|ছে কেন|ছেন কেন|এটা|\bis\b|\bare\b)"
PAST = r"(ছিল|ছিলেন|ছিলাম|তেন|তাম|পড়ত|করত|দেখেছিলাম|গেলে|হলে|দিয়েছিল|কষেনি|was|were|had|would)"
YOU = r"(তোর|তুই|তোকে|তোমার|তুমি|আপনি|আপনার|you)"
COMMAND = [(r"ওঠ পেছনে|পেছনে ওঠ", "ride_vehicle"), (r"আমার দিকে তাকা", "look"), (r"বেঁধে নে|পরে নে|পর\b", "wear_helmet"),
           (r"পালা(ও|!)|দৌড়(ও|া!)|run!", "run"), (r"বস(ো|ুন|!)", "sit"), (r"দাঁড়া(ও|ন)?!", "stand"),
           (r"দরজা খোল(ো|ুন)?", "open_door"), (r"চল(ো|ুন)?\b", "walk")]
EMOTION = [("terrif|panic|horrif|fear|scared|ভয়|আতঙ্ক", "scared"), ("sad|heavy heart|grief|দুঃখ", "sad"),
           ("angry|furious|রাগ", "angry"), ("mysterious|whisper|low", "mysterious"), ("surpris|shock|চমক", "surprised"),
           ("calm|soft|reminisc|natural|casual", "calm")]


def _strip_metaphor(text):
    text = _n(text)
    """'যেন পাথরের তৈরি দুটো শীতল দিঘি' is a comparison, not a pond on screen: drop such clauses"""
    t = re.sub(_n(r"যেন[^।?!,]*"), " ", text)
    t = re.sub(_n(r"\S+\s*(মতো|মত|সদৃশ)\b"), " ", t)
    return re.sub(r"\blike an? \w+|\bas if [^.?!,]*", " ", t)


def _emotion(feel, text):
    s = _n(f"{feel} {text}".lower())
    for pat, emo in EMOTION:
        if re.search(_n(pat), s):
            return emo
    return "calm"


def _name_in(text, cast):
    for c in cast:
        for nm in [c.get("name", "")] + list(c.get("aliases", [])):
            if nm and _n(nm.split()[0]) in _n(text):
                return c["id"]
    return None


def offline(lines, cast, place=""):
    """the rules way: no network, every decision explainable"""
    out = []
    for ln in lines:
        text = _strip_metaphor(f"{ln.get('text', '')} {ln.get('en', '')}")
        spk = ln.get("speaker") or "narrator"
        narr = spk == "narrator"
        lis = ln.get("listener")
        emo = _emotion(ln.get("feel", "") or ln.get("emotion", ""), ln.get("text", ""))
        doing, seen = [], set()
        for pat, act in COMMAND:
            if not narr and re.search(_n(pat), text):
                doing.append({"act": act, "who": lis, "mode": "command", "target": spk if act == "look" else None,
                              "object": None, "words": unicodedata.normalize("NFC", re.search(_n(pat), text).group(0))})
                seen.add(act)
        for pat, act, obj in RULES:
            m = re.search(_n(pat), text, re.I)
            if not m or act in seen:
                continue
            if act == "hold_lantern" and "swing_lantern" in seen:
                continue
            seen.add(act)
            clause = re.split(r"[।?!]", text[m.start():] + "।")[0]
            before = re.split(r"[।?!]", text[:m.start()])[-1]
            sentence = before + clause
            named = _name_in(sentence, cast)
            if narr:
                mode, who = "happens", named or ln.get("subject")
            elif act in ("stiff", "tremble") and named and not re.search(_n(PAST), sentence):
                mode, who = "happens", named               # "সায়ন তো অসাড়!" - a state of someone here, now
            elif re.search(_n(PAST), sentence) and not re.search(_n(PRESENT), sentence):
                mode, who = "mentioned", None
            elif re.search(_n(PRESENT), sentence):
                mode = "happens"
                who = named or (lis if re.search(_n(YOU), sentence) or act in ("stiff", "swing_lantern",
                                                                                             "hold_lantern") else spk)
            else:
                mode, who = "mentioned", None
            if act in ("rain", "lightning", "fire", "breath", "smell", "train", "vehicle_crash") and mode != "mentioned":
                who = None
            ongoing = mode == "happens" and not narr and act in ("stiff", "swing_lantern", "hold_lantern", "tremble",
                                                                    "stand", "sit", "fire", "rain")
            doing.append({"act": act, "who": who, "mode": mode, "target": None, "object": obj,
                          "words": unicodedata.normalize("NFC", m.group(0)),
                          "ongoing": ongoing})
        if not narr:
            doing.insert(0, {"act": "scream" if "!" in ln.get("text", "") and emo == "scared" else "talk", "who": spk,
                             "mode": "happens", "target": lis, "object": None, "words": "(বলছে)"})
        out.append({"i": ln["i"], "speaker": spk, "who": spk if not narr else None, "where": place, "emotion": emo,
                    "target": lis, "objects": sorted({d["object"] for d in doing if d.get("object")}), "doing": doing})
    return out


PROMPT = """You are the ACTION ASSISTANT of a Bengali horror-story animation engine. For EVERY numbered line below
say what really happens on screen. Return JSON: {{"lines":[{{"i":n,"emotion":"calm|scared|sad|angry|surprised|mysterious",
"doing":[{{"act":"<one of: {vocab}>","who":"<character id or null>","mode":"happens|command|mentioned",
"target":"<character id / door / null>","object":"<lantern / door / vehicle / ... or null>","words":"<the exact words that say it>",
"ongoing":true|false}}]}}]}}
Rules: "happens" only if the story says it happens NOW in this scene (narration, or a speaker describing what is going on
right now). "command" = someone is asked to do it (it is NOT shown as done). "mentioned" = past, plan, memory, rumour,
comparison ("যেন ... দিঘি" is a comparison, not a place). "words" MUST be copied exactly from that line - an action
whose words are not in the line is thrown away. Use only the act names given; if nothing fits write
"other:<short english description>" (never invent a nearer act). Do not add actions the text does not say.
Characters: {cast}
Place: {place}
Lines:
{lines}"""


def gemini(lines, cast, place, llm):
    vocab = ", ".join(VOCAB)
    ls = "\n".join(f"{ln['i']}. [{ln.get('speaker') or 'narrator'} -> {ln.get('listener') or '-'}] ({ln.get('feel', '')}) "
                   f"{ln.get('text', '')}" for ln in lines)
    cs = ", ".join(f"{c['id']} ({c.get('name', '')})" for c in cast)
    raw = llm(PROMPT.format(vocab=vocab, cast=cs, place=place, lines=ls))
    if not raw:
        return None
    data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    by_i = {int(x["i"]): x for x in data.get("lines", []) if "i" in x}
    out = []
    ids = {c["id"] for c in cast}

    def _bare(x):                                          # letters only: quotes / dashes / spaces never decide
        return re.sub(r"[\W_]+", "", _n(x), flags=re.U)
    for ln in lines:
        g = by_i.get(int(ln["i"]), {})
        spk = ln.get("speaker") or "narrator"
        doing, rejected = [], []
        line_bare = _bare(f"{ln.get('text', '')} {ln.get('en', '')}")
        for d in g.get("doing", []) or []:
            act = str(d.get("act", "")).strip()
            words = str(d.get("words", "")).strip()
            if act not in ("talk", "whisper", "scream") and (not _bare(words) or _bare(words) not in line_bare):
                rejected.append({"act": act, "words": words[:60]})       # Gemini named words the line does not have:
                continue                                                 # an invented action is never animated
            if act not in VOCAB and not act.startswith("other:"):
                act = "other:" + act
            who = d.get("who") if d.get("who") in ids else None
            mode = d.get("mode") if d.get("mode") in ("happens", "command", "mentioned") else "mentioned"
            doing.append({"act": act, "who": who, "mode": mode, "target": d.get("target"), "object": d.get("object"),
                          "words": str(d.get("words", ""))[:80], "ongoing": bool(d.get("ongoing"))})
        if spk != "narrator" and not any(d["act"] in ("talk", "whisper", "scream") for d in doing):
            doing.insert(0, {"act": "talk", "who": spk, "mode": "happens", "target": ln.get("listener"), "object": None,
                             "words": "(বলছে)"})
        out.append({"i": ln["i"], "speaker": spk, "who": spk if spk != "narrator" else None, "where": place,
                    "emotion": g.get("emotion") or _emotion(ln.get("feel", ""), ln.get("text", "")),
                    "target": ln.get("listener"), "objects": sorted({str(d["object"]) for d in doing if d.get("object")}),
                    "doing": doing, "rejected": rejected})
    return out


def analyse(lines, cast, place="", llm=None, log=print):
    """lines: [{"i", "speaker" (id or "narrator"), "listener", "text", "en"?, "feel"/"emotion"}]
    cast: [{"id", "name", "aliases"}]. Returns {"source", "lines"}."""
    if llm:
        try:
            res = gemini(lines, cast, place, llm)
            if res:
                return {"source": "gemini", "lines": res}
        except Exception as e:
            log(f"  action assistant: Gemini answer unusable ({str(e)[:100]}) - offline rules used")
    return {"source": "offline-rules", "lines": offline(lines, cast, place)}


def collect(ledger_path, analysed):
    """count every act the stories ask for (so the most wanted animations are built first)"""
    try:
        led = json.load(open(ledger_path, encoding="utf-8"))
    except Exception:
        led = {}
    for ln in analysed:
        for d in ln["doing"]:
            if d["mode"] != "mentioned":
                led[d["act"]] = led.get(d["act"], 0) + 1
    os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(led.items(), key=lambda kv: -kv[1])), f, ensure_ascii=False, indent=1)
    return led
