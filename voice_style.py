"""VOICE STYLE PROFILE (owner, 24 Nov 2026: "MANDATORY VOICE SAMPLE STYLE EXTRACTION & NARRATION IDENTITY LOCK").

The approved reference recordings (assets/style_sample_*.mp3 - the stories you gave as "stories must be like this")
are MEASURED here, not guessed:

  * speaking speed (syllables a second) and its rhythm (how much it changes from phrase to phrase);
  * pitch: middle pitch, its range, how much it moves (expressiveness), how sentences end (falling / level);
  * pauses: between words, between sentences, between paragraphs - their typical length, and how often;
  * loudness: how wide the dynamics are, how often the voice drops to a near-whisper, how often it rises;
  * breathing: how many pauses long enough for a breath per minute;
  * the opening (first 2 minutes), the middle and the last part (the climax and the ending) separately - how the
    presenter slows down / speeds up, pauses longer or rises in the strong moments.

Everything that cannot be measured from sound alone (pronunciation, the hook, the climax, the ending, suspense
technique, conversational expression) comes from the listening notes the style teacher already made from the SAME
recordings (assets/style_model.json) - it is labelled as such.

The result is saved for good as assets/voice_style_profile.json. Every episode uses it:
  - the narrator's voice direction (Gemini) is written from it (speed, pauses, pitch movement, sentence endings,
    whispers only where the story needs them, no exaggerated horror voice);
  - the silences between lines / paragraphs in the sound track follow its measured pauses;
  - check_narration() compares each episode's finished narration with it and writes
    narration_consistency_report.json (speed, pitch, pauses, dynamics, rhythm), with what the voice provider cannot
    reproduce stated plainly.

VOICE IDENTITY: the reference recordings are other people's productions. Their presenter's own voice is NOT cloned
(that would copy a real person's voice without his consent); the narration keeps the approved Gemini narrator voice
and reproduces the presenter's STORYTELLING STYLE. This limitation is written into the profile and every report.

python voice_style.py build      -> (re)builds the profile from the reference recordings
python voice_style.py check X.wav -> compares one recording with the profile"""
import datetime as dt
import glob
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "assets", "voice_style_profile.json")
SR = 16000
HOP = 0.01


