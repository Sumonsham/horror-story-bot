"""MATCH ASSISTANT (assistant 3 of 3) - role: the honest judge between the story and the video.

For every action the Action assistant found, it decides what the engine shows and says so:
  MATCH       the engine has this animation and shows exactly it
  SUBSTITUTE  the engine does not have it; the CLOSEST honest replacement is shown and the report says what
              is shown instead (e.g. "faints" -> "cowers in fear"; no tears -> sad face, head down)
  MISSING     nothing honest can be shown (a motorbike, a train, eating...) - nothing fake is drawn; the line
              plays over the place and the characters as they are, and the report lists it
  COMMAND     someone is only ASKED to do it - the story does not say it was done, so it is not shown done
              (the speaker gestures towards the listener)
  MENTIONED   past / plan / memory / comparison - nothing to show
  SOUND       heard, not seen (breathing, a knock with nobody visible) - a sound effect
  NOT_VISUAL  a smell, a thought - nothing to show
It also checks the place (door needed for a knock, fire only where there is a fire) and COLLECTS every
MISSING / SUBSTITUTE into the ledger, so the next animations to build are known.
Nothing is ever reported as MATCH unless the renderer really draws it.
"""
import json
import os

import location_library as L

# act -> (status, engine op or None, what is shown - Bengali)
CAPS = {
    "talk": ("MATCH", "talk", "কথা বলছে - ঠোঁট আসল গলার আওয়াজের সাথে নড়ছে, শ্রোতা তার দিকে তাকিয়ে"),
    "whisper": ("MATCH", "talk", "ফিসফিস করে বলছে (ঠোঁট আওয়াজের সাথে)"),
    "scream": ("MATCH", "scream", "ভয়ে চেঁচিয়ে বলছে - ভয়ের মুখ, ঠোঁট আওয়াজের সাথে"),
    "sit": ("MATCH", "pose_sit", "বসে আছে"),
    "sit_down": ("MATCH", "sit_down", "বসে পড়ছে"),
    "stand": ("MATCH", "pose_stand", "দাঁড়িয়ে আছে"),
    "stand_up": ("MATCH", "stand_up", "উঠে দাঁড়াচ্ছে"),
    "walk": ("MATCH", "walk", "হেঁটে যাচ্ছে (পা মাটিতে, হাঁটার চক্র)"),
    "run": ("MATCH", "run", "দৌড়চ্ছে (দৌড়ের চক্র, শরীর সামনে ঝুঁকে)"),
    "turn": ("MATCH", "turn", "ঘুরে দাঁড়াচ্ছে"),
    "look": ("MATCH", "look", "তাকাচ্ছে (মাথা + চোখের মণি লক্ষ্যের দিকে)"),
    "look_back": ("MATCH", "look_back", "পেছন ফিরে তাকাচ্ছে - শরীর ঘোরে, মুখ পাশ থেকে পেছনের দিকে"),
    "nod": ("MATCH", "nod", "মাথা নাড়ছে"),
    "point": ("MATCH", "point", "আঙুল তুলে দেখাচ্ছে"),
    "knock": ("MATCH", "knock", "দরজায় ধাক্কা - দরজা কেঁপে ওঠে + ধাক্কার শব্দ"),
    "open_door": ("MATCH", "open_door", "দরজা খুলছে (বাইরে অন্ধকার/বৃষ্টি দেখা যায়)"),
    "close_door": ("MATCH", "close_door", "দরজা বন্ধ হচ্ছে"),
    "enter": ("MATCH", "enter", "ভেতরে/ফ্রেমে ঢুকছে (হেঁটে)"),
    "exit": ("MATCH", "exit", "বেরিয়ে যাচ্ছে (হেঁটে ফ্রেমের বাইরে)"),
    "tremble": ("MATCH", "tremble", "ভয়ে কাঁপছে"),
    "stiff": ("MATCH", "stiff", "কাঠের মতো শক্ত হয়ে দাঁড়িয়ে - হাত সোজা, নড়াচড়া নেই, চোখে পলক নেই"),
    "hold_lantern": ("MATCH", "hold_lantern", "হাতে লণ্ঠন (আলো সাথে সাথে চলে)"),
    "swing_lantern": ("MATCH", "swing_lantern", "লণ্ঠন দোলাচ্ছে (আলোও দোলে)"),
    "stare": ("MATCH", "stare", "একদৃষ্টে তাকিয়ে - চোখে পলক পড়ে না"),
    "figure_appears": ("MATCH", "figure", "দূরে এক ছায়ামূর্তি দেখা দেয়"),
    "vanish": ("MATCH", "vanish", "মিলিয়ে যায় (ধীরে স্বচ্ছ হয়ে)"),
    "rain": ("MATCH", "rain", "বৃষ্টি / ঝড়"),
    "lightning": ("MATCH", "lightning", "বিদ্যুৎ চমক + বাজের শব্দ"),
    "fire": ("MATCH", "fire", "আগুন জ্বলছে"),
    "cry": ("SUBSTITUTE", "sad", "চোখের জল আঁকা নেই - দুঃখের মুখ, মাথা নিচু দেখানো হয়েছে"),
    "fall": ("SUBSTITUTE", "cower", "পড়ে যাওয়া/অজ্ঞান হওয়ার অ্যানিমেশন নেই - ভয়ে কুঁকড়ে যাওয়া দেখানো হয়েছে"),
    "hug": ("SUBSTITUTE", "reach", "জড়িয়ে ধরা নেই - কাছে গিয়ে হাত বাড়ানো দেখানো হয়েছে"),
    "grab": ("SUBSTITUTE", "reach", "হাত ধরা নেই - হাত বাড়ানো দেখানো হয়েছে"),
    "wear_helmet": ("SUBSTITUTE", "hand_to_head", "হেলমেট আঁকা নেই - মাথায় হাত তোলা দেখানো হয়েছে"),
    "breath": ("SOUND", "sfx_breath", "নিঃশ্বাসের শব্দ (দেখার কিছু নেই)"),
    "smell": ("NOT_VISUAL", None, "গন্ধ - ছবিতে দেখানো যায় না"),
    "ride_vehicle": ("MISSING", None, "বাইক/গাড়ি আঁকা নেই - কিছু দেখানো হয়নি"),
    "vehicle_crash": ("MISSING", None, "গাড়ি দুর্ঘটনা আঁকা নেই - কিছু দেখানো হয়নি"),
    "train": ("MISSING", None, "ট্রেন আঁকা নেই (স্টেশন আছে, ট্রেন নেই)"),
    "eat": ("MISSING", None, "খাওয়া/পান করার অ্যানিমেশন নেই"),
    "climb": ("MISSING", None, "চড়ার অ্যানিমেশন নেই"),
    "pray": ("MISSING", None, "প্রার্থনার অ্যানিমেশন নেই"),
    "fight": ("MISSING", None, "মারামারির অ্যানিমেশন নেই"),
    "write": ("MISSING", None, "লেখা/পড়ার অ্যানিমেশন নেই"),
    "dig": ("MISSING", None, "খোঁড়ার অ্যানিমেশন নেই"),
    "die": ("MISSING", None, "মৃত্যু/দেহ দেখানো হয় না"),
    "light_lamp": ("SUBSTITUTE", "hold_lantern", "প্রদীপ জ্বালানো নেই - হাতে জ্বলন্ত লণ্ঠন দেখানো হয়েছে"),
}
STATUS_BN = {"MATCH": "মিলেছে", "SUBSTITUTE": "কাছাকাছি বিকল্প", "MISSING": "নেই (দেখানো হয়নি)", "COMMAND": "শুধু বলা হয়েছে",
             "MENTIONED": "শুধু উল্লেখ", "SOUND": "শুধু শব্দ", "NOT_VISUAL": "দেখানোর নয়", "REACTION": "স্বাভাবিক প্রতিক্রিয়া"}


