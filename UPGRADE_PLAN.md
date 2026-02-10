# ReelForge Upgrade Plan — Implementation Guide for Claude Code

## How to use this file

This document is a **step-by-step implementation plan** for upgrading the ReelForge pipeline. Work through it **one tier at a time**, in order. Each task has acceptance criteria. Do NOT skip ahead — later tasks depend on earlier ones.

The existing codebase is described in `CLAUDE.md`. Read that first if you haven't.

---

## TIER 1 — Highest Impact, Implement First

### Task 1.1: Karaoke-Style Captions with Pillow Rendering ✅ COMPLETED

**Problem:** Current captions use MoviePy TextClip which only supports one color per clip. Rival accounts use CapCut-style captions where the active word is highlighted in yellow while other words stay white, with thick black outlines.

**Status:** Completed 2026-02-09. Font downloaded, `pillow_renderer.py` created, `video_compositor.py` updated with conditional branch, config updated with new settings. Validation passed.

**Implementation:**

1. Download **Montserrat Black (900 weight)** from Google Fonts → save to `assets/fonts/Montserrat-Black.ttf`
   - This is the #1 font used in viral short-form content (used in ~60% of captioned videos)
   - Fallback: keep Poppins-ExtraBold as secondary option

2. Create a new module `reelforge/captions/pillow_renderer.py` with a `render_caption_frame()` function:

```python
from PIL import Image, ImageDraw, ImageFont
import numpy as np

def render_caption_frame(
    words: list[str],
    active_index: int,
    frame_w: int = 1080,
    frame_h: int = 200,
    font_path: str = "assets/fonts/Montserrat-Black.ttf",
    font_size: int = 65,
    active_color: tuple = (255, 215, 0, 255),      # Yellow (#FFD700)
    inactive_color: tuple = (255, 255, 255, 255),   # White
    stroke_color: tuple = (0, 0, 0, 255),           # Black outline
    stroke_width: int = 4,
    word_spacing: int = 15,
) -> np.ndarray:
    """Render a caption frame with one word highlighted (karaoke style).
    
    Returns RGBA numpy array suitable for MoviePy ImageClip.
    """
    img = Image.new('RGBA', (frame_w, frame_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, font_size)

    # Measure all words
    word_widths = []
    for w in words:
        bbox = draw.textbbox((0, 0), w.upper(), font=font)
        word_widths.append(bbox[2] - bbox[0])

    total_w = sum(word_widths) + word_spacing * (len(words) - 1)
    x = (frame_w - total_w) // 2
    y = (frame_h - font_size) // 2

    # Draw each word
    for i, word in enumerate(words):
        color = active_color if i == active_index else inactive_color
        draw.text(
            (x, y), word.upper(), font=font, fill=color,
            stroke_width=stroke_width, stroke_fill=stroke_color
        )
        x += word_widths[i] + word_spacing

    return np.array(img)
```

3. Create a `build_karaoke_clips()` function that:
   - Takes WhisperX word segments and groups them into chunks of 3-4 words
   - For each word timestamp within a chunk, calls `render_caption_frame()` with that word as active
   - Creates `ImageClip` from each frame, sets duration to match word timing
   - Returns list of clips positioned at `("center", int(video_height * 0.62))`

4. Update `video_compositor.py` to use the new Pillow-rendered captions instead of MoviePy TextClip.

5. Add config options to `config.yaml`:
```yaml
captions:
  renderer: "pillow"  # "pillow" (karaoke) or "textclip" (legacy)
  font: "assets/fonts/Montserrat-Black.ttf"
  font_size: 65
  active_color: "#FFD700"    # Yellow
  inactive_color: "#FFFFFF"  # White
  stroke_color: "#000000"
  stroke_width: 4
  words_per_group: 3
  position_y: 0.62  # relative to frame height
```

**Acceptance criteria:**
- Captions render with yellow active word, white inactive words, black 4px outline
- Font is Montserrat Black at 65px, all uppercase
- Words grouped in chunks of 3-4
- Positioned in lower-center of frame, avoiding bottom 15% safe zone
- No visual regression — old TextClip mode still available via config

