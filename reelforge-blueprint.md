# ReelForge — Faceless AI/Tech Reel Pipeline

## PROJECT CONTEXT (Transfer this entire file to Claude Code)

This document contains the complete research, architecture, and step-by-step implementation plan for building a semi-automated system that produces faceless AI/tech social media reels (TikTok, Instagram Reels, YouTube Shorts) in the style of @algorithmswithpeter on Instagram.

## IMPLEMENTATION NOTE (2026-02-08)

For the current repository folder layout and compatibility shims, see:

- `docs/architecture/reorg-plan.md`

`reorg-plan.md` is the canonical record of code organization changes made after this blueprint.

### What the final videos look like
- 60-second vertical reels (1080×1920, 9:16)
- AI-generated voiceover narrating a tech topic (no real voice)
- Minecraft parkour / satisfying gameplay as background footage
- Cartoon character (e.g., Peter Griffin) overlaid at bottom of frame
- Bold, word-by-word animated captions overlaid on screen
- Optional screenshot/screen recording overlays of the tool being discussed
- Hashtags and caption for posting

### User workflow
1. User provides: topic idea + optional screenshots/links
2. System generates: script → voiceover audio → word-level timestamps → composited video
3. User reviews in CapCut/DaVinci Resolve for final tweaks → publishes

### Budget: $10-30/month | Automation level: Semi-automated | Character: Cartoon overlay

---

## ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────┐
│                    INPUT LAYER                           │
│  User provides: topic, screenshots, links, preferences  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              STEP 1: SCRIPT GENERATION                   │
│  Tool: OpenAI API / Ollama / DeepSeek / Claude API       │
│  Input: topic + template prompt                          │
│  Output: structured script (hook + body + CTA)           │
│  Target: 140-160 words, ~60 seconds at 150 WPM           │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              STEP 2: VOICEOVER (TTS)                     │
│  Tool: EdgeTTS (free) or ElevenLabs ($5/mo) or          │
│        Voicebox.sh (free, local GPU required)            │
│  Input: script text                                      │
│  Output: voiceover.mp3                                   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│         STEP 3: WORD-LEVEL TIMESTAMPS                    │
│  Tool: WhisperX (free, local)                            │
│  Input: voiceover.mp3                                    │
│  Output: word_segments [{word, start, end}, ...]         │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│            STEP 4: VIDEO COMPOSITING                     │
│  Tool: MoviePy + FFmpeg (free)                           │
│  Layers (bottom to top):                                 │
│    1. Background gameplay (Minecraft/satisfying clip)    │
│    2. Cartoon character PNG (bottom-center)              │
│    3. Screenshot overlays (timed to narration)           │
│    4. Word-by-word captions (from WhisperX timestamps)   │
│  Input: all assets + timestamps                          │
│  Output: draft_video.mp4                                 │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│         STEP 5: HUMAN REVIEW + PUBLISH                   │
│  Tool: CapCut (free) or DaVinci Resolve (free)           │
│  User: reviews, tweaks timing, adds finishing touches    │
│  Exports: 1080x1920, 30fps, H.264                       │
│  Publishes to: TikTok, Instagram Reels, YouTube Shorts   │
└─────────────────────────────────────────────────────────┘
```

---

## PROJECT STRUCTURE

```
reelforge/
├── README.md
├── requirements.txt
├── config.yaml                  # API keys, voice settings, paths
├── main.py                      # CLI entry point
├── reelforge/
│   ├── __init__.py
│   ├── script_generator.py      # Step 1: LLM script generation
│   ├── tts_engine.py            # Step 2: Text-to-speech (EdgeTTS/ElevenLabs)
│   ├── caption_generator.py     # Step 3: WhisperX word-level timestamps
│   ├── video_compositor.py      # Step 4: MoviePy video assembly
│   ├── templates/
│   │   └── script_prompts.py    # Prompt templates for different video styles
│   └── utils/
│       ├── __init__.py
│       └── helpers.py           # File handling, config loading
├── assets/
│   ├── backgrounds/             # Minecraft parkour clips (.mp4)
│   ├── characters/              # Cartoon character PNGs (transparent)
│   ├── fonts/                   # Poppins-ExtraBold.ttf etc.
│   └── screenshots/             # Per-video screenshot overlays
├── output/                      # Generated videos land here
└── tests/
    └── test_pipeline.py
