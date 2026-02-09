# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ReelForge is a semi-automated pipeline for generating faceless AI/tech social media reels (TikTok, Instagram Reels, YouTube Shorts). It generates 60-second vertical reels (1080×1920) with AI-generated scripts, voiceover narration, word-by-word animated captions, background footage, and optional character overlays.

## Architecture

### Core Pipeline Flow
1. **Script Generation** → LLM generates 140-160 word script optimized for 60-second reels
2. **Text-to-Speech** → EdgeTTS converts script to audio (with dialogue support)
3. **Caption Generation** → WhisperX generates word-level timestamps
4. **Video Composition** → MoviePy/FFmpeg assembles final video with all layers
5. **Quality Gates** → Validates duration, caption coverage, risky claims detection
6. **Optional Upload** → Google Drive integration for automated storage

### Package Structure (Post-Reorganization)

```
reelforge/
├── cli/                    # Click-based CLI commands
│   ├── app.py             # Main CLI entrypoint with command wiring
│   ├── commands/          # Individual command implementations
│   └── interactive/       # Interactive wizard for UI-driven workflow
├── pipeline/              # Orchestration and quality control
│   ├── orchestrator.py    # End-to-end generate pipeline with retry logic
│   ├── quality_gate.py    # Duration validation, risky claims detection
│   ├── outputs.py         # Output path resolution and helpers
│   └── drive_upload.py    # Google Drive upload post-processing
├── script/                # Script generation
│   ├── generator.py       # ScriptGenerator using Google Gemini
│   └── templates/prompts.py  # Prompt templates for solo/dialogue styles
├── audio/                 # Text-to-speech
│   └── tts_engine.py      # TTSEngine using EdgeTTS (free, no API key)
├── captions/              # Caption generation
│   └── whisperx_generator.py  # CaptionGenerator using WhisperX
├── video/                 # Video composition (canonical package)
│   └── compositor.py      # Moved from video_compositor.py
├── research/              # Screenshot research and overlay
│   └── screenshot_researcher.py  # Web scraping for contextual screenshots
├── integrations/          # External services
│   └── google_drive/uploader.py  # OAuth-based Drive uploader
├── core/                  # Core utilities
│   ├── logging.py         # Centralized logging setup
│   └── run_context.py     # RunPaths for output organization
├── shared/                # Shared configuration
│   └── config.py          # YAML config loading
└── video_compositor.py    # LEGACY: kept for test compatibility (monkeypatch targets)
```

**Important**: `main.py` remains the primary entrypoint (`python main.py <command>`) and provides backward compatibility shims for tests that import helpers from `main.*`.

### Configuration System

All configuration lives in `config.yaml`. Key sections:
- `script`: Gemini model selection, fallback models, temperature
- `tts`: Voice selection, rate/pitch adjustments
- `captions`: Font, size, positioning, words-per-line grouping
- `video`: Resolution, FPS, layout parameters, character positioning
- `integrations.google_drive`: OAuth paths, folder IDs, upload policies
- `research`: Screenshot auto-discovery settings (disabled by default)
- `generation.duration`: Min/max bounds (45-60s), max retries

**API Key Required**: Set your Gemini API key via environment variable or directly in `config.yaml` under `gemini_api_key`.

## Common Commands

### Development Setup
```bash
# Activate virtual environment (already set up)
source venv/bin/activate

# Verify installation
python main.py --help
```

### Testing
```bash
# Run full test suite
pytest tests/ -v

# Run specific test file
pytest tests/test_pipeline.py -v

# Run with coverage
pytest tests/ --cov=reelforge --cov-report=term-missing

# Compile check before committing
python -m compileall -q main.py reelforge
```

### CLI Commands

```bash
# Validate configuration and assets
python main.py validate

# Generate a script only (preview before full pipeline)
python main.py script -t "Your Topic" -s solo

# Generate TTS audio from script
python main.py tts -s script.txt -o audio.mp3

# List available EdgeTTS voices
python main.py list-voices -l en -g Male

# Full pipeline: script → audio → captions → video
python main.py generate "Your Topic" -s solo

# Dialogue style with two characters
python main.py generate "Your Topic" -s dialogue -d "Extra context"

# Use custom script (skip unreliable LLM generation)
python main.py generate -t "Your Topic" --custom-script path/to/script.txt -s dialogue

# Google Drive OAuth setup (one-time)
python main.py drive-auth
```

### Custom Script Mode (Bypass LLM Generation)

If Gemini/LLM generation is unreliable, you can provide your own script:

**Format for dialogue mode with MCP markers:**
```
REEL TITLE: Your Title Here

A: First line of dialogue
B: Second line with screenshot marker [SHOW:S1]
A: Third line
B: Fourth line with another marker [SHOW:S2]

S1=keyword1, S2=keyword2, S3=keyword3
```

**Usage:**
```bash
# Via CLI
python main.py generate -t "Topic" --custom-script my_script.txt -s dialogue

# Via interactive wizard
python main.py
# → Choose "Generate a new reel"
# → Select "dialogue" style
# → Answer "Yes" to "Do you want to provide your own script?"
# → Paste your script (Ctrl+D when done)
```

**Example:** See `example_custom_script.txt` for a complete example.

