"""End-to-end generate pipeline orchestration."""

from __future__ import annotations

import atexit
import json
import logging
import multiprocessing
import os
import queue
import re
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import click

from reelforge.core.logging import setup_logging
from reelforge.core.progress import StageReporter
from reelforge.shared.config import load_config


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_generate_lock(*, lock_path: Path, run_dir: Path, log_path: Path, logger) -> None:
    """Prevent multiple concurrent generate runs in the same workspace."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists():
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        existing_pid = int(payload.get("pid") or 0)
        if _pid_is_alive(existing_pid):
            active_run_dir = payload.get("run_dir")
            active_log = payload.get("log_path")
            raise RuntimeError(
                "Another ReelForge generate run is already active "
                f"(pid={existing_pid}, run_dir={active_run_dir}, log={active_log}). "
                "Wait for it to finish or stop that process before starting a new run."
            )
        logger.warning("Found stale generate lock at %s; replacing it.", lock_path)
        lock_path.unlink(missing_ok=True)

    payload = {
        "pid": os.getpid(),
        "run_dir": str(run_dir),
        "log_path": str(log_path),
        "created_at": int(time.time()),
    }
    lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _release_generate_lock(*, lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        # Lock cleanup should never mask pipeline success/failure.
        return


def _duration_is_soft_acceptable(
    *,
    duration_seconds: float,
    lower_bound: int,
    upper_bound: int,
    attempt: int,
) -> bool:
    """Accept near misses after at least one retry to avoid excessive TTS churn."""
    if attempt < 2:
        return False
    soft_min = max(1, lower_bound - 3)
    return soft_min <= duration_seconds <= upper_bound


def _compose_video_worker(
    *,
    cfg: Dict[str, Any],
    compose_kwargs: Dict[str, Any],
    progress_queue,
    result_queue,
) -> None:
    from reelforge.video_compositor import VideoCompositor

    def _on_progress(percent: int) -> None:
        try:
            progress_queue.put({"type": "progress", "percent": int(percent)})
        except Exception:
            return

    try:
        compositor = VideoCompositor(cfg)
        result = compositor.compose_video(
            audio_path=compose_kwargs["audio_path"],
            captions_data=compose_kwargs["captions_data"],
            output_path=compose_kwargs["output_path"],
            background_path=compose_kwargs.get("background_path"),
            character_path=compose_kwargs.get("character_path"),
            secondary_character_path=compose_kwargs.get("secondary_character_path"),
            speaker_timeline=compose_kwargs.get("speaker_timeline"),
            screenshots_data=compose_kwargs.get("screenshots_data"),
            progress_callback=_on_progress,
        )
        result_queue.put(
            {
                "ok": True,
                "video_path": str(result),
                "selected_background": compositor.last_background_path,
            }
        )
    except Exception as exc:
        result_queue.put({"ok": False, "error": str(exc)})
    finally:
        progress_queue.put({"type": "done"})


def _compose_video_with_timeout(
    *,
    cfg: Dict[str, Any],
    compose_kwargs: Dict[str, Any],
    progress_enabled: bool,
):
    render_cfg = cfg.get("render", {})
    timeout_seconds = int(render_cfg.get("timeout_seconds", 900))
    if timeout_seconds < 30:
        timeout_seconds = 30

    ctx = multiprocessing.get_context("spawn")
    progress_queue = ctx.Queue()
    result_queue = ctx.Queue()
    process = ctx.Process(
        target=_compose_video_worker,
        kwargs={
            "cfg": cfg,
            "compose_kwargs": compose_kwargs,
            "progress_queue": progress_queue,
            "result_queue": result_queue,
        },
    )

    started = time.monotonic()
    last_percent = -1
    timed_out = False
    result_payload: Optional[Dict[str, Any]] = None
    process.start()

    if progress_enabled:
        click.echo("Composing video:   0%", nl=False)

    try:
        while True:
            elapsed = time.monotonic() - started
            if elapsed > timeout_seconds:
                timed_out = True
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                break

            try:
                while True:
                    msg = progress_queue.get_nowait()
                    if msg.get("type") == "progress":
                        percent = int(msg.get("percent", 0))
                        if percent != last_percent:
                            last_percent = percent
                            if progress_enabled:
                                click.echo(f"\rComposing video: {percent:3d}%", nl=False)
            except queue.Empty:
                pass

            try:
                result_payload = result_queue.get_nowait()
                break
            except queue.Empty:
                pass

            if not process.is_alive():
                break
            time.sleep(0.1)
    finally:
        process.join(timeout=2)

    elapsed = time.monotonic() - started
    if timed_out:
        if progress_enabled:
            click.echo("\rComposing video: timeout")
        raise RuntimeError(
            f"Video composition exceeded timeout ({timeout_seconds}s) at {max(last_percent, 0)}% progress."
        )

    if result_payload is None:
        try:
            result_payload = result_queue.get_nowait()
        except queue.Empty:
            result_payload = None

    if not result_payload:
        if progress_enabled:
            click.echo("\rComposing video: failed")
        raise RuntimeError(
            f"Video composition process exited unexpectedly (exit_code={process.exitcode})."
        )

    if not result_payload.get("ok"):
        if progress_enabled:
            click.echo("\rComposing video: failed")
        raise RuntimeError(str(result_payload.get("error") or "Unknown compose failure"))

    if progress_enabled:
        click.echo("\rComposing video: 100%")
    return (
        str(result_payload["video_path"]),
        result_payload.get("selected_background"),
        max(last_percent, 0),
        elapsed,
    )


def _strip_markers(text: str) -> str:
    """Remove [SHOW:S#] markers from script text so TTS doesn't speak them."""
    return re.sub(r'\s*\[SHOW:S\d+\]', '', text)


def _configure_external_logging(*, suppress_noise: bool) -> None:
    """Reduce third-party terminal noise while keeping app logs useful."""
    if not suppress_noise:
        return

    noisy_loggers = [
        "whisperx",
        "whisperx.asr",
        "whisperx.vads.pyannote",
        "pytorch_lightning",
        "pyannote",
        "torch",
    ]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.ERROR)


