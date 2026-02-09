"""Quick script+audio command."""

from __future__ import annotations

from typing import Optional

import click

from reelforge.pipeline.outputs import _audio_duration
from reelforge.core.run_context import create_run_paths
from reelforge.shared.config import load_config


@click.command()
@click.argument('topic')
@click.option('--style', '-s', type=click.Choice(['solo', 'dialogue']), default='dialogue', help='Script style')
@click.option('--output', '-o', default=None, help='Output base name')
def quick(topic: str, style: str, output: Optional[str]):
    """Quickly generate script + audio only."""
    try:
        from reelforge.script.generator import ScriptGenerator
        from reelforge.audio.tts_engine import TTSEngine

        if output is None:
            run = create_run_paths("output")
            script_path = str(run.script_path)
            audio_path = str(run.audio_path)
        else:
            script_path = f"{output}_script.txt"
            audio_path = f"{output}_audio.mp3"

        cfg = load_config()

        generator = ScriptGenerator(cfg)
        word_limit = "130 words" if style == "dialogue" else "140 words"
        script_text = generator.generate(topic, f"Keep punchy, max {word_limit} for 60s reel", style)

        import os
        os.makedirs(os.path.dirname(script_path) or '.', exist_ok=True)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_text)

        engine = TTSEngine(cfg)
        if style == "dialogue":
            parsed_dialogue = generator.parse_dialogue(script_text)
            engine.synthesize_dialogue_sync(parsed_dialogue, audio_path)
        else:
            engine.synthesize_sync(script_text, audio_path, rate="+20%")

        duration = _audio_duration(audio_path)

        click.echo(f"Done! {duration:.1f}s audio")
        click.echo(f"Script: {script_path}")
        click.echo(f"Audio: {audio_path}")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()
