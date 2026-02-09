#!/usr/bin/env python3
"""ReelForge CLI - backward-compatible main entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from reelforge.cli.app import cli
from reelforge.pipeline import drive_upload as _drive_upload_impl
from reelforge.pipeline.orchestrator import _run_generate_pipeline
from reelforge.pipeline.outputs import _audio_duration, _build_output_paths, _resolve_duration_bounds, _resolve_mode
from reelforge.pipeline.quality_gate import (
    _assess_output_quality,
    _caption_coverage_ratio,
    _detect_risky_claims,
    _dialogue_is_strictly_alternating,
)


def _drive_upload_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return _drive_upload_impl._drive_upload_defaults(cfg)


def _upload_artifacts_to_drive(
    *,
    cfg: Dict[str, Any],
    logger,
    run_dir: Path,
    video_path: Path,
    metadata_path: Path,
) -> Dict[str, Any]:
    # Intentionally route defaults through this module-level function so tests
    # that monkeypatch `main._drive_upload_defaults` continue to work.
    return _drive_upload_impl._upload_artifacts_to_drive(
        cfg=cfg,
        logger=logger,
        run_dir=run_dir,
        video_path=video_path,
        metadata_path=metadata_path,
        defaults_factory=_drive_upload_defaults,
    )


if __name__ == '__main__':
    cli()