# ----------------------------------------------------------------------------------------------- measuring
def load(path, start=0.0, seconds=None):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-i", path]
    if seconds:
        cmd += ["-t", f"{seconds:.2f}"]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def _frames(a, win=0.04, hop=HOP):
    w, h = int(SR * win), int(SR * hop)
    n = max(0, (len(a) - w) // h)
    if n <= 0:
        return np.zeros((0, w)), h
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    return a[idx], h


def _pitch(fr):
    """F0 per frame (Hz, 0 = unvoiced) by normalised autocorrelation, 70-400 Hz"""
    x = fr - fr.mean(axis=1, keepdims=True)
    x = x * np.hanning(x.shape[1])[None, :]
    n = 1 << int(np.ceil(np.log2(2 * x.shape[1])))
    spec = np.fft.rfft(x, n, axis=1)
    ac = np.fft.irfft(np.abs(spec) ** 2, n, axis=1)[:, : x.shape[1]]
    ac /= ac[:, :1] + 1e-12
    lo, hi = int(SR / 400), int(SR / 70)
    seg = ac[:, lo:hi]
    k = np.argmax(seg, axis=1)
    peak = seg[np.arange(len(seg)), k]
    f0 = SR / (k + lo)
    f0[peak < 0.45] = 0.0
    return f0


def features(a, label=""):
    """the measured delivery of one stretch of narration"""
    fr, h = _frames(a)
    if len(fr) < 50:
        return None
    # (the reference is a produced show: a music / ambience bed runs under the voice, so a "pause" is where the
    # voice band drops well below the voice's own level nearby - not where the sound is silent)
    spec = np.abs(np.fft.rfft(fr * np.hanning(fr.shape[1])[None, :], axis=1))
    freqs = np.fft.rfftfreq(fr.shape[1], 1 / SR)
    band = (freqs >= 250) & (freqs <= 3500)
    rms = np.sqrt(np.mean(spec[:, band] ** 2, axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    w_ = int(3.0 / HOP)
    pad = np.pad(db, (w_ // 2, w_ - w_ // 2 - 1), mode="edge")
    from numpy.lib.stride_tricks import sliding_window_view
    local = np.percentile(sliding_window_view(pad, w_)[:: 10], 90, axis=1)
    local = np.repeat(local, 10)[: len(db)]
    if len(local) < len(db):
        local = np.pad(local, (0, len(db) - len(local)), mode="edge")
    speech = db > local - 11                              # the voice (the bed / room is well below it)
    # smooth the speech mask a little (a stop consonant is not a pause)
    k = 5
    sm = np.convolve(speech.astype(float), np.ones(k) / k, mode="same") > 0.4
    # pauses = runs of non-speech between speech
    pauses, run, started = [], 0, False
    for v in sm:
        if v:
            if started and run:
                pauses.append(run * HOP)
            run, started = 0, True
        else:
            run += 1
    pauses = np.array([p for p in pauses if p >= 0.12])
    word = pauses[(pauses < 0.35)]
    sent = pauses[(pauses >= 0.35) & (pauses < 1.0)]
    para = pauses[(pauses >= 1.0) & (pauses < 4.0)]
    minutes = len(sm) * HOP / 60.0
    speech_s = sm.sum() * HOP
    # syllable nuclei: peaks of the smoothed loudness envelope inside speech
    env = np.convolve(rms, np.ones(7) / 7, mode="same")
    envd = 20 * np.log10(env + 1e-9)
    pk = (envd[1:-1] > envd[:-2]) & (envd[1:-1] >= envd[2:]) & sm[1:-1]
    idx = np.where(pk)[0] + 1
    keep = []
    for i in idx:                                         # a nucleus stands out from the dip before it
        lo_ = envd[max(0, i - 12):i].min() if i > 0 else envd[i]
        if envd[i] - lo_ > 2.5 and (not keep or i - keep[-1] >= 8):
            keep.append(i)
    syl_rate = len(keep) / max(1.0, speech_s)
    # rhythm: how much the speed changes from one phrase (between pauses >= 0.35 s) to the next
    bounds = np.where(np.diff(sm.astype(int)) != 0)[0]
    rates = []
    starts = [b + 1 for b in bounds if not sm[b] and sm[b + 1]] if len(bounds) else []
    ends = [b + 1 for b in bounds if sm[b] and not sm[b + 1]] if len(bounds) else []
    keep_arr = np.array(keep)
    for s0 in starts:
        e0 = next((e for e in ends if e > s0), None)
        if e0 and (e0 - s0) * HOP >= 1.2:
            n_ = ((keep_arr >= s0) & (keep_arr < e0)).sum()
            rates.append(n_ / ((e0 - s0) * HOP))
    f0 = _pitch(fr)
    v = (f0 > 0) & speech
    f0v = f0[v]
    if len(f0v) > 50:
        med = float(np.median(f0v))
        f0v = np.where(f0v > med * 1.7, f0v / 2, np.where(f0v < med / 1.7, f0v * 2, f0v))   # octave errors folded
        med = float(np.median(f0v))
        f0 = np.where(f0 > med * 1.7, f0 / 2, np.where((f0 > 0) & (f0 < med / 1.7), f0 * 2, f0))
        st = 12 * np.log2(f0v / med)
        p10, p90 = np.percentile(st, [10, 90])
        q25, q75 = np.percentile(st, [25, 75])
        # sentence endings: the last 0.4 s of speech before a pause >= 0.35 s, against the phrase's middle
        falls = []
        for e0 in ends:
            seg = f0[max(0, e0 - 40):e0]
            seg = seg[seg > 0]
            pre = f0[max(0, e0 - 200):max(0, e0 - 40)]
            pre = pre[pre > 0]
            if len(seg) > 8 and len(pre) > 20:
                falls.append(12 * np.log2(np.median(seg) / np.median(pre)))
        pitch = {"median_hz": round(med, 1), "range_semitones_p10_p90": round(float(p90 - p10), 2),
                 "movement_semitones_sd": round(float((q75 - q25) / 1.35), 2),
                 "sentence_end_change_semitones": round(float(np.median(falls)), 2) if falls else None,
                 "falling_ends_share": round(float(np.mean(np.array(falls) < -0.5)), 2) if falls else None}
    else:
        pitch = {"median_hz": None}
    sdb = db[sm]
    dyn = float(np.percentile(sdb, 90) - np.percentile(sdb, 10)) if len(sdb) else 0.0
    soft = float(np.mean(sdb < np.percentile(sdb, 50) - 9)) if len(sdb) else 0.0
    strong = float(np.mean(sdb > np.percentile(sdb, 50) + 6)) if len(sdb) else 0.0
    return {"label": label, "minutes": round(minutes, 2), "speech_share": round(speech_s / max(1e-6, minutes * 60), 3),
            "syllables_per_second": round(syl_rate, 2),
            "syllables_per_second_with_pauses": round(len(keep) / max(1.0, minutes * 60), 2),
            "rhythm_rate_sd": round(float(np.std(rates)), 2) if len(rates) > 3 else None,
            "pause_word_s": round(float(np.median(word)), 2) if len(word) else None,
            "pause_sentence_s": round(float(np.median(sent)), 2) if len(sent) else None,
            "pause_paragraph_s": round(float(np.median(para)), 2) if len(para) else None,
            "sentence_pauses_per_min": round(len(sent) / max(1e-6, minutes), 1),
            "long_pauses_per_min": round(len(para) / max(1e-6, minutes), 1),
            "breath_pauses_per_min": round(len(pauses[pauses >= 0.3]) / max(1e-6, minutes), 1),
            "pitch": pitch, "dynamics_db_p10_p90": round(dyn, 1), "near_whisper_share": round(soft, 3),
            "raised_voice_share": round(strong, 3)}


def _median_dict(rows):
    out = {}
    keys = [k for k in rows[0] if k not in ("label", "pitch")]
    for k in keys:
        vals = [r[k] for r in rows if r.get(k) is not None]
        out[k] = round(float(np.median(vals)), 3) if vals else None
    pk = [k for k in rows[0].get("pitch", {}) if k]
    out["pitch"] = {}
    for k in pk:
        vals = [r["pitch"].get(k) for r in rows if r.get("pitch", {}).get(k) is not None]
        out["pitch"][k] = round(float(np.median(vals)), 3) if vals else None
    return out


# ----------------------------------------------------------------------------------------------- the profile
def build(samples=None, log=print):
    samples = samples or sorted(glob.glob(os.path.join(HERE, "assets", "style_sample*.mp3"))
                                + glob.glob(os.path.join(HERE, "assets", "style_samples", "*")))
    samples = [s for s in samples if s.lower().endswith((".mp3", ".m4a", ".ogg", ".wav", ".opus", ".aac"))]
    if not samples:
        raise RuntimeError("no reference recording (assets/style_sample*.mp3)")
    parts = {"opening": [], "middle": [], "final": [], "all": []}
    per_file = {}
    for s in samples:
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", s],
                                 capture_output=True, text=True).stdout.strip() or 0)
        if d < 120:
            continue
        rows = []
        # (the first 25 s is usually the show's music / title; whole stories are measured in 3-minute pieces)
        cuts = [("opening", 25.0, 120.0)]
        t = 145.0
        while t + 180 < d - 60:
            cuts.append(("middle", t, 180.0))
            t += 360.0
        cuts.append(("final", max(145.0, d - 300.0), 240.0))
        for lab, st, ln in cuts:
            f = features(load(s, st, ln), lab)
            if f:
                rows.append(f)
                parts[lab].append(f)
                parts["all"].append(f)
        per_file[os.path.basename(s)] = {"minutes": round(d / 60, 1), "pieces": len(rows)}
        log(f"  measured {os.path.basename(s)}: {len(rows)} pieces of {d / 60:.0f} min")
    if not parts["all"]:
        raise RuntimeError("the reference recordings could not be measured")
    meas = {k: _median_dict(v) for k, v in parts.items() if v}
    notes = {}
    try:
        with open(os.path.join(HERE, "assets", "style_model.json"), encoding="utf-8") as f:
            sm = json.load(f)
        narr, opens, fears, endings = [], [], [], []
        for _s, v in (sm.get("samples") or {}).items():
            for nb in v.get("notes", []):
                for stv in nb.get("stories", []):
                    narr.append(stv.get("narrator"))
                    opens.append(stv.get("opening"))
                    fears.append(stv.get("fear"))
                    endings.append(stv.get("turn_and_ending"))
        notes = {"narrator_presentation": [x for x in narr if x][:4], "opening_and_hook": [x for x in opens if x][:3],
                 "suspense_build": [x for x in fears if x][:3], "climax_and_ending": [x for x in endings if x][:3],
                 "craft": (sm.get("craft") or [])[:8]}
    except Exception:
        notes = {}
    a = meas["all"]
    prof = {"version": 1, "made": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
            "reference": per_file, "locked": True,
            "note": "THE default narration reference for every episode until the owner changes it.",
            "measured": meas,
            "listening_notes": notes,
            "direction": direction(meas),
            "direction_short": direction_short(meas),
            "pauses_for_the_sound_track": pauses_for(meas),
            "limitations": [
                "Voice identity: the reference presenter's own voice is not cloned (it is a real person's voice); the "
                "approved Gemini narrator voice is used, with this presenter's storytelling style.",
                "Speed, pauses, pitch movement, dynamics and rhythm are measured and directed; the voice provider "
                "follows directions, it cannot be set to an exact number - each episode is measured and reported.",
                "Pronunciation and emotional colour cannot be measured from sound alone here: they are directed from "
                "the listening notes, and checked only for speed / pitch / pauses."]}
    os.makedirs(os.path.dirname(PROFILE), exist_ok=True)
    with open(PROFILE, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=1)
    return prof


def _word(x, table):
    for lim, w in table:
        if x is not None and x <= lim:
            return w
    return table[-1][1]


def direction(meas):
    """the measured style -> how the narrator is told to tell the story (English, for the voice model)"""
    a, op, fi = meas.get("all", {}), meas.get("opening", {}), meas.get("final", {})
    rate = a.get("syllables_per_second_with_pauses") or 3.5         # (the pace a listener hears, pauses included)
    pace = _word(rate, [(2.6, "slow, unhurried"), (3.4, "calm, moderate"), (4.2, "brisk but clear"), (99, "quick")])
    pr = a.get("pitch", {}) or {}
    mv = pr.get("movement_semitones_sd") or 2.5
    pitchw = _word(mv, [(2.5, "a steady, low-key pitch with small movements"), (5.0, "natural pitch movement, warm and "
                        "conversational"), (99, "wide, expressive pitch movement")])
    ends = pr.get("falling_ends_share")
    endw = ("sentences usually settle DOWN at the end (a gentle fall), never a sing-song rise" if (ends or 0) >= 0.5 else
            "sentence ends stay mostly level, a slight fall at full stops")
    ps, pp = a.get("pause_sentence_s") or 0.6, a.get("pause_paragraph_s") or 1.3
    soft = a.get("near_whisper_share") or 0.0
    whisper = ("drops to a hushed, close-to-the-microphone level now and then - only at secret, dreadful moments"
               if soft > 0.05 else "hardly ever whispers - hushed only when a character truly must")
    op_rate, fi_rate = op.get("syllables_per_second_with_pauses"), fi.get("syllables_per_second_with_pauses")
    opening = ("the opening is told more slowly than the rest, letting the place and the silence sink in"
               if op_rate and op_rate < rate * 0.95 else "the opening keeps the same calm pace as the rest")
    climax = ("towards the end the telling tightens and speeds up slightly, with stronger emphasis on the key words"
              if fi_rate and fi_rate > rate * 1.04 else "the climax is not shouted: the same controlled pace, "
              "the weight comes from pauses and emphasis")
    return (f"Storyteller's delivery (measured from the approved reference): {pace} - about {rate:.1f} syllables a "
            f"second; {pitchw}; {endw}. Pause about {ps:.1f} s after a sentence and about {pp:.1f} s between "
            f"paragraphs, longer just before a reveal. {opening[0].upper() + opening[1:]}; mystery builds gradually; {climax}. "
            f"The voice {whisper}. "
            "Normal narration sounds natural and conversational, not every sentence frightening, no exaggerated horror "
            "voice; emotional scenes are told with feeling; a sudden horror event gets a short silence, then a firm, "
            "clear emphasis. The ending is told quietly, letting the last line hang.")


def direction_short(meas):
    """the same, short enough for the voice model's style line (a long instruction can be read out by mistake)"""
    a = meas.get("all", {})
    rate = a.get("syllables_per_second_with_pauses") or 3.5
    pace = _word(rate, [(2.6, "slow"), (3.4, "calm, moderate"), (4.2, "brisk"), (99, "quick")])
    ends = (a.get("pitch", {}) or {}).get("falling_ends_share") or 0
    return (f"Pace {pace}; natural, warm pitch movement; " + ("sentences settle down at the end; " if ends >= 0.5 else "")
            + f"a short pause after each sentence, longer before a reveal; hushed only at dreadful moments; "
            "not every sentence frightening; the climax controlled, weight from pauses; the ending quiet")


def pauses_for(meas):
    a = meas.get("all", {})
    clamp = lambda x, lo, hi, d: max(lo, min(hi, x if x else d))
    return {"between_lines_s": round(clamp(a.get("pause_sentence_s"), 0.3, 0.9, 0.5), 2),
            "between_scenes_s": round(clamp(a.get("pause_paragraph_s"), 0.8, 2.2, 1.2), 2)}


def profile():
    try:
        with open(PROFILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def tempo_for(wavs):
    """how much the narrator's recordings should be slowed (or quickened) to the reference speed: 0.90 - 1.06,
    1.0 when it is already close (within 6 %) or cannot be measured"""
    prof = profile()
    if not prof or not wavs:
        return 1.0
    pieces = []
    for w in wavs:
        try:
            pieces += [load(w), np.zeros(int(SR * 0.6))]
        except Exception:
            continue
        if sum(len(x) for x in pieces) > SR * 170:
            break
    if not pieces:
        return 1.0
    f = features(np.concatenate(pieces), "probe")
    ref = prof["measured"]["all"].get("syllables_per_second")
    if not f or not ref or not f.get("syllables_per_second"):
        return 1.0
    r = ref / f["syllables_per_second"]
    if abs(1 - r) < 0.06:
        return 1.0
    return round(max(0.90, min(1.06, r)), 3)


# ----------------------------------------------------------------------------------------------- the checker
TOL = {"syllables_per_second": 0.15, "pause_sentence_s": 0.35, "pause_paragraph_s": 0.4, "dynamics_db_p10_p90": 0.35}


def check_narration(wavs, out_json=None, log=print):
    """the finished narration of an episode (the narrator's clean line recordings, in order) against the profile"""
    prof = profile()
    if not prof:
        return None
    pieces = []
    for w in wavs:
        try:
            pieces.append(load(w))
            pieces.append(np.zeros(int(SR * 0.6)))
        except Exception:
            continue
    if not pieces:
        return None
    a = np.concatenate(pieces)
    rows_ = []                                            # (measured in 3-minute pieces, like the reference)
    step = int(SR * 180)
    for i in range(0, len(a), step):
        seg = a[i:i + step]
        if len(seg) > SR * 30:
            f = features(seg, "episode")
            if f:
                rows_.append(f)
    if not rows_:
        return None
    got = _median_dict(rows_)
    ref = prof["measured"]["all"]
    rows = []

    def cmp(name, g, r, tol):
        if g is None or r is None:
            rows.append({"what": name, "episode": g, "reference": r, "result": "not measured"})
            return
        dev = abs(g - r) / max(1e-6, abs(r))
        rows.append({"what": name, "episode": g, "reference": r, "deviation": round(dev, 2),
                     "result": "matches" if dev <= tol else "differs"})
    cmp("speaking speed (syllables/s)", got["syllables_per_second"], ref.get("syllables_per_second"), TOL["syllables_per_second"])
    cmp("pause between sentences (s)", got["pause_sentence_s"], ref.get("pause_sentence_s"), TOL["pause_sentence_s"])
    cmp("dynamics (dB, quiet to strong)", got["dynamics_db_p10_p90"], ref.get("dynamics_db_p10_p90"), TOL["dynamics_db_p10_p90"])
    gp, rp = got.get("pitch", {}), ref.get("pitch", {})
    cmp("pitch movement (semitones)", gp.get("movement_semitones_sd"), rp.get("movement_semitones_sd"), 0.35)
    cmp("sentence endings (semitones)", gp.get("sentence_end_change_semitones"), rp.get("sentence_end_change_semitones"), 0.8)
    cmp("rhythm (speed changes)", got.get("rhythm_rate_sd"), ref.get("rhythm_rate_sd"), 0.5)
    rep = {"made": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "lines": len(wavs),
           "episode": got, "comparison": rows,
           "matches": sum(1 for r in rows if r["result"] == "matches"),
           "differs": [r["what"] for r in rows if r["result"] == "differs"],
           "pause_track_used": prof.get("pauses_for_the_sound_track"),
           "limitations": prof.get("limitations", [])}
    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
    log(f"  narration vs the reference style: {rep['matches']}/{len(rows)} match"
        + (f"; differs: {', '.join(rep['differs'])}" if rep["differs"] else ""))
    return rep


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        p = build()
        print(json.dumps(p["measured"]["all"], indent=1))
        print(p["direction"])
    elif cmd == "check":
        print(json.dumps(check_narration(sys.argv[2:]), ensure_ascii=False, indent=1))
