"""ENGINE 2 - the permanent, reusable 2D cartoon animation engine (versioned, separate from the production engine).

Stage 2 (this version): the PERMANENT CHARACTER ASSET LIBRARY (library.py).
The production engine is not touched; engine 2 is switched OFF (ENGINE2 is not read by any production path yet).
Nothing here calls an image generator: the library only stores, checks and versions what already exists or what an
explicit asset-creation run (char_sheet) made, and it NEVER grants visual approval - only the owner does
(assets/character_library/APPROVALS.json, edited by hand).
"""
ENGINE_VERSION = "2.0.0-stage2"
