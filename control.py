"""V8 control state - the settings you change from Telegram.

The Telegram poller (telegram-poll.yml, every ~15 minutes) is the ONLY writer; it keeps one small file,
control.json, on its own branch `bot-state` (so it never collides with the story runs' saves on main).
The story run only READS it. If the file cannot be read, the safe defaults below are used - which are exactly
how the bot worked before V8 (everything on), plus AUTO_DISCOVER.
"""
import copy
import json
import os
import subprocess

STATE_BRANCH = "bot-state"
FILE = "control.json"
TOPIC_MODES = ("AUTO_DISCOVER", "TRUE_INCIDENT_PRIORITY", "TRENDING_TOPIC_PRIORITY", "USER_SUPPLIED", "MIXED")

DEFAULT = {
    "autodiscover": True,
    "topic_mode": "AUTO_DISCOVER",
    "autopublish": True,
    "destinations": {"youtube": True, "facebook": True, "podcast": True},
    "paused": None,
    "user_topics": [],
    "handled": [],
    "updated": "",
}

_CACHE = {}


def _merge(base, got):
    out = copy.deepcopy(base)
    if isinstance(got, dict):
        for k, v in got.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
    return out


def read_raw(repo_dir="."):
    """control.json: a local copy (the poller's checkout, or CONTROL_FILE), else the bot-state branch via git."""
    local = os.environ.get("CONTROL_FILE") or ""
    for p in (local, os.path.join(repo_dir, "state", FILE)):
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    if os.environ.get("MOCK") == "1" or os.environ.get("GITHUB_ACTIONS") != "true":
        return {}
    try:
        subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", STATE_BRANCH], cwd=repo_dir,
                       capture_output=True, timeout=60)
        r = subprocess.run(["git", "show", f"FETCH_HEAD:{FILE}"], cwd=repo_dir, capture_output=True, text=True,
                           timeout=30)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
    except Exception:
        return {}


def get(repo_dir=".", fresh=False):
    """The settings, with GitHub Variables as the final word (AUTO_DISCOVER=0, TOPIC_MODE=...)."""
    if "s" in _CACHE and not fresh:
        return _CACHE["s"]
    s = _merge(DEFAULT, read_raw(repo_dir))
    if os.environ.get("AUTO_DISCOVER", "").strip() == "0":
        s["autodiscover"] = False
    tm = os.environ.get("TOPIC_MODE", "").strip().upper()
    if tm in TOPIC_MODES:
        s["topic_mode"] = tm
    if s.get("topic_mode") not in TOPIC_MODES:
        s["topic_mode"] = "AUTO_DISCOVER"
    _CACHE["s"] = s
    return s


def dest_on(name, repo_dir="."):
    """Is this destination switched on? (/youtube_off, /facebook_off, /podcast_off, /autopublish_off)"""
    s = get(repo_dir)
    if not s.get("autopublish", True):
        return False
    return bool((s.get("destinations") or {}).get(name, True))


def handled_ids(repo_dir="."):
    return {int(x) for x in (get(repo_dir).get("handled") or []) if str(x).lstrip("-").isdigit()}


# =====================================================================================================
# THE TELEGRAM POLLER  (python control.py poll  - run by .github/workflows/telegram-poll.yml)
# Reads your messages every ~15 minutes WITHOUT consuming them (no 'offset'), so the story runs still see
# your stories, pictures and voice clips exactly as before. Only YOUR chat (TELEGRAM_CHAT_ID) is obeyed.
# =====================================================================================================
import datetime as _dt
import re as _re
import sys as _sys

_IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
_BN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
WORKFLOW = "horror-story.yml"

