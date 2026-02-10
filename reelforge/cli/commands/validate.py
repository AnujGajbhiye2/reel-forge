"""Config validation command."""

from __future__ import annotations

from pathlib import Path

import click

from reelforge.shared.config import load_config


@click.command()
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def validate(config: str):
    """Validate configuration and check assets."""
    try:
        cfg = load_config(config)
        click.echo(f"Configuration loaded from: {config}")

        key = cfg.get('openai_api_key') or cfg.get('gemini_api_key')
        if key in {None, 'YOUR_OPENAI_API_KEY_HERE', 'YOUR_GEMINI_API_KEY_HERE'}:
            click.echo("Warning: OpenAI API key not configured")
        else:
            click.echo("OpenAI API key configured")

        backgrounds = cfg['assets']['backgrounds']
        click.echo(f"\nBackground videos: {len(backgrounds)}")
        for bg in backgrounds:
            state = "OK" if Path(bg).exists() else "MISSING"
            click.echo(f"  {state:7s} {bg}")

        characters = cfg['assets']['characters']
        click.echo(f"\nCharacter images: {len(characters)}")
        for char in characters:
            state = "OK" if Path(char).exists() else "MISSING"
            click.echo(f"  {state:7s} {char}")

        font = cfg['assets']['fonts']['main']
        if Path(font).exists():
            click.echo(f"\nFont: {font}")
        else:
            click.echo(f"\nFont missing: {font}")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