---

### Task 1.2: Sound Effects & Background Music Layer ✅ COMPLETED

**Problem:** Videos have no sound design — just voiceover. Adding layered audio (background music, transition whooshes, pop sounds) dramatically increases perceived quality.

**Status:** Completed 2026-02-10. Audio assets generated (whoosh, pop, sting SFX + ambient music), pydub installed, `mixer.py` created, orchestrator integration added, config updated. Validation passed.

**Implementation:**

1. Create `assets/sfx/` directory with subdirectories:
   - `assets/sfx/whoosh/` — 3-5 whoosh sounds for transitions
   - `assets/sfx/pop/` — 2-3 pop/notification sounds for screenshot appearances
   - `assets/sfx/sting/` — 2-3 dramatic stings for emphasis moments
   - `assets/music/` — 3-5 lo-fi/ambient background tracks (30-90 seconds each)
   
   Sources (all royalty-free, no attribution required):
   - Pixabay Sound Effects: https://pixabay.com/sound-effects/
   - Mixkit: https://mixkit.co/free-sound-effects/
   - Pixabay Music: https://pixabay.com/music/
   - Mixkit Music: https://mixkit.co/free-stock-music/

2. Create `reelforge/audio/mixer.py`:

```python
from pydub import AudioSegment
import random
import os

class AudioMixer:
    def __init__(self, config: dict):
        self.sfx_dir = config.get("paths", {}).get("sfx_dir", "assets/sfx")
        self.music_dir = config.get("paths", {}).get("music_dir", "assets/music")
        self.music_volume_db = config.get("audio", {}).get("music_volume_db", -18)
        self.sfx_volume_db = config.get("audio", {}).get("sfx_volume_db", -6)

    def mix(
        self,
        voiceover_path: str,
        output_path: str,
        sfx_cues: list[dict] | None = None,
        add_music: bool = True,
    ) -> str:
        """Mix voiceover with background music and sound effects.
        
        sfx_cues: [{"type": "whoosh", "time_ms": 5000}, ...]
        """
        voiceover = AudioSegment.from_file(voiceover_path)
        
        # Add background music
        if add_music:
            music_files = [f for f in os.listdir(self.music_dir) 
                          if f.endswith(('.mp3', '.wav'))]
            if music_files:
                track = AudioSegment.from_file(
                    os.path.join(self.music_dir, random.choice(music_files))
                )
                # Adjust volume and loop to match voiceover length
                track = track + self.music_volume_db
                if len(track) < len(voiceover):
                    loops_needed = (len(voiceover) // len(track)) + 1
                    track = track * loops_needed
                track = track[:len(voiceover)]
                # Fade in/out
                track = track.fade_in(2000).fade_out(3000)
                voiceover = voiceover.overlay(track)
        
        # Add sound effects at cue points
        if sfx_cues:
            for cue in sfx_cues:
                sfx_type = cue["type"]  # "whoosh", "pop", "sting"
                time_ms = cue["time_ms"]
                sfx_subdir = os.path.join(self.sfx_dir, sfx_type)
                if os.path.isdir(sfx_subdir):
                    files = [f for f in os.listdir(sfx_subdir) 
                            if f.endswith(('.mp3', '.wav'))]
                    if files:
                        sfx = AudioSegment.from_file(
                            os.path.join(sfx_subdir, random.choice(files))
                        )
                        sfx = sfx + self.sfx_volume_db
                        voiceover = voiceover.overlay(sfx, position=time_ms)
        
        voiceover.export(output_path, format="mp3")
        return output_path
```

3. Update the orchestrator to:
   - Parse `[SFX: type]` markers from scripts (if present) and convert to sfx_cues with timestamps
   - Auto-generate sfx_cues for screenshot overlay appearances (pop sound) and background clip transitions (whoosh)
   - Call `AudioMixer.mix()` after TTS generation, before video compositing

4. Add to `config.yaml`:
```yaml
audio:
  background_music: true
  music_volume_db: -18  # Background music level relative to voice
  sfx_volume_db: -6     # Sound effects level relative to voice
  auto_sfx: true        # Auto-add whoosh on transitions, pop on screenshots

paths:
  sfx_dir: "assets/sfx"
  music_dir: "assets/music"
```

