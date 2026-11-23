# The remaining six characters (after the owner approves the samples)

They are built with the same engine and the same standard. Nothing in the engine has to be rewritten.

## Steps for each character
1. Turn the brief in `characters.PENDING` into a full identity spec in `characters.SPECS`. A spec has:
   - head shape;
   - face structure: eyes, nose, mouth;
   - hairstyle;
   - body proportions in heads;
   - costume, palette and personality.
2. Run `python -m tvtoon.production sample` with the new id included. The `qa.identity_distance` check against every other character must be 4 or more.
3. Check the sheets, the test clip and the lip-sync demo in the gallery. A character that is rejected is revised alone.
4. The owner writes `USER_APPROVED` in `tvtoon/approvals.json`.

## Briefs
| Category | Character | Brief | Differs from the sample by |
|---|---|---|---|
| Adult male | Gopal Kaku | tall, thin postman; long head, pointed nose, side-burns, khaki shirt and trousers, cloth bag | height, long head, costume |
| Adult female | Malati | plump cheerful fish-seller; round face, big bun, red-bordered yellow saree | round head, bun, wide body |
| Elderly male | Haran Kaka | short grumpy farmer; square head, grey stubble, gamchha on the shoulder, lungi | square head, stubble, lungi |
| Elderly female | Annapurna Pishi | tall strict aunt; long face, spectacles, purple saree | long face, glasses, colour |
| Boy | Titu | small shy boy; egg head, round glasses, bowl haircut, green shirt | glasses, hair, shy body language |
| Girl | Piu | tiny energetic girl; short bob, red frock, missing front tooth | bob hair, smaller, tooth gap |

## Still to add for all twelve characters
- A true side view and a back view: a turned puppet set per character.
- More locations: house interior, road, pond ghat, school.
- Voices: female and child voices come from the free Gemini key (`GEMINI_TTS_KEY`) on GitHub.