HELP_BN = """🤖 Telegram কন্ট্রোল সেন্টার (উত্তর আসে ~১৫ মিনিটের মধ্যে):
আগের সব কমান্ড আগের মতোই: অবস্থা · বন্ধ / বন্ধ ভূত ৩ দিন · চালু · বাদ ভূত ১ · ১ বদলাও / ২ বদলাও · ধাঁচ (অডিও) · ধাঁচ মুছে দাও · ধাঁচ আবার শেখো · আমার গলা মুছে দাও
নতুন:
/status - সব খবর · /calendar - কখন কী যাবে · /destinations - কোথায় কোথায় প্রকাশ হয়
/autodiscover_on · /autodiscover_off - bot নিজে বিষয় খুঁজবে কি না (ডিফল্ট: চালু)
/discover_now - এখনই বিষয় খুঁজে তালিকা পাঠাও (ভিডিও নয়)
/topic_mode - AUTO_DISCOVER / TRUE_INCIDENT_PRIORITY / TRENDING_TOPIC_PRIORITY / USER_SUPPLIED / MIXED
/topic <বিষয় বা লিংক> - আপনার পছন্দের বিষয় (ঐচ্ছিক) · /topic_queue - লাইনে কী আছে
/research_sources - শেষ গল্পের উৎস ও যাচাই
/podcast_status · /rss_status · /spotify_status · /apple_podcasts_status
/autopublish_on · /autopublish_off · /youtube_on · /youtube_off · /facebook_on · /facebook_off · /podcast_on · /podcast_off
/retry_publish - শেষ ভিডিও যেখানে যায়নি সেখানে আবার · /cancel_job - চলমান কাজ থামাও
বাংলাতেও বলা যায়: "নিজে সত্য ঘটনা খুঁজে গল্প বানাও", "ট্রেন্ডিং হরর বিষয় খুঁজে তৈরি করো", "আজকের গল্প সব প্ল্যাটফর্মে প্রকাশ করো", "Spotify আর Apple Podcasts-এর অবস্থা দেখাও\""""

TOGGLES = {"/autodiscover_on": ("autodiscover", True), "/autodiscover_off": ("autodiscover", False),
           "/autopublish_on": ("autopublish", True), "/autopublish_off": ("autopublish", False),
           "/youtube_on": ("youtube", True), "/youtube_off": ("youtube", False),
           "/facebook_on": ("facebook", True), "/facebook_off": ("facebook", False),
           "/podcast_on": ("podcast", True), "/podcast_off": ("podcast", False)}

NATURAL = [  # (pattern, command) - natural Bengali / English sentences
    (r"সত্য\s*ঘটনা.*(খুঁজ|বানা|তৈরি)", "/discover_true"),
    (r"ট্রেন্ড.*(খুঁজ|বানা|তৈরি)|trending", "/discover_trend"),
    (r"(নিজে|নতুন).*(গল্প|বিষয়).*(খুঁজ|তৈরি|বানা)", "/discover_now"),
    (r"সব\s*প্ল্যাটফর্মে.*প্রকাশ", "/publish_all"),
    (r"spotify|স্পটিফাই|apple|অ্যাপল", "/podcast_status"),
    (r"পডকাস্ট.*(অবস্থা|খবর)", "/podcast_status"),
    (r"(কবে|কখন).*(ভিডিও|গল্প)|ক্যালেন্ডার|সময়সূচি", "/calendar"),
]
LEGACY_STATUS = ("অবস্থা", "/অবস্থা", "status", "খবর")
LEGACY_HELP = ("সাহায্য", "/help", "help", "কমান্ড")
LEGACY_PAUSE = ("বন্ধ", "/pause", "pause", "/বন্ধ")
LEGACY_RESUME = ("চালু", "/resume", "resume", "/চালু")


