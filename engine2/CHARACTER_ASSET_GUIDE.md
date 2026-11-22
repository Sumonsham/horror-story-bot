# Character asset guide

## Where assets live

| Path | What | Who writes it |
|---|---|---|
| `assets/character_library/<id>/v<N>/reference/original.png` | the ORIGINAL identity reference, never changed | `library_sync` (copy, sha256) |
| `assets/character_library/APPROVALS.json` | owner decisions | **the owner only** |
| `assets/character_art/<id>/pose_first/` | pose-first pictures; `originals/` holds the provider files byte for byte | `pose_art` |
| `assets/character_art/<id>/inbox/<pose>.png` | the owner's own drawings, which always win over generated ones | the owner |
| `assets/character_rigs/<id>/` | prep.json, layers, Rigby2D work file and export | rig rebuild (once per character) |

## Pose names the MVP understands

- `master` (rig pose, arms 35-45 deg away from the body);
- `stand`, `talk`, `listen`;
- `point_index` or `point`;
- `arm45`, `arm90`, `arm120`, `both_up`;
- `sit`, `walk1`..`walk4`;
- `fear` or `scared`.

## Rules for a drawing

- One complete figure per picture, on a plain background. The ground shadow is removed automatically.
- The same face, hair, moustache, shirt, trousers and sandals as the reference. The `asset_qa` identity check measures this; your eyes decide.
- The master: both arms clearly away from the torso, armpits visible, fingers visible, feet apart.
- Never crop a pose out of another picture. Never repair a failed master with patches.

## How to approve (owner)

Open `assets/character_library/APPROVALS.json` on GitHub, tap the pencil, and add an entry like this one (every pose has its own status):

```json
"hari": {"pose_first": {"arm45": "USER_APPROVED", "arm90": "USER_APPROVED", "point_index": "REJECTED"}}
```

Commit the change. Nothing is used in production before this, and a test can never write this file.
