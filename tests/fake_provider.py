"""A STAND-IN image provider for the offline tests ONLY: it draws the character with the code rig on the grey
studio background (3/4 view, arms and legs apart) so segmentation, rigging, QA, pause and resume can be tested
without Cloudflare. It says nothing about the real AI pictures' quality - that is tested on GitHub (art_test)."""
import cv2
import numpy as np

import cartoon_rig as R
import cinematic_camera as cc


class Fake:
    def __init__(self, design, limit_after=None, broken=()):
        self.design, self.calls, self.limit_after, self.broken = design, 0, limit_after, set(broken)

    def __call__(self, prompt, ref, seed, w, h):
        self.calls += 1
        if self.limit_after is not None and self.calls > self.limit_after:
            raise RuntimeError("Cloudflare: daily free allocation used up (4006)")
        img = np.full((h, w, 3), (180, 180, 180), np.uint8)
        ch = R.Character("x", dict(self.design, ink=(24, 20, 26)))
        if "establishing view" in prompt:                                       # a plate
            return cv2.imencode(".png", cv2.resize(np.full((576, 1024, 3), (60, 70, 50), np.uint8), (w, h)))[1].tobytes()
        piece = ("torso" if "ONLY the clothed TORSO" in prompt else "arm" if "ONLY ONE ARM" in prompt else
                 "legs" if "ONLY the LOWER BODY" in prompt else
                 "skirt" if "LOWER GARMENT" in prompt else "pallu" if "loose decorated END" in prompt else
                 "hair_back" if "BACK PART of this character's long hair" in prompt else None)
        if piece == "pallu":                                                  # a draped cloth end, drawn simply
            col = tuple(int(c) for c in self.design.get("lower", (40, 40, 170)))
            pts = np.array([(w * 0.35, h * 0.08), (w * 0.62, h * 0.08), (w * 0.7, h * 0.9), (w * 0.28, h * 0.92)], np.int32)
            cv2.fillPoly(img, [pts], col, cv2.LINE_AA)
            cv2.polylines(img, [pts], True, (24, 20, 26), 3, cv2.LINE_AA)
            bc = tuple(int(c) for c in self.design.get("border") or (40, 170, 220))
            cv2.line(img, (int(w * 0.29), int(h * 0.88)), (int(w * 0.69), int(h * 0.86)), bc, 10, cv2.LINE_AA)
            return cv2.imencode(".png", img)[1].tobytes()
        if piece == "hair_back":
            cam = cc.Camera(w, h)
            st = {"x": 960, "ground_y": 935, "facing": 0.8, "head_yaw": 0.6, "pose": dict(R.POSES["stand"]), "t": 0.0,
                  "only": {"hair_back"}}
            j = ch.joints(dict(st, ground_y=935 + ch.foot_floor(st)))
            cam.set(j["head"][0], j["head"][1] + 90, 0.86 * h / (330 * cam.base))
            ch.draw(R.Painter(img, cam), st)
            return cv2.imencode(".png", img)[1].tobytes()
        if piece == "skirt":
            piece, self_sari = "legs", True
        if piece:
            if piece in self.broken:
                return cv2.imencode(".png", img)[1].tobytes()
            cam = cc.Camera(w, h)
            only = {"torso": {"torso"}, "arm": {"near_arm"}, "legs": {"legs"}}[piece]
            if self.design.get("sari") or self.design.get("robe") or locals().get("self_sari"):   # a saree: blouse torso; the
                if piece == "torso":                                      # lower piece is the saree from the waist down
                    ch = R.Character("x", dict(self.design, sari=False, robe=False, hem=20, ink=(24, 20, 26)))
                elif piece == "legs":
                    only = {"torso", "legs"}
            pose = dict(R.POSES["stand"], uarm_n=0, farm_n=0, thigh_n=8, thigh_f=-8)
            st = {"x": 960, "ground_y": 935, "facing": 0.8, "head_yaw": 0.6, "pose": pose, "t": 0.0, "only": only}
            j = ch.joints(dict(st, ground_y=935 + ch.foot_floor(st)))
            ys = {"torso": (j["neck"][1] - 10, j["hip"][1] + 50), "arm": (j["sh_n"][1] - 15, j["hd_n"][1] + 40),
                  "legs": (j["hip"][1] - 10, 945)}[piece]
            z = 0.86 * h / ((ys[1] - ys[0]) * cam.base)
            cxw = j["sh_n"][0] if piece == "arm" else 960
            cam.set(cxw, (ys[0] + ys[1]) / 2, z)
            ch.draw(R.Painter(img, cam), st)
            if piece == "legs" and (self.design.get("sari") or self.design.get("robe")):
                cut = int(cam.to_screen(960, j["hip"][1] - 8)[1])
                img[:max(0, cut)] = (180, 180, 180)
            return cv2.imencode(".png", img)[1].tobytes()
        if "head and neck only" in prompt:
            view = "front" if "FRONT" in prompt else "profile" if "PROFILE" in prompt else "three_q"
            yaw = {"front": 0.0, "three_q": 0.6, "profile": 1.0}[view]
            cam = cc.Camera(w, h)
            hgt = self.design.get("height", 1.0)
            cam.set(960, 935 - 335 * hgt, 4.6 / hgt)
            ch.draw(R.Painter(img, cam), {"x": 960, "ground_y": 935, "facing": 1.0, "head_yaw": yaw, "pose": dict(R.POSES["stand"]),
                                          "brows": "fear" if "frightened" in prompt else "", "t": 0.0})
            img[int(h * 0.97):] = (180, 180, 180)
        else:
            if "body" in self.broken and self.calls == 1:
                return cv2.imencode(".png", img)[1].tobytes()                  # an empty picture: must fail the check
            cam = cc.Camera(w, h)
            cam.set(960, 935 - 175 * self.design.get("height", 1.0), 2.1 / self.design.get("height", 1.0))
            spread = 34 if "overlap" in self.broken else 52                 # a good A-pose / a bad overlapping one
            pose = dict(R.POSES["stand"], uarm_n=spread, farm_n=spread - 4, uarm_f=-spread + 2, farm_f=-spread + 6,
                        thigh_n=10, thigh_f=-10, shin_n=8, shin_f=-8)
            ch.draw(R.Painter(img, cam), {"x": 960, "ground_y": 935, "facing": 1.0 if "overlap" in self.broken else 0.55,
                                          "head_yaw": 0.6, "pose": pose, "t": 0.0})
        return cv2.imencode(".png", img)[1].tobytes()


class FakeMulti:
    """one stand-in provider for several characters: the look text in the prompt says whose picture it is"""

    def __init__(self, designs, limit_after=None):
        self.f = {k: Fake(d) for k, d in designs.items()}
        self.calls, self.limit_after = 0, limit_after

    def __call__(self, prompt, ref, seed, w, h):
        self.calls += 1
        if self.limit_after is not None and self.calls > self.limit_after:
            raise RuntimeError("HTTP 429: daily free allocation used up (4006)")
        for k, f in self.f.items():
            if k in prompt:
                return f(prompt, ref, seed, w, h)
        return next(iter(self.f.values()))(prompt, ref, seed, w, h)