5. Add `pydub` to requirements.txt

**Acceptance criteria:**
- Background music loops under voiceover at -18dB with fade in/out
- Pop sound plays when screenshot overlays appear
- Whoosh sound plays on background clip transitions
- All SFX/music is configurable and optional
- Works with existing pipeline when no SFX files are present (graceful fallback)

---

### Task 1.3: Upgraded Script Prompt Templates ✅ COMPLETED

**Problem:** Current prompt produces generic scripts. Rival accounts use the "smart vs. naive" character dynamic with stronger hooks, escalating reveals, and comment-driving CTAs.

**Status:** Completed 2026-02-10. Created `hooks.py` with hook/CTA templates (5 categories each), upgraded MCP prompt (V2) with Character A/B definitions and beat-by-beat timing, integrated hook library in generator with random injection, added hook validation (first line < 10 words) in orchestrator retry loop. Validation passed.

**Implementation:**

1. Replace the dialogue prompt in `reelforge/script/` (wherever prompts are defined — check `mcp_generator.py` and `templates/script_prompts.py`):

```python
DIALOGUE_PROMPT_V2 = """You are a viral short-form video scriptwriter for the "brainrot" character dialogue format on TikTok/Instagram Reels.

Topic: {topic}
{context}

Write a 60-second dialogue (100-130 words total) between two characters:

CHARACTER A — The Curious Reactor:
- Asks relatable "dumb" questions everyone's thinking
- Reacts with genuine shock: "Wait, WHAT?", "No way...", "You're lying"
- Never uses filler: no "Hey guys", "So basically", "Well actually"

CHARACTER B — The Knowledge Dropper:
- Explains with simple analogies a 12-year-old would get
- Drops escalating facts — each revelation bigger than the last
- Slightly cocky/teasing but helpful

SCRIPT STRUCTURE (follow this beat-for-beat):
- Lines 1-2 (HOOK, 0-3 sec): A asks a scroll-stopping question OR B makes a shocking claim. Under 10 words. Must create instant curiosity.
- Lines 3-10 (BUILD, 3-45 sec): Alternating reveals. B explains, A reacts with shock, B goes deeper. Each B line reveals something more surprising.
- Lines 11-12 (TWIST, 45-52 sec): "Wait, it gets even crazier..." — the biggest reveal
- Lines 13-14 (CTA, 52-60 sec): End with EITHER a comment-driving question ("What would you pick? Comment below") OR a cliffhanger ("I'll show you in part 2... follow so you don't miss it")

RULES:
- Every single line MUST be under 15 words
- Use power words: STOP, DELETE, FREE, REPLACE, NEVER, MISTAKE, SECRET
- Include [SHOW:S#] markers where B mentions a tool/app/website that should show a screenshot
- Total word count: 100-130 words
- Tone: casual, surprising, slightly controversial, Gen Z energy
- NO greetings, NO filler, NO corporate language, NO "In this video"

OUTPUT FORMAT:
A: [line]
B: [line] [SHOW:S1]
A: [line]
...

S1=keyword_for_screenshot, S2=keyword_for_screenshot

HOOK TEMPLATES (pick one or remix):
- "Nobody talks about this AI that [shocking thing]"
- "This free tool does what [expensive app] charges $20/month for"  
- "Delete [popular thing] right now. Here's why."
- "STOP using [old method]. [New thing] changes everything."
- "I found an AI that literally [impossible-sounding thing]"
"""
```

2. Add a **hook library** system — create `reelforge/script/hooks.py`:

