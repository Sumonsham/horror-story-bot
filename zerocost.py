"""ZERO_COST_MODE (V8 Phase 27 / 35-G): one guard at the network boundary.

Every `requests` call of the bot goes through requests.Session.request - this module wraps it ONCE, so no
provider can be reached by a new, forgotten code path:
  * reading public pages (GET / HEAD) is free and allowed, except the known paid endpoints below;
  * a call that SENDS or CREATES something (POST / PUT / PATCH / DELETE) is allowed only to an approved host;
  * a blocked call raises ZeroCostBlocked (a normal requests error, so the bot's existing try/except blocks
    treat it like any other failed call) and a Bengali reason is logged.

Switches (GitHub Secrets / env):
  ZERO_COST_MODE=0           turn the guard off (not recommended)
  ZERO_COST_EXTRA_ALLOW=a,b  more hosts YOU have checked are free
  CHIRP_APPROVED=0           also block Google Cloud TTS (Chirp). Default: allowed, because you approved on
                             21 Nov 2026 "Gemini first, Chirp only when Gemini is used up" - it stays capped by
                             CHIRP_MONTH_CAP inside the free monthly share.
  TTS_PAID is ignored while ZERO_COST_MODE is on (that was the only switch that used a paid key on purpose).
"""
import os
import sys
import threading
from urllib.parse import urlparse

import requests

READ_METHODS = {"GET", "HEAD", "OPTIONS"}

# hosts the bot may SEND to - each one is used inside its free terms by this bot
APPROVED_HOSTS = {
    "generativelanguage.googleapis.com": "Gemini API (free tier key)",
    "oauth2.googleapis.com": "Google sign-in for YouTube (free)",
    "www.googleapis.com": "YouTube Data API (free daily quota)",
    "youtube.googleapis.com": "YouTube Data API (free daily quota)",
    "youtubeanalytics.googleapis.com": "YouTube Analytics API (free)",
    "graph.facebook.com": "Facebook Graph API (free)",
    "graph-video.facebook.com": "Facebook video upload (free)",
    "rupload.facebook.com": "Facebook Reels upload (free)",
    "api.cloudflare.com": "Cloudflare Workers AI (free daily allocation, one account)",
    "api.telegram.org": "Telegram Bot API (free)",
    "api.github.com": "GitHub API (free for this public repo)",
    "uploads.github.com": "GitHub Release uploads (podcast audio, video backup - free)",
    "freesound.org": "Freesound (CC0 sounds, free key)",
    "huggingface.co": "free open voice model download",
    # kept because you configured them as free backups (USE_AGNES=0 / no FREEMODEL_API_KEY switches them off)
    "apihub.agnes-ai.com": "Agnes AI pictures (your configured free backup)",
    "freemodel.in": "FreeModel text (your configured free backup)",
}

# endpoints that need a billing account - blocked unless explicitly approved
PAID_HOSTS = {
    "texttospeech.googleapis.com": "CHIRP_APPROVED",          # Google Cloud TTS (billing account required)
    "aiplatform.googleapis.com": None,                         # Vertex AI (paid)
    "api.openai.com": None, "api.anthropic.com": None, "api.elevenlabs.io": None,
    "api.replicate.com": None, "api.runwayml.com": None, "api.stability.ai": None,
    "speech.googleapis.com": None, "vision.googleapis.com": None, "customsearch.googleapis.com": None,
    "serpapi.com": None, "api.bing.microsoft.com": None,
}

STATS = {"blocked": [], "calls": 0}
_LOCK = threading.Lock()
_INSTALLED = [False]


class ZeroCostBlocked(requests.exceptions.RequestException):
    pass


def enabled():
    return os.environ.get("ZERO_COST_MODE", "1").strip() != "0"


def _extra_allowed():
    return {h.strip().lower() for h in os.environ.get("ZERO_COST_EXTRA_ALLOW", "").split(",") if h.strip()}


def _host_match(host, table):
    host = (host or "").lower().split(":")[0]
    for h in table:
        if host == h or host.endswith("." + h):
            return h
    return None


def check(method, url):
    """(allowed: bool, reason in Bengali)"""
    if not enabled():
        return True, ""
    host = (urlparse(str(url)).hostname or "").lower()
    method = str(method or "GET").upper()
    if _host_match(host, _extra_allowed()):
        return True, ""
    paid = _host_match(host, PAID_HOSTS)
    if paid:
        switch = PAID_HOSTS[paid]
        if switch and os.environ.get(switch, "1").strip() != "0":
            return True, ""                          # (Chirp: approved by you, capped in extras.chirp_ok)
        return False, f"ZERO_COST: '{host}' টাকা লাগে এমন পরিষেবা - তাই ডাকা হল না"
    if method in READ_METHODS:
        return True, ""                              # reading a public page costs nothing
    if _host_match(host, APPROVED_HOSTS):
        return True, ""
    return False, (f"ZERO_COST: '{host}' অনুমোদিত তালিকায় নেই - কিছু পাঠানো হল না "
                   "(নিশ্চিত ফ্রি হলে ZERO_COST_EXTRA_ALLOW-এ যোগ করুন)")


def install():
    """Wrap requests once (idempotent)."""
    if _INSTALLED[0]:
        return
    _INSTALLED[0] = True
    original = requests.sessions.Session.request

    def guarded(self, method, url, *a, **kw):
        ok, why = check(method, url)
        with _LOCK:
            STATS["calls"] += 1
            if not ok:
                STATS["blocked"].append(why)
        if not ok:
            print(why, file=sys.stderr, flush=True)
            raise ZeroCostBlocked(why)
        return original(self, method, url, *a, **kw)

    requests.sessions.Session.request = guarded


def summary_bn():
    if not enabled():
        return "⚠️ ZERO_COST_MODE বন্ধ আছে"
    n = len(STATS["blocked"])
    return "💰 ZERO_COST: খরচ ০ টাকা" + (f" (টাকা লাগত এমন {n}টি request আটকানো হয়েছে)" if n else "")