def judge(analysed, location, cast_ids):
    """analysed: Action assistant lines; returns {"lines": [...], "counts": {...}, "ops": [...]}"""
    feats = L.LOCATIONS.get(location, {}).get("features", [])
    out, ops, counts = [], [], {}
    for ln in analysed:
        items = []
        for d in ln["doing"]:
            act, mode = d["act"], d["mode"]
            status, op, shown = CAPS.get(act, ("MISSING", None, f"এই অ্যানিমেশন নেই ({act}) - কিছু দেখানো হয়নি"))
            who = d.get("who") if d.get("who") in cast_ids else None
            if mode == "mentioned":
                status, op, shown = "MENTIONED", None, "শুধু কথায় উল্লেখ (অতীত/পরিকল্পনা/তুলনা) - দেখানোর কিছু নেই"
            elif mode == "command":
                status, op = "COMMAND", None
                shown = "শুধু করতে বলা হয়েছে - গল্পে করা হয়েছে বলা নেই, তাই করা দেখানো হয়নি (বক্তা শ্রোতার দিকে হাত দেখায়)"
            elif op in ("knock", "open_door", "close_door") and "door" not in feats:
                status, op, shown = "SUBSTITUTE", "sfx_knock" if op == "knock" else None, \
                    "এই জায়গায় দরজা নেই - শুধু ধাক্কার শব্দ" if op == "knock" else "এই জায়গায় দরজা নেই - দেখানো হয়নি"
            elif op == "knock" and who is None:
                status, shown = "MATCH", "দরজায় বাইরে থেকে ধাক্কা - দরজা কেঁপে ওঠে + শব্দ (কে ধাক্কা দিচ্ছে গল্পে দেখা যায় না)"
            elif op == "fire" and "pyre_fire" not in feats:
                status, op, shown = "SUBSTITUTE", "hold_lantern" if who else None, "এখানে আগুনের দৃশ্য নেই - লণ্ঠন/প্রদীপের আলো"
            elif op in ("stiff", "tremble", "swing_lantern", "hold_lantern", "look", "look_back", "walk", "run", "enter",
                        "exit", "stand_up", "sit_down", "reach", "cower", "sad", "hand_to_head", "point", "stare") and who is None:
                status, op, shown = "MISSING", None, f"কে করছে বোঝা যায়নি - দেখানো হয়নি ({act})"
            if status in ("MATCH", "SUBSTITUTE", "SOUND") and op:
                ops.append({"line": ln["i"], "op": op, "who": who, "target": d.get("target"),
                            "ongoing": bool(d.get("ongoing")), "act": act})
            elif status == "COMMAND" and ln.get("who") and not any(o["line"] == ln["i"] and o["act"] == "gesture" for o in ops):
                ops.append({"line": ln["i"], "op": "point", "who": ln["who"], "target": ln.get("target"), "ongoing": False,
                            "act": "gesture"})
            counts[status] = counts.get(status, 0) + 1
            items.append({"act": act, "who": who, "mode": mode, "words": d.get("words", ""), "status": status,
                          "status_bn": STATUS_BN[status], "shown_bn": shown})
        out.append({"i": ln["i"], "speaker": ln["speaker"], "emotion": ln["emotion"], "items": items})
    return {"lines": out, "counts": counts, "ops": ops}