**Benefits:**
- ✅ No dependence on LLM API reliability
- ✅ Full control over dialogue content
- ✅ Manually tune timing and pacing
- ✅ Works with MCP markers for screenshot placement
```

### Configuration Validation
Before running generation, always verify:
1. `config.yaml` has valid Gemini API key
2. Asset paths exist: `assets/backgrounds/`, `assets/characters/`, `assets/fonts/`
3. At least one background video exists in `assets/backgrounds/`

## Key Implementation Details

### Duration Retry Logic
The pipeline uses a multi-attempt strategy to hit the 45-60 second target:
- Attempts 1-2: Use primary model (gemini-2.5-pro)
- Attempts 3+: Fall back to faster models (gemini-2.5-flash, gemini-2.0-flash)
- Each attempt refines constraints based on previous duration
- Best attempt (closest to midpoint) is kept as fallback if all fail

### Caption Grouping
Captions show 3 words at a time (configurable via `captions.max_words_per_line`) for readability. WhisperX provides word-level timestamps which are grouped in `VideoCompositor`.

### Video Layers (bottom to top)
1. **Background**: Randomly selected gameplay clip, looped/trimmed to audio duration
2. **Character**: PNG overlay positioned at bottom (configurable Y position)
3. **Screenshots** (optional): Research-generated or user-provided overlays
4. **Captions**: Word-grouped text clips with stroke/color styling

### Screenshot Research (Optional)
When `research.enabled: true`:
- Uses Playwright to capture web screenshots
- DuckDuckGo search for relevant URLs
- Prioritizes trusted domains (wikipedia, docs sites)
- Falls back to image search if capture fails
- Screenshots timed to script mentions

### Google Drive Integration
When `integrations.google_drive.enabled: true`:
- Uploads video + metadata JSON after successful generation
- Organizes as `YYYY/MM/DD/run_<timestamp>[_run-name]/`
- Uses OAuth2 flow (client_secret.json → token.json)
- Configurable retry/backoff on upload failures

## Quality Gates

Before accepting a video as successful:
1. **Duration check**: Audio must be within configured min/max bounds
2. **Caption coverage**: Word timestamps must cover ≥80% of audio duration
3. **Risky claims**: Detects absolute statements ("always", "never", "best") and warns
4. **Dialogue alternation** (dialogue mode only): Ensures strict speaker turn-taking

Failed quality gates trigger retries with adjusted constraints.

## Test Compatibility Notes

The reorganization maintains compatibility with existing tests:
- Tests importing from `main.py` (e.g., `main._assess_output_quality`) still work via shims
- `reelforge/video_compositor.py` kept as legacy home for `VideoCompositor` class
- Monkeypatches targeting `reelforge.video_compositor.ImageClip` remain functional

When writing new tests:
- Import from canonical package paths (e.g., `from reelforge.pipeline.quality_gate import ...`)
- Avoid adding new imports from `main.py` (legacy only)

## Script Generation Guidelines

### Solo Style
- Target: 140-160 words
- Structure: Hook (0-3s) → Body (3-50s) → CTA (50-60s)
- Tone: Conversational, energetic, short sentences (5-12 words)
- Avoid: Greetings, jargon, filler words

### Dialogue Style
- Target: 140-160 words total
- Structure: Alternating speakers (strict turn-taking required)
- Characters: Two distinct voices (configured in TTS)
- Speaker labels: `[PETER]` and `[STEWIE]` in script text

## External Dependencies

**Required System Packages:**
- FFmpeg 6.1+ (video processing)
- ImageMagick 6.9+ (MoviePy TextClip support)

**Python Dependencies:**
- `google-genai` for Gemini script generation
- `edge-tts` for free TTS (no API key needed)
- `whisperx` for word-level timestamps (requires PyTorch)
- `moviepy` for video composition
- `playwright` for screenshot research (requires `playwright install`)

## Logging

Logs are written to `logs/` directory:
- Dev mode: DEBUG level, console output enabled
- Prod mode: WARNING level, file only
- Each run creates timestamped log file
- Configured via `config.yaml` under `logging`

## Output Organization

Generated files go to `output/` with structure:
```
output/
└── YYYY/
    └── MM/
        └── DD/
            └── run_<timestamp>[_run-name]/
                ├── video.mp4
                ├── script.txt
                ├── audio.mp3
                ├── captions.json
                └── metadata.json
```

Custom output paths can be specified via `-o` flag.

## Common Pitfalls

1. **Missing Gemini API Key**: Pipeline will fail at script generation. Set in config.yaml or environment.
2. **No background videos**: Ensure at least one .mp4/.mov file exists in `assets/backgrounds/`
3. **WhisperX on CPU**: Slow but functional. GPU recommended for faster caption generation.
4. **Duration validation failures**: If scripts consistently fail duration checks, adjust `generation.duration.min_seconds` in config.
5. **Google Drive OAuth expiry**: Re-run `python main.py drive-auth` if uploads fail with auth errors.

## Development Workflow

1. Start with `python main.py validate` to ensure config is correct
2. Test script generation alone: `python main.py script -t "Topic"`
3. Test TTS separately: `python main.py tts -s script.txt`
4. Full pipeline once components work: `python main.py generate "Topic"`
5. Review output in CapCut/DaVinci Resolve before publishing

## References

- Blueprint: `reelforge-blueprint.md` (original architecture design)
- Reorganization: `docs/architecture/reorg-plan.md` (codebase cleanup record)
- Configuration: `config.yaml` (all runtime settings)
