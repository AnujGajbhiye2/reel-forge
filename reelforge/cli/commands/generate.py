"""Generate command."""

from __future__ import annotations

import click

from reelforge.pipeline.orchestrator import _run_generate_pipeline


@click.command()
@click.option('--topic', '-t', required=True, help='Topic for the video')
@click.option('--details', '-d', default='', help='Additional topic details')
@click.option('--style', '-s', type=click.Choice(['solo', 'dialogue']), default='dialogue', help='Script style')
@click.option('--background', '-b', help='Specific background video (random if not specified)')
@click.option('--character', '-ch', help='Primary character image overlay (optional)')
@click.option('--secondary-character', '-ch2', default=None, help='Secondary character image for dialogue mode')
@click.option('--output', '-o', default=None, help='Output video path (auto run folder if not specified)')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
@click.option('--mode', type=click.Choice(['dev', 'prod']), default=None, help='Run mode override')
@click.option('--min-duration', type=int, default=None, help='Minimum target duration in seconds')
@click.option('--max-duration', type=int, default=None, help='Maximum target duration in seconds')
@click.option('--max-retries', type=int, default=None, help='Maximum generation attempts for duration target')
@click.option('--run-name', default=None, help='Optional run name suffix for output folder')
@click.option('--voice', '-v', default=None, help='Primary voice override')
@click.option('--auto-screenshots/--no-auto-screenshots', default=None, help='Enable automatic web screenshot research')
@click.option('--screenshot-count', type=int, default=None, help='Target screenshot count override')
@click.option('--seed-url', multiple=True, help='Trusted URL seed for screenshot capture (repeatable)')
@click.option('--websites', default=None, help='Specific websites/tools to feature (comma-separated, for MCP mode)')
@click.option('--length', default='45s', type=click.Choice(['30s', '45s', '60s']), help='Target video length (for MCP mode)')
@click.option('--profanity', default='none', type=click.Choice(['none', 'light', 'allowed']), help='Profanity level (for MCP mode)')
@click.option('--disable-mcp', is_flag=True, help='Disable MCP, use legacy script generator')
@click.option('--custom-script', type=click.Path(exists=True), default=None, help='Path to custom script file (skips LLM generation)')
def generate(
    topic: str,
    details: str,
    style: str,
    background: str | None,
    character: str | None,
    secondary_character: str | None,
    output: str | None,
    config: str,
    mode: str | None,
    min_duration: int | None,
    max_duration: int | None,
    max_retries: int | None,
    run_name: str | None,
    voice: str | None,
    auto_screenshots: bool | None,
    screenshot_count: int | None,
    seed_url: tuple[str, ...],
    websites: str | None,
    length: str,
    profanity: str,
    disable_mcp: bool,
    custom_script: str | None,
):
    """Generate complete reel from topic to final video."""
    try:
        result = _run_generate_pipeline(
            topic=topic,
            details=details,
            style=style,
            background=background,
            character=character,
            secondary_character=secondary_character,
            output=output,
            config_path=config,
            mode=mode,
            min_duration=min_duration,
            max_duration=max_duration,
            max_retries=max_retries,
            run_name=run_name,
            primary_voice=voice,
            auto_screenshots=auto_screenshots,
            screenshot_count=screenshot_count,
            seed_urls=list(seed_url),
            websites=websites,
            length=length,
            profanity=profanity,
            disable_mcp=disable_mcp,
            custom_script_path=custom_script,
        )

        click.echo("=" * 60)
        click.echo("REEL GENERATED SUCCESSFULLY")
        click.echo("=" * 60)
        click.echo(f"Script:   {result['script_path']}")
        click.echo(f"Audio:    {result['audio_path']}")
        click.echo(f"Captions: {result['captions_path']}")
        click.echo(f"Video:    {result['video_path']}")
        click.echo(f"Metadata: {result['metadata_path']}")
        click.echo(f"Log:      {result['log_path']}")
        click.echo(f"Size:     {result['size_mb']:.1f} MB")
        click.echo(f"Duration: {result['duration']:.1f}s")
        click.echo(f"Quality:  {result['quality_verdict']}")
        click.echo(f"Drive:    {result.get('drive_upload_status', 'skipped')}")
        click.echo("=" * 60)
    except Exception as exc:
        click.echo(f"Pipeline failed: {exc}", err=True)
        raise click.Abort()
