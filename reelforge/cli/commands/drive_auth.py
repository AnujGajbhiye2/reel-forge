"""Google Drive auth command."""

from __future__ import annotations

import click

from reelforge.shared.config import load_config


@click.command()
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def drive_auth(config: str):
    """Run one-time Google Drive OAuth flow and store token JSON."""
    try:
        from reelforge.integrations.google_drive.uploader import GoogleDriveUploader

        cfg = load_config(config)
        uploader = GoogleDriveUploader.from_config(cfg)
        token_path = uploader.authenticate_interactive()
        click.echo(f"Google Drive auth complete. Token saved to: {token_path}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()