```python
HOOK_TEMPLATES = {
    "curiosity_gap": [
        "Nobody's talking about this AI that {capability}",
        "I found something that {shocking_claim}",
        "There's a free tool that {replaces_expensive_thing}",
    ],
    "negative_hook": [
        "STOP using {old_thing} right now",
        "Delete {popular_app}. Here's why.",
        "This is why {common_practice} is a mistake",
    ],
    "bold_claim": [
        "This free AI is better than {expensive_tool}",
        "I tested every {category} tool. Only {number} are worth it.",
        "{Tool} just killed {competitor} and nobody noticed",
    ],
    "controversy": [
        "Programmers are going to hate this",
        "{Popular_opinion}? That's completely wrong.",
        "Everyone's using {thing} wrong. Here's the right way.",
    ],
}

CTA_TEMPLATES = {
    "comment_bait": [
        "Which one would you pick? Comment below.",
        "Comment '{keyword}' and I'll send you the link",
        "Agree or disagree? Fight me in the comments.",
    ],
    "follow_bait": [
        "Follow for part 2 — I'll show you how to set it up",
        "I'm dropping the full tutorial tomorrow. Follow so you don't miss it.",
    ],
    "save_bait": [
        "Save this before it gets taken down.",
        "Bookmark this. You'll need it later.",
    ],
}
```

3. Modify the script generator to:
   - Randomly select a hook template category per generation
   - Include 2-3 hook variations in the prompt as examples
   - Validate that the generated hook line is under 10 words
   - Validate alternating A/B pattern (already done per CLAUDE.md)

**Acceptance criteria:**
- New prompt template produces noticeably better hooks (test with 5 topics)
- Hook library is accessible and randomizable
- Generated scripts follow the beat structure: hook → build → twist → CTA
- Word count stays within 100-130 range
- Backward compatible with existing custom script format

---

## TIER 2 — High Impact, Implement Next

### Task 2.1: Audio-Reactive Character Animation ✅ COMPLETED

**Problem:** Characters are static PNGs. Even subtle animation (bobbing when speaking) dramatically increases perceived quality.

**Status:** Completed 2026-02-10. Added scipy dependency, created `character_animator.py` with audio amplitude analysis, integrated in video compositor with per-segment position functions, updated config with animation settings. Validation passed.

**Implementation:**

1. Create `reelforge/animation/character_animator.py`:

```python
import numpy as np
from scipy.io import wavfile
from moviepy.editor import ImageClip

class CharacterAnimator:
    def __init__(self, config: dict):
        self.bounce_amount = config.get("character", {}).get("bounce_pixels", 15)
        self.animation_type = config.get("character", {}).get("animation", "bounce")  # "bounce", "none"

    def load_audio_amplitude(self, audio_path: str, window_ms: int = 50) -> tuple:
        """Load audio and return (sample_rate, mono_data) for amplitude lookup."""
        # Convert mp3 to wav first if needed
        if audio_path.endswith('.mp3'):
            from pydub import AudioSegment
            audio = AudioSegment.from_mp3(audio_path)
            wav_path = audio_path.replace('.mp3', '_temp.wav')
            audio.export(wav_path, format='wav')
            audio_path = wav_path
        
        rate, data = wavfile.read(audio_path)
        if data.ndim > 1:
            data = data.mean(axis=1)
        return rate, data.astype(np.float32)

    def get_amplitude(self, t: float, rate: int, audio_data: np.ndarray, 
                      window_ms: int = 50) -> float:
        """Get normalized audio amplitude at time t."""
        center = int(t * rate)
        half = int(rate * window_ms / 2000)
        chunk = audio_data[max(0, center - half):center + half]
        if len(chunk) == 0:
            return 0.0
        rms = np.sqrt(np.mean(chunk ** 2))
        return min(rms / 16000, 1.0)  # Normalize to 0-1

    def animate_clip(self, character_clip: ImageClip, audio_path: str,
                     base_x: int, base_y: int) -> ImageClip:
        """Apply audio-reactive bounce animation to character clip."""
        if self.animation_type == "none":
            return character_clip.set_position((base_x, base_y))
        
        rate, audio_data = self.load_audio_amplitude(audio_path)
        bounce = self.bounce_amount

        return character_clip.set_position(
            lambda t: (base_x, base_y - int(bounce * self.get_amplitude(t, rate, audio_data)))
        )
```

2. Update `video_compositor.py` to use `CharacterAnimator` when compositing character overlays.

