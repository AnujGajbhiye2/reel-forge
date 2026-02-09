"""Caption generation command."""

from __future__ import annotations

import os
from typing import Optional

import click

from reelforge.shared.config import load_config


@click.command()
@click.option('--audio', '-a', required=True, help='Audio file path')
@click.option('--output', '-o', default=None, help='Output file (JSON or SRT)')
@click.option('--format', '-f', type=click.Choice(['json', 'srt', 'both']), default='both', help='Output format')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def captions(audio: str, output: Optional[str], format: str, config: str):
    """Generate word-level captions from audio using WhisperX."""
    try:
        from reelforge.captions.whisperx_generator import CaptionGenerator

        if not os.path.exists(audio):
            click.echo(f"Error: Audio file not found: {audio}", err=True)
            raise click.Abort()

        if output is None:
            base = os.path.splitext(audio)[0]
            output_json = f"{base}_captions.json"
            output_srt = f"{base}_captions.srt"
        else:
            base = os.path.splitext(output)[0]
            output_json = f"{base}.json"
            output_srt = f"{base}.srt"

        cfg = load_config(config)
        generator = CaptionGenerator(cfg)

        word_captions = generator.generate_captions(audio)
        formatted_captions = generator.format_captions(word_captions)

        if format in ['json', 'both']:
            generator.save_captions_json(word_captions, output_json)
            click.echo(f"JSON saved: {output_json}")

        if format in ['srt', 'both']:
            generator.create_srt_subtitles(formatted_captions, output_srt)
            click.echo(f"SRT saved: {output_srt}")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()
