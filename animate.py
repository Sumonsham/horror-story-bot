"""Character animation helpers used by main.scene_clip_animated (V8: this module was imported by main.py but was
missing from the repository, so speech-synced motion, blinking and lip movement were silently skipped).

Everything is local and free (numpy + OpenCV + ffmpeg) - no paid AI video service (ZERO_COST).
  voice_envelope(audio, fps)          -> 0..1 loudness per video frame (the speaking character moves with it)
  viseme_at(text, t, dur)             -> mouth shape at time t of a spoken line: "a" open, "e" wide, "o" round, "m" closed
  find_faces(rgb)                     -> faces in a cut-out character: box, eyes, mouth (x, y, width), skin colour
  draw_face(rgb, faces, blink, mouth, shape, gaze)  -> the picture with eyelids / mouth drawn for this frame
Face drawing stays OFF for horror unless the GitHub Variable FACE_ANIM=1 (as before); the voice-synced head
motion works always. Any failure returns the picture unchanged - the video is never stopped by this module.
"""
import subprocess

import numpy as np

_BILABIAL = set("mbpvfমবপভফ")
_OPEN = set("aআা")
_WIDE = set("eiyইঈএঐিীেৈ")
_ROUND = set("ouwউঊওঔুূোৌ")


def voice_envelope(audio, fps, sr=16000):
    """loudness (RMS) of the line's audio per video frame, smoothed, 0..1"""
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                             capture_output=True, timeout=300).stdout
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    except Exception:
        return np.zeros(0, dtype=np.float32)
    if x.size == 0:
        return np.zeros(0, dtype=np.float32)
    hop = max(1, int(round(sr / float(fps))))
    n = int(np.ceil(x.size / hop))
    x = np.pad(x, (0, n * hop - x.size))
    rms = np.sqrt((x.reshape(n, hop) ** 2).mean(axis=1) + 1e-12)
    if rms.size >= 3:
        rms = np.convolve(rms, np.ones(3) / 3.0, mode="same")
    top = float(np.percentile(rms, 95)) or 1.0
    env = np.clip((rms - 0.02 * top) / (top * 0.98), 0.0, 1.0)
    return env.astype(np.float32)


def viseme_at(text, t, dur):
    """the mouth shape at second t of a line lasting dur seconds (letters spread evenly over the line)"""
    letters = [c for c in str(text or "").lower() if c.isalpha() or "ঀ" <= c <= "৿"]
    if not letters or dur <= 0:
        return "a"
    i = min(len(letters) - 1, max(0, int(len(letters) * float(t) / float(dur))))
    c = letters[i]
    if c in _BILABIAL:
        return "m"
    for j in range(i, min(len(letters), i + 3)):       # the next vowel sound decides the shape
        if letters[j] in _ROUND:
            return "o"
        if letters[j] in _WIDE:
            return "e"
        if letters[j] in _OPEN:
            return "a"
    return "a"


def _cascade(name):
    import cv2
    path = getattr(cv2, "data", None)
    if path is None:
        return None
    c = cv2.CascadeClassifier(path.haarcascades + name)
    return None if c.empty() else c


def find_faces(rgb):
    """faces in an RGB picture: [{box, eyes: [(x, y, r)], mouth: (x, y, width), skin: (r, g, b)}]"""
    try:
        import cv2
        img = np.ascontiguousarray(np.asarray(rgb)[..., :3]).astype(np.uint8)
        gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))
        fc, ec = _cascade("haarcascade_frontalface_default.xml"), _cascade("haarcascade_eye.xml")
        if fc is None:
            return []
        faces = []
        min_side = max(40, min(img.shape[:2]) // 12)
        for (x, y, w, h) in fc.detectMultiScale(gray, 1.1, 6, minSize=(min_side, min_side)):
            eyes = []
            if ec is not None:
                roi = gray[y:y + h // 2, x:x + w]
                for (ex, ey, ew, eh) in ec.detectMultiScale(roi, 1.1, 5, minSize=(max(6, w // 10), max(6, h // 10)))[:2]:
                    eyes.append((int(x + ex + ew / 2), int(y + ey + eh / 2), int(max(ew, eh) / 2)))
            if len(eyes) < 2:                          # (typical eye places when the eyes were not found)
                eyes = [(int(x + w * 0.32), int(y + h * 0.40), int(w * 0.09)),
                        (int(x + w * 0.68), int(y + h * 0.40), int(w * 0.09))]
            cheek = img[int(y + h * 0.55):int(y + h * 0.65), int(x + w * 0.2):int(x + w * 0.35)]
            skin = tuple(int(v) for v in (cheek.reshape(-1, 3).mean(axis=0) if cheek.size else (150, 110, 90)))
            faces.append({"box": (int(x), int(y), int(w), int(h)), "eyes": eyes,
                          "mouth": (int(x + w / 2), int(y + h * 0.78), int(w * 0.36)), "skin": skin})
        return faces
    except Exception:
        return []


def draw_face(rgb, faces, blink=0.0, mouth=0.0, shape="a", gaze=(0.0, 0.0)):
    """eyelids (blink 0..1), a slight look left/right (gaze -1..1) and the mouth opening (0..1, shape a/e/o/m)"""
    try:
        import cv2
        pic = np.array(rgb, dtype=np.float32, copy=True)
        H, W = pic.shape[:2]
        for f in faces or []:
            x, y, w, h = f["box"]
            skin = np.array(f.get("skin") or (150, 110, 90), dtype=np.float32)
            for (ex, ey, er) in f.get("eyes") or []:
                x0, x1, y0, y1 = max(0, ex - er), min(W, ex + er), max(0, ey - er), min(H, ey + er)
                if x1 <= x0 or y1 <= y0:
                    continue
                gx = int(round(float(gaze[0] if gaze else 0.0) * er * 0.25))
                if gx:                                  # the eye content shifts a little towards the look
                    pic[y0:y1, x0:x1] = np.roll(pic[y0:y1, x0:x1], gx, axis=1)
                if blink > 0.02:                        # the lid comes down from the top
                    lid = np.zeros((H, W), np.float32)
                    cv2.ellipse(lid, (ex, int(ey - er + er * blink)), (er, max(1, int(er * blink))), 0, 0, 360, 1.0, -1)
                    lid = cv2.GaussianBlur(lid, (0, 0), max(1.0, er * 0.15))[..., None]
                    pic = pic * (1 - lid) + (skin * 0.85) * lid
            if mouth > 0.03 and shape != "m":
                mx, my, mw = f["mouth"]
                ax = max(2, int(mw * {"e": 0.55, "o": 0.30}.get(shape, 0.42)))
                ay = max(1, int(h * 0.10 * float(mouth) * {"o": 1.25, "e": 0.7}.get(shape, 1.0)))
                m = np.zeros((H, W), np.float32)
                cv2.ellipse(m, (mx, my), (ax, ay), 0, 0, 360, 1.0, -1)
                m = cv2.GaussianBlur(m, (0, 0), max(1.0, ay * 0.35))[..., None]
                inside = np.array([40, 18, 18], np.float32)
                pic = pic * (1 - 0.85 * m) + inside * (0.85 * m)
        return pic
    except Exception:
        return rgb