3. Add config:
```yaml
character:
  animation: "bounce"  # "bounce" or "none"
  bounce_pixels: 15
```

**Acceptance criteria:**
- Character visibly bobs up when audio amplitude is high (speaking)
- Stays still during silence
- Bounce is subtle (15px max) — not distracting
- Configurable, can be disabled

---

### Task 2.2: Kokoro TTS Integration (Optional Upgrade) ✅ COMPLETED

**Problem:** EdgeTTS sounds robotic. Kokoro-82M is free, Apache 2.0 licensed, pip-installable, runs on CPU, and sounds significantly more natural.

**Status:** Completed 2026-02-10. Added kokoro and soundfile dependencies, created `kokoro_engine.py` with synthesize_sync and synthesize_dialogue_sync methods matching TTSEngine interface, integrated in orchestrator with graceful fallback to EdgeTTS, updated config with Kokoro voice settings. Validation passed.

**Implementation:**

1. Add to `tts_engine.py` (or create `reelforge/audio/kokoro_engine.py`):

```python
# pip install kokoro soundfile
from kokoro import KPipeline
import soundfile as sf

class KokoroTTSEngine:
    def __init__(self, config: dict):
        self.lang = config.get("tts", {}).get("kokoro_lang", "a")  # 'a' = American English
        self.voice_a = config.get("tts", {}).get("kokoro_voice_a", "am_adam")
        self.voice_b = config.get("tts", {}).get("kokoro_voice_b", "af_heart")
        self.pipeline = KPipeline(lang_code=self.lang)
    
    def generate(self, text: str, output_path: str, voice: str = None) -> str:
        voice = voice or self.voice_a
        audio_chunks = []
        for _, _, audio in self.pipeline(text, voice=voice):
            audio_chunks.append(audio)
        
        import numpy as np
        full_audio = np.concatenate(audio_chunks)
        sf.write(output_path, full_audio, 24000)
        return output_path
    
    def generate_dialogue(self, script: str, output_path: str) -> str:
        """Generate dialogue with alternating Kokoro voices for A/B speakers."""
        import re
        from pydub import AudioSegment
        
        # Parse A/B segments
        segments = re.findall(
            r'(?:^|\n)\s*([AB]):\s*(.*?)(?=\n\s*[AB]:|$)', 
            script, re.DOTALL
        )
        
        voice_map = {"A": self.voice_a, "B": self.voice_b}
        combined = AudioSegment.empty()
        
        for i, (speaker, text) in enumerate(segments):
            text = text.strip()
            if not text:
                continue
            temp_path = f"/tmp/kokoro_seg_{i}.wav"
            self.generate(text, temp_path, voice=voice_map.get(speaker, self.voice_a))
            seg = AudioSegment.from_wav(temp_path)
            combined += seg
            # Small pause between speakers
            combined += AudioSegment.silent(duration=200)
        
        combined.export(output_path, format="mp3")
        return output_path
```

2. Add to config.yaml:
```yaml
tts:
  provider: "kokoro"  # "edge", "kokoro", "elevenlabs"
  kokoro_lang: "a"  # American English
  kokoro_voice_a: "am_adam"    # Character A voice
  kokoro_voice_b: "af_heart"  # Character B voice
```

3. Add `kokoro` and `soundfile` to requirements.txt

**NOTE:** Kokoro voices — see https://huggingface.co/hexgrad/Kokoro-82M for full voice list. Good pairs for dialogue:
- `am_adam` (male, conversational) + `af_heart` (female, warm)
- `am_michael` (male, authoritative) + `am_adam` (male, casual)

**Acceptance criteria:**
- Kokoro TTS works as drop-in replacement for EdgeTTS
- Dialogue mode generates alternating voices for A/B speakers
- Config switch between edge/kokoro/elevenlabs
- Falls back to EdgeTTS if Kokoro fails to install

---

### Task 2.3: Background Clip Transitions ✅ COMPLETED

**Problem:** Background gameplay clips cut abruptly. Even a 0.3s crossfade makes them feel professional.

