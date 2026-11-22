# Dependency and licence report (hybrid 2D MVP)

The MVP adds no new dependency. Everything it uses was already in the project or already installed by the workflow.

| Tool | Licence | How it gets here | GPU / desktop / model download | Used for |
|---|---|---|---|---|
| numpy, OpenCV (`opencv-python-headless`) | BSD-3 / Apache-2.0 | workflow `pip install` (existing) | no / no / no | images, cut-out, identity checks, raster |
| ffmpeg | LGPL/GPL build (BtbN) | workflow download (existing) | no / no / no | encoding H.264 + AAC |
| Rigby2D Python runtime (vendored, `engine2/rigby/runtime`) | MIT OR Apache-2.0 | in the repository, at the commit in `RIGBY2D_COMMIT` | no / no / no | rig poses |
| Rhubarb Lip Sync 1.14.0 | MIT | downloaded at run time by `rig_test` / `render_test` from its official GitHub release | no / no / no (`-r phonetic` needs no language model) | mouth timing; without it, the amplitude fallback is used and reported |
| Node 22 + Rigby2D CLI | MIT/Apache | only for rebuilding a rig (once per character, not daily) | no / no / no | AutoRig, joints, weights |

**Not used** (evaluated in `RIG_PIPELINE.md`):
- **SAM 2:** its model download is needed and it is not required for flat cartoon art.
- **OpenToonz:** needs an artist at the GUI.
- **Inpainting:** it would invent anatomy.
- **Rhubarb in this sandbox:** downloading it here was not permitted, so the local test run used the amplitude fallback.
