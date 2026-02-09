"""Text-to-speech command."""

from __future__ import annotations

import os
from typing import Optional

import click

from reelforge.pipeline.outputs import _audio_duration
from reelforge.shared.config import load_config


@click.command()
@click.option('--text', '-t', help='Text to convert to speech')
@click.option('--script', '-s', help='Script file to convert to speech')
@click.option('--output', '-o', default='output/audio.mp3', help='Output audio file path')
@click.option('--voice', '-v', help='Voice ID (optional, uses config default)')
@click.option('--rate', '-r', help='Speech rate (e.g., "+10%", "-5%")')
@click.option('--dialogue', '-d', is_flag=True, help='Script is dialogue format')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def tts(text: Optional[str], script: Optional[str], output: str, voice: Optional[str], rate: Optional[str], dialogue: bool, config: str):
    """Convert text to speech using EdgeTTS."""
    try:
        from reelforge.audio.tts_engine import TTSEngine

        if not text and not script:
            click.echo("Error: Must provide either --text or --script", err=True)
            raise click.Abort()

        cfg = load_config(config)
        engine = TTSEngine(cfg)

        if script:
            if not os.path.exists(script):
                click.echo(f"Error: Script file not found: {script}", err=True)
                raise click.Abort()
            with open(script, 'r', encoding='utf-8') as f:
                text = f.read()

        if dialogue:
            from reelforge.script.generator import ScriptGenerator

            generator = ScriptGenerator.__new__(ScriptGenerator)
            parsed_dialogue = generator.parse_dialogue(text or "")
            if not parsed_dialogue:
                click.echo("Error: Failed to parse dialogue format", err=True)
                raise click.Abort()
            engine.synthesize_dialogue_sync(parsed_dialogue, output)
        else:
            engine.synthesize_sync(text or "", output, voice=voice, rate=rate)

        duration = _audio_duration(output)
        click.echo(f"Audio generated: {output}")
        click.echo(f"Duration: {duration:.1f} seconds")

    except ValueError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise click.Abort()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()
