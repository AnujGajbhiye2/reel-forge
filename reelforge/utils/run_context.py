"""
Run context and artifact path helpers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RunPaths:
    """Paths for all generated artifacts in one run."""

    run_dir: Path
    script_path: Path
    audio_path: Path
    captions_path: Path
    video_path: Path
    metadata_path: Path


def slugify_name(value: str) -> str:
    """Create a filesystem-safe, readable slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-")


def create_run_paths(output_dir: str = "output", run_name: Optional[str] = None) -> RunPaths:
    """
    Create a timestamped run directory and standard artifact paths.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = ""
    if run_name:
        slug = slugify_name(run_name)
        suffix = f"_{slug}" if slug else ""

    run_dir = Path(output_dir) / f"run_{timestamp}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    return RunPaths(
        run_dir=run_dir,
        script_path=run_dir / "script.txt",
        audio_path=run_dir / "audio.mp3",
        captions_path=run_dir / "captions.json",
        video_path=run_dir / "video.mp4",
        metadata_path=run_dir / "metadata.json",
    )