def _jl(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def parse(text):
    """message -> (command, argument) or None. Old Bengali commands that only the story run can do ('বাদ ...',
    '১ বদলাও', 'ধাঁচ ...', 'গলা মুছে দাও') return None, so they keep working exactly as before."""
    t = str(text or "").strip()
    low = t.lower().translate(_BN).rstrip("?।!. ")
    if not low:
        return None
    first = low.split()[0].split("@")[0]
    if first.startswith("/"):
        if first in TOGGLES or first in ("/discover_now", "/topic_queue", "/research_sources", "/podcast_status",
                                         "/rss_status", "/spotify_status", "/apple_podcasts_status", "/destinations",
                                         "/calendar", "/status", "/retry_publish", "/cancel_job", "/help",
                                         "/style_refresh"):
            return first, t[len(first):].strip()
        if first == "/topic_mode":
            return first, t.split(None, 1)[1].strip().upper() if len(t.split()) > 1 else ""
        if first in ("/topic", "/topic_add"):
            return "/topic", t.split(None, 1)[1].strip() if len(t.split()) > 1 else ""
    if any(low == w or low.startswith(w + " ") for w in LEGACY_STATUS):
        return "/status", ""
    if any(low == w for w in LEGACY_HELP):
        return "/help", ""
    for w in LEGACY_PAUSE:
        if low == w or low.startswith(w + " "):
            rest = low[len(w):]
            if any(x in rest for x in ("কার্টুন", "cartoon")):
                return None                            # (the cartoon bot's own command)
            n = _re.search(r"\d+", rest)
            return "/pause", n.group() if n else ""
    for w in LEGACY_RESUME:
        if low == w or low.startswith(w + " "):
            if any(x in low for x in ("কার্টুন", "cartoon")):
                return None
            return "/resume", ""
    if len(t) <= 200:
        for rx, cmd in NATURAL:
            if _re.search(rx, low, _re.I):
                return cmd, ""
    return None


def _tg(tok, chat, text):
    try:
        requests_ = __import__("requests")
        requests_.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                       data={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"})
    except Exception as e:
        print("telegram send failed:", str(e)[:100])


def _gh(method, path, **kw):
    import requests as rq
    tok, repo = os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", "")
    if not (tok and repo):
        return None
    return rq.request(method, f"https://api.github.com/repos/{repo}{path}", timeout=30,
                      headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}, **kw)


def _dispatch(mode):
    r = _gh("POST", f"/actions/workflows/{WORKFLOW}/dispatches", json={"ref": os.environ.get("MAIN_BRANCH", "main"),
                                                                       "inputs": {"mode": mode}})
    return bool(r is not None and r.status_code in (200, 204))


def _fmt_dt(iso):
    try:
        return _dt.datetime.fromisoformat(str(iso)).astimezone(_IST).strftime("%d %b, %I:%M %p")
    except Exception:
        return str(iso or "")[:16]


def status_text(s, root="."):
    hist = _jl(os.path.join(root, "history.json"), [])
    last = hist[-1] if hist else {}
    paused = s.get("paused")
    lines = ["📋 ভূতের bot - অবস্থা",
             ("⏸️ বন্ধ আছে" + (f" ({str(paused.get('until'))[:10]} পর্যন্ত)" if paused.get("until") not in (None, "forever")
                              else "") if paused else "▶️ চালু আছে"),
             f"🧭 নিজে বিষয় খোঁজা: {'চালু' if s.get('autodiscover', True) else 'বন্ধ'} · মোড: {s.get('topic_mode')}",
             dest_text(s)]
    if last:
        lines.append(f"🎬 শেষ গল্প: {_re.sub(r'[|].*$', '', str(last.get('title', '')))[:60].strip()} "
                     f"({_fmt_dt(last.get('date'))}) - FB {'✓' if last.get('facebook') else '✗'} · "
                     f"YT {'✓' if last.get('youtube') else '✗'}")
    led = (_jl(os.path.join(root, "assets", "discovery_ledger.json"), {}) or {}).get("entries") or []
    if led:
        e = led[-1]
        lines.append(f"🔎 শেষ বিষয়-সন্ধান: {_fmt_dt(e.get('at'))} · {e.get('pool_size', 0)}টি বিষয় · "
                     f"শ্রেণি: {e.get('story_class') or '-'}")
    u = _jl(os.path.join(root, "assets", "tts_usage.json"), {})
    if isinstance(u, dict) and u.get("used") is not None:
        lines.append(f"🎙️ Gemini গলা আজ: {u.get('used')} request · Chirp এই মাসে: {(u.get('chirp') or {}).get('chars', 0)} অক্ষর")
    q = [t for t in (s.get("user_topics") or [])]
    if q:
        lines.append(f"📝 আপনার দেওয়া বিষয়: {len(q)}টা")
    lines.append("💰 ZERO_COST চালু - কোনো paid API ডাকা হয় না")
    return "\n".join(lines)


def dest_text(s):
    d = s.get("destinations") or {}
    on = lambda k: "✓" if s.get("autopublish", True) and d.get(k, True) else "✗"
    return (f"📤 প্রকাশ: {'স্বয়ংক্রিয়' if s.get('autopublish', True) else 'বন্ধ (ভিডিও তৈরি হবে, প্রকাশ নয়)'} · "
            f"YouTube {on('youtube')} · Facebook {on('facebook')} · Podcast/RSS/Spotify/Apple {on('podcast')} · "
            "Telegram চ্যানেল ✓ · ওয়েবসাইট ✓")


def calendar_text():
    now = _dt.datetime.now(_IST)
    lines = ["🗓️ সময়সূচি (ভারতের সময়; শুরু করে cron-job.org, GitHub-এর backup ঘড়ি ৭৫ মিনিট পরে):",
             "• রাত ২টো - দিনের দুটো গল্প লেখা", "• সকাল ১০টা - দিনের টিজার",
             "• দুপুর ২টো - গল্প ১ (YouTube + Facebook + Reel/Short + Podcast)",
             "• রাত ৮টা - গল্প ২ (একই সব জায়গায়)", "• শনিবার রাত ১০টা - YouTube Live",
             "• অমাবস্যার রাত - রাত ৮টার গল্পই অমাবস্যা স্পেশাল",
             "⚠️ GitHub-এর ফ্রি ঘড়ি কখনও দেরি করতে পারে - তাই নির্দিষ্ট মিনিটে চলার নিশ্চয়তা নেই।"]
    for add in range(0, 2):
        d = (now + _dt.timedelta(days=add)).date()
        for h in (14, 20):
            t = _dt.datetime(d.year, d.month, d.day, h, tzinfo=_IST)
            if t > now:
                lines.append(f"⏭️ পরের গল্প: {t.strftime('%d %b, %I %p')}")
                return "\n".join(lines)
    return "\n".join(lines)


def podcast_text(root=".", which="all"):
    ps = _jl(os.path.join(root, "state", "podcast_status.json"), None) or \
        _jl(os.path.join(root, "assets", "podcast_status.json"), {}) or {}
    eps = _jl(os.path.join(root, "docs", "podcast.json"), []) or []
    base = ""
    try:
        base = open(os.path.join(root, "docs", "live.txt"), encoding="utf-8").read().strip()
    except Exception:
        pass
    feed = (base.rstrip("/") + "/podcast.xml") if base else "(ঠিকানা এখনও জানা নেই)"
    last = eps[-1] if eps else {}
    lines = [f"🎧 Podcast: {len(eps)}টি পর্ব · RSS: {feed}"]
    if last:
        lines.append(f"শেষ পর্ব: {str(last.get('title', ''))[:70]} ({str(last.get('date', ''))[:16]})")
    rss = ps.get("rss") or {}
    if which in ("all", "rss"):
        lines.append(f"📡 RSS: {rss.get('status', 'UNKNOWN')}" + (f" · যাচাই {_fmt_dt(rss.get('checked'))}" if rss.get("checked") else "")
                     + (f" · {rss.get('note')}" if rss.get("note") else ""))
    if which in ("all", "spotify"):
        sp = ps.get("spotify") or {}
        lines.append(f"🟢 Spotify: {sp.get('status', 'FEED_READY' if eps else 'UNKNOWN')}" + (f" · {sp.get('url')}" if sp.get("url") else "")
                     + (f" · {sp.get('note')}" if sp.get("note") else ""))
    if which in ("all", "apple"):
        ap = ps.get("apple") or {}
        lines.append(f"🍎 Apple Podcasts: {ap.get('status', 'FEED_READY' if eps else 'UNKNOWN')}" + (f" · {ap.get('url')}" if ap.get("url") else "")
                     + (f" · {ap.get('note')}" if ap.get("note") else ""))
    lines.append("(Spotify/Apple নিজেরাই RSS পড়ে নেয়; RSS-এ থাকা মানেই ওখানে এসে গেছে বলা হয় না - যাচাই করা অবস্থাই দেখানো হয়)")
    return "\n".join(lines)


def research_text(root="."):
    led = (_jl(os.path.join(root, "assets", "discovery_ledger.json"), {}) or {}).get("entries") or []
    sel = [e for e in led if e.get("selected")]
    if not sel:
        return "🔎 এখনও কোনো বিষয়-সন্ধানের রেকর্ড নেই।"
    e = sel[-1]
    c = next((x for x in e.get("candidates") or [] if x.get("id") == e.get("selected")), {})
    lines = [f"🔎 শেষ বেছে নেওয়া বিষয় ({_fmt_dt(e.get('at'))}): {c.get('title', '')[:90]}",
             f"শ্রেণি: {e.get('story_class')} · উৎস: {c.get('source') or c.get('kind')}",
             f"স্কোর: {json.dumps(c.get('scores') or {}, ensure_ascii=False)}"]
    for u in (e.get("sources") or [])[:5]:
        lines.append(f"• {u}")
    if not e.get("sources"):
        lines.append("(যাচাই করা উৎস-পাতা নেই - তাই এটি কাল্পনিক গল্প হিসেবে চিহ্নিত)")
    if e.get("claim_kinds"):
        lines.append("দাবির ধরন: " + ", ".join(f"{k} {v}" for k, v in e["claim_kinds"].items()))
    return "\n".join(lines)


def topic_queue_text(s, root="."):
    used = set((_jl(os.path.join(root, "assets", "topic_queue.json"), {}) or {}).get("used_user") or [])
    q = [t for t in s.get("user_topics") or [] if t.get("id") not in used]
    lines = [f"📝 আপনার দেওয়া বিষয় লাইনে: {len(q)}টা"] + [f"  {i + 1}. {str(t.get('text'))[:70]}" for i, t in enumerate(q[:8])]
    led = (_jl(os.path.join(root, "assets", "discovery_ledger.json"), {}) or {}).get("entries") or []
    if led:
        top = [c for c in (led[-1].get("candidates") or []) if c.get("eligible")][:5]
        if top:
            lines.append("🧭 শেষ খোঁজে সেরা বিষয়গুলো:")
            lines += [f"  • {str(c.get('title'))[:70]} ({(c.get('scores') or {}).get('total')})" for c in top]
    lines.append("নতুন বিষয় দিতে: /topic <বিষয়>  (না দিলেও bot নিজে খুঁজে নেয়)")
    return "\n".join(lines)


def handle(cmd, arg, s, root=".", uid=None):
    """apply one command to the state s; returns the Bengali answer"""
    today = _dt.datetime.now(_IST).date().isoformat()
    if cmd == "/help":
        return HELP_BN
    if cmd == "/status":
        return status_text(s, root)
    if cmd in TOGGLES:
        key, val = TOGGLES[cmd]
        if key in ("autodiscover", "autopublish"):
            s[key] = val
        else:
            s.setdefault("destinations", {})[key] = val
        if key == "autopublish" and val is False:
            return "⏸️ স্বয়ংক্রিয় প্রকাশ বন্ধ - ভিডিও তৈরি হবে, কিন্তু কোথাও প্রকাশ হবে না। চালু করতে: /autopublish_on\n" + dest_text(s)
        return "✅ ঠিক আছে।\n" + (dest_text(s) if key not in ("autodiscover",) else
                                 f"🧭 নিজে বিষয় খোঁজা এখন {'চালু' if val else 'বন্ধ (আগের নিয়মে বিষয় বাছা হবে)'}")
    if cmd == "/style_refresh":                       # (the story run does it - it reads the same message)
        return "🔄 ঠিক আছে - পরের run-এ প্রতিটা নমুনা গল্পের ধাঁচ নতুন করে তৈরি হবে, হলে Telegram-এ জানাবে।"
    if cmd == "/destinations":
        return dest_text(s)
    if cmd == "/calendar":
        return calendar_text()
    if cmd == "/topic_mode":
        if arg in TOPIC_MODES:
            s["topic_mode"] = arg
            return f"✅ বিষয়-মোড: {arg}"
        return f"এখনকার মোড: {s.get('topic_mode')}\nবদলাতে লিখুন, যেমন: /topic_mode TRUE_INCIDENT_PRIORITY\nমোড: " + ", ".join(TOPIC_MODES)
    if cmd == "/topic":
        if not arg:
            return "বিষয়টা লিখুন, যেমন: /topic পুরুলিয়ার পরিত্যক্ত রেলস্টেশন"
        s.setdefault("user_topics", []).append({"id": uid, "text": arg[:500], "at": today})
        s["user_topics"] = s["user_topics"][-30:]
        return f"✅ বিষয় লাইনে রাখলাম: {arg[:80]}\nপরের গল্পে এটি আগে বিবেচনা হবে (উৎস না মিললে এটি কাল্পনিক গল্প হিসেবে চিহ্নিত হবে)।"
    if cmd == "/topic_queue":
        return topic_queue_text(s, root)
    if cmd == "/research_sources":
        return research_text(root)
    if cmd in ("/podcast_status", "/rss_status", "/spotify_status", "/apple_podcasts_status"):
        return podcast_text(root, {"/rss_status": "rss", "/spotify_status": "spotify",
                                   "/apple_podcasts_status": "apple"}.get(cmd, "all"))
    if cmd in ("/discover_now", "/discover_true", "/discover_trend"):
        if cmd != "/discover_now":
            s["next_prefer"] = {"prefer": "true" if cmd == "/discover_true" else "trend", "day": today}
        ok = _dispatch("discover")
        pre = {"/discover_true": "পরের গল্পে সত্য ঘটনাকে অগ্রাধিকার দেওয়া হবে। ",
               "/discover_trend": "পরের গল্পে ট্রেন্ডিং বিষয়কে অগ্রাধিকার দেওয়া হবে। "}.get(cmd, "")
        return pre + ("🧭 বিষয় খোঁজা শুরু হল - ফলাফল কিছুক্ষণের মধ্যে আসবে (চলমান ভিডিও-কাজ থাকলে তার পরে)।" if ok else
                      "⚠️ এখনই খোঁজা চালু করা গেল না (GitHub অনুমতি) - পরের নির্ধারিত গল্পে নিজে থেকেই খুঁজবে।")
    if cmd == "/publish_all":
        s["autopublish"] = True
        s["destinations"] = {"youtube": True, "facebook": True, "podcast": True}
        return "✅ সব প্ল্যাটফর্মে প্রকাশ চালু (পরের গল্প থেকে, নির্ধারিত সময়ে)।\n" + dest_text(s)
    if cmd == "/retry_publish":
        ok = _dispatch("retry")
        return ("🔁 শেষ ভিডিও যে জায়গাগুলোয় যায়নি, শুধু সেখানে আবার চেষ্টা শুরু হল।" if ok else
                "⚠️ আবার-চেষ্টা চালু করা গেল না (GitHub অনুমতি)।")
    if cmd == "/cancel_job":
        r = _gh("GET", f"/actions/workflows/{WORKFLOW}/runs", params={"status": "in_progress", "per_page": 5})
        runs = (r.json().get("workflow_runs") or []) if r is not None and r.ok else []
        n = 0
        for run in runs:
            c = _gh("POST", f"/actions/runs/{run['id']}/cancel")
            n += 1 if c is not None and c.status_code in (200, 202) else 0
        return f"🛑 {n}টি চলমান কাজ থামানো হল।" if n else "এখন কোনো কাজ চলছে না।"
    if cmd == "/pause":
        until = "forever"
        if arg.isdigit():
            until = (_dt.datetime.now(_IST) + _dt.timedelta(days=min(int(arg), 60))).isoformat(timespec="minutes")
        s["paused"] = {"until": until, "since": _dt.datetime.now(_IST).isoformat(timespec="minutes")}
        return "⏸️ ভূতের bot বন্ধ" + ("" if until == "forever" else f" {arg} দিনের জন্য") + " - নতুন ভিডিও যাবে না। আবার চালাতে: চালু"
    if cmd == "/resume":
        s["paused"] = None
        s["resumed_at"] = _dt.datetime.now(_IST).isoformat(timespec="minutes")
        return "▶️ ভূতের bot চালু - পরের সময় থেকে আবার ভিডিও যাবে।"
    return "বুঝতে পারিনি। /help লিখলে সব কমান্ড দেখবেন।"


def paused(s):
    p = s.get("paused")
    if not p:
        return False
    u = p.get("until")
    if u and u != "forever":
        try:
            return _dt.datetime.now(_IST) < _dt.datetime.fromisoformat(u)
        except ValueError:
            return False
    return True


# Telegram remembers the update kinds of the LAST reader - every reader of this bot asks for the same list
# (extras.TG_UPDATES), otherwise the story run would miss channel posts / new-channel events.
TG_UPDATES = ["message", "channel_post", "my_chat_member"]

# The '/' menu: tap '/' in the chat with the bot and every command is listed with its Bengali meaning.
# Shown ONLY in your own chat (scope = your chat) - viewers who write to the bot never see these.
MENU = [
    ("status", "সব খবর - চালু/বন্ধ, শেষ গল্প, প্রকাশ, খরচ"),
    ("calendar", "কখন কোন গল্প/টিজার/Live যাবে"),
    ("destinations", "কোথায় কোথায় প্রকাশ হচ্ছে"),
    ("discover_now", "এখনই নিজে বিষয় খুঁজে তালিকা পাঠাও (ভিডিও নয়)"),
    ("topic", "আপনার বিষয় দিন - /topic তারপর বিষয় লিখুন"),
    ("topic_queue", "লাইনে কোন কোন বিষয় আছে"),
    ("topic_mode", "বিষয় বাছাইয়ের মোড দেখুন/বদলান"),
    ("research_sources", "শেষ গল্পের উৎস ও যাচাই"),
    ("autodiscover_on", "bot নিজে বিষয় খুঁজবে (ডিফল্ট)"),
    ("autodiscover_off", "নিজে খোঁজা বন্ধ - আগের নিয়মে বিষয়"),
    ("podcast_status", "Podcast: RSS, Spotify, Apple - সব অবস্থা"),
    ("rss_status", "RSS ফিড ঠিক আছে কি না"),
    ("spotify_status", "Spotify-র অবস্থা"),
    ("apple_podcasts_status", "Apple Podcasts-এর অবস্থা"),
    ("autopublish_on", "স্বয়ংক্রিয় প্রকাশ চালু"),
    ("autopublish_off", "প্রকাশ বন্ধ - ভিডিও তৈরি হবে, যাবে না"),
    ("youtube_on", "YouTube-এ প্রকাশ চালু"),
    ("youtube_off", "YouTube-এ প্রকাশ বন্ধ"),
    ("facebook_on", "Facebook-এ প্রকাশ চালু"),
    ("facebook_off", "Facebook-এ প্রকাশ বন্ধ"),
    ("podcast_on", "Podcast/Spotify/Apple-এ পর্ব চালু"),
    ("podcast_off", "Podcast-এ পর্ব বন্ধ"),
    ("retry_publish", "শেষ ভিডিও যেখানে যায়নি, শুধু সেখানে আবার"),
    ("cancel_job", "চলমান কাজ থামাও"),
    ("pause", "ভূতের bot বন্ধ (/pause 3 = ৩ দিন)"),
    ("resume", "ভূতের bot আবার চালু"),
    ("style_refresh", "নমুনা গল্পের ধাঁচ আবার শেখো (পরের run-এ)"),
    ("help", "সব কমান্ড ও বাংলা নির্দেশ"),
]


def set_menu(tok, chat, s):
    """sets the '/' command list for your chat once (again only when the list changes)"""
    import hashlib
    import requests as rq
    h = hashlib.sha1(json.dumps(MENU, ensure_ascii=False).encode()).hexdigest()[:10]
    if s.get("menu") == h:
        return False
    r = rq.post(f"https://api.telegram.org/bot{tok}/setMyCommands", timeout=30, json={
        "commands": [{"command": c, "description": d} for c, d in MENU],
        "scope": {"type": "chat", "chat_id": int(chat) if str(chat).lstrip("-").isdigit() else chat}})
    if r.ok and r.json().get("ok"):
        s["menu"] = h
        print("'/' menu set in your chat")
        return True
    print("menu not set:", r.text[:150])
    return False


def poll(state_dir="state", root="."):
    import requests as rq
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (tok and chat):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing - nothing to do")
        return 0
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, FILE)
    s = _merge(DEFAULT, _jl(path, {}))
    try:
        set_menu(tok, chat, s)                         # the '/' menu in your Telegram chat
    except Exception as e:
        print("menu not set:", str(e)[:100])
    before = json.dumps({k: v for k, v in s.items() if k != "updated"}, sort_keys=True, ensure_ascii=False)
    r = rq.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=30,
               params={"allowed_updates": json.dumps(TG_UPDATES)}).json()   # (no offset: nothing is consumed)
    handled = set(int(x) for x in s.get("handled") or [])
    since = _dt.datetime.now(_dt.timezone.utc).timestamp() - 6 * 3600   # (never answer very old messages)
    n = 0
    for u in r.get("result") or []:
        uid, m = u.get("update_id"), u.get("message") or {}
        if uid in handled or str((m.get("chat") or {}).get("id")) != str(chat) or int(m.get("date") or 0) < since:
            continue
        p = parse(m.get("text") or "")
        if not p:
            continue                                   # stories, pictures, 'বাদ', 'বদলাও'... -> the story run
        cmd, arg = p
        try:
            ans = handle(cmd, arg, s, root, uid)
        except Exception as e:
            ans = f"⚠️ কমান্ড চালাতে সমস্যা: {str(e)[:120]}"
        _tg(tok, chat, ans)
        handled.add(uid)
        n += 1
    s["handled"] = sorted(handled)[-500:]
    after = json.dumps({k: v for k, v in s.items() if k != "updated"}, sort_keys=True, ensure_ascii=False)
    if after != before or not os.path.exists(path):   # (saved only when something really changed)
        s["updated"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
    print(f"answered {n} command(s)")
    return n


if __name__ == "__main__":
    import zerocost
    zerocost.install()
    if len(_sys.argv) > 1 and _sys.argv[1] == "poll":
        poll()
