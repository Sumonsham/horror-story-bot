"""V8 podcast check (run by the Telegram poller, at most every 3 hours): is the PUBLIC RSS feed really live, is
the newest episode in it, does its audio open - and is it on Apple Podcasts / Spotify?

Honest statuses only (Phase 35-D9): FEED_READY, LISTED, EPISODE_AVAILABLE, FAILED, UNKNOWN, ...
An episode is never called "on Spotify / Apple" just because it is in the RSS feed. Apple is checked with
Apple's free public lookup (itunes.apple.com/lookup). Spotify has no key-less public lookup, so its episode
status stays UNKNOWN unless a free Spotify app key is added later - it is reported as such.
Writes <state_dir>/podcast_status.json (bot-state branch). Nothing is published, nothing costs money.
"""
import datetime as dt
import json
import os
import sys
import xml.etree.ElementTree as ET

import requests

APPLE_DEFAULT_ID = "6834719714"     # (the show id already used in main.py's Apple Podcasts link)
UA = {"User-Agent": "DailyHorrorStoryBot/1.0 (podcast feed check)"}


def _jl(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def check_feed(feed_url, want_guid=None):
    out = {"status": "UNKNOWN", "url": feed_url}
    try:
        r = requests.get(feed_url, headers=UA, timeout=30)
    except Exception as e:
        return dict(out, status="FAILED", note=f"ফিড খোলা গেল না: {str(e)[:80]}")
    if not r.ok:
        return dict(out, status="FAILED", note=f"ফিড HTTP {r.status_code}")
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        return dict(out, status="FAILED", note=f"XML ভুল: {str(e)[:80]}")
    items = root.findall("./channel/item")
    guids = [i.findtext("guid") for i in items]
    out.update(episodes=len(items), newest=guids[0] if guids else None)
    if len(guids) != len(set(guids)):
        return dict(out, status="FAILED", note="একই GUID দুবার")
    if want_guid and want_guid not in guids:
        return dict(out, status="EPISODE_MISSING", note=f"নতুন পর্ব {want_guid} এখনও লাইভ ফিডে নেই (ওয়েবসাইট আপডেট হতে কয়েক মিনিট লাগে)")
    enc = items[0].find("enclosure") if items else None
    if enc is not None:
        try:
            h = requests.head(enc.get("url"), headers=UA, timeout=30, allow_redirects=True)
            if not h.ok:
                return dict(out, status="FAILED", note=f"নতুন পর্বের অডিও খুলছে না (HTTP {h.status_code})")
        except Exception as e:
            return dict(out, status="FAILED", note=f"অডিও যাচাই হল না: {str(e)[:60]}")
    return dict(out, status="FEED_READY", note="লাইভ ফিড ঠিক আছে, নতুন পর্বের অডিও খোলে")


def check_apple(show_id, newest_title):
    out = {"status": "UNKNOWN", "url": f"https://podcasts.apple.com/podcast/id{show_id}"}
    try:
        r = requests.get("https://itunes.apple.com/lookup", headers=UA, timeout=30,
                         params={"id": show_id, "entity": "podcastEpisode", "limit": 10})
        res = r.json().get("results") or [] if r.ok else []
    except Exception as e:
        return dict(out, note=f"Apple lookup হল না: {str(e)[:60]}")
    if not res:
        return dict(out, status="UNKNOWN", note="Apple-এ শোটি খুঁজে পাওয়া গেল না (id ঠিক আছে কি না দেখুন)")
    show = res[0]
    out["url"] = show.get("collectionViewUrl") or out["url"]
    eps = [x.get("trackName", "") for x in res[1:]]
    key = str(newest_title or "").split("|")[0].strip()[:25]
    if key and any(key in e for e in eps):
        return dict(out, status="EPISODE_AVAILABLE", note="নতুন পর্ব Apple Podcasts-এ এসে গেছে")
    return dict(out, status="LISTED", note="শো Apple-এ আছে; নতুন পর্ব এখনও দেখা যাচ্ছে না (Apple সাধারণত কয়েক ঘণ্টা নেয়)")


def check_spotify(spotify_url):
    if spotify_url:
        return {"status": "LISTED", "url": spotify_url,
                "note": "শো Spotify-তে আছে; Spotify নিজে RSS পড়ে - পর্ব-স্তরের যাচাই ফ্রি-তে সম্ভব নয় (UNKNOWN)"}
    return {"status": "FEED_READY", "note": "SPOTIFY_URL দেওয়া নেই - Spotify for Creators-এ একবার RSS জমা/claim করতে হবে"}


def main(state_dir="state", root="."):
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, "podcast_status.json")
    old = _jl(path, {}) or {}
    eps = _jl(os.path.join(root, "docs", "podcast.json"), []) or []
    newest = eps[-1] if eps else {}
    try:
        last = dt.datetime.fromisoformat(str(old.get("checked")))
        fresh = (dt.datetime.now(dt.timezone.utc) - last).total_seconds() < 3 * 3600
    except Exception:
        fresh = False
    if fresh and old.get("guid") == newest.get("guid"):
        print("podcast checked recently - skipped")
        return old
    try:
        base = open(os.path.join(root, "docs", "live.txt"), encoding="utf-8").read().strip()
    except Exception:
        base = ""
    st = {"guid": newest.get("guid"), "checked": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
    st["rss"] = check_feed(base.rstrip("/") + "/podcast.xml", newest.get("guid")) if base else \
        {"status": "UNKNOWN", "note": "ওয়েবসাইটের ঠিকানা (docs/live.txt) নেই"}
    st["rss"]["checked"] = st["checked"]
    st["apple"] = check_apple(os.environ.get("APPLE_PODCAST_ID") or APPLE_DEFAULT_ID, newest.get("title"))
    st["spotify"] = check_spotify(os.environ.get("SPOTIFY_URL", "").strip())
    same = {k: (old.get(k) or {}).get("status") for k in ("rss", "apple", "spotify")} == \
        {k: st[k].get("status") for k in ("rss", "apple", "spotify")} and old.get("guid") == st["guid"]
    if not same or not fresh:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    print("podcast:", {k: st[k].get("status") for k in ("rss", "apple", "spotify")})
    return st


if __name__ == "__main__":
    import zerocost
    zerocost.install()
    main(sys.argv[1] if len(sys.argv) > 1 else "state")
