# ReelForge Codebase Reorganization Record

## Purpose
This document records the February 8, 2026 reorganization and cleanup that reduced file bloat while preserving existing behavior and CLI contracts.

## Goals
- Keep underlying logic unchanged.
- Move code into clearer pipeline-domain folders.
- Preserve compatibility for existing scripts/tests and CLI usage.
- Keep `python main.py ...` as the primary entrypoint.

## Compatibility Contract
The following remain stable after reorganization:
- CLI usage via `python main.py ...`
- Existing command names/options
- Helper imports used by tests from `main.py`:
  - `_assess_output_quality`
  - `_caption_coverage_ratio`
  - `_detect_risky_claims`
  - `_dialogue_is_strictly_alternating`
  - `_drive_upload_defaults`
  - `_upload_artifacts_to_drive`

## New Layout (Canonical)
```text
reelforge/
├── cli/
│   ├── app.py
│   ├── commands/
│   └── interactive/
├── pipeline/
│   ├── orchestrator.py
│   ├── quality_gate.py
│   ├── outputs.py
│   └── drive_upload.py
├── script/
│   ├── generator.py
│   └── templates/prompts.py
├── audio/tts_engine.py
├── captions/whisperx_generator.py
├── research/screenshot_researcher.py
├── integrations/google_drive/uploader.py
├── core/
│   ├── logging.py
│   └── run_context.py
└── shared/config.py
```

## Cleanup Note
After the reorganization, a cleanup pass removed legacy shim modules and old folders (`reelforge/utils`, `reelforge/templates`) once all imports were migrated to canonical package paths.

## Main Entrypoint Strategy
- `main.py` is now a thin compatibility entrypoint.
- CLI is wired from `reelforge/cli/app.py`.
- Pipeline internals are moved to `reelforge/pipeline/*`.
- `main.py` keeps compatibility wrappers so monkeypatched tests continue to work.

## Special Compatibility Note
`reelforge/video_compositor.py` remains the class-definition home for `VideoCompositor` to preserve tests/patches that monkeypatch module-level symbols (`ImageClip`, `ColorClip`).

## Validation Executed
- `venv/bin/python -m compileall -q main.py reelforge`
- `venv/bin/python -m pytest -q`
- Result: `60 passed, 2 skipped`

## Future Cleanup (Optional, Non-Urgent)
- Further split large modules (`research/screenshot_researcher.py`) if readability pressure increases.
