"""V8 AUTO_DISCOVER - the bot finds today's subject by itself (Phase 13 + 35).

Free, key-less public sources only (reading costs nothing; zerocost.py guards every call):
  * Google News RSS   - news.google.com/rss/search  (Bengali + English queries)
  * Google Trends RSS - trends.google.com/trending/rss?geo=IN  (what India searches today - a SIGNAL only)
  * Wikipedia API     - documented haunted places / unexplained cases (bn + en)
  * YouTube trends    - already collected by extras.trending_topics (real titles + real view counts)
  * Gemini + Google Search grounding - builds the research dossier and gives the real source pages

Flow: queries -> candidate pool (10+) -> de-duplicate against everything already used -> score on 8 named
dimensions (with the reasons) -> pick -> research dossier (fact classes) -> class label:
  "true"     = সত্য ঘটনা অবলম্বনে        (2+ independent source pages that we opened ourselves)
  "inspired" = ঘটনা থেকে অনুপ্রাণিত কাল্পনিক কাহিনি (1 checked source page)
  "fiction"  = সম্পূর্ণ কাল্পনিক গল্প      (a trending THEME - no factual claim at all)
Every step is written to assets/discovery_ledger.json (queries, time, URLs, scores, reasons, choice).
Nothing here invents a source, a date, a view count or a fact: when a source is missing it says so.
"""
import datetime as dt
import hashlib
import html as _html
import json
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlparse

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; DailyHorrorStoryBot/1.0; +https://github.com)",
      "Accept-Language": "bn-IN,bn;q=0.9,en-IN;q=0.8,en;q=0.7"}

QUERIES = [
    ("bn", "ভৌতিক ঘটনা"), ("bn", "রহস্যময় ঘটনা পশ্চিমবঙ্গ"), ("bn", "অলৌকিক ঘটনা গ্রাম"),
    ("bn", "ভূতুড়ে বাড়ি"), ("bn", "রহস্যজনক নিখোঁজ"),
    ("en", "haunted West Bengal"), ("en", "mysterious incident Bengal villagers"), ("en", "paranormal Kolkata"),
    ("en", "haunted railway station India"), ("en", "unexplained mystery India ghost"),
]
WIKI_QUERIES = [("en", "haunted places West Bengal"), ("en", "reportedly haunted India"), ("bn", "ভূতুড়ে স্থান")]

HORROR_RX = re.compile(
    r"(?i)ghost|haunt|paranormal|spirit|supernatural|myster|unexplain|curse|abandon|eerie|spooky|black magic|"
    r"tantri|witch|possess|apparition|bhoot|bhut|ভূত|ভৌতিক|অলৌকিক|রহস্য|অশরীরী|আত্মা|তান্ত্রিক|অভিশপ্ত|"
    r"পরিত্যক্ত|ভূতুড়ে|গা ছমছম|অদ্ভুত|কালো জাদু")
SENSITIVE_RX = re.compile(
    r"(?i)suicid|rape|sexual|molest|minor girl|minor boy|child|lynch|witch[- ]hunt|branded (a )?witch|"
    r"mob|beaten to death|human sacrifice|sacrific|murder|killed|dead body|body found|"
    r"আত্মহত্যা|ধর্ষণ|শ্লীলতাহানি|শিশু|নাবালক|নাবালিকা|গণপিটুনি|ডাইনি অপবাদ|ডাইনি সন্দেহে|বলি|খুন|মৃতদেহ|দেহ উদ্ধার")
BENGAL_RX = re.compile(
    r"(?i)west bengal|bengal|kolkata|calcutta|howrah|hooghly|hugli|bardhaman|burdwan|nadia|murshidabad|malda|"
    r"darjeeling|jalpaiguri|cooch|alipurduar|dinajpur|birbhum|bankura|purulia|medinipur|midnapore|jhargram|"
    r"sundarban|24 parganas|siliguri|asansol|durgapur|bangladesh|dhaka|chittagong|sylhet|"
    r"পশ্চিমবঙ্গ|কলকাতা|হাওড়া|হুগলি|বর্ধমান|নদিয়া|মুর্শিদাবাদ|মালদা|দার্জিলিং|জলপাইগুড়ি|কোচবিহার|"
    r"বীরভূম|বাঁকুড়া|পুরুলিয়া|মেদিনীপুর|সুন্দরবন|শিলিগুড়ি|বাংলাদেশ|ঢাকা")
