## Upgrade Plan (February 2026)

See `UPGRADE_PLAN.md` for the full implementation guide. Work through tiers in order.

### Priority Summary
1. **Tier 1 (this week):** Pillow-rendered karaoke captions (yellow highlight active word, Montserrat Black font), PyDub audio mixer (background music + SFX), upgraded script prompts with hook library
2. **Tier 2 (next 1-2 weeks):** Audio-reactive character bounce, Kokoro TTS integration, background clip crossfade transitions, expression switching per dialogue line
3. **Tier 3 (ongoing):** Rhubarb lip sync, zoom pulse effects, thumbnail optimization, auto-posting

### New Modules to Create
- `reelforge/captions/pillow_renderer.py` — Karaoke-style caption rendering with Pillow
- `reelforge/audio/mixer.py` — AudioMixer class for background music + SFX layering
- `reelforge/audio/kokoro_engine.py` — Kokoro-82M TTS integration (optional upgrade from EdgeTTS)
- `reelforge/animation/character_animator.py` — Audio-reactive character bounce animation
- `reelforge/animation/expression_mapper.py` — Map dialogue keywords to character pose PNGs
- `reelforge/script/hooks.py` — Hook template library and CTA templates

### New Dependencies
- `pydub` — audio mixing
- `kokoro` — better TTS (optional)
- `soundfile` — audio I/O for Kokoro
- `scipy` — audio amplitude analysis for character animation

### New Asset Directories
- `assets/fonts/Montserrat-Black.ttf` — Primary caption font
- `assets/sfx/whoosh/`, `assets/sfx/pop/`, `assets/sfx/sting/` — Sound effects
- `assets/music/` — Background music tracks
- `assets/characters/char_a/`, `assets/characters/char_b/` — Multiple poses per character