**Status:** Completed 2026-02-10. Added `create_background_with_transitions()` and `apply_ken_burns()` methods to video compositor, integrated in `process_background()` with conditional logic, updated config with transition settings. Validation passed.

**Implementation:**

Add a transition method to `video_compositor.py` that applies crossfade between background clip segments. Use MoviePy's `crossfadein`/`crossfadeout`:

```python
def create_background_with_transitions(self, clip_paths: list, total_duration: float, 
                                        transition_duration: float = 0.3) -> VideoClip:
    """Concatenate background clips with crossfade transitions."""
    clips = []
    for path in clip_paths:
        clip = VideoFileClip(path).resize((1080, 1920))
        clips.append(clip)
    
    # Apply crossfades
    if len(clips) > 1:
        for i in range(1, len(clips)):
            clips[i] = clips[i].crossfadein(transition_duration)
        
        from moviepy.editor import concatenate_videoclips
        background = concatenate_videoclips(clips, method="compose", padding=-transition_duration)
    else:
        background = clips[0]
    
    # Loop/trim to match duration
    if background.duration < total_duration:
        background = background.loop(duration=total_duration)
    else:
        background = background.subclip(0, total_duration)
    
    return background
```

Also add a subtle **Ken Burns effect** (slow zoom) to keep static moments alive:

```python
def apply_ken_burns(self, clip, zoom_ratio=0.04):
    """Apply slow zoom-in effect over the clip duration."""
    def zoom_effect(get_frame, t):
        frame = get_frame(t)
        h, w = frame.shape[:2]
        progress = t / clip.duration
        z = 1 + zoom_ratio * progress
        crop_h, crop_w = int(h / z), int(w / z)
        y1 = (h - crop_h) // 2
        x1 = (w - crop_w) // 2
        cropped = frame[y1:y1+crop_h, x1:x1+crop_w]
        import cv2
        return cv2.resize(cropped, (w, h))
    return clip.fl(zoom_effect)
```

**Acceptance criteria:**
- Background clips crossfade smoothly (0.3s default)
- Ken Burns slow zoom keeps visuals alive
- Both effects configurable and optional

---

### Task 2.4: Multiple Character Poses / Expression Switching ✅ COMPLETED

**Problem:** Single static character image for the entire video is flat. Switching between 3-4 poses per emotion adds life.

**Status:** Completed 2026-02-10. Created character pose directories (char_a, char_b) with placeholder poses, created `expression_mapper.py` with keyword-based expression detection, updated video compositor to support directory-based characters with pose selection per segment, updated config with character_dirs settings. Validation passed.

**Implementation:**

1. Update the character asset structure:
```
assets/characters/
├── char_a/
│   ├── neutral.png
│   ├── surprised.png    # mouth open, eyes wide
│   ├── happy.png        # smiling
│   └── talking.png      # mouth open
├── char_b/
│   ├── neutral.png
│   ├── explaining.png   # hand gesture
│   ├── smug.png         # know-it-all expression
│   └── talking.png
```

2. Create `reelforge/animation/expression_mapper.py`:

```python
import random

# Map keywords in dialogue lines to expressions
EXPRESSION_KEYWORDS = {
    "surprised": ["what", "really", "no way", "wait", "seriously", "lying", "impossible"],
    "happy": ["amazing", "awesome", "love", "great", "perfect", "best"],
    "explaining": ["because", "actually", "basically", "means", "works", "imagine"],
    "smug": ["told you", "obviously", "easy", "simple", "better"],
}

def get_expression(line: str, speaker: str, available_poses: list[str]) -> str:
    """Determine character expression based on dialogue line content."""
    line_lower = line.lower()
    
    for expression, keywords in EXPRESSION_KEYWORDS.items():
        if any(kw in line_lower for kw in keywords):
            if expression in available_poses:
                return expression
    
    # Default: alternate between neutral and talking
    return "talking" if "talking" in available_poses else "neutral"
```

3. Update `video_compositor.py` to switch character PNGs per dialogue segment based on expression mapping.

**Acceptance criteria:**
- Character expression changes per dialogue line
- Falls back gracefully to single PNG if poses don't exist
- Keyword-based mapping is configurable

---

