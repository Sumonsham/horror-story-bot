# Daily Horror Story Bot — Final Complete Patch (v2, Zero Features Removed)

Ei ZIP-e apnar repo-r 5-ta exact fixed file dewa hoyeche—apnar kono unique feature (V8, tvtoon, engine2, Telegram control, series bible, podcast, map, voice style, quality gate, ityadi) baad dewa hoyni.

## Ki ki thik kora hoyeche:

1. `main.py` (repo-r root folder-e upload korun)
   - **Critical Cartoon Animation Fix (`ANIM_MODE=tvtoon`):** Agey `build_video()`-te `tvbot.render_part()` diye animated cartoon clip (`clip_XX.mp4`) toiri howar poreo `jobs.append(...)` hoye jeto, ar `render_clips()`-er parallel worker-gulo agey theke clip ache kina na dekhei oi animated clip-er opor static `tv_still_XX.jpg` slideshow overwrite kore dito.
   - Ekhon `tv_done` check add kora hoyeche ebong `render_clips()`-er shurutei already-rendered clip (`>= 1000 bytes`) filter kore baad dewa hoyeche. Fole apnar `tvtoon` animated cartoon clip ar overwrite hobe na, r kono scene fail korle classic fallback-o thikmoto kaj korbe.
   - Baki 15,276 line ebong shob unique feature 100% okkhoto ache.

2. `tvtoon/scene.py` (repo-r `tvtoon/` folder-e upload korun)
   - 9:16 portrait (Reels/Shorts) render-e nicher onshe shobshomoy halka badami (`#c9a172`) rong ashto; ekhon raat, horror, ghor (`ghar`), nouka (`boat`) ba train/bus/tram-er bhetore automatic dark background (`#121218`) ashbe.

3. `tvtoon/studio.py` (repo-r `tvtoon/` folder-e upload korun)
   - `QualityControl`-e `ffprobe`-er `r_frame_rate` porar jonno unsafe `eval()` shoriye safe fraction parsing add kora hoyeche.

4. `docs/podcast.json` ebong `docs/podcast.xml` (repo-r `docs/` folder-e upload korun)
   - `2026-11-24-14` ("জলঙ্গির ছাইমেটে যাত্রী") episode-er description theke bhul kore dhoke pora English `Chapter 2 / Chapter 3 / Chapter 5` summary shoriye porishkar Bangla bornona dewa hoyeche ebong RSS XML validate kora hoyeche.

## Upload korar por ja korben:
1. ZIP-ta extract kore ei 5-ta file exact folder path-e upload/replace kore commit korun.
2. Repo-te `TVTOON_OFF` variable set kora thakle sheta delete ba `0` rakhben, ar `.github/workflows/horror-story.yml`-e `ANIM_MODE: tvtoon` chalu ache kina ekbar dekhe neben.