INDIA_RX = re.compile(r"(?i)india|bihar|odisha|assam|jharkhand|tripura|ভারত")
PLACE_RX = re.compile(
    r"(?i)station|railway|house|bungalow|mansion|rajbari|palace|fort|hospital|school|hostel|road|highway|"
    r"bridge|river|forest|jungle|pond|lake|temple|cemetery|graveyard|crematorium|tunnel|mine|tea garden|"
    r"স্টেশন|বাড়ি|রাজবাড়ি|হাসপাতাল|রাস্তা|সেতু|নদী|জঙ্গল|পুকুর|মন্দির|শ্মশান|কবরস্থান|বাগান")
CREDIBLE = ("anandabazar", "telegraphindia", "thehindu", "indianexpress", "hindustantimes", "timesofindia",
            "indiatimes", "ndtv", "bbc", "eisamay", "sangbadpratidin", "bartamanpatrika", "prothomalo",
            "thedailystar", "bdnews24", "abplive", "news18", "indiatoday", "thewall", "kolkata24x7", "tv9bangla",
            "zeenews", "deccanherald", "scroll.in", "thequint", "livemint", "wikipedia", "outlookindia",
            "dhakatribune", "jugantor", "kalerkantho", "banglanews24", "thestatesman")

KIND_BN = {"true": "সত্য ঘটনা অবলম্বনে", "inspired": "ঘটনা থেকে অনুপ্রাণিত কাল্পনিক কাহিনি",
           "fiction": "সম্পূর্ণ কাল্পনিক গল্প"}


def _log(*a):
    print(*a, flush=True)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _iso(t=None):
    return (t or _now()).isoformat(timespec="minutes")


def _get(url, params=None, timeout=25):
    return requests.get(url, params=params, headers=UA, timeout=timeout)


def _text(el, tag):
    for c in el:
        if c.tag == tag or c.tag.endswith("}" + tag):
            return (c.text or "").strip()
    return ""


# ------------------------------------------------------------------ sources
def news_rss(q, lang):
    """Google News RSS search (free, public). [{title, link, published, source, source_url}]"""
    hl, ceid = ("bn", "IN:bn") if lang == "bn" else ("en-IN", "IN:en")
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={hl}&gl=IN&ceid={ceid}"
    r = _get(url)
    if not r.ok:
        return []
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        src = it.find("source")
        title = _html.unescape(_text(it, "title"))
        sname = (src.text or "").strip() if src is not None else ""
        if sname and title.endswith(" - " + sname):
            title = title[: -len(sname) - 3]
        out.append({"title": title.strip(), "link": _text(it, "link"), "published": _text(it, "pubDate"),
                    "source": sname, "source_url": src.get("url", "") if src is not None else ""})
    return out[:30]


def trends_rss(geo="IN"):
    """Google Trends 'trending now' RSS (free, public): today's searches in India - a SIGNAL, not a source."""
    r = _get("https://trends.google.com/trending/rss", params={"geo": geo})
    if not r.ok:
        return []
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        news = []
        for c in it:
            if c.tag.endswith("news_item"):
                news.append({"title": _html.unescape(_text(c, "news_item_title")), "url": _text(c, "news_item_url"),
                             "source": _text(c, "news_item_source")})
        out.append({"title": _text(it, "title"), "traffic": _text(it, "approx_traffic"),
                    "published": _text(it, "pubDate"), "news": news})
    return out


def wiki_search(q, lang):
    r = _get(f"https://{lang}.wikipedia.org/w/api.php",
             params={"action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": 8})
    if not r.ok:
        return []
    out = []
    for x in (r.json().get("query") or {}).get("search") or []:
        snip = re.sub(r"<[^>]+>", "", _html.unescape(x.get("snippet", "")))
        out.append({"title": x.get("title", ""), "snippet": snip,
                    "url": f"https://{lang}.wikipedia.org/wiki/{quote_plus(x.get('title', '').replace(' ', '_'))}"})
    return out


