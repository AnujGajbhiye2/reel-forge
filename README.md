# ReelForge 🎬

Semi-automated pipeline for producing faceless AI/tech social media reels (TikTok, Instagram Reels, YouTube Shorts).

## 📋 Project Status

| Phase | Module | Status |
|-------|--------|--------|
| 1 | Project Setup & Folder Structure | ✅ Complete |
| 2 | Config System | ✅ Complete |
| 3 | Script Generator (LLM) | ✅ Complete |
| 4 | TTS Engine (EdgeTTS) | ✅ Complete |
| 5 | Caption Generator (WhisperX) | 🔄 Next |
| 6 | Video Compositor (MoviePy) | ⏳ Planned |
| 7 | Pipeline Integration | ⏳ Planned |
| 8 | Advanced Features | ⏳ Planned |

## 🎯 What It Does

ReelForge generates 60-second vertical reels (1080×1920) with:
- ✅ AI-generated scripts using Gemini (or other LLMs)
- 🔄 AI voiceover narration (EdgeTTS - free, no API key needed)
- ⏳ Word-by-word animated captions (WhisperX)
- ⏳ Minecraft parkour / gameplay background footage
- ⏳ Cartoon character overlay
- ⏳ Optional screenshot overlays

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
cd reel-forge

# Activate virtual environment (already set up)
source venv/bin/activate

# Verify installation
python main.py --help
```

### 2. Configuration

1. Get a Gemini API key: https://aistudio.google.com/app/apikey
2. Add it to `config.yaml`:
   ```yaml
   gemini_api_key: "your-api-key-here"
   ```

### 3. Generate Your First Script

```bash
# Solo narrator style
python main.py script -t "ChatGPT-4" -d "Latest AI model from OpenAI" -s solo

# Dialogue style (two characters)
python main.py script -t "Cursor IDE" -d "AI-powered code editor" -s dialogue
```

## 📖 Available Commands

### `validate` - Check Configuration
```bash
python main.py validate
```
Validates config.yaml and checks all asset paths.

### `script` - Generate Scripts (Phase 3) ✅
```bash
# Generate a solo narrator script
python main.py script -t "Your Topic" -s solo

# Generate a dialogue script
python main.py script -t "Your Topic" -s dialogue -d "Extra context"

# Save to custom path
python main.py script -t "Your Topic" -o my_script.txt
```

**Features:**
- Hook in first 3 seconds
- 140-160 word target (~60 seconds)
- Short sentences (5-12 words)
- Conversational, energetic tone
- Strong call-to-action

### `list-voices` - List Available Voices ✅
```bash
# List all English voices
python main.py list-voices -l en

# List English male voices
python main.py list-voices -l en -g Male

# List English female voices
python main.py list-voices -l en -g Female

# List Spanish voices
python main.py list-voices -l es
```

### `tts` - Text-to-Speech (Phase 4) ✅
```bash
# From text
python main.py tts -t "Your text here" -o audio.mp3

# From script file
python main.py tts -s script.txt -o audio.mp3

# Dialogue with multiple voices
python main.py tts -s dialogue.txt -d -o dialogue_audio.mp3

# Custom voice and rate
python main.py tts -t "Fast speech" -o fast.mp3 -v en-US-GuyNeural -r "+20%"
```

**Features:**
- Free EdgeTTS voices (no API key needed)
- 322 voices across 100+ locales
- Adjustable rate and pitch
- Dialogue support with multiple voices
- Automatic audio concatenation

### `captions` - Generate Captions (Phase 5) ⏳
```bash
python main.py captions -a audio.mp3 -o captions.json
```
*Coming soon: WhisperX integration*

### `compose` - Compose Video (Phase 6) ⏳
```bash
python main.py compose -b background.mp4 -a audio.mp3 -c captions.json
```
*Coming soon: MoviePy video composition*

### `generate` - Full Pipeline (Phase 7) ⏳
```bash
python main.py generate "Your Topic" -s solo
```
*Coming soon: End-to-end generation*

### `drive-auth` - Google Drive OAuth Setup
```bash
python main.py drive-auth
```
Runs the one-time Google OAuth browser flow and writes a token JSON file.

### Google Drive Auto Upload
Enable upload after successful `generate` runs via `config.yaml`:
```yaml
integrations:
  google_drive:
    enabled: true
    parent_folder_id: "1rw-msgfUfL1K8PFEZs4eKvKKE4bmWQ82"
    oauth:
      client_secret_path: ".secrets/client_secret.json"
      token_path: ".secrets/google_drive_token.json"
