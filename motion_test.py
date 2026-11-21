"""MOTION TEST - the movements alone (no dialogue), to judge that they look like real people:
a man walks in (speeds up, slows down, stops), the seated friend stands up (leans forward, pushes up), walks to him,
they shake hands (the hands meet, three shakes), hug (arms round, lean in), the visitor turns (head first) and walks
away, the friend looks back after him. Every step goes through the planner AND the MOTION assistant.

    python motion_test.py   -> work/motion_test/motion_test.mp4 + motion_report.json
"""
import json
import os
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import animation_quality_check as qc  # noqa: E402
import animation_renderer  # noqa: E402
import character_designer as CD  # noqa: E402
import scene_planner  # noqa: E402
import story_test  # noqa: E402

OUT = os.path.join(HERE, "work", "motion_test")


def run(W=1280, H=720, fps=24, log=print):
    os.makedirs(OUT, exist_ok=True)
    people = [{"id": "ramesh", "name": "Ramesh", "gender": "male", "age": "old", "kind": "human",
               "look": "a village elder of about sixty-five, short grey hair, grey moustache, a cream kurta and white dhoti, a brown shawl"},
              {"id": "kamal", "name": "Kamal", "gender": "male", "age": "young", "kind": "human",
               "look": "a young man of about twenty-five, neatly combed black hair, a green shirt and grey trousers, a cloth bag"}]
    chars = [{"id": c["id"], "design": CD.design(c)[0], "name": c["name"]} for c in people]
    beats = [(2.0, "enter", "kamal"), (5.5, "stand_up", "ramesh"), (7.5, "handshake", "ramesh"), (14.0, "hug", "kamal"),
             (18.5, "exit", "kamal"), (19.5, "look", "ramesh")]
    lines = [{"i": k + 1, "speaker": "narrator", "listener": None, "t0": t, "t1": t + 0.5, "clip": None} for k, (t, _, _) in enumerate(beats)]
    ops = [{"line": k + 1, "op": op, "who": who, "target": ("kamal" if who == "ramesh" else "ramesh"), "ongoing": False}
           for k, (_, op, who) in enumerate(beats)]
    plan, _ = scene_planner.plan_from_story({"id": "M", "location": "pond", "weather": {}, "duration": 27.0, "lead_in": 2.0,
                                             "characters": chars, "lines": lines, "ops": ops})
    plan["camera"] = [{"t0": 0.0, "t1": 5.0, "type": "wide", "z0": 1.0, "z1": 1.15, "cx": 1000, "cy": 640},
                      {"t0": 5.0, "t1": 18.5, "type": "two_shot", "a": "ramesh", "b": "kamal", "z": 1.75, "push": 0.04},
                      {"t0": 18.5, "t1": 27.0, "type": "wide", "z0": 1.15, "z1": 1.05, "cx": 1000, "cy": 640}]
    n = int(plan["duration"] * story_test.SR)
    mix = story_test.ambience(plan, n)
    mix = mix / (np.abs(mix).max() + 1e-6) * 0.7
    audio = os.path.join(OUT, "motion.wav")
    with wave.open(audio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(story_test.SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    video = os.path.join(OUT, "motion_test.mp4")
    rep, scene = animation_renderer.render(plan, {}, video, os.path.join(OUT, "chunks"), W, H, fps, audio, log=log)
    q = qc.check(video, plan, rep, scene)
    report = {"motion_assistant": plan["motion_report"], "actions": plan["actions"], "render": rep, "quality": q}
    with open(os.path.join(OUT, "motion_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    log(plan["motion_report"]["summary_bn"])
    log(json.dumps({k: v.get("pass") for k, v in q.items() if isinstance(v, dict)}))
    return report


if __name__ == "__main__":
    run()
