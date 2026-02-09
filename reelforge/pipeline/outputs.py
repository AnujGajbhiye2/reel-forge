"""Pipeline IO and output path helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from reelforge.core.run_context import create_run_paths

try:
    from moviepy import AudioFileClip
except ImportError:
    from moviepy.editor import AudioFileClip


def _audio_duration(audio_path: str) -> float:
    audio = AudioFileClip(audio_path)
    duration = float(audio.duration)
    audio.close()
    return duration


def _resolve_mode(cfg: Dict[str, Any], mode_override: Optional[str]) -> str:
    mode = mode_override or cfg.get("app", {}).get("mode", "dev")
    return mode if mode in {"dev", "prod"} else "dev"


def _resolve_duration_bounds(
    cfg: Dict[str, Any],
    min_duration: Optional[int],
    max_duration: Optional[int],
    max_retries: Optional[int],
) -> tuple[int, int, int]:
    duration_cfg = cfg.get("generation", {}).get("duration", {})
    minimum = int(min_duration if min_duration is not None else duration_cfg.get("min_seconds", 45))
    maximum = int(max_duration if max_duration is not None else duration_cfg.get("max_seconds", 60))
    retries = int(max_retries if max_retries is not None else duration_cfg.get("max_retries", 3))

    if minimum >= maximum:
        raise ValueError("min duration must be smaller than max duration")
    if retries < 1:
        raise ValueError("max retries must be at least 1")

    return minimum, maximum, retries


def _build_output_paths(
    cfg: Dict[str, Any],
    output: Optional[str],
    run_name: Optional[str],
) -> Dict[str, Path]:
    if output:
        base = Path(output)
        output_base = base.with_suffix("")
        out_dir = output_base.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        return {
            "run_dir": out_dir,
            "script": output_base.with_name(f"{output_base.name}_script.txt"),
            "audio": output_base.with_name(f"{output_base.name}_audio.mp3"),
            "captions": output_base.with_name(f"{output_base.name}_captions.json"),
            "video": output_base.with_suffix(".mp4"),
            "metadata": output_base.with_name(f"{output_base.name}_metadata.json"),
        }

    output_root = cfg.get("output", {}).get("directory", "output")
    run = create_run_paths(output_dir=output_root, run_name=run_name)
    return {
        "run_dir": run.run_dir,
        "script": run.script_path,
        "audio": run.audio_path,
        "captions": run.captions_path,
        "video": run.video_path,
        "metadata": run.metadata_path,
    }