```

---

## STEP-BY-STEP IMPLEMENTATION PLAN

### Phase 1: Project Setup & Dependencies

```bash
mkdir reelforge && cd reelforge
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Core dependencies
pip install edge-tts moviepy openai pyyaml pillow click

# WhisperX (for word-level timestamps)
# NOTE: WhisperX requires PyTorch - install PyTorch first for your system
# See https://pytorch.org/get-started/locally/
pip install torch torchaudio  # CPU version, or with CUDA
pip install whisperx

# System dependencies (user must install externally):
# - FFmpeg: https://ffmpeg.org/download.html
# - ImageMagick: https://imagemagick.org/script/download.php (needed by MoviePy TextClip)
```

**⚠️ EXTERNAL STEPS THE USER MUST DO:**
1. Install FFmpeg system-wide (`brew install ffmpeg` / `apt install ffmpeg` / `choco install ffmpeg`)
2. Install ImageMagick system-wide (`brew install imagemagick` / `apt install imagemagick`)
3. Download Poppins-ExtraBold.ttf from Google Fonts → place in `assets/fonts/`
4. (Optional) Sign up for ElevenLabs ($5/mo Starter) at https://elevenlabs.io if you want voice cloning
5. (Optional) Get an OpenAI API key at https://platform.openai.com if using GPT for scripts
6. Download 5-10 Minecraft parkour clips from Pixabay → place in `assets/backgrounds/`
7. Download cartoon character PNGs (transparent) → place in `assets/characters/`

---

### Phase 2: Config System

**config.yaml:**
```yaml
# Script generation
script:
  provider: "openai"  # "openai", "ollama", "deepseek", "claude"
  model: "gpt-4o-mini"  # or "llama3" for ollama
  api_key: ""  # Leave empty for ollama
  base_url: ""  # For ollama: http://localhost:11434/v1

# Text-to-speech
tts:
  provider: "edge"  # "edge", "elevenlabs", "voicebox"
  voice: "en-US-GuyNeural"  # EdgeTTS voice name
  rate: "+10%"  # Speed adjustment
  # ElevenLabs settings (if provider is "elevenlabs")
  elevenlabs_api_key: ""
  elevenlabs_voice_id: ""
  elevenlabs_model: "eleven_multilingual_v2"

# Video settings
video:
  width: 1080
  height: 1920
  fps: 30
  codec: "libx264"
  audio_codec: "aac"

# Caption style
captions:
  font: "assets/fonts/Poppins-ExtraBold.ttf"
  font_size: 72
  color: "yellow"
  stroke_color: "black"
  stroke_width: 4
  position_y: 0.45  # Relative to frame height (0.0 = top, 1.0 = bottom)
  max_words_per_line: 3  # Show 3 words at a time instead of 1

# Character overlay
character:
  default_image: "assets/characters/peter.png"
  height: 400  # Pixel height of character on screen
  position_y: 1400  # Pixels from top (for 1920 height, ~73% down)

# Paths
paths:
  backgrounds_dir: "assets/backgrounds"
  characters_dir: "assets/characters"
  fonts_dir: "assets/fonts"
  output_dir: "output"
```

---

### Phase 3: Script Generator Module

**reelforge/templates/script_prompts.py** — Contains prompt templates:

```python
SOLO_NARRATOR_PROMPT = """Write a 60-second voiceover script (140-160 words) for a faceless tech reel.

Topic: {topic}
{context}

FORMAT RULES:
1. HOOK (first sentence): Bold, contrarian, or curiosity-inducing statement. Under 15 words. Must stop the scroll.
2. BODY: Explain the topic in simple, conversational language. Short sentences (5-12 words each). Use analogies. ONE concept only. No jargon.
3. CTA (last sentence): End with "Follow for more daily AI tips" OR a binary choice question that triggers comments.

STYLE: Casual, energetic, slightly humorous. Like explaining to a smart friend.
NO: Greetings, "hey guys", filler words, multiple topics.

Output ONLY the script text, no labels or formatting."""

