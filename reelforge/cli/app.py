"""CLI application entrypoint and command wiring."""

from __future__ import annotations

import click

from reelforge.cli.interactive.wizard import launch_interactive_wizard
from reelforge.cli.commands.captions import captions
from reelforge.cli.commands.compose import compose
from reelforge.cli.commands.drive_auth import drive_auth
from reelforge.cli.commands.generate import generate
from reelforge.cli.commands.list_voices import list_voices
from reelforge.cli.commands.quick import quick
from reelforge.cli.commands.script import script
from reelforge.cli.commands.tts import tts
from reelforge.cli.commands.validate import validate
from reelforge.shared.config import load_config


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx: click.Context):
    """
    ReelForge - Semi-automated faceless AI/tech social media reel generator.
    """
    if ctx.invoked_subcommand is not None:
        return

    try:
        cfg = load_config("config.yaml")
        wizard = launch_interactive_wizard(cfg)
    except Exception as exc:
        click.echo(f"Interactive mode unavailable: {exc}", err=True)
        click.echo("Run 'python main.py --help' for CLI commands.")
        return

    if not wizard:
        return

    action = wizard.get("action")
    if action == "list_voices":
        ctx.invoke(list_voices, language="en", gender="all")
        return
    if action == "validate":
        ctx.invoke(validate, config="config.yaml")
        return

    ctx.invoke(
        generate,
        topic=wizard["topic"],
        details=wizard["details"],
        style=wizard["style"],
        background=wizard.get("background"),
        character=wizard.get("character"),
        secondary_character=wizard.get("secondary_character"),
        output=None,
        config="config.yaml",
        mode=wizard.get("mode"),
        min_duration=None,
        max_duration=None,
        max_retries=None,
        run_name=wizard.get("run_name"),
        voice=wizard.get("voice"),
        websites=None,
        length="60s",
        profanity="none",
        disable_mcp=False,
        custom_script=wizard.get("custom_script_path"),
    )


cli.add_command(generate)
cli.add_command(script)
cli.add_command(tts)
cli.add_command(captions)
cli.add_command(compose)
cli.add_command(quick)
cli.add_command(list_voices)
cli.add_command(drive_auth)
cli.add_command(validate)
