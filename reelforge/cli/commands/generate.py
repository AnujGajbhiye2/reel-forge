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
@click.option('--websites', default=None, help='Specific websites/tools to feature (comma-separated, for MCP mode)')
@click.option('--length', default='60s', type=click.Choice(['30s', '45s', '60s']), help='Target video length (for MCP mode)')
@click.option('--profanity', default='none', type=click.Choice(['none', 'light', 'allowed']), help='Profanity level (for MCP mode)')
@click.option('--disable-mcp', is_flag=True, help='Disable MCP, use legacy script generator')
@click.option('--custom-script', type=click.Path(exists=True), default=None, help='Path to custom script file (skips LLM generation)')
@click.option('--image-map', type=click.Path(exists=True), default=None, help='Optional JSON map of marker IDs to local files/URLs')
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
    websites: str | None,
    length: str,
    profanity: str,
    disable_mcp: bool,
    custom_script: str | None,
    image_map: str | None = None,
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
            websites=websites,
            length=length,
            profanity=profanity,
            disable_mcp=disable_mcp,
            custom_script_path=custom_script,
            image_map_path=image_map,
        )

        click.echo("")
        click.echo("=" * 60)
        click.echo("  REEL GENERATED SUCCESSFULLY")
        click.echo("=" * 60)
        click.echo(f"  Video:    {result['video_path']}")
        click.echo(f"  Duration: {result['duration']:.1f}s | Size: {result['size_mb']:.1f} MB")
        click.echo(f"  Quality:  {result['quality_verdict']}")
        click.echo(
            f"  Audio:    {result['audio_duration_seconds']:.2f}s | "
            f"Captions: {result['caption_word_count']}/{result['script_word_count']} "
            f"({result['caption_coverage_ratio']:.2f})"
        )
        click.echo(
            f"  Images:   {result['screenshot_captured_count']}/{result['screenshot_target_count']} "
            f"({result['screenshot_coverage_ratio']:.2f})"
        )
        if result.get("screenshot_top_failure"):
            click.echo(f"  Image Note: {result['screenshot_top_failure']}")
        click.echo(
            f"  Drive:    {result.get('drive_upload_status', 'unknown')}"
            + (
                f" ({result['drive_upload_error_short']})"
                if result.get("drive_upload_error_short")
                else ""
            )
        )
        click.echo("-" * 60)
        click.echo(f"  Script:   {result['script_path']}")
        click.echo(f"  Audio:    {result['audio_path']}")
        click.echo(f"  Captions: {result['captions_path']}")
        click.echo(f"  Metadata: {result['metadata_path']}")
        if result.get("summary_mode") == "verbose":
            click.echo(f"  Log:      {result['log_path']}")
        click.echo("=" * 60)
    except Exception as exc:
        click.echo(f"Pipeline failed: {exc}", err=True)
        raise click.Abort()
