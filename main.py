#!/usr/bin/env python3
"""
ReelForge CLI - Main entry point for the reel generation pipeline.
"""

import os
import click
import torch
from pathlib import Path
from reelforge.utils import load_config


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """
    ReelForge - Semi-automated faceless AI/tech social media reel generator.
    """
    pass


@cli.command()
@click.option('--topic', '-t', required=True, help='Topic for the video')
@click.option('--details', '-d', default='', help='Additional topic details')
@click.option('--style', '-s', type=click.Choice(['solo', 'dialogue']), default='dialogue', help='Script style')
@click.option('--background', '-b', help='Specific background video (random if not specified)')
@click.option('--character', '-ch', help='Character image overlay (optional)')
@click.option('--output', '-o', default=None, help='Output filename (auto-generated if not specified)')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def generate(topic: str, details: str, style: str, background: str, character: str, output: str, config: str):
    """
    🚀 FULL PIPELINE: Generate complete reel from topic to final video!

    This command runs all phases automatically:
    - Phase 3: Generate script with LLM
    - Phase 4: Convert to speech with EdgeTTS
    - Phase 5: Generate word-level captions with WhisperX
    - Phase 6: Compose final video with MoviePy

    Example:
        python main.py generate -t "Why AI won't replace developers"
        python main.py generate -t "Top 3 Python tips" -s solo
    """
    try:
        from reelforge.script_generator import ScriptGenerator
        from reelforge.tts_engine import TTSEngine
        from reelforge.caption_generator import CaptionGenerator
        from reelforge.video_compositor import VideoCompositor
        import datetime

        cfg = load_config(config)

        # Generate output filename
        if output is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_base = f"output/reel_{timestamp}"
        else:
            output_base = os.path.splitext(output)[0]

        script_path = f"{output_base}_script.txt"
        audio_path = f"{output_base}_audio.mp3"
        captions_path = f"{output_base}_captions.json"
        video_path = f"{output_base}.mp4"

        click.echo("=" * 60)
        click.echo("🚀 REELFORGE FULL PIPELINE")
        click.echo("=" * 60)
        click.echo(f"Topic: {topic}")
        click.echo(f"Style: {style}")
        click.echo(f"Output: {video_path}")
        click.echo("=" * 60)

        # PHASE 3: Generate Script
        click.echo("\n📝 PHASE 1/4: Generating script...")
        generator = ScriptGenerator(cfg)

        word_limit = "130 words" if style == "dialogue" else "140 words"
        optimization = f"{details} Keep punchy, max {word_limit} for 60s reel" if details else f"Keep punchy, max {word_limit} for 60s reel"

        script_text = generator.generate(topic, optimization, style)

        os.makedirs(os.path.dirname(script_path) or '.', exist_ok=True)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_text)

        is_valid, validation_msg = generator.validate_script_length(script_text, style)
        word_count = len(script_text.split())

        click.echo(f"   ✓ Script: {word_count} words")
        click.echo(f"   ✓ {validation_msg}")
        click.echo(f"   ✓ Saved: {script_path}")

        # PHASE 4: Generate Audio
        click.echo(f"\n🎙️  PHASE 2/4: Converting to speech...")
        engine = TTSEngine(cfg)

        if style == "dialogue":
            parsed_dialogue = generator.parse_dialogue(script_text)
            engine.synthesize_dialogue_sync(parsed_dialogue, audio_path)
        else:
            engine.synthesize_sync(script_text, audio_path, rate="+20%")

        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip

        audio = AudioFileClip(audio_path)
        duration = audio.duration
        audio.close()

        click.echo(f"   ✓ Audio: {duration:.1f}s")
        click.echo(f"   ✓ Saved: {audio_path}")

        # PHASE 5: Generate Captions
        click.echo(f"\n📊 PHASE 3/4: Generating captions...")
        caption_gen = CaptionGenerator(cfg)

        word_captions = caption_gen.generate_captions(audio_path)
        caption_gen.save_captions_json(word_captions, captions_path)
        formatted_captions = caption_gen.format_captions(word_captions)

        click.echo(f"   ✓ Words: {len(word_captions)}")
        click.echo(f"   ✓ Segments: {len(formatted_captions)}")
        click.echo(f"   ✓ Saved: {captions_path}")

        # PHASE 6: Compose Video
        click.echo(f"\n🎬 PHASE 4/4: Composing final video...")
        compositor = VideoCompositor(cfg)

        if background:
            click.echo(f"   Using: {background}")
        else:
            click.echo(f"   Using: Random background")

        result = compositor.compose_video(
            audio_path=audio_path,
            captions_data=formatted_captions,
            output_path=video_path,
            background_path=background,
            character_path=character
        )

        size_mb = os.path.getsize(result) / (1024 * 1024)

        click.echo("=" * 60)
        click.echo("✅ REEL GENERATED SUCCESSFULLY!")
        click.echo("=" * 60)
        click.echo(f"📄 Script: {script_path}")
        click.echo(f"🎙️  Audio: {audio_path}")
        click.echo(f"📊 Captions: {captions_path}")
        click.echo(f"🎬 VIDEO: {video_path}")
        click.echo(f"   Size: {size_mb:.1f} MB")
        click.echo(f"   Duration: {duration:.1f}s")
        click.echo("=" * 60)
        click.echo("\n🎉 Ready to upload to TikTok/Instagram/YouTube Shorts!")
        click.echo("💡 Review in video editor for final tweaks if needed")

    except Exception as e:
        click.echo(f"\n❌ Pipeline failed: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@cli.command()
@click.option('--topic', '-t', required=True, help='Topic for the script')
@click.option('--details', '-d', default='', help='Additional topic details')
@click.option('--style', '-s', type=click.Choice(['solo', 'dialogue']), default='solo', help='Script style')
@click.option('--output', '-o', default='script.txt', help='Output file path')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def script(topic: str, details: str, style: str, output: str, config: str):
    """
    Generate only the script (Phase 3).

    Example:
        python main.py script -t "DeepAI platform" -d "Free AI tools" -s solo
        python main.py script -t "Cursor IDE tips" -s dialogue -o my_script.txt
    """
    try:
        from reelforge.script_generator import ScriptGenerator

        click.echo(f"📝 Generating {style} script about: {topic}")

        if details:
            click.echo(f"   Context: {details}")

        cfg = load_config(config)
        generator = ScriptGenerator(cfg)

        script_text = generator.generate(topic, details, style)

        # Save to file
        with open(output, 'w', encoding='utf-8') as f:
            f.write(script_text)

        click.echo(f"\n✅ Script generated and saved to: {output}")
        click.echo("\n" + "="*60)
        click.echo(script_text)
        click.echo("="*60)

        # Validate script length
        is_valid, validation_msg = generator.validate_script_length(script_text, style)

        # Show word count and estimated duration
        word_count = len(script_text.split())
        estimated_duration = word_count / 2.5  # ~150 words per minute = 2.5 words per second
        click.echo(f"\n📊 Stats:")
        click.echo(f"   Words: {word_count}")
        click.echo(f"   Estimated duration: {estimated_duration:.1f} seconds")
        click.echo(f"   {validation_msg}")

        if not is_valid:
            click.echo("\n⚠️  WARNING: Script is too long and will likely exceed 60 seconds!")
            click.echo("   Consider regenerating with more specific constraints.")
            click.echo("   Or manually edit the script to shorten it.")

    except ValueError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--text', '-t', help='Text to convert to speech')
@click.option('--script', '-s', help='Script file to convert to speech')
@click.option('--output', '-o', default='output/audio.mp3', help='Output audio file path')
@click.option('--voice', '-v', help='Voice ID (optional, uses config default)')
@click.option('--rate', '-r', help='Speech rate (e.g., "+10%", "-5%")')
@click.option('--dialogue', '-d', is_flag=True, help='Script is dialogue format (requires character voice mapping)')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def tts(text: str, script: str, output: str, voice: str, rate: str, dialogue: bool, config: str):
    """
    Convert text to speech using EdgeTTS (Phase 4).

    Example:
        python main.py tts -t "Hello, this is a test" -o test.mp3
        python main.py tts -s script.txt -o voiceover.mp3
        python main.py tts -s dialogue.txt -d -o dialogue_audio.mp3
    """
    try:
        from reelforge.tts_engine import TTSEngine

        if not text and not script:
            click.echo("❌ Error: Must provide either --text or --script", err=True)
            raise click.Abort()

        cfg = load_config(config)
        engine = TTSEngine(cfg)

        # Read text from file if script is provided
        if script:
            if not os.path.exists(script):
                click.echo(f"❌ Error: Script file not found: {script}", err=True)
                raise click.Abort()

            with open(script, 'r', encoding='utf-8') as f:
                text = f.read()

            click.echo(f"📄 Loaded script from: {script}")

        click.echo(f"🎙️  Converting text to speech...")
        click.echo(f"   Text length: {len(text)} characters")
        click.echo(f"   Voice: {voice or cfg['tts']['voice']}")

        if dialogue:
            # Parse dialogue and synthesize with multiple voices
            from reelforge.script_generator import ScriptGenerator

            # Create temporary generator just for parsing
            temp_config = {
                'gemini_api_key': 'not-needed-for-parsing',
                'script': {'base_url': '', 'model': '', 'temperature': 0, 'max_tokens': 0}
            }
            generator = ScriptGenerator(temp_config)

            parsed_dialogue = generator.parse_dialogue(text)

            if not parsed_dialogue:
                click.echo("❌ Error: Failed to parse dialogue format", err=True)
                raise click.Abort()

            click.echo(f"   Detected {len(parsed_dialogue)} characters")

            # Synthesize dialogue
            result_path = engine.synthesize_dialogue_sync(parsed_dialogue, output)

        else:
            # Synthesize single voice
            result_path = engine.synthesize_sync(text, output, voice=voice, rate=rate)

        click.echo(f"\n✅ Audio generated: {result_path}")

        # Show audio info
        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip

        audio = AudioFileClip(str(result_path))
        duration = audio.duration
        audio.close()

        click.echo(f"📊 Duration: {duration:.1f} seconds")

        if duration < 55:
            click.echo("   ⚠️  Audio is shorter than 55 seconds")
        elif duration > 65:
            click.echo("   ⚠️  Audio is longer than 65 seconds")

    except ValueError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--audio', '-a', required=True, help='Audio file path')
@click.option('--output', '-o', default=None, help='Output file (JSON or SRT)')
@click.option('--format', '-f', type=click.Choice(['json', 'srt', 'both']), default='both', help='Output format')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def captions(audio: str, output: str, format: str, config: str):
    """
    Generate word-level captions from audio using WhisperX (Phase 5).

    Example:
        python main.py captions -a output/audio.mp3
        python main.py captions -a audio.mp3 -o captions.json -f json
    """
    try:
        from reelforge.caption_generator import CaptionGenerator

        if not os.path.exists(audio):
            click.echo(f"❌ Error: Audio file not found: {audio}", err=True)
            raise click.Abort()

        # Generate output paths
        if output is None:
            base = os.path.splitext(audio)[0]
            output_json = f"{base}_captions.json"
            output_srt = f"{base}_captions.srt"
        else:
            base = os.path.splitext(output)[0]
            output_json = f"{base}.json"
            output_srt = f"{base}.srt"

        cfg = load_config(config)

        click.echo(f"📊 Generating captions from: {audio}")
        click.echo(f"   Using WhisperX (base model)")
        click.echo(f"   Device: {'GPU' if torch.cuda.is_available() else 'CPU'}")

        generator = CaptionGenerator(cfg)

        # Generate word-level captions
        click.echo("\n🔍 Transcribing audio...")
        word_captions = generator.generate_captions(audio)

        click.echo(f"   ✓ Found {len(word_captions)} words")

        # Format captions
        formatted_captions = generator.format_captions(word_captions)
        click.echo(f"   ✓ Grouped into {len(formatted_captions)} caption segments")

        # Save in requested formats
        saved_files = []

        if format in ['json', 'both']:
            generator.save_captions_json(word_captions, output_json)
            click.echo(f"\n✅ JSON saved: {output_json}")
            saved_files.append(output_json)

        if format in ['srt', 'both']:
            generator.create_srt_subtitles(formatted_captions, output_srt)
            click.echo(f"✅ SRT saved: {output_srt}")
            saved_files.append(output_srt)

        # Show sample
        if formatted_captions:
            click.echo(f"\n📝 Sample captions:")
            for cap in formatted_captions[:3]:
                click.echo(f"   [{cap['start']:.1f}s - {cap['end']:.1f}s] {cap['text']}")
            if len(formatted_captions) > 3:
                click.echo(f"   ... and {len(formatted_captions) - 3} more")

        click.echo(f"\n💡 Next: Use these captions in video composition (Phase 6)")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--audio', '-a', required=True, help='Audio file path')
@click.option('--captions', '-c', required=True, help='Captions JSON file path')
@click.option('--background', '-b', help='Background video (random if not specified)')
@click.option('--character', '-ch', help='Character image path (optional)')
@click.option('--output', '-o', default='output/video.mp4', help='Output video path')
@click.option('--config', '-cfg', default='config.yaml', help='Path to config file')
def compose(audio: str, captions: str, background: str, character: str, output: str, config: str):
    """
    Compose final video from audio + captions + background (Phase 6).

    Example:
        python main.py compose -a audio.mp3 -c captions.json
        python main.py compose -a audio.mp3 -c captions.json -b video.mp4 -ch character.png
    """
    try:
        from reelforge.video_compositor import VideoCompositor
        from reelforge.caption_generator import CaptionGenerator

        # Validate inputs
        if not os.path.exists(audio):
            click.echo(f"❌ Error: Audio file not found: {audio}", err=True)
            raise click.Abort()

        if not os.path.exists(captions):
            click.echo(f"❌ Error: Captions file not found: {captions}", err=True)
            raise click.Abort()

        cfg = load_config(config)

        click.echo(f"🎬 Composing video...")
        click.echo(f"   Audio: {audio}")
        click.echo(f"   Captions: {captions}")

        if background:
            click.echo(f"   Background: {background}")
        else:
            click.echo(f"   Background: Random selection")

        if character:
            click.echo(f"   Character: {character}")

        # Load captions
        caption_gen = CaptionGenerator(cfg)
        word_captions = caption_gen.load_captions_json(captions)
        formatted_captions = caption_gen.format_captions(word_captions)

        # Compose video
        compositor = VideoCompositor(cfg)

        result = compositor.compose_video(
            audio_path=audio,
            captions_data=formatted_captions,
            output_path=output,
            background_path=background,
            character_path=character
        )

        click.echo(f"\n✅ Video created: {result}")

        # Show file size
        size_mb = os.path.getsize(result) / (1024 * 1024)
        click.echo(f"   Size: {size_mb:.1f} MB")

        click.echo(f"\n🎉 Ready to upload to TikTok/Instagram/YouTube Shorts!")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument('topic')
@click.option('--style', '-s', type=click.Choice(['solo', 'dialogue']), default='dialogue', help='Script style')
@click.option('--output', '-o', default=None, help='Output base name')
def quick(topic: str, style: str, output: str):
    """
    QUICK: Generate script + audio in ONE command (optimized for 60s reels).

    Example:
        python main.py quick "Why AI won't replace developers"
    """
    try:
        from reelforge.script_generator import ScriptGenerator
        from reelforge.tts_engine import TTSEngine
        import datetime

        if output is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"output/reel_{timestamp}"

        script_path = f"{output}_script.txt"
        audio_path = f"{output}_audio.mp3"

        cfg = load_config()

        click.echo(f"📝 Step 1/2: Generating {style} script...")
        generator = ScriptGenerator(cfg)

        word_limit = "130 words" if style == "dialogue" else "140 words"
        script_text = generator.generate(topic, f"Keep punchy, max {word_limit} for 60s reel", style)

        os.makedirs(os.path.dirname(script_path) or '.', exist_ok=True)
        with open(script_path, 'w') as f:
            f.write(script_text)

        _, validation_msg = generator.validate_script_length(script_text, style)
        click.echo(f"   ✓ {validation_msg}")

        click.echo(f"\n🎙️  Step 2/2: Converting to speech (optimized: +20% rate)...")

        engine = TTSEngine(cfg)
        if style == "dialogue":
            parsed_dialogue = generator.parse_dialogue(script_text)
            engine.synthesize_dialogue_sync(parsed_dialogue, audio_path)
        else:
            engine.synthesize_sync(script_text, audio_path, rate="+20%")

        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        audio.close()

        click.echo(f"\n✅ Done! {duration:.1f}s audio")
        click.echo(f"   📄 {script_path}")
        click.echo(f"   🎙️  {audio_path}")
        if 50 <= duration <= 70:
            click.echo(f"   🎯 Perfect for 60s reel!")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--language', '-l', default='en', help='Filter by language code (e.g., "en", "es", "fr")')
@click.option('--gender', '-g', type=click.Choice(['Male', 'Female', 'all']), default='all', help='Filter by gender')
def list_voices(language: str, gender: str):
    """
    List available EdgeTTS voices.

    Example:
        python main.py list-voices
        python main.py list-voices -l en -g Male
        python main.py list-voices -l es
    """
    try:
        from reelforge.tts_engine import TTSEngine

        click.echo(f"🎙️  Fetching available EdgeTTS voices...\n")

        voices = TTSEngine.list_voices_sync()

        # Filter by language
        if language:
            voices = [v for v in voices if v['Locale'].startswith(language)]

        # Filter by gender
        if gender != 'all':
            voices = [v for v in voices if v['Gender'] == gender]

        if not voices:
            click.echo(f"No voices found matching criteria (language={language}, gender={gender})")
            return

        click.echo(f"Found {len(voices)} voices:\n")

        # Group by locale
        from collections import defaultdict
        by_locale = defaultdict(list)
        for v in voices:
            by_locale[v['Locale']].append(v)

        for locale in sorted(by_locale.keys()):
            click.echo(f"📍 {locale}")
            for v in by_locale[locale]:
                gender_icon = "👨" if v['Gender'] == 'Male' else "👩"
                click.echo(f"   {gender_icon} {v['ShortName']:35s} ({v['Gender']})")
            click.echo()

        click.echo(f"💡 Tip: Use voice ShortName in config.yaml or with --voice flag")
        click.echo(f"   Example: --voice {voices[0]['ShortName']}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def validate(config: str):
    """
    Validate configuration and check assets.
    """
    try:
        cfg = load_config(config)
        click.echo(f"✓ Configuration loaded from: {config}")

        # Check API key
        if cfg.get('gemini_api_key') == 'YOUR_GEMINI_API_KEY_HERE':
            click.echo("⚠ Gemini API key not configured")
        else:
            click.echo("✓ Gemini API key configured")

        # Check assets
        backgrounds = cfg['assets']['backgrounds']
        click.echo(f"\nBackground videos: {len(backgrounds)}")
        for bg in backgrounds:
            if Path(bg).exists():
                click.echo(f"  ✓ {bg}")
            else:
                click.echo(f"  ✗ {bg} (not found)")

        characters = cfg['assets']['characters']
        click.echo(f"\nCharacter images: {len(characters)}")
        for char in characters:
            if Path(char).exists():
                click.echo(f"  ✓ {char}")
            else:
                click.echo(f"  ✗ {char} (not found)")

        font = cfg['assets']['fonts']['main']
        if Path(font).exists():
            click.echo(f"\n✓ Font: {font}")
        else:
            click.echo(f"\n✗ Font: {font} (not found)")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)


if __name__ == '__main__':
    cli()
