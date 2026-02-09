# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Global Rules

- **DO NOT** write tests or documentation unless the user explicitly asks for it.
- **DO NOT** create .md files, README updates, or docstring additions unless explicitly requested.
- **DO NOT** add comments to code you didn't change.
- Keep changes minimal and focused on what was requested.

## Project Overview

ReelForge is a semi-automated pipeline for generating faceless AI/tech social media reels (TikTok, Instagram Reels, YouTube Shorts). It generates 45-60 second vertical reels (1080x1920) with AI-generated or user-provided scripts, voiceover narration, word-by-word animated captions, background footage, and optional character overlays.

## Architecture

### Pipeline Flow
1. **Script** - LLM generates or user provides a 100-140 word dialogue script with `[SHOW:S#]` markers
2. **Media Harvest** - Fetches screenshots for marker keywords via external screen-scraper
3. **TTS** - EdgeTTS converts clean script (markers stripped) to audio
4. **Captions** - WhisperX generates word-level timestamps
5. **Video Composition** - MoviePy assembles: background + characters + screenshots + captions
6. **Quality Gate** - Validates duration, coverage, format (lenient for custom scripts)

### Package Structure

```
reelforge/
├── cli/                    # Click-based CLI (app.py, commands/, interactive/)
├── pipeline/               # Orchestration (orchestrator.py, quality_gate.py, outputs.py)
├── script/                 # Script generation (generator.py, mcp_generator.py, types.py)
├── audio/                  # TTS engine (tts_engine.py)
├── captions/               # WhisperX caption generator (whisperx_generator.py)
├── media/                  # Media harvest client + marker resolver
├── research/               # Legacy screenshot researcher (fallback, disabled by default)
├── core/                   # Logging, run context
├── shared/                 # Config loading
├── integrations/           # Google Drive uploader
└── video_compositor.py     # VideoCompositor class
```

`main.py` is the CLI entrypoint (`python main.py <command>`).

## Common Commands

```bash
source venv/bin/activate
python main.py --help
python main.py validate
python main.py generate -t "Topic" -s dialogue --custom-script my_script.txt
pytest tests/ -v
python -m compileall -q main.py reelforge
```

### Custom Script Format (dialogue with markers)
```
A: First line of dialogue
B: Second line with screenshot marker [SHOW:S1]
A: Third line
B: Fourth line with another marker [SHOW:S2]

S1=keyword1, S2=keyword2
```

Word count targets: dialogue 100-130 words, solo 110-140 words. Custom scripts have wider tolerance.

## Key Config Sections (config.yaml)

- `script.use_mcp` - Enable MCP integration (default: true)
- `media_harvest.enabled` - Enable screenshot fetching (default: true)
- `generation.duration` - Min/max seconds (45-60), max retries (5)
- `captions` - Font size, safe zones, words per line
- `video` - Resolution, FPS, framing, character positioning

## Important Implementation Notes

- `[SHOW:S#]` markers are stripped from script text before TTS via `_strip_markers()` in orchestrator.py
- Custom scripts get 3s duration tolerance and soft word-count failures (won't trash the video)
- Console logging is at WARNING level; details go to log files in `logs/`
- MoviePy video rendering is silent (logger=None)

### MCP Integration (Simplified, 2026-02-09)

**Problem Solved**: Original MCP subprocess calls failed with "Invalid request parameters" (-32602) due to async stdio protocol mismatch.

**Current Implementation**:
- `MCPScriptGenerator` (`reelforge/script/mcp_generator.py`) uses direct Gemini SDK with MCP prompt template
- No subprocess complexity - simpler, more reliable, easier to debug
- Key methods: `generate()`, `parse_dialogue()`, `expand_short_script()`
- Output format: Dialogue lines with `[SHOW:S#]` markers + single keyword line at end
- Keyword format: `S1=subject1, S2=subject2` (comma-separated ID=subject pairs)
- `parse_dialogue()` handles A:, [A], (A) formats and strips REEL TITLE lines
- `expand_short_script()` regenerates with stricter constraints (doesn't expand existing text)

### Quality Gate Optimization (Early Checks, 2026-02-09)

**Problem Solved**: Quality checks ran AFTER 9+ minute video rendering, wasting time on videos that would fail validation.

**Current Implementation**:
- **Dialogue alternation** - checked in retry loop right after parsing (~line 221 in orchestrator.py)
  - Fails fast during generation attempts, provides specific feedback to LLM
- **Script word count** - checked in pre-render quality gate (after caption generation, ~line 330)
  - Catches too-long scripts before expensive rendering
- **Caption coverage** - checked in pre-render quality gate (after caption generation)
  - Critical: coverage < 0.75 fails immediately, prevents render when WhisperX transcription fails
- Final quality gate still runs for metadata/reporting purposes
- Result: Quality failures caught in seconds, not after 9+ minutes


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