def _load_manual_image_map(
    *,
    image_map_path: Optional[str],
    run_dir: Path,
    logger,
) -> Dict[str, str]:
    """Load optional marker image overrides from JSON map."""
    if not image_map_path:
        return {}

    raw = Path(image_map_path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("image-map must be a JSON object keyed by marker IDs (e.g. S1).")

    resolved: Dict[str, str] = {}
    manual_dir = run_dir / "manual_images"
    manual_dir.mkdir(parents=True, exist_ok=True)

    for marker_id, value in payload.items():
        marker = str(marker_id).strip().upper()
        if not marker:
            continue

        source = str(value).strip() if value is not None else ""
        if not source:
            continue

        if source.startswith("http://") or source.startswith("https://"):
            parsed = urlparse(source)
            suffix = Path(parsed.path).suffix.lower() or ".jpg"
            destination = manual_dir / f"{marker.lower()}{suffix}"
            urllib.request.urlretrieve(source, destination)
            resolved[marker] = str(destination)
            logger.info("Downloaded manual image map %s from URL", marker)
            continue

        local_path = Path(source).expanduser()
        if not local_path.is_absolute():
            local_path = (Path.cwd() / local_path).resolve()
        if not local_path.exists():
            raise RuntimeError(f"image-map path for {marker} does not exist: {local_path}")
        resolved[marker] = str(local_path)

    logger.info("Loaded %d manual image-map overrides", len(resolved))
    return resolved


def _write_failure_snapshot(
    *,
    run_dir: Path,
    stage: str,
    reason: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist structured failure details for post-mortem debugging."""
    payload: Dict[str, Any] = {
        "stage": stage,
        "reason": reason,
    }
    if extra:
        payload.update(extra)

    try:
        snapshot_path = run_dir / "failure_snapshot.json"
        with open(snapshot_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except Exception:
        # Snapshot logging must never mask the original failure.
        return

def _discover_local_screenshots(
    keyword_map: Dict[str, str],
    screenshots_dir: Path,
    logger,
) -> Dict[str, str]:
    """Discover user-provided screenshots from a local folder.

    Convention: files named S1.png, S2.jpg, etc.
    Matches marker IDs (case-insensitive) to files in the directory.
    """
    if not screenshots_dir.exists():
        return {}

    id_to_path: Dict[str, str] = {}
    for marker_id in keyword_map:
        for ext in ('.png', '.jpg', '.jpeg', '.webp'):
            for name in (marker_id.lower(), marker_id.upper()):
                candidate = screenshots_dir / f"{name}{ext}"
                if candidate.exists():
                    id_to_path[marker_id] = str(candidate)
                    logger.info("Found local screenshot for %s: %s", marker_id, candidate)
                    break
            if marker_id in id_to_path:
                break

    return id_to_path


from reelforge.pipeline.drive_upload import _drive_upload_defaults, _upload_artifacts_to_drive
from reelforge.pipeline.outputs import _audio_duration, _build_output_paths, _resolve_duration_bounds, _resolve_mode
from reelforge.pipeline.quality_gate import _assess_output_quality


def _run_generate_pipeline(
    *,
    topic: str,
    details: str,
    style: str,
    background: Optional[str],
    character: Optional[str],
    secondary_character: Optional[str],
    output: Optional[str],
    config_path: str,
    mode: Optional[str],
    min_duration: Optional[int],
    max_duration: Optional[int],
    max_retries: Optional[int],
    run_name: Optional[str],
    primary_voice: Optional[str],
    websites: Optional[str] = None,
    length: str = "60s",
    profanity: str = "none",
    disable_mcp: bool = False,
    custom_script_path: Optional[str] = None,
    image_map_path: Optional[str] = None,
    drive_defaults_factory=None,
) -> Dict[str, Any]:
    from reelforge.captions.whisperx_generator import CaptionGenerator
    from reelforge.script.generator import ScriptGenerator
    from reelforge.audio.tts_engine import TTSEngine

    cfg = load_config(config_path)
    selected_mode = _resolve_mode(cfg, mode)
    logger, log_path = setup_logging(selected_mode, cfg.get("logging", {}).get("dir", "logs"))
    ui_cfg = cfg.get("ui", {})
    progress_enabled = bool(ui_cfg.get("progress", True))
    suppress_noise = bool(ui_cfg.get("noise_suppression", True))
    _configure_external_logging(suppress_noise=suppress_noise)
    reporter = StageReporter(enabled=progress_enabled)

    lower_bound, upper_bound, attempts_allowed = _resolve_duration_bounds(
        cfg, min_duration, max_duration, max_retries
    )

    paths = _build_output_paths(cfg, output, run_name)
    output_root = Path(cfg.get("output", {}).get("directory", "output"))
    lock_path = output_root / ".reelforge_generate.lock"
    _acquire_generate_lock(
        lock_path=lock_path,
        run_dir=paths["run_dir"],
        log_path=Path(log_path),
        logger=logger,
    )
    atexit.register(_release_generate_lock, lock_path=lock_path)
    manual_image_map = _load_manual_image_map(
        image_map_path=image_map_path,
        run_dir=paths["run_dir"],
        logger=logger,
    )
    manual_image_applied = 0
    manual_markers_applied: set[str] = set()
    screenshot_source_by_marker: Dict[str, Dict[str, Any]] = {}
    compose_elapsed_seconds = 0.0
    compose_last_progress_percent = 0

    logger.info("Starting generation topic='%s' style='%s'", topic, style)
    logger.info("Output video path: %s", paths["video"])

    # Select script generator (MCP or legacy)
    mcp_mode = cfg.get("script", {}).get("use_mcp", True) and not disable_mcp
    if mcp_mode:
        from reelforge.script.mcp_generator import MCPScriptGenerator
        generator = MCPScriptGenerator(cfg)
        logger.info("Using MCP script generator")
    else:
        generator = ScriptGenerator(cfg)
        logger.info("Using legacy script generator")

    # Initialize TTS engine (Kokoro or EdgeTTS)
    tts_provider = cfg.get("tts", {}).get("provider", "edge")
    if tts_provider == "kokoro":
        try:
            from reelforge.audio.kokoro_engine import KokoroTTSEngine
            engine = KokoroTTSEngine(cfg)
            logger.info("Using Kokoro TTS engine")
        except Exception as e:
            logger.warning(f"Kokoro TTS not available, falling back to EdgeTTS: {e}")
            engine = TTSEngine(cfg)
    else:
        engine = TTSEngine(cfg)

    caption_gen = CaptionGenerator(cfg)
    screenshots_dir = Path(cfg.get("screenshots", {}).get("directory", "screenshots"))
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    script_text = ""
    script_with_markers = None
    keyword_map = {}
    id_to_path = {}
    parsed_dialogue: Dict[str, list] = {}
    speaker_timeline = None
    final_duration = 0.0
    attempts_used = 0
    duration_accepted = False
    audio_created = False
    last_failure_reason = "unknown"
    target_midpoint = (lower_bound + upper_bound) / 2.0
    best_distance = float("inf")
    best_duration = 0.0
    best_script_text = ""
    best_speaker_timeline = None
    best_audio_path = paths["run_dir"] / "best_attempt_audio.mp3"
    min_word_target = 130 if style == "solo" else 120
    max_word_target = 160 if style == "solo" else 150
    model_candidates = list(getattr(generator, "models", [generator.model]))
    model_index = 0
    script_sanitization_applied = False
    script_sanitization_changes = 0

    constraints = (
        f"Keep pace punchy and complete. Target spoken duration between {lower_bound} and {upper_bound} seconds. "
        f"Do not underwrite. End cleanly with a strong closing line."
    )
    enhanced_details = f"{details} {constraints}".strip()

    def _sanitize_dialogue_if_needed(text: str) -> str:
        nonlocal script_sanitization_applied, script_sanitization_changes
        if style != "dialogue":
            return text
        from reelforge.script.types import sanitize_dialogue_script

        cleaned = sanitize_dialogue_script(text)
        if cleaned != text:
            script_sanitization_applied = True
            script_sanitization_changes += 1
            logger.info("Sanitized dialogue script output (removed non-dialogue wrapper lines)")
        return cleaned

    # Handle custom script (skip LLM generation)
    is_custom_script = bool(custom_script_path)
    if custom_script_path:
        logger.info("Using custom script from: %s", custom_script_path)
        with open(custom_script_path, 'r', encoding='utf-8') as f:
            raw_script = f.read()

        # Parse MCP format if markers are present
        if '[SHOW:' in raw_script:
            from reelforge.script.types import parse_mcp_output
            script_with_markers = parse_mcp_output(raw_script)
            keyword_map = script_with_markers.keyword_map
            # Strip markers from the text that goes to TTS/captions
            script_text = _strip_markers(script_with_markers.dialogue_text)
            logger.info("Custom script has %d MCP markers", len(keyword_map))
        else:
            script_text = raw_script.strip()

        if style == "dialogue":
            script_text = _sanitize_dialogue_if_needed(script_text)
        else:
            # Strip REEL TITLE lines for solo/custom non-MCP scripts.
            script_text = re.sub(r'^REEL TITLE:.*\n?', '', script_text, flags=re.MULTILINE).strip()

        from reelforge.pipeline.quality_gate import _word_count
        word_count = _word_count(script_text)
        logger.info("Custom script loaded with %d words", word_count)

        # Upfront validation with clear feedback
        hard_min = max(1, min_word_target - 30)  # absolute floor (e.g. 70 for dialogue)
        hard_max = max_word_target + 40           # absolute ceiling (e.g. 170 for dialogue)
        if word_count < hard_min:
            reason = (
                f"Script too short: {word_count} words. "
                f"Minimum is ~{min_word_target} words for '{style}' style "
                f"(hard floor: {hard_min}). Please add more content."
            )
            _write_failure_snapshot(
                run_dir=paths["run_dir"],
                stage="custom_script_validation",
                reason=reason,
                extra={"style": style, "word_count": word_count},
            )
            raise RuntimeError(
                reason
            )
        if word_count > hard_max:
            reason = (
                f"Script too long: {word_count} words. "
                f"Maximum is ~{max_word_target} words for '{style}' style "
                f"(hard ceiling: {hard_max}). Please shorten your script."
            )
            _write_failure_snapshot(
                run_dir=paths["run_dir"],
                stage="custom_script_validation",
                reason=reason,
                extra={"style": style, "word_count": word_count},
            )
            raise RuntimeError(
                reason
            )

        # Validate script format for dialogue mode
        if style == "dialogue":
            parsed_dialogue = generator.parse_dialogue(script_text)
            if not parsed_dialogue:
                reason = (
                    "Custom script is not in valid dialogue format. "
                    "Expected format: 'A: text' and 'B: text' on separate lines."
                )
                _write_failure_snapshot(
                    run_dir=paths["run_dir"],
                    stage="custom_script_validation",
                    reason=reason,
                    extra={"style": style},
                )
                raise RuntimeError(
                    reason
                )

            # Check dialogue alternation
            from reelforge.pipeline.quality_gate import _dialogue_is_strictly_alternating
            if not _dialogue_is_strictly_alternating(script_text):
                reason = (
                    "Custom dialogue script is not in strict alternating speaker format. "
                    "Speaker A must be followed by speaker B, then A, then B, etc."
                )
                _write_failure_snapshot(
                    run_dir=paths["run_dir"],
                    stage="custom_script_validation",
                    reason=reason,
                    extra={"style": style},
                )
                raise RuntimeError(
                    reason
                )

        # Save script
        with open(paths["script"], "w", encoding="utf-8") as handle:
            handle.write(script_text)

        # Generate TTS (skip retry loop)
        attempts_used = 1
        with reporter.stage("Generating audio"):
            if style == "dialogue":
                voice_mapping = None
                if primary_voice:
                    chars = list(parsed_dialogue.keys())
                    voice_mapping = {chars[0]: primary_voice}

                dialogue_result = engine.synthesize_dialogue_sync(
                    parsed_dialogue,
                    str(paths["audio"]),
                    voice_mapping=voice_mapping,
                    return_timeline=True,
                )
                _, speaker_timeline = dialogue_result
            else:
                engine.synthesize_sync(
                    script_text,
                    str(paths["audio"]),
                    voice=primary_voice,
                    rate=cfg.get("tts", {}).get("rate", "+15%"),
                )

        if not Path(paths["audio"]).exists():
            _write_failure_snapshot(
                run_dir=paths["run_dir"],
                stage="tts_generation",
                reason="TTS failed to generate audio from custom script.",
            )
            raise RuntimeError("TTS failed to generate audio from custom script.")

        final_duration = _audio_duration(str(paths["audio"]))
        logger.info("Custom script audio duration: %.2fs", final_duration)

        # Custom scripts use a softer warning band for short-form socials.
        custom_soft_min = max(1, lower_bound - 3)
        if not (custom_soft_min <= final_duration <= upper_bound):
            logger.warning(
                "Custom script duration (%.2fs) is outside preferred range (%d-%ds). "
                "Continuing anyway since this is a custom script.",
                final_duration, custom_soft_min, upper_bound
            )
        else:
            logger.info(
                "Custom script duration %.2fs is within preferred short-form band (%d-%ds).",
                final_duration, custom_soft_min, upper_bound
            )

        duration_accepted = True
        audio_created = True

        # Discover user-provided screenshots for custom scripts with MCP markers
        if script_with_markers and keyword_map:
            id_to_path = _discover_local_screenshots(keyword_map, screenshots_dir, logger)
            if manual_image_map:
                for marker, image_path in manual_image_map.items():
                    if marker not in keyword_map:
                        continue
                    id_to_path[marker] = image_path
                    if marker not in manual_markers_applied:
                        manual_image_applied += 1
                        manual_markers_applied.add(marker)
                    screenshot_source_by_marker[marker] = {
                        "path": image_path,
                        "source": "manual_image_map",
                        "source_url": image_path,
                        "score": None,
                        "keyword": keyword_map.get(marker),
                    }
            if id_to_path:
                logger.info("Discovered %d/%d screenshots", len(id_to_path), len(keyword_map))
            else:
                logger.info("No screenshots found. Place S1.png, S2.png etc. in '%s/' to add visuals.", screenshots_dir)

    # Normal LLM generation with retry loop (skip if custom script provided)
    if not custom_script_path:
        for attempt in range(1, attempts_allowed + 1):
            attempts_used = attempt
            logger.info("Duration attempt %d/%d", attempt, attempts_allowed)
            model_in_use = model_candidates[model_index]
            logger.info("Script model: %s", model_in_use)

            try:
                if mcp_mode:
                    # MCP generator has different signature
                    from reelforge.script.mcp_generator import MCPScriptGenerator
                    if isinstance(generator, MCPScriptGenerator):
                        result = generator.generate(
                            topic=topic,
                            details=enhanced_details,
                            style=style,
                            websites=websites,
                            length=length,
                            profanity=profanity,
                            model=model_in_use,
                        )
                        # Extract script text and markers
                        script_with_markers = result
                        # Strip markers so TTS doesn't speak "[SHOW:S1]"
                        script_text = _strip_markers(result.dialogue_text)
                        keyword_map = result.keyword_map
                        logger.info("MCP generated %d screenshot markers", len(keyword_map))
                    else:
                        script_text = generator.generate(topic, enhanced_details, style, model=model_in_use)
                else:
                    script_text = generator.generate(topic, enhanced_details, style, model=model_in_use)
            except Exception as exc:
                last_failure_reason = f"Script generation failed on model {model_in_use}: {exc}"
                logger.warning("%s", last_failure_reason)
                if model_index < len(model_candidates) - 1:
                    model_index += 1
                    logger.warning(
                        "Switching script model to %s for the next attempt",
                        model_candidates[model_index],
                    )
                if attempt == attempts_allowed and not audio_created:
                    _write_failure_snapshot(
                        run_dir=paths["run_dir"],
                        stage="script_generation",
                        reason=last_failure_reason,
                        extra={"attempt": attempt, "model": model_in_use},
                    )
                    raise RuntimeError(
                        f"Could not generate script after {attempts_allowed} attempts. "
                        f"Last failure: {last_failure_reason}"
                    )
                continue
            script_text = _sanitize_dialogue_if_needed(script_text)
            word_count = len(script_text.split())
            logger.info("Generated script with %d words", word_count)

            if word_count < min_word_target:
                logger.warning("Short script sample: %s", script_text[:220].replace("\n", " "))
                last_failure_reason = (
                    f"Script too short ({word_count} words). "
                    f"Target should be at least {min_word_target} words."
                )
                logger.warning("%s", last_failure_reason)
                try:
                    repaired_script = generator.expand_short_script(
                        topic=topic,
                        short_script=script_text,
                        style=style,
                        min_words=min_word_target,
                        max_words=max_word_target,
                        details=enhanced_details,
                        model=model_in_use,
                    )
                    repaired_script = _sanitize_dialogue_if_needed(repaired_script)
                    repaired_word_count = len(repaired_script.split())
                    logger.info("Expanded script candidate has %d words", repaired_word_count)
                    if repaired_word_count >= min_word_target:
                        script_text = repaired_script
                        word_count = repaired_word_count
                        logger.info("Short script repaired successfully")
                    else:
                        logger.warning(
                            "Expanded script still short (%d words); retrying generation",
                            repaired_word_count,
                        )
                except Exception as exc:
                    logger.warning("Failed to expand short script: %s", exc)

            if word_count < min_word_target:
                enhanced_details = (
                    f"{details} {constraints} "
                    f"Previous attempt was only {word_count} words. "
                    f"Rewrite to be substantially longer and return at least {min_word_target} words."
                ).strip()
                if model_index < len(model_candidates) - 1:
                    model_index += 1
                    logger.warning(
                        "Switching script model to %s for the next attempt",
                        model_candidates[model_index],
                    )
                if attempt < attempts_allowed:
                    continue
                _write_failure_snapshot(
                    run_dir=paths["run_dir"],
                    stage="script_generation",
                    reason=(
                        f"No script met minimum length after {attempts_used} attempts. "
                        f"Last attempt had {word_count} words (required at least {min_word_target})."
                    ),
                    extra={"attempts_used": attempts_used, "word_count": word_count},
                )
                raise RuntimeError(
                    f"No script met minimum length after {attempts_used} attempts. "
                    f"Last attempt had {word_count} words (required at least {min_word_target})."
                )

            with open(paths["script"], "w", encoding="utf-8") as handle:
                handle.write(script_text)

            speaker_timeline = None

            with reporter.stage(f"Generating audio (attempt {attempt}/{attempts_allowed})"):
                if style == "dialogue":
                    parsed_dialogue = generator.parse_dialogue(script_text)
                    if not parsed_dialogue:
                        logger.warning("Could not parse dialogue on attempt %d", attempt)
                        last_failure_reason = "Failed to parse dialogue format from model response."
                        enhanced_details = (
                            f"{details} {constraints} "
                            "Use strict alternating format like 'A: ...' and 'B: ...' for each line."
                        ).strip()
                        if attempt == attempts_allowed and not audio_created:
                            _write_failure_snapshot(
                                run_dir=paths["run_dir"],
                                stage="dialogue_validation",
                                reason="Could not parse dialogue in any generation attempt.",
                                extra={"attempt": attempt},
                            )
                            raise RuntimeError("Could not parse dialogue in any generation attempt.")
                        continue

                    # Check dialogue alternation BEFORE TTS
                    from reelforge.pipeline.quality_gate import _dialogue_is_strictly_alternating
                    if not _dialogue_is_strictly_alternating(script_text):
                        logger.warning("Dialogue script is not strictly alternating on attempt %d", attempt)
                        last_failure_reason = "Dialogue script is not in strict alternating speaker format."
                        enhanced_details = (
                            f"{details} {constraints} "
                            "CRITICAL: Use STRICT alternating format. "
                            "Speaker A must be followed by speaker B, then A, then B, etc. "
                            "Never have two consecutive lines from the same speaker."
                        ).strip()
                        if attempt == attempts_allowed and not audio_created:
                            _write_failure_snapshot(
                                run_dir=paths["run_dir"],
                                stage="dialogue_validation",
                                reason="Could not generate strictly alternating dialogue after all attempts.",
                                extra={"attempt": attempt},
                            )
                            raise RuntimeError("Could not generate strictly alternating dialogue after all attempts.")
                        continue

                    # Check hook quality (first line should be short and punchy)
                    first_line = script_text.split('\n')[0] if '\n' in script_text else script_text
                    # Remove speaker prefix (A:, B:, [A], etc.)
                    first_line_clean = first_line.split(':', 1)[-1].strip() if ':' in first_line else first_line
                    first_line_words = len(first_line_clean.split())
                    if first_line_words > 10:
                        logger.warning("Hook too long (%d words) on attempt %d", first_line_words, attempt)
                        last_failure_reason = f"Hook is too long ({first_line_words} words, max 10)."
                        enhanced_details = (
                            f"{details} {constraints} "
                            "CRITICAL: First line (hook) must be UNDER 10 WORDS. "
                            "Use a short, punchy hook to grab attention in first 3 seconds."
                        ).strip()
                        if attempt < attempts_allowed:
                            continue

                    voice_mapping = None
                    if primary_voice:
                        chars = list(parsed_dialogue.keys())
                        voice_mapping = {chars[0]: primary_voice}

                    dialogue_result = engine.synthesize_dialogue_sync(
                        parsed_dialogue,
                        str(paths["audio"]),
                        voice_mapping=voice_mapping,
                        return_timeline=True,
                    )
                    _, speaker_timeline = dialogue_result
                    audio_created = True
                else:
                    engine.synthesize_sync(
                        script_text,
                        str(paths["audio"]),
                        voice=primary_voice,
                        rate=cfg.get("tts", {}).get("rate", "+15%"),
                    )
                    audio_created = True

            if not Path(paths["audio"]).exists():
                audio_created = False
                last_failure_reason = "TTS did not produce audio file."
                logger.warning("%s", last_failure_reason)
                if attempt == attempts_allowed:
                    _write_failure_snapshot(
                        run_dir=paths["run_dir"],
                        stage="tts_generation",
                        reason=(
                            f"Could not generate audio after {attempts_allowed} attempts. "
                            f"Reason: {last_failure_reason}"
                        ),
                        extra={"attempt": attempt},
                    )
                    raise RuntimeError(
                        f"Could not generate audio after {attempts_allowed} attempts. "
                        f"Reason: {last_failure_reason}"
                    )
                continue

            # Discover user-provided screenshots (only once)
            if script_with_markers and keyword_map and not id_to_path:
                id_to_path = _discover_local_screenshots(keyword_map, screenshots_dir, logger)
                if manual_image_map:
                    for marker, image_path in manual_image_map.items():
                        if marker not in keyword_map:
                            continue
                        id_to_path[marker] = image_path
                        if marker not in manual_markers_applied:
                            manual_image_applied += 1
                            manual_markers_applied.add(marker)
                        screenshot_source_by_marker[marker] = {
                            "path": image_path,
                            "source": "manual_image_map",
                            "source_url": image_path,
                            "score": None,
                            "keyword": keyword_map.get(marker),
                        }
                if id_to_path:
                    logger.info("Discovered %d/%d screenshots", len(id_to_path), len(keyword_map))

            final_duration = _audio_duration(str(paths["audio"]))
            logger.info("Audio duration attempt %d: %.2fs", attempt, final_duration)
            distance = abs(final_duration - target_midpoint)
            if distance < best_distance:
                best_distance = distance
                best_duration = final_duration
                best_script_text = script_text
                best_speaker_timeline = speaker_timeline
                shutil.copy2(paths["audio"], best_audio_path)

            if lower_bound <= final_duration <= upper_bound:
                logger.info("Duration accepted in target window")
                duration_accepted = True
                break
            if _duration_is_soft_acceptable(
                duration_seconds=final_duration,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                attempt=attempt,
            ):
                logger.info(
                    "Duration accepted in soft window after retries: %.2fs (hard target %d-%ds)",
                    final_duration,
                    lower_bound,
                    upper_bound,
                )
                duration_accepted = True
                break

            last_failure_reason = (
                f"Audio duration out of range ({final_duration:.2f}s). "
                f"Target is {lower_bound}-{upper_bound}s."
            )
            logger.warning("%s", last_failure_reason)
            enhanced_details = (
                f"{details} {constraints} "
                f"Previous output duration was {final_duration:.1f}s. "
                f"Adjust pacing and length to land between {lower_bound} and {upper_bound} seconds."
            ).strip()

    if not audio_created:
        _write_failure_snapshot(
            run_dir=paths["run_dir"],
            stage="tts_generation",
            reason=(
                "No audio file was created during generation attempts. "
                f"Last failure: {last_failure_reason}"
            ),
        )
        raise RuntimeError(
            "No audio file was created during generation attempts. "
            f"Last failure: {last_failure_reason}"
        )

    if not duration_accepted:
        if best_audio_path.exists():
            shutil.copy2(best_audio_path, paths["audio"])
            if best_script_text:
                with open(paths["script"], "w", encoding="utf-8") as handle:
                    handle.write(best_script_text)
            final_duration = best_duration
            speaker_timeline = best_speaker_timeline
            logger.warning(
                "Duration target not met after %d attempts; using closest attempt at %.2fs",
                attempts_used,
                best_duration,
            )
        else:
            _write_failure_snapshot(
                run_dir=paths["run_dir"],
                stage="duration_resolution",
                reason=(
                    "Duration target not met and no fallback audio available. "
                    f"Last failure: {last_failure_reason}"
                ),
            )
            raise RuntimeError(
                "Duration target not met and no fallback audio available. "
                f"Last failure: {last_failure_reason}"
            )

    with reporter.stage("Generating captions"):
        word_captions = caption_gen.generate_captions(str(paths["audio"]))
        caption_gen.save_captions_json(word_captions, str(paths["captions"]))
        formatted_captions = caption_gen.format_captions(word_captions)

    # Early quality check BEFORE expensive video composition
    from reelforge.pipeline.quality_gate import (
        _word_count,
        _caption_coverage_ratio,
        _word_count_overrun_tolerance,
    )
    script_word_count = _word_count(script_text)
    caption_word_count = len(word_captions)
    coverage_ratio = _caption_coverage_ratio(script_text, word_captions)
    effective_max_word_target = max_word_target + _word_count_overrun_tolerance(style)

    early_failures: List[str] = []

    # Check script length
    if script_word_count > effective_max_word_target:
        early_failures.append(
            f"Script too long for style '{style}': {script_word_count} words "
            f"(max {effective_max_word_target})."
        )

    # Check caption coverage (critical check)
    if caption_word_count == 0:
        early_failures.append("No caption words were generated.")
    elif coverage_ratio < 0.75:
        early_failures.append(
            f"Caption coverage is too low: {caption_word_count}/{script_word_count} ({coverage_ratio:.2f}). "
            "This indicates a critical WhisperX transcription failure."
        )

    if early_failures:
        logger.error("Pre-render quality check failed: %s", " | ".join(early_failures))
        _write_failure_snapshot(
            run_dir=paths["run_dir"],
            stage="pre_render_quality_gate",
            reason=" | ".join(early_failures),
        )
        raise RuntimeError(
            "Quality gate failed before video composition. "
            f"Failures: {'; '.join(early_failures)}"
        )

    logger.info(
        "Pre-render quality check passed: script_words=%d caption_words=%d coverage=%.2f",
        script_word_count,
        caption_word_count,
        coverage_ratio,
    )

    screenshots_data: List[Dict[str, Any]] = []
    screenshot_plan_path = None
    screenshot_target_count = 0
    screenshot_effective_target_count = 0
    screenshot_extracted_targets_count = 0
    screenshot_captured_count = 0
    screenshot_failures: List[str] = []
    screenshot_capture_breakdown: Dict[str, int] = {}
    screenshot_unresolved_targets: List[str] = []

    # NEW: Marker-based screenshot timing (MCP mode)
    if script_with_markers and id_to_path:
        try:
            from reelforge.media.marker_resolver import MarkerResolver
            resolver = MarkerResolver(cfg)
            screenshots_data = resolver.resolve_markers_to_timestamps(
                script_with_markers=script_with_markers,
                word_captions=word_captions,
                id_to_path=id_to_path
            )
            screenshot_captured_count = len(screenshots_data)
            screenshot_target_count = len(keyword_map)
            screenshot_effective_target_count = screenshot_target_count
            screenshot_extracted_targets_count = screenshot_target_count
            unresolved_marker_ids = [marker for marker in keyword_map if marker not in id_to_path]
            if unresolved_marker_ids:
                screenshot_unresolved_targets = [keyword_map[marker] for marker in unresolved_marker_ids]
                screenshot_failures.append(
                    f"Missing imagery for {len(unresolved_marker_ids)} marker(s): {', '.join(unresolved_marker_ids)}"
                )
            logger.info("Resolved %d screenshot markers to timestamps", len(screenshots_data))
        except Exception as exc:
            logger.warning("Marker resolution failed: %s", exc)
            screenshots_data = []
    elif script_with_markers and keyword_map:
        screenshot_target_count = len(keyword_map)
        screenshot_effective_target_count = screenshot_target_count
        screenshot_extracted_targets_count = screenshot_target_count
        screenshot_unresolved_targets = [keyword_map[marker] for marker in keyword_map]
        screenshot_failures.append("No marker imagery was available for MCP script markers.")


    # Audio mixing: Add background music and sound effects
    if cfg.get("audio", {}).get("background_music", False):
        try:
            from reelforge.audio.mixer import AudioMixer
            mixer = AudioMixer(cfg)

            # Auto-generate SFX cues from screenshot data
            sfx_cues = []
            if screenshots_data and cfg.get("audio", {}).get("auto_sfx", True):
                for shot in screenshots_data:
                    # Add pop sound at screenshot appearance
                    sfx_cues.append({"type": "pop", "time_ms": int(shot["start"] * 1000)})

            # Mix audio with background music and SFX
            mixed_path = paths["run_dir"] / "audio_mixed.mp3"
            if reporter:
                with reporter.stage("Mixing audio"):
                    mixer.mix(str(paths["audio"]), str(mixed_path), sfx_cues=sfx_cues, add_music=True)
            else:
                mixer.mix(str(paths["audio"]), str(mixed_path), sfx_cues=sfx_cues, add_music=True)

            # Replace original audio path with mixed version
            paths["audio"] = mixed_path
            logger.info("Audio mixing complete: background music + %d SFX cues", len(sfx_cues))

        except Exception as e:
            logger.warning("Audio mixing failed, using original audio: %s", e)

    compose_kwargs = {
        "audio_path": str(paths["audio"]),
        "captions_data": formatted_captions,
        "output_path": str(paths["video"]),
        "background_path": background,
        "character_path": character,
        "secondary_character_path": secondary_character,
        "speaker_timeline": speaker_timeline,
        "screenshots_data": screenshots_data,
    }

    try:
        result_video, selected_background, compose_last_progress_percent, compose_elapsed_seconds = _compose_video_with_timeout(
            cfg=cfg,
            compose_kwargs=compose_kwargs,
            progress_enabled=progress_enabled,
        )
    except Exception as exc:
        _write_failure_snapshot(
            run_dir=paths["run_dir"],
            stage="video_composition",
            reason=str(exc),
            extra={
                "compose_progress_percent": compose_last_progress_percent,
                "compose_elapsed_seconds": round(compose_elapsed_seconds, 2),
            },
        )
        raise

    size_mb = os.path.getsize(result_video) / (1024 * 1024)
    selected_background = selected_background or background

    screenshot_enabled_for_quality = bool(screenshot_captured_count > 0)
    quality = _assess_output_quality(
        script_text=script_text,
        style=style,
        duration_seconds=final_duration,
        min_duration=lower_bound,
        max_duration=upper_bound,
        word_captions=word_captions,
        min_word_target=min_word_target,
        max_word_target=max_word_target,
        screenshot_enabled=screenshot_enabled_for_quality,
        screenshot_target_count=screenshot_target_count,
        screenshot_captured_count=screenshot_captured_count,
        screenshot_gold_coverage_min=0.80,
        screenshot_effective_target_count=screenshot_effective_target_count,
        custom_script=is_custom_script,
    )
    logger.info(
        "Quality verdict: %s (caption coverage %.3f, script words %d, caption words %d)",
        quality["quality_verdict"],
        quality["caption_coverage_ratio"],
        quality["script_word_count"],
        quality["caption_word_count"],
    )
    if quality["quality_failures"]:
        logger.warning("Quality failures: %s", " | ".join(quality["quality_failures"]))

    metadata = {
        "topic": topic,
        "style": style,
        "duration_seconds": round(final_duration, 3),
        "duration_target_met": duration_accepted,
        "word_count": quality["script_word_count"],
        "attempts": attempts_used,
        "background": selected_background,
        "selected_background": selected_background,
        "background_requested": background,
        "character": character,
        "secondary_character": secondary_character,
        "auto_screenshots_enabled": False,
        "screenshot_target_count": screenshot_target_count,
        "effective_screenshot_target_count": screenshot_effective_target_count,
        "extracted_targets_count": screenshot_extracted_targets_count,
        "screenshot_captured_count": screenshot_captured_count,
        "screenshot_coverage_ratio": quality["screenshot_coverage_ratio"],
        "screenshot_plan_path": screenshot_plan_path,
        "screenshot_failures": screenshot_failures,
        "screenshot_unresolved_targets": screenshot_unresolved_targets,
        "screenshot_capture_breakdown": screenshot_capture_breakdown,
        "manual_image_overrides_applied": manual_image_applied,
        "screenshot_sources": [
            {
                "file": item.get("file"),
                "source_url": (
                    (screenshot_source_by_marker.get(item.get("marker_id"), {}).get("source_url"))
                    or item.get("source_url")
                ),
                "source_domain": (
                    urlparse(
                        (
                            screenshot_source_by_marker.get(item.get("marker_id"), {}).get("source_url")
                            or item.get("source_url")
                            or ""
                        )
                    ).netloc
                    or item.get("source_domain")
                ),
                "start": item.get("start"),
                "end": item.get("end"),
                "target_label": item.get("target_label"),
                "capture_strategy": (
                    (screenshot_source_by_marker.get(item.get("marker_id"), {}).get("source"))
                    or item.get("capture_strategy")
                ),
            }
            for item in screenshots_data
        ],
        "caption_word_count": quality["caption_word_count"],
        "script_word_count": quality["script_word_count"],
        "caption_coverage_ratio": quality["caption_coverage_ratio"],
        "quality_verdict": quality["quality_verdict"],
        "quality_failures": quality["quality_failures"],
        "script_sanitization_applied": script_sanitization_applied,
        "script_sanitization_changes": script_sanitization_changes,
        "compose_elapsed_seconds": round(compose_elapsed_seconds, 2),
        "compose_last_progress_percent": compose_last_progress_percent,
        "failure_stage": None,
        "failure_reason": None,
        "log_file": str(log_path),
        "drive_upload_enabled": bool(cfg.get("integrations", {}).get("google_drive", {}).get("enabled", False)),
    }
    defaults_builder = drive_defaults_factory or _drive_upload_defaults
    metadata.update(defaults_builder(cfg))

    if quality["quality_verdict"] == "trash":
        with open(paths["metadata"], "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2)
        _write_failure_snapshot(
            run_dir=paths["run_dir"],
            stage="quality_gate",
            reason="; ".join(quality["quality_failures"]),
            extra={"quality_verdict": quality["quality_verdict"]},
        )
        raise RuntimeError(
            "Quality gate failed with verdict=trash. "
            f"Failures: {'; '.join(quality['quality_failures'])}"
        )

    with open(paths["metadata"], "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

    with reporter.stage("Uploading artifacts"):
        drive_metadata = _upload_artifacts_to_drive(
            cfg=cfg,
            logger=logger,
            run_dir=paths["run_dir"],
            video_path=paths["video"],
            metadata_path=paths["metadata"],
            defaults_factory=defaults_builder,
        )
    metadata.update(drive_metadata)

    with open(paths["metadata"], "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

    drive_error = str(metadata.get("drive_upload_error") or "")
    drive_error_short = ""
    if drive_error:
        drive_error_short = drive_error.split("{", 1)[0].strip().strip("()").strip().strip("'\"")

    result = {
        "script_path": str(paths["script"]),
        "audio_path": str(paths["audio"]),
        "captions_path": str(paths["captions"]),
        "video_path": str(paths["video"]),
        "metadata_path": str(paths["metadata"]),
        "log_path": str(log_path),
        "duration": final_duration,
        "audio_duration_seconds": final_duration,
        "size_mb": size_mb,
        "caption_word_count": quality["caption_word_count"],
        "script_word_count": quality["script_word_count"],
        "caption_coverage_ratio": quality["caption_coverage_ratio"],
        "screenshot_target_count": screenshot_target_count,
        "screenshot_captured_count": screenshot_captured_count,
        "screenshot_coverage_ratio": quality["screenshot_coverage_ratio"],
        "screenshot_top_failure": (screenshot_failures[0] if screenshot_failures else None),
        "quality_verdict": quality["quality_verdict"],
        "drive_upload_status": metadata.get("drive_upload_status"),
        "drive_upload_error_short": drive_error_short,
        "summary_mode": str(ui_cfg.get("summary_mode", "compact")),
    }
    _release_generate_lock(lock_path=lock_path)
    return result
