# Codex Notes - ReelForge Reliability (2026-02-10)

## Context
Recent upgrades in `UPGRADE_PLAN.md` are implemented (karaoke captions, audio mixer, prompt v2, animation, Kokoro, transitions, pose switching). Current failures are post-upgrade regressions and hardening gaps.

## Primary Failures Observed
1. Video composition crash:
   - Error: `'ImageClip' object has no attribute 'set_start'`
   - Root cause: MoviePy v2 API mismatch in `reelforge/captions/pillow_renderer.py`.

2. Additional latent MoviePy breakpoints:
   - Legacy `set_position` usage in animation/compositor branches.

3. Script output instability:
   - Frequent non-alternating dialogue retries.
   - Wrapper residue like headings/keyword labels leaking into validation path.

4. Diagnostics gap:
   - Composition exception wrapping reduced traceback context.
   - Failures lacked structured per-run crash artifact.

5. Caption runtime drift risk:
   - WhisperX stack warnings indicate potential environment drift.

## Decisions Applied
- Failure policy: fail fast on invalid dialogue format.
- Duration policy: keep closest attempt with explicit warning.
- Caption stack policy: lock tested dependency versions and surface drift warnings.

## Implemented Actions
1. MoviePy compatibility hardening
   - Updated `pillow_renderer` to prefer `with_start` / `with_position` with v1 fallbacks.
   - Added position compatibility helper in `video_compositor`.
   - Updated animation code to v2-first position handling.

2. Script sanitization and MCP parsing hardening
   - Added `sanitize_dialogue_script()` in `reelforge/script/types.py`.
   - `parse_mcp_output()` now sanitizes dialogue even when keyword lines are missing and parses keyword lines robustly.
   - Orchestrator now sanitizes generated/expanded dialogue before validation/TTS.

3. Failure observability
   - Added `_write_failure_snapshot()` to orchestrator.
   - Writes `failure_snapshot.json` with stage/reason for key fatal paths (validation, script gen, TTS, pre-render quality gate, composition, quality trash verdict).
   - `video_compositor` now logs full exception context and re-raises with chained traceback.

4. Metadata improvements
   - Added `duration_target_met`.
   - Added `script_sanitization_applied` and `script_sanitization_changes`.
   - Added placeholder `failure_stage` / `failure_reason` fields.

5. Dependency pinning and runtime checks
   - Pinned `torch==2.8.0`, `torchaudio==2.8.0`, `pyannote.audio==3.4.0` in `requirements.txt`.
   - Added runtime drift warning checks in `CaptionGenerator`.

6. Regression tests added/updated
   - `tests/test_pillow_renderer.py`: validates karaoke clip build on MoviePy v2-style API.
   - `tests/test_video_compositor_layout.py`: validates position compatibility helper behavior.
   - `tests/test_mcp_integration.py`: validates sanitization and wrapper-line handling in MCP parsing.

## Expected Outcome
- Caption composition no longer crashes on MoviePy v2 API differences.
- Dialogue wrapper noise is stripped before quality checks and TTS.
- Fatal runs leave actionable stage-specific failure snapshots.
- Output metadata explicitly indicates duration-target compliance and sanitization activity.
