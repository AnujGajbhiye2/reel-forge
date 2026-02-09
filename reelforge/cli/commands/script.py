"""Script generation command."""

from __future__ import annotations

import click

from reelforge.shared.config import load_config


@click.command()
@click.option('--topic', '-t', required=True, help='Topic for the script')
@click.option('--details', '-d', default='', help='Additional topic details')
@click.option('--style', '-s', type=click.Choice(['solo', 'dialogue']), default='solo', help='Script style')
@click.option('--output', '-o', default='script.txt', help='Output file path')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def script(topic: str, details: str, style: str, output: str, config: str):
    """Generate only the script."""
    try:
        from reelforge.script.generator import ScriptGenerator

        cfg = load_config(config)
        generator = ScriptGenerator(cfg)

        script_text = generator.generate(topic, details, style)

        with open(output, 'w', encoding='utf-8') as f:
            f.write(script_text)

        click.echo(f"Script generated and saved to: {output}")

        is_valid, validation_msg = generator.validate_script_length(script_text, style)
        word_count = len(script_text.split())
        estimated_duration = word_count / 2.5
        click.echo(f"Words: {word_count}")
        click.echo(f"Estimated duration: {estimated_duration:.1f} seconds")
        click.echo(validation_msg)

        if not is_valid:
            click.echo("Warning: script likely exceeds target reel duration")

    except ValueError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise click.Abort()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()