def add_reactions(result, reactions):
    """the planner's natural reactions (a head turns to a knock) are listed too, marked REACTION - never hidden"""
    for r in reactions:
        for ln in result["lines"]:
            if ln["i"] == r["line"]:
                ln["items"].append({"act": r["act"], "who": r["who"], "mode": "reaction", "words": "",
                                    "status": "REACTION", "status_bn": STATUS_BN["REACTION"], "shown_bn": r["why"]})
                result["counts"]["REACTION"] = result["counts"].get("REACTION", 0) + 1
    return result


def collect(ledger_path, result):
    try:
        led = json.load(open(ledger_path, encoding="utf-8"))
    except Exception:
        led = {"MISSING": {}, "SUBSTITUTE": {}}
    for ln in result["lines"]:
        for it in ln["items"]:
            if it["status"] in ("MISSING", "SUBSTITUTE"):
                led.setdefault(it["status"], {})
                led[it["status"]][it["act"]] = led[it["status"]].get(it["act"], 0) + 1
    os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(led, f, ensure_ascii=False, indent=1)
    return led


def report_bn(scenes):
    """a readable Bengali report: per scene the place, per line every action and what the video shows"""
    out = ["# গল্প ↔ ভিডিও মিলের রিপোর্ট", ""]
    tot = {}
    for sc in scenes:
        loc = sc["location"]
        out.append(f"## দৃশ্য {sc['id']}: {L.LOCATIONS[loc]['bn']} ({loc}) - জায়গা: {loc_status(loc, sc)}")
        out.append(f"(Action assistant: {sc['action_source']}, Location assistant: {sc['location_source']})")
        for ln in sc["match"]["lines"]:
            txt = next((l["text"] for l in sc["lines"] if l["i"] == ln["i"]), "")
            out.append(f"- লাইন {ln['i']} [{ln['speaker']}, {ln['emotion']}]: {txt}")
            for it in ln["items"]:
                out.append(f"    - {it['act']} ({it['who'] or '-'}, {it['mode']}): **{it['status_bn']}** - {it['shown_bn']}")
        for k, v in sc["match"]["counts"].items():
            tot[k] = tot.get(k, 0) + v
        out.append("")
    out.append("## মোট")
    out += [f"- {STATUS_BN[k]} ({k}): {v}" for k, v in sorted(tot.items())]
    return "\n".join(out), tot


def loc_status(loc, sc):
    r = sc.get("location_result", {})
    return f"{r.get('status', 'MATCH')} - {r.get('reason', '')}"