```
Folder organization in Drive:
- `YYYY/MM/DD/run_<timestamp>[_run-name]/video.mp4`
- `YYYY/MM/DD/run_<timestamp>[_run-name]/metadata.json`

## 📁 Project Structure

```
reelforge/
├── config.yaml              # Configuration (API keys, settings)
├── main.py                  # CLI entry point
├── requirements.txt         # Python dependencies
├── reelforge/
│   ├── script_generator.py  # ✅ LLM script generation
│   ├── tts_engine.py        # 🔄 Text-to-speech
│   ├── caption_generator.py # ⏳ WhisperX captions
│   ├── video_compositor.py  # ⏳ MoviePy composition
│   ├── templates/
│   │   └── script_prompts.py # Prompt templates
│   └── utils/
│       └── helpers.py        # Config & file utilities
├── assets/
│   ├── backgrounds/         # 8 gameplay clips (Subway Surfers, Minecraft)
│   ├── characters/          # Character PNGs
│   ├── fonts/               # Poppins-ExtraBold.ttf
│   └── screenshots/         # Per-video overlays
├── output/                  # Generated videos and assets
└── tests/                   # Test suite
```

## 🎨 Assets Included

- **8 Background Videos**: Subway Surfers + Minecraft parkour clips
- **2 Character Images**: Character PNGs for overlay
- **Poppins-ExtraBold Font**: For captions

## ⚙️ Configuration

Edit `config.yaml` to customize:

```yaml
# API Keys
gemini_api_key: "your-key-here"

# Script Generation
script:
  model: "gemini-2.5-pro"
  fallback_models:
    - "gemini-2.5-flash"
    - "gemini-2.0-flash"
  temperature: 0.7

# TTS Settings
tts:
  voice: "en-US-ChristopherNeural"
  rate: "+5%"

# Video Settings
video:
  resolution:
    width: 1080
    height: 1920
  fps: 30
  duration: 60

# Caption Style
captions:
  font_size: 80
  font_color: "white"
  max_words_per_line: 3
```

## 🧪 Testing

```bash
# Run Phase 3 tests
python test_phase3.py

# Run unit tests (requires pytest)
pip install pytest
pytest tests/ -v
```

## 💰 Cost Estimate

| Service | Cost |
|---------|------|
| Gemini API (scripts) | $0-2/month (free tier available) |
| EdgeTTS (voice) | $0 (free) |
| WhisperX (captions) | $0 (local) |
| **Total** | **$0-2/month** |

## 🎬 Example Workflow (When Complete)

1. **Generate Script**
   ```bash
   python main.py script -t "ChatGPT-4" -s solo
   ```

2. **Generate Full Reel** (Phase 7)
   ```bash
   python main.py generate "ChatGPT-4" -s solo
   ```

3. **Review in Video Editor**
   - Open in CapCut or DaVinci Resolve
   - Add final touches
   - Export 1080×1920, 30fps

4. **Publish**
   - TikTok, Instagram Reels, YouTube Shorts
   - Add 5-10 hashtags

## 📚 Documentation

- `reelforge-blueprint.md` - Full architecture and implementation plan
- `PHASE3_COMPLETE.md` - Phase 3 completion summary
- `config.yaml` - Configuration reference

## 🔧 System Requirements

- Python 3.12+
- FFmpeg 6.1+ (installed)
- ImageMagick 6.9+ (installed)
- 8GB RAM minimum
- GPU recommended for WhisperX (CPU works but slower)

## 🤝 Contributing

This is a personal project following the blueprint in `reelforge-blueprint.md`. Each phase is implemented sequentially with full testing before moving to the next.

## 📝 License

This project is for educational purposes. Be mindful of:
- Gemini API terms of service
- Character image licensing (use original characters for production)
- Background footage licenses (included assets are for demonstration)

## 🔗 Resources

- [Gemini API](https://aistudio.google.com/app/apikey)
- [EdgeTTS](https://github.com/rany2/edge-tts)
- [WhisperX](https://github.com/m-bain/whisperx)
- [MoviePy](https://zulko.github.io/moviepy/)

---

**Current Version**: 0.1.0
**Last Updated**: Phase 3 Complete (Script Generator Module)