DIALOGUE_PROMPT = """Write a 60-second dialogue script (140-160 words) for a faceless tech reel featuring two characters.

Topic: {topic}
{context}

CHARACTERS:
- PETER: Curious everyman. Asks "dumb" but relatable questions. Speaks simply.
- STEWIE: Tech expert. Explains with analogies and humor. Slightly condescending but helpful.

FORMAT:
[PETER] (hook question — must create curiosity, under 15 words)
[STEWIE] (explanation — clear, conversational, uses analogies)
[PETER] (follow-up question or amazed reaction)
[STEWIE] (deeper explanation or practical tip)
[PETER] (closing reaction)
[STEWIE] (CTA: "Follow for more" or binary choice question)

RULES: Short sentences only (5-12 words). One concept. No jargon. No greetings.

Output ONLY the dialogue with [PETER] and [STEWIE] labels."""
```

**reelforge/script_generator.py:**

```python
import openai
import yaml
from reelforge.templates.script_prompts import SOLO_NARRATOR_PROMPT, DIALOGUE_PROMPT

class ScriptGenerator:
    def __init__(self, config: dict):
        self.config = config["script"]
        self.client = openai.OpenAI(
            api_key=self.config.get("api_key", "not-needed"),
            base_url=self.config.get("base_url") or None
        )

    def generate(self, topic: str, context: str = "", style: str = "solo") -> str:
        """Generate a reel script from a topic.

        Args:
            topic: The main topic (e.g., "DeepAI platform")
            context: Optional extra context (links, features, screenshots description)
            style: "solo" for single narrator, "dialogue" for Peter/Stewie style

        Returns:
            Script text ready for TTS
        """
        template = DIALOGUE_PROMPT if style == "dialogue" else SOLO_NARRATOR_PROMPT
        prompt = template.format(
            topic=topic,
            context=f"Additional context: {context}" if context else ""
        )

        response = self.client.chat.completions.create(
            model=self.config["model"],
            messages=[
                {"role": "system", "content": "You are a viral short-form content scriptwriter specializing in AI and tech topics."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=500
        )

        return response.choices[0].message.content.strip()
```

---

### Phase 4: TTS Engine Module

**reelforge/tts_engine.py:**

```python
import asyncio
import edge_tts
import os

class TTSEngine:
    def __init__(self, config: dict):
        self.config = config["tts"]
        self.provider = self.config["provider"]

    async def _generate_edge(self, text: str, output_path: str) -> str:
        """Generate audio using EdgeTTS (free, no API key)."""
        communicate = edge_tts.Communicate(
            text,
            voice=self.config.get("voice", "en-US-GuyNeural"),
            rate=self.config.get("rate", "+0%")
        )
        await communicate.save(output_path)
        return output_path

    async def _generate_elevenlabs(self, text: str, output_path: str) -> str:
        """Generate audio using ElevenLabs API."""
        # Requires: pip install elevenlabs
        from elevenlabs import generate, save
        audio = generate(
            text=text,
            voice=self.config["elevenlabs_voice_id"],
            model=self.config.get("elevenlabs_model", "eleven_multilingual_v2"),
            api_key=self.config["elevenlabs_api_key"]
        )
        save(audio, output_path)
        return output_path

    def generate(self, text: str, output_path: str = "output/voiceover.mp3") -> str:
        """Generate voiceover audio from text.

        Args:
            text: Script text to convert to speech
            output_path: Where to save the audio file

        Returns:
            Path to the generated audio file
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if self.provider == "edge":
            return asyncio.run(self._generate_edge(text, output_path))
        elif self.provider == "elevenlabs":
            return asyncio.run(self._generate_elevenlabs(text, output_path))
        else:
            raise ValueError(f"Unknown TTS provider: {self.provider}")

    def generate_dialogue(self, script: str, output_path: str = "output/voiceover.mp3") -> str:
        """Generate dialogue audio with alternating voices for [PETER]/[STEWIE] labels.

        Splits the dialogue, generates each part separately, then concatenates.
        """
        import re
        from moviepy import concatenate_audioclips, AudioFileClip

        # Parse dialogue into segments
        segments = re.findall(r'\[(PETER|STEWIE)\]\s*(.*?)(?=\[(?:PETER|STEWIE)\]|$)', script, re.DOTALL)

        voice_map = {
            "PETER": self.config.get("voice", "en-US-GuyNeural"),
            "STEWIE": self.config.get("voice_alt", "en-US-AndrewNeural"),
        }

        audio_clips = []
        temp_files = []

        for i, (speaker, text) in enumerate(segments):
            temp_path = f"output/temp_dialogue_{i}.mp3"
            temp_files.append(temp_path)

            # Temporarily swap voice
            original_voice = self.config["voice"]
            self.config["voice"] = voice_map.get(speaker, original_voice)

            self.generate(text.strip(), temp_path)
            self.config["voice"] = original_voice

            audio_clips.append(AudioFileClip(temp_path))

        # Concatenate all segments
        final_audio = concatenate_audioclips(audio_clips)
        final_audio.write_audiofile(output_path)

        # Cleanup temp files
        for f in temp_files:
            os.remove(f)

        return output_path
```

---

### Phase 5: Caption Generator Module

**reelforge/caption_generator.py:**

```python
import whisperx
import torch

class CaptionGenerator:
    def __init__(self, device: str = None):
        """Initialize WhisperX for word-level timestamp generation.

        Args:
            device: "cuda" for GPU, "cpu" for CPU. Auto-detects if None.
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.compute_type = "float16" if self.device == "cuda" else "int8"

    def generate_timestamps(self, audio_path: str) -> list[dict]:
        """Generate word-level timestamps from an audio file.

        Args:
            audio_path: Path to the voiceover audio file

        Returns:
            List of dicts: [{"word": "Stop", "start": 0.12, "end": 0.45}, ...]
        """
        # Load and transcribe
        model = whisperx.load_model("base", self.device, compute_type=self.compute_type)
        audio = whisperx.load_audio(audio_path)
        result = model.transcribe(audio, batch_size=16)

        # Align for word-level timestamps
        model_a, metadata = whisperx.load_align_model(language_code="en", device=self.device)
        aligned = whisperx.align(
            result["segments"], model_a, metadata, audio, self.device,
            return_char_alignments=False
        )

        # Extract word segments
        word_segments = []
        for segment in aligned["segments"]:
            for word_info in segment.get("words", []):
                if "start" in word_info and "end" in word_info:
                    word_segments.append({
                        "word": word_info["word"],
                        "start": word_info["start"],
                        "end": word_info["end"]
                    })

        return word_segments

    def generate_ass_subtitles(self, word_segments: list[dict], output_path: str,
                                font: str = "Poppins ExtraBold", font_size: int = 48,
                                color: str = "&H0000FFFF",  # Yellow in ASS BGR format
                                outline_color: str = "&H00000000",
                                outline_width: int = 4,
                                words_per_group: int = 3) -> str:
        """Generate ASS subtitle file from word timestamps for FFmpeg burning.

        This is the PERFORMANT alternative to MoviePy TextClips.
        Group words into chunks of `words_per_group` for readability.

        Args:
            word_segments: Output from generate_timestamps()
            output_path: Where to save the .ass file
            words_per_group: Number of words to show at once (3 is standard)

        Returns:
            Path to the .ass file
        """
        # ASS header
        header = f"""[Script Info]
Title: ReelForge Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{color},&H000000FF,{outline_color},&H00000000,-1,0,0,0,100,100,0,0,1,{outline_width},0,5,50,50,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        # Group words
        events = []
        for i in range(0, len(word_segments), words_per_group):
            group = word_segments[i:i + words_per_group]
            text = " ".join(w["word"] for w in group)
            start = group[0]["start"]
            end = group[-1]["end"]

            # Format time as H:MM:SS.CC
            start_str = self._format_ass_time(start)
            end_str = self._format_ass_time(end)

            events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events))

        return output_path

    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        """Convert seconds to ASS time format H:MM:SS.CC"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
```

---

### Phase 6: Video Compositor Module

**reelforge/video_compositor.py:**

```python
import os
import random
import subprocess
from moviepy import (
    VideoFileClip, AudioFileClip, ImageClip,
    CompositeVideoClip, TextClip, concatenate_videoclips
)

class VideoCompositor:
    def __init__(self, config: dict):
        self.config = config
        self.video_cfg = config["video"]
        self.char_cfg = config["character"]
        self.caption_cfg = config["captions"]

    def select_background(self, duration: float) -> VideoFileClip:
        """Pick a random background clip and loop/trim to match audio duration."""
        bg_dir = self.config["paths"]["backgrounds_dir"]
        clips = [f for f in os.listdir(bg_dir) if f.endswith(('.mp4', '.mov', '.webm'))]

        if not clips:
            raise FileNotFoundError(f"No background clips found in {bg_dir}")

        chosen = os.path.join(bg_dir, random.choice(clips))
        bg = VideoFileClip(chosen)

        # Loop if clip is shorter than audio
        if bg.duration < duration:
            loops_needed = int(duration / bg.duration) + 1
            bg = concatenate_videoclips([bg] * loops_needed)

        # Trim to exact duration and resize to 9:16
        bg = bg.subclipped(0, duration)
        bg = bg.resized((self.video_cfg["width"], self.video_cfg["height"]))

        return bg

    def create_character_overlay(self, duration: float, character_path: str = None) -> ImageClip:
        """Create a character image overlay positioned at bottom of frame."""
        char_path = character_path or self.char_cfg["default_image"]

        char = (ImageClip(char_path)
                .with_duration(duration)
                .resized(height=self.char_cfg["height"])
                .with_position(("center", self.char_cfg["position_y"])))

        return char

    def create_screenshot_overlays(self, screenshots: list[dict], frame_width: int = 1080) -> list:
        """Create timed screenshot overlays.

        Args:
            screenshots: List of dicts with keys:
                - file: path to screenshot image
                - start: start time in seconds
                - end: end time in seconds
                - position: (x, y) or ("center", y_ratio) — optional

        Returns:
            List of ImageClip objects
        """
        overlays = []
        for ss in screenshots:
            img = (ImageClip(ss["file"])
                   .with_start(ss["start"])
                   .with_duration(ss["end"] - ss["start"])
                   .resized(width=int(frame_width * 0.85)))  # 85% of frame width

            pos = ss.get("position", ("center", 0.25))
            img = img.with_position(pos, relative=True if isinstance(pos[1], float) else False)
            overlays.append(img)

        return overlays

    def assemble_with_moviepy(self, audio_path: str, word_segments: list[dict],
                               screenshots: list[dict] = None,
                               character_path: str = None,
                               output_path: str = "output/draft_video.mp4") -> str:
        """Full assembly using MoviePy (simpler but slower for many captions).

        Best for videos with < 50 word segments. For more, use assemble_with_ffmpeg().
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        audio = AudioFileClip(audio_path)
        duration = audio.duration

        # Layer 1: Background
        bg = self.select_background(duration)

        # Layer 2: Character
        char = self.create_character_overlay(duration, character_path)

        # Layer 3: Screenshots (optional)
        ss_overlays = self.create_screenshot_overlays(screenshots or [])

        # Layer 4: Captions (word-by-word)
        captions = []
        words_per_group = self.caption_cfg.get("max_words_per_line", 3)

        for i in range(0, len(word_segments), words_per_group):
            group = word_segments[i:i + words_per_group]
            text = " ".join(w["word"] for w in group)
            start = group[0]["start"]
            end = group[-1]["end"]

            txt = (TextClip(
                        font=self.caption_cfg["font"],
                        text=text.upper(),
                        font_size=self.caption_cfg["font_size"],
                        color=self.caption_cfg["color"],
                        stroke_color=self.caption_cfg["stroke_color"],
                        stroke_width=self.caption_cfg["stroke_width"],
                   )
                   .with_start(start)
                   .with_duration(end - start)
                   .with_position(("center", self.caption_cfg["position_y"]), relative=True))
            captions.append(txt)

        # Composite all layers
        all_layers = [bg, char] + ss_overlays + captions
        final = CompositeVideoClip(all_layers).with_audio(audio)

        final.write_videofile(
            output_path,
            fps=self.video_cfg["fps"],
            codec=self.video_cfg["codec"],
            audio_codec=self.video_cfg["audio_codec"],
            threads=4
        )

        return output_path

    def assemble_with_ffmpeg(self, audio_path: str, ass_subtitle_path: str,
                              character_path: str = None,
                              output_path: str = "output/draft_video.mp4") -> str:
        """Assembly using FFmpeg directly (faster, handles many captions efficiently).

        This method:
        1. Selects and loops a background clip
        2. Overlays the character PNG
        3. Burns ASS subtitles (from CaptionGenerator.generate_ass_subtitles)
        4. Mixes in the voiceover audio

        Recommended for production use.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        audio = AudioFileClip(audio_path)
        duration = audio.duration
        audio.close()

        # Select a background clip
        bg_dir = self.config["paths"]["backgrounds_dir"]
        clips = [f for f in os.listdir(bg_dir) if f.endswith(('.mp4', '.mov', '.webm'))]
        bg_path = os.path.join(bg_dir, random.choice(clips))

        char_path = character_path or self.char_cfg["default_image"]

        w = self.video_cfg["width"]
        h = self.video_cfg["height"]
        char_h = self.char_cfg["height"]
        char_y = self.char_cfg["position_y"]

        # Build FFmpeg command
        # -stream_loop -1 loops the background, -t trims to duration
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", bg_path,    # Input 0: looped background
            "-i", char_path,                          # Input 1: character PNG
            "-i", audio_path,                         # Input 2: audio
            "-filter_complex",
            (
                f"[0:v]scale={w}:{h},setsar=1[bg];"
                f"[1:v]scale=-1:{char_h}[char];"
                f"[bg][char]overlay=(W-w)/2:{char_y}[composed];"
                f"[composed]ass='{ass_subtitle_path}'[final]"
            ),
            "-map", "[final]",
            "-map", "2:a",
            "-t", str(duration),
            "-c:v", self.video_cfg["codec"],
            "-crf", "22",
            "-preset", "fast",
            "-c:a", self.video_cfg["audio_codec"],
            "-b:a", "192k",
            "-r", str(self.video_cfg["fps"]),
            output_path
        ]

        subprocess.run(cmd, check=True)
        return output_path
```

---

### Phase 7: CLI Entry Point

**main.py:**

```python
#!/usr/bin/env python3
"""ReelForge — Faceless AI/Tech Reel Pipeline CLI"""

import click
import yaml
import os
from datetime import datetime

from reelforge.script_generator import ScriptGenerator
from reelforge.tts_engine import TTSEngine
from reelforge.caption_generator import CaptionGenerator
from reelforge.video_compositor import VideoCompositor


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


@click.group()
def cli():
    """ReelForge — Generate faceless AI/tech reels from a topic."""
    pass


@cli.command()
@click.argument("topic")
@click.option("--context", "-c", default="", help="Extra context: links, features, tool description")
@click.option("--style", "-s", type=click.Choice(["solo", "dialogue"]), default="solo", help="Script style")
@click.option("--screenshots", "-ss", multiple=True, help="Screenshot paths with timing: 'path.png:5.0:12.0'")
@click.option("--character", "-ch", default=None, help="Override character image path")
@click.option("--output", "-o", default=None, help="Output video path")
@click.option("--method", "-m", type=click.Choice(["moviepy", "ffmpeg"]), default="ffmpeg", help="Compositing method")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def generate(topic, context, style, screenshots, character, output, method, config_path):
    """Generate a reel from a topic.

    Example:
        python main.py generate "DeepAI platform" -c "Free AI tools, image gen, text gen" -s dialogue
        python main.py generate "Cursor IDE tips" -ss "screenshot1.png:5.0:12.0" -ss "screenshot2.png:15.0:22.0"
    """
    config = load_config(config_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output or f"output/reel_{timestamp}.mp4"

    # Step 1: Generate script
    click.echo("📝 Step 1/4: Generating script...")
    script_gen = ScriptGenerator(config)
    script = script_gen.generate(topic, context, style)
    click.echo(f"\n--- GENERATED SCRIPT ---\n{script}\n------------------------\n")

    # Save script for reference
    script_path = output_path.replace(".mp4", "_script.txt")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(script)

    # Step 2: Generate voiceover
    click.echo("🎙️  Step 2/4: Generating voiceover...")
    tts = TTSEngine(config)
    audio_path = output_path.replace(".mp4", "_audio.mp3")

    if style == "dialogue":
        tts.generate_dialogue(script, audio_path)
    else:
        # Strip any remaining labels for solo mode
        clean_script = script.replace("[NARRATOR]", "").strip()
        tts.generate(clean_script, audio_path)

    click.echo(f"   Audio saved to: {audio_path}")

    # Step 3: Generate word-level timestamps
    click.echo("📊 Step 3/4: Generating word-level timestamps...")
    caption_gen = CaptionGenerator()
    word_segments = caption_gen.generate_timestamps(audio_path)
    click.echo(f"   Found {len(word_segments)} words with timestamps")

    # Step 4: Composite video
    click.echo("🎬 Step 4/4: Compositing video...")
    compositor = VideoCompositor(config)

    # Parse screenshot args (format: "path.png:start:end")
    parsed_screenshots = []
    for ss in screenshots:
        parts = ss.split(":")
        parsed_screenshots.append({
            "file": parts[0],
            "start": float(parts[1]),
            "end": float(parts[2]),
        })

    if method == "ffmpeg":
        # Generate ASS subtitles for FFmpeg method
        ass_path = output_path.replace(".mp4", "_captions.ass")
        caption_gen.generate_ass_subtitles(word_segments, ass_path)
        result = compositor.assemble_with_ffmpeg(audio_path, ass_path, character, output_path)
    else:
        result = compositor.assemble_with_moviepy(audio_path, word_segments, parsed_screenshots, character, output_path)

    click.echo(f"\n✅ Video generated: {result}")
    click.echo(f"📄 Script saved: {script_path}")
    click.echo("\n🎯 Next steps:")
    click.echo("   1. Review the video in CapCut or DaVinci Resolve")
    click.echo("   2. Add any screenshot overlays or tweaks")
    click.echo("   3. Export and publish to TikTok, Instagram, YouTube Shorts")


@cli.command()
@click.argument("topic")
@click.option("--context", "-c", default="", help="Extra context")
@click.option("--style", "-s", type=click.Choice(["solo", "dialogue"]), default="solo")
@click.option("--config", "config_path", default="config.yaml")
def script_only(topic, context, style, config_path):
    """Generate only the script (for review before full pipeline)."""
    config = load_config(config_path)
    script_gen = ScriptGenerator(config)
    script = script_gen.generate(topic, context, style)
    click.echo(script)


@cli.command()
def list_voices():
    """List available EdgeTTS voices."""
    import asyncio
    async def _list():
        voices = await edge_tts.list_voices()
        en_voices = [v for v in voices if v["Locale"].startswith("en-")]
        for v in en_voices:
            click.echo(f"  {v['ShortName']:30s} | {v['Gender']:8s} | {v['Locale']}")
    asyncio.run(_list())


if __name__ == "__main__":
    cli()
```

---

### Phase 8: requirements.txt

```
edge-tts>=6.1.0
moviepy>=2.0.0
openai>=1.0.0
pyyaml>=6.0
pillow>=10.0.0
click>=8.0.0
torch>=2.0.0
torchaudio>=2.0.0
whisperx @ git+https://github.com/m-bain/whisperx.git
```

---

## EXTERNAL STEPS REFERENCE (Things the user must do manually)

### Before first run:

1. **Install FFmpeg** (required for video compositing)
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `sudo apt install ffmpeg`
   - Windows: `choco install ffmpeg` or download from https://ffmpeg.org/download.html

2. **Install ImageMagick** (required by MoviePy for TextClip)
   - macOS: `brew install imagemagick`
   - Ubuntu/Debian: `sudo apt install imagemagick`
   - Windows: Download from https://imagemagick.org/script/download.php
   - ⚠️ On Ubuntu, you may need to edit `/etc/ImageMagick-6/policy.xml` to allow PDF operations

3. **Download Poppins-ExtraBold font**
   - Go to https://fonts.google.com/specimen/Poppins
   - Click "Download family"
   - Extract `Poppins-ExtraBold.ttf` → copy to `assets/fonts/Poppins-ExtraBold.ttf`

4. **Collect 5-10 background clips** (do this once, reuse forever)
   - Go to https://pixabay.com/videos/search/minecraft%20parkour/
   - Download 5-10 vertical (9:16) or square clips, each 60-90 seconds
   - Place in `assets/backgrounds/`
   - Alternatives: search "subway surfers gameplay", "satisfying videos", "soap cutting"

5. **Get cartoon character PNG(s) with transparent background**
   - Search "Peter Griffin PNG transparent" on PNGWing, CleanPNG, or StickPNG
   - Or create your own original character via:
     - Krikey AI (https://krikey.ai) — free tier for basic, $15/mo for pro
     - Commission on Fiverr ($20-50 one-time) for a legally safe original character
   - Save to `assets/characters/peter.png` (or your character name)
   - ⚠️ Legal note: Using copyrighted characters (Peter Griffin, etc.) is copyright infringement.
     For long-term safety, invest in an original character.

6. **Configure API keys** in `config.yaml`:
   - For script generation: OpenAI API key (https://platform.openai.com) OR use Ollama locally (free)
   - For voice (optional upgrade): ElevenLabs API key (https://elevenlabs.io, $5/mo Starter plan)

### For each video:

7. **Prepare any screenshots** of the tool/app being discussed
   - Take screenshots or screen recordings using OBS Studio or built-in screen capture
   - Save to `assets/screenshots/` before running the pipeline

8. **After pipeline generates the video:**
   - Open in **CapCut** (free, https://capcut.com) or **DaVinci Resolve** (free, https://blackmagicdesign.com/products/davinciresolve)
   - Review timing, add any missing screenshot overlays, fix caption issues
   - CapCut has built-in auto-captions if you want to redo captions manually
   - Export as 1080×1920, 30fps, H.264
   - Publish to TikTok, Instagram Reels, YouTube Shorts with 5-10 hashtags

---

## EXISTING OPEN-SOURCE PROJECTS TO REFERENCE

These can be forked or studied for implementation patterns:

1. **Stewie_it_v1** — https://github.com/Traverser25/Stewie_it_v1
   Closest match to @algorithmswithpeter format. Generates Peter/Stewie dialogues with AI voices over gameplay. Study its MoviePy compositing logic and character overlay approach.

2. **MoneyPrinterTurbo** — https://github.com/harry0703/MoneyPrinterTurbo (22K+ stars)
   Most feature-complete short video automation. Has Streamlit web UI, multi-LLM support, subtitle generation. Fork and add character overlay support.

3. **ShortGPT** — https://github.com/RayVentura/ShortGPT (7K stars)
   Modular engine with JSON-based editing markup. Good architecture patterns for the pipeline.

---

## CONTENT STRATEGY TIPS

### Script structure (3-act format):
- **Hook (0-3 sec):** Pattern-interrupt. "Stop using Google for coding." / "This free AI tool replaces $300 software."
- **Body (3-50 sec):** One concept, simple language, 5-12 word sentences, analogies.
- **CTA (50-60 sec):** "Follow for more" or binary question ("Python or JavaScript? Comment below.")

### Engagement multipliers:
- First frame MUST contain text (becomes profile grid thumbnail)
- Visual changes every 2-3 seconds
- Binary choice questions in CTA get 3-5x more comments
- Post at peak hours (check Instagram Insights)
- Daily posting consistency is key
- Use 5-10 hashtags mixing niche (#aitool, #codinglife) and broad (#tech, #learnontiktok)

### Monthly cost estimate:
| Component | Cost |
|-----------|------|
| EdgeTTS (voice) | $0 |
| OpenAI API (scripts, ~30 videos) | ~$1-2 |
| ElevenLabs Starter (optional) | $5 |
| Everything else | $0 |
| **Total** | **$1-7/month** |
