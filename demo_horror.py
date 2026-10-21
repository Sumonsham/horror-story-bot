"""DEMO ONLY (posts nothing): a ~20 second horror sample made with the REAL bot code -
AI pictures, expressive voices, lip sync, blinking, frightened darting eyes, ghost voice.
Output: work/demo_horror.mp4 (download from the run page, 'Artifacts')."""
import os
import shutil
import subprocess

import extras
import main as M

os.makedirs(M.WORK, exist_ok=True)
J = lambda n: os.path.join(M.WORK, n)
M.FONT = M.find_font("bn")

story = {"setting": "an abandoned old zamindar mansion in rural Bengal at night, broken windows, a lantern, cobwebs, "
                    "moonlight through dust, ultra realistic, cinematic",
         "characters": [
             {"name": "Mitali", "gender": "female", "age": "young", "kind": "human",
              "look": "young Bengali woman, 24, long black hair, big frightened eyes, red-bordered white cotton "
                      "saree, small red bindi, holding a brass lantern"},
             {"name": "Chhaya", "gender": "female", "age": "adult", "kind": "ghost",
              "look": "pale female ghost in a faded red wedding saree, long wet black hair over half her face, "
                      "hollow white glowing eyes, grey cracked skin"}]}
cast = M.Cast(story)
seed = 777
M.make_cast_sheet(cast, J("sheet.jpg"), seed)
shots = [
    ("mitali", "Close-up of Mitali's terrified face lit by her lantern, looking straight at the camera, "
               "whispering, sweat on her forehead, dark corridor behind her", "dark corridor of the mansion", ["Mitali"]),
    ("ghost", "Medium close-up of the female ghost Chhaya standing in the moonlit doorway, facing the camera, "
              "slowly speaking, hair over half her face", "broken doorway of the mansion", ["Chhaya"]),
]
for k, action, place, names in shots:
    M.log(f"picture: {k}")
    if not M.make_image(cast, action, place, names, J(k + ".jpg"), seed):
        raise SystemExit(f"could not make picture {k}")

voices = M.Voices("bn", cast)
lines = [
    ("mitali", {"speaker": "Mitali", "emotion": "whisper", "delivery": "terrified trembling whisper, slow",
                "text": "কে... কে ওখানে? আমি জানি, তুমি অন্ধকারে দাঁড়িয়ে আছো।",
                "voice_text": "<gasp> কে... কে ওখানে? <short pause> আমি জানি, তুমি অন্ধকারে দাঁড়িয়ে আছো।"}),
    ("ghost", {"speaker": "Chhaya", "emotion": "eerie", "delivery": "slow, cold, cruel whisper, then a low laugh",
               "text": "এত বছর ধরে তোর অপেক্ষায় ছিলাম, মিতালি। আজ আর তুই পালাতে পারবি না।",
               "voice_text": "এত বছর ধরে তোর অপেক্ষায় ছিলাম, মিতালি। <long pause> আজ আর তুই পালাতে পারবি না। <cackle>"}),
]
clips = []
for i, (k, ln) in enumerate(lines):
    a = J(f"audio_{i}.wav")
    d, subs = M.make_scene_audio([ln], voices, "bn", i, ["wind"], "tense" if i == 0 else "scare", a,
                                 ["old house wind howling"], "dark corridor")
    talk = [(st, st + du, nar, ln.get("emotion", ""), tx) for (st, du, nar, tx) in subs]
    c = J(f"clip_{i}.mp4")
    M.scene_clip([(J(k + ".jpg"), 0.0)], a, c, i, "tense" if i == 0 else "scare", talk)
    clips.append(c)
with open(J("list.txt"), "w") as f:
    f.writelines(f"file '{os.path.basename(c)}'\n" for c in clips)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", J("list.txt"),
                "-c", "copy", J("demo_horror.mp4")], check=True)
for k, *_ in shots:
    shutil.copy(J(k + ".jpg"), J("pic_" + k + ".jpg"))
M.log("DEMO READY: work/demo_horror.mp4")