## TIER 3 — Ongoing Polish

### Task 3.1: Rhubarb Lip Sync Integration

For proper phoneme-based mouth animation. Requires:
- Install Rhubarb Lip Sync binary (https://github.com/DanielSWolf/rhubarb-lip-sync/releases)
- Create 6-9 mouth shape PNGs per character (A, B, C, D, E, F, G, H, X shapes)
- Run `rhubarb -f json audio.wav` → parse output → switch mouth PNGs per frame in MoviePy
- This is a multi-day task. Do NOT attempt until Tiers 1-2 are complete.

### Task 3.2: Zoom Pulse on Emphasis

Add a brief zoom-in (1.15x over 0.3s, then back) on key words/moments. Parse emphasis markers from script `[EMPHASIS]` or auto-detect from audio amplitude spikes.

### Task 3.3: First Frame / Thumbnail Optimization

The first frame of the video becomes the grid thumbnail on Instagram. Ensure:
- Frame 0 contains the hook text (first caption words) rendered large
- Character is visible
- Background is visually interesting (not a dark frame)
- Consider generating a separate thumbnail image

### Task 3.4: Auto-Posting via Buffer / Platform APIs

- Buffer free tier: 3 channels, 10 scheduled posts
- Or use TikTok/Instagram/YouTube APIs directly
- Create `reelforge/integrations/publisher.py`

---

## FREE RESOURCE LINKS

### Fonts
- Montserrat Black: https://fonts.google.com/specimen/Montserrat (download, extract Black weight)
- Bangers: https://fonts.google.com/specimen/Bangers (comic/bold alternative)
- Bebas Neue: https://fonts.google.com/specimen/Bebas+Neue (condensed all-caps)

### Sound Effects (royalty-free, no attribution)
- Pixabay SFX: https://pixabay.com/sound-effects/
- Mixkit SFX: https://mixkit.co/free-sound-effects/
- Search for: "whoosh", "pop", "notification", "dramatic sting"

### Background Music (royalty-free)
- Pixabay Music: https://pixabay.com/music/ (search "lo-fi", "ambient", "chill")
- Mixkit Music: https://mixkit.co/free-stock-music/
- YouTube Audio Library: https://studio.youtube.com/channel/UC/music (requires YouTube account)

### Background Video Footage
- Pixabay Videos: https://pixabay.com/videos/ (search "minecraft parkour", "satisfying")
- Mixkit Videos: https://mixkit.co/free-stock-video/

### TTS
- Kokoro-82M: https://huggingface.co/hexgrad/Kokoro-82M (`pip install kokoro`)
- Edge-TTS: already installed (`pip install edge-tts`)

### Caption Tools (reference)
- pycaps: https://github.com/francozanardi/pycaps (MIT, CSS-styled animated subtitles)
- pysubs2: https://github.com/tkarabela/pysubs2 (ASS subtitle generation)

### Character Animation (reference)
- Rhubarb Lip Sync: https://github.com/DanielSWolf/rhubarb-lip-sync
- PyToon: https://github.com/lukerbs/pytoon

---

## DEPENDENCIES TO ADD

```
# Add to requirements.txt
pydub>=0.25.0
kokoro>=0.9.0        # Optional: better TTS
soundfile>=0.12.0    # For Kokoro output
scipy>=1.10.0        # For audio amplitude analysis
```

---

## ALGORITHM TIPS (For the human, not for code)

These are content strategy notes — not code tasks:

1. **Post to TikTok first**, then Instagram 2hrs later, YouTube Shorts 4hrs later
2. **Never cross-post with watermarks** — upload clean master to each platform
3. **Hashtags are dying** — use 3-5 max, focus on keyword SEO in captions and on-screen text
4. **Target 50%+ completion rate** for 60-second videos
5. **First 1.5 seconds are everything** — 60% of drops happen in first 3 seconds
6. **Visual change every 3-4 seconds** maintains 58% retention vs 41% for static
7. **Saves and shares outweigh likes** in 2025 algorithm ranking
8. **Optimal lengths**: 21-34s for max completion, 60-90s for max total watch time