# ------------------------------------------------------------------ helpers
def _tokens(s):
    return {w for w in re.findall(r"[\wঀ-৿]{3,}", str(s or "").lower())
            if w not in {"the", "and", "with", "from", "this", "that", "story", "ghost", "haunted", "india",
                         "bengal", "west", "new", "news", "গল্প", "ঘটনা", "night", "village", "rural", "house",
                         "isolated", "lonely", "abandoned", "mysterious", "strange", "old", "who", "finds", "his", "her",
                         "their", "original", "topic", "same", "our", "own", "bengali", "where", "when", "into"}}


def similarity(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def _age_days(published):
    try:
        from email.utils import parsedate_to_datetime
        return (_now() - parsedate_to_datetime(published)).days
    except Exception:
        return None


def _cid(title):
    return hashlib.sha1(str(title).lower().encode()).hexdigest()[:10]


def credible(name_or_url):
    s = str(name_or_url or "").lower().replace(" ", "")
    return any(c in s for c in CREDIBLE)


# ------------------------------------------------------------------ scoring (8 named dimensions, 0-10 each)
def score(c, used_texts, trend_titles):
    text = f"{c.get('title', '')} {c.get('snippet', '')}"
    why = []
    # 1) trend evidence - only what we really observed
    tr = 2
    if any(similarity(c["title"], t) >= 0.5 for t in trend_titles):
        tr += 4
        why.append("Google Trends-এ আজ এই বিষয়ের খোঁজ")
    if c.get("outlets", 1) > 1:
        tr += min(3, c["outlets"] - 1)
        why.append(f"{c['outlets']}টি আলাদা সংবাদমাধ্যমে খবর")
    if c.get("views"):
        tr += 3
        why.append(f"YouTube-এ এই সপ্তাহে {c['views']:,} বার দেখা (প্রকাশ্য সংখ্যা)")
    age = _age_days(c.get("published", ""))
    if age is not None and age <= 30:
        tr += 1
    tr = min(10, tr)
    # 2) audience relevance (Bengali-speaking audience)
    rel = 8 if BENGAL_RX.search(text) else 5 if INDIA_RX.search(text) else 3
    if re.search(r"[ঀ-৿]", text):
        rel = min(10, rel + 1)
    # 3) source quality
    srcq = 8 if credible(c.get("source")) or credible(c.get("source_url")) else 7 if c.get("kind") == "wiki" else \
        3 if c.get("kind") in ("youtube", "trend") else 4
    # 4) originality (not used before)
    sim = max([similarity(c["title"], u) for u in used_texts] or [0.0])
    orig = round(10 * (1 - sim), 1)
    # 5) narrative potential
    nar = min(10, 3 + 2 * len(set(m.lower() for m in HORROR_RX.findall(text))))
    # 6) visual / animation potential
    vis = 7 if PLACE_RX.search(text) else 4
    # 7) sensitivity / risk (higher = riskier)
    risk = 9 if SENSITIVE_RX.search(text) else 2
    if risk >= 9:
        why.append("সংবেদনশীল বিষয় (মৃত্যু / অপরাধ / শিশু) - বাদ")
    # 8) duplication risk
    dup = round(10 * sim, 1)
    if sim >= 0.5:
        why.append("আগে প্রায় একই বিষয়ে গল্প হয়েছে - বাদ")
    total = round(0.2 * tr + 0.15 * rel + 0.2 * srcq + 0.1 * orig + 0.15 * nar + 0.1 * vis - 0.15 * risk
                  - 0.1 * dup, 2)
    c["scores"] = {"trend": tr, "relevance": rel, "source": srcq, "originality": orig, "narrative": nar,
                   "visual": vis, "risk": risk, "duplication": dup, "total": total}
    c["eligible"] = risk < 8 and sim < 0.5 and bool(HORROR_RX.search(text) or c.get("kind") in ("trend", "user"))
    if not HORROR_RX.search(text) and c.get("kind") not in ("trend", "user"):
        why.append("ভৌতিক / রহস্যের উপাদান নেই")
    c["why"] = why
    return c


# ------------------------------------------------------------------ the pool
def build_pool(used_texts, trend_topics=None, youtube_top=None, user_topics=None, ledger=None):
    """All candidates with their scores. ledger['queries'] records every query and how many results came."""
    ledger = ledger if ledger is not None else {}
    qlog = ledger.setdefault("queries", [])
    pool = []
    trends = []
    try:
        trends = trends_rss()
        qlog.append({"source": "google_trends_rss", "q": "geo=IN", "n": len(trends), "at": _iso()})
    except Exception as e:
        qlog.append({"source": "google_trends_rss", "q": "geo=IN", "error": str(e)[:120], "at": _iso()})
    trend_titles = [t["title"] for t in trends] + [n["title"] for t in trends for n in t.get("news", [])]
    for t in trends:                                  # a trending search that is itself about a mystery
        for n in t.get("news", []):
            if HORROR_RX.search(n.get("title", "")):
                pool.append({"kind": "news", "title": n["title"], "link": n.get("url", ""), "source": n.get("source", ""),
                             "published": t.get("published", ""), "query": f"trends:{t['title']}"})
    for lang, q in QUERIES:
        try:
            items = news_rss(q, lang)
            qlog.append({"source": "google_news_rss", "q": q, "lang": lang, "n": len(items), "at": _iso()})
        except Exception as e:
            items = []
            qlog.append({"source": "google_news_rss", "q": q, "lang": lang, "error": str(e)[:120], "at": _iso()})
        for it in items:
            age = _age_days(it.get("published", ""))
            if age is not None and age > 730:
                continue
            pool.append({"kind": "news", "title": it["title"], "link": it["link"], "source": it["source"],
                         "source_url": it["source_url"], "published": it["published"], "query": q})
    for lang, q in WIKI_QUERIES:
        try:
            items = wiki_search(q, lang)
            qlog.append({"source": f"wikipedia_{lang}", "q": q, "n": len(items), "at": _iso()})
        except Exception as e:
            items = []
            qlog.append({"source": f"wikipedia_{lang}", "q": q, "error": str(e)[:120], "at": _iso()})
        for it in items:
            pool.append({"kind": "wiki", "title": it["title"], "link": it["url"], "source": "Wikipedia",
                         "snippet": it["snippet"], "query": q})
    for t in trend_topics or []:                      # ORIGINAL story themes that ride YouTube's trends
        pool.append({"kind": "trend", "title": str(t)[:200], "source": "YouTube trends (topic only)",
                     "query": "youtube_trending"})
    for v in youtube_top or []:                       # real titles + real view counts -> evidence only
        m = re.match(r"(.*)\s\(([\d,]+)\)$", str(v))
        if m:
            for c in pool:
                if c["kind"] == "trend" and similarity(c["title"], m.group(1)) >= 0.3:
                    c["views"] = max(c.get("views", 0), int(m.group(2).replace(",", "")))
    for u in user_topics or []:
        pool.append({"kind": "user", "title": str(u.get("text", ""))[:300], "source": "আপনার Telegram",
                     "user_id": u.get("id"), "query": "user"})
    # merge the same story told by several outlets
    merged = []
    for c in pool:
        if not c.get("title"):
            continue
        same = next((m for m in merged if m["kind"] == c["kind"] and similarity(m["title"], c["title"]) >= 0.6), None)
        if same:
            same["outlets"] = same.get("outlets", 1) + (1 if c.get("source") != same.get("source") else 0)
            same.setdefault("also", []).append({"title": c["title"], "source": c.get("source"), "link": c.get("link")})
        else:
            merged.append(dict(c, outlets=1))
    for c in merged:
        c["id"] = _cid(c["title"])
        score(c, used_texts, trend_titles)
    merged.sort(key=lambda c: (not c["eligible"], -c["scores"]["total"]))
    return merged


# ------------------------------------------------------------------ source verification
def page_ok(url, must=()):
    """Open the page ourselves: reachable, real HTML/text, and (if given) mentions one of the key words."""
    try:
        r = requests.get(url, headers=UA, timeout=25, allow_redirects=True)
    except Exception:
        return False, url
    if not r.ok or "text" not in r.headers.get("content-type", "text"):
        return False, r.url or url
    body = r.text[:400000].lower()
    if must and not any(str(m).lower() in body for m in must if m and len(str(m)) >= 4):
        return False, r.url or url
    return True, r.url or url


def classify_sources(sources, key_words):
    """[{title,url}] -> the ones we opened and found really about the subject (different sites only)."""
    good, sites = [], set()
    for s in sources:
        ok, final = page_ok(s.get("url", ""), key_words)
        host = (urlparse(final).hostname or "").replace("www.", "")
        if ok and host and host not in sites and "google." not in host and "vertexaisearch" not in host:
            sites.add(host)
            good.append({"title": s.get("title") or host, "url": final, "site": host,
                         "credible": credible(host)})
        if len(good) >= 5:
            break
    return good


DOSSIER_PROMPT = """Search the web (Google) and OPEN the source pages, then answer. We make Bengali horror audio
stories and must be honest about what is real. Subject: "{title}" ({hint}).
Find what reputable sources (newspapers, books, official notices, documented local history) really report about it.
Reply with ONLY a JSON object:
{{"found": true/false, "place": "town / village, district, state/country (only if the sources say it)",
 "era": "date or period (only if the sources say it, else 'unknown')", "title_en": "short neutral name",
 "what_is_reported": "8-12 neutral English sentences: what the sources say happened / what people reported",
 "claims": [{{"text": "...", "type": "VERIFIED_FACT|REPORTED_CLAIM|WITNESS_ACCOUNT|DISPUTED|FOLKLORE"}}],
 "unknown": ["what remains unexplained / not known"],
 "sensitivity": "low|medium|high (high = real recent death, crime, suicide, a minor, an ongoing investigation)",
 "key_words": ["3-6 distinctive words/names of the PLACE or event that a source page must contain"]}}
Rules: never invent a source, date, witness, quote or official statement. A reported ghost is a REPORT, never a
fact. No private person's name (victims, families, accused): use roles only. found=false if nothing reliable."""


def make_dossier(c, gemini_search):
    """gemini_search(prompt) -> (json_dict, [{title,url}]) or (None, []). Returns the dossier or None."""
    hint = c.get("source") or c.get("kind")
    if c.get("published"):
        hint += f", {c['published'][:16]}"
    ans, srcs = gemini_search(DOSSIER_PROMPT.format(title=c["title"], hint=hint))
    if not isinstance(ans, dict) or not ans.get("found"):
        return None
    if str(ans.get("sensitivity", "")).lower() == "high":
        return {"rejected": "high sensitivity (real recent tragedy / crime / minor)", **ans}
    cands = list(srcs or [])
    if c.get("kind") == "wiki" and c.get("link"):
        cands.insert(0, {"title": c["title"], "url": c["link"]})
    keys = [k for k in (ans.get("key_words") or []) if isinstance(k, str)][:6] or list(_tokens(c["title"]))[:4]
    verified = classify_sources(cands, keys)
    claims = [x for x in (ans.get("claims") or []) if isinstance(x, dict) and x.get("text")][:20]
    kinds = {}
    for x in claims:
        kinds[x.get("type", "REPORTED_CLAIM")] = kinds.get(x.get("type", "REPORTED_CLAIM"), 0) + 1
    cls = "true" if len(verified) >= 2 and any(v["credible"] for v in verified) else \
        "inspired" if verified else None
    return {"title_en": ans.get("title_en") or c["title"], "place": ans.get("place", ""), "era": ans.get("era", ""),
            "what_is_reported": str(ans.get("what_is_reported", ""))[:2500], "claims": claims,
            "claim_kinds": kinds, "unknown": ans.get("unknown") or [], "sources": verified,
            "sources_offered": len(cands), "class": cls, "key_words": keys}


# ------------------------------------------------------------------ the whole step
def discover(used_texts, gemini_search=None, prefer="mixed", trend_topics=None, youtube_top=None,
             user_topics=None, ledger_path=None, slot=None, max_dossiers=2):
    """Returns the chosen subject:
    {id, class: true|inspired|fiction, theme, title, sources, dossier, report_bn, ledger_id} or None."""
    rec = {"id": _now().strftime("%Y%m%d%H%M") + "-" + (str(slot or "x").replace("@", "_")), "at": _iso(),
           "slot": slot, "prefer": prefer}
    pool = build_pool(used_texts, trend_topics, youtube_top, user_topics, rec)
    chosen, dossier = None, None
    users = [c for c in pool if c["kind"] == "user" and c["eligible"]]
    facts = [c for c in pool if c["kind"] in ("news", "wiki") and c["eligible"]]
    themes = [c for c in pool if c["kind"] == "trend" and c["eligible"]]
    tried = 0
    if users:
        chosen = users[0]
        chosen["status"] = "selected: আপনার দেওয়া বিষয়"
    if not chosen and prefer in ("true", "mixed") and gemini_search:
        for c in facts:
            if tried >= max_dossiers:
                break
            tried += 1
            try:
                d = make_dossier(c, gemini_search)
            except Exception as e:
                d = None
                c["status"] = f"dossier failed: {str(e)[:80]}"
            if d and d.get("class") and not d.get("rejected"):
                chosen, dossier = c, d
                c["status"] = "selected"
                break
            c["status"] = "rejected: " + ((d or {}).get("rejected") or
                                          ("যাচাইযোগ্য উৎস-পাতা পাওয়া যায়নি" if d else "নির্ভরযোগ্য তথ্য মেলেনি"))
    if not chosen and themes:
        chosen = themes[0]
        chosen["status"] = "selected"
    if not chosen and facts and not gemini_search:
        pass                                          # (no research tool -> never a 'true' label without a dossier)
    cls = (dossier or {}).get("class") or ("fiction" if chosen else None)
    out = None
    if chosen:
        if chosen["kind"] == "user":
            theme = f"the creator's chosen subject: {chosen['title']}"
        elif dossier:
            theme = f"a real reported account: {dossier['title_en']} ({dossier.get('place', '')})"
        else:
            theme = chosen["title"]
        out = {"id": rec["id"], "class": cls, "theme": theme, "title": chosen["title"], "candidate": chosen["id"],
               "kind": chosen["kind"], "sources": (dossier or {}).get("sources") or [], "dossier": dossier,
               "user_id": chosen.get("user_id"), "scores": chosen.get("scores")}
        bits = [f"{len(pool)}টি বিষয় যাচাই", f"বেছে নেওয়া: {chosen['title'][:70]}", KIND_BN.get(cls, "")]
        if out["sources"]:
            bits.append(f"{len(out['sources'])}টি উৎস-পাতা নিজে খুলে মিলিয়েছে")
        if chosen.get("why"):
            bits.append("কারণ: " + "; ".join(chosen["why"][:2]))
        out["report_bn"] = " · ".join(b for b in bits if b)
    rec.update(pool_size=len(pool), candidates=[
        {k: c.get(k) for k in ("id", "kind", "title", "source", "link", "published", "query", "outlets", "views",
                               "scores", "eligible", "why", "status")} for c in pool[:15]],
        selected=(out or {}).get("candidate"), story_class=cls,
        sources=[s["url"] for s in (out or {}).get("sources") or []],
        claim_kinds=(dossier or {}).get("claim_kinds"),
        note=None if out else "কোনো উপযুক্ত বিষয় মেলেনি - আগের নিয়মে গল্প হবে")
    if ledger_path:
        save_ledger(ledger_path, rec)
    return out


def save_ledger(path, rec, keep=120):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"entries": []}
    if not isinstance(data, dict):
        data = {"entries": []}
    data["entries"] = (data.get("entries") or [])[-(keep - 1):] + [rec]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def used_titles(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        out = []
        for e in data.get("entries") or []:
            for c in e.get("candidates") or []:
                if c.get("id") == e.get("selected"):
                    out.append(c.get("title", ""))
        return out
    except Exception:
        return []
