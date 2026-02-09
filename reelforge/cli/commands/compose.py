"""Video composition command."""

from __future__ import annotations

import json
import os
from typing import Optional

import click

from reelforge.shared.config import load_config


@click.command()
@click.option('--audio', '-a', required=True, help='Audio file path')
@click.option('--captions', '-c', required=True, help='Captions JSON file path')
@click.option('--background', '-b', help='Background video (random if not specified)')
@click.option('--character', '-ch', help='Primary character image path (optional)')
@click.option('--secondary-character', '-ch2', default=None, help='Secondary character image for dialogue mode')
@click.option('--screenshots-json', default=None, help='Screenshot timeline JSON from screenshot researcher')
@click.option('--output', '-o', default='output/video.mp4', help='Output video path')
@click.option('--config', '-cfg', default='config.yaml', help='Path to config file')
def compose(audio: str, captions: str, background: Optional[str], character: Optional[str], secondary_character: Optional[str], screenshots_json: Optional[str], output: str, config: str):
    """Compose final video from audio + captions + background."""
    try:
        from reelforge.captions.whisperx_generator import CaptionGenerator
        from reelforge.video_compositor import VideoCompositor

        if not os.path.exists(audio):
            click.echo(f"Error: Audio file not found: {audio}", err=True)
            raise click.Abort()

        if not os.path.exists(captions):
            click.echo(f"Error: Captions file not found: {captions}", err=True)
            raise click.Abort()

        cfg = load_config(config)

        caption_gen = CaptionGenerator(cfg)
        word_captions = caption_gen.load_captions_json(captions)
        formatted_captions = caption_gen.format_captions(word_captions)
        screenshots_data = []
        if screenshots_json:
            if not os.path.exists(screenshots_json):
                click.echo(f"Error: Screenshots JSON file not found: {screenshots_json}", err=True)
                raise click.Abort()
            with open(screenshots_json, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, list):
                screenshots_data = payload
            else:
                screenshots_data = payload.get("screenshots", [])

        compositor = VideoCompositor(cfg)
        result = compositor.compose_video(
            audio_path=audio,
            captions_data=formatted_captions,
            output_path=output,
            background_path=background,
            character_path=character,
            secondary_character_path=secondary_character,
            speaker_timeline=None,
            screenshots_data=screenshots_data,
        )

        click.echo(f"Video created: {result}")
        size_mb = os.path.getsize(result) / (1024 * 1024)
        click.echo(f"Size: {size_mb:.1f} MB")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()
