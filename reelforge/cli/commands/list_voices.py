"""List voices command."""

from __future__ import annotations

import click


@click.command(name="list-voices")
@click.option('--language', '-l', default='en', help='Filter by language code (e.g., "en", "es", "fr")')
@click.option('--gender', '-g', type=click.Choice(['Male', 'Female', 'all']), default='all', help='Filter by gender')
def list_voices(language: str, gender: str):
    """List available EdgeTTS voices."""
    try:
        from collections import defaultdict

        from reelforge.audio.tts_engine import TTSEngine

        voices = TTSEngine.list_voices_sync()

        if language:
            voices = [v for v in voices if v['Locale'].startswith(language)]

        if gender != 'all':
            voices = [v for v in voices if v['Gender'] == gender]

        if not voices:
            click.echo(f"No voices found matching criteria (language={language}, gender={gender})")
            return

        click.echo(f"Found {len(voices)} voices:\n")

        by_locale = defaultdict(list)
        for voice in voices:
            by_locale[voice['Locale']].append(voice)

        for locale in sorted(by_locale.keys()):
            click.echo(f"{locale}")
            for voice in by_locale[locale]:
                click.echo(f"  {voice['ShortName']:35s} ({voice['Gender']})")
            click.echo()

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()
