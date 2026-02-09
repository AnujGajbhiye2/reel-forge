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
