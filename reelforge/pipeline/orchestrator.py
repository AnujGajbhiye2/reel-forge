"""End-to-end generate pipeline orchestration."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from reelforge.core.logging import setup_logging
from reelforge.shared.config import load_config

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
    auto_screenshots: Optional[bool],
    screenshot_count: Optional[int],
    seed_urls: Optional[List[str]],
    websites: Optional[str] = None,
    length: str = "45s",
    profanity: str = "none",
    disable_mcp: bool = False,
    custom_script_path: Optional[str] = None,
    drive_defaults_factory=None,
) -> Dict[str, Any]:
    from reelforge.captions.whisperx_generator import CaptionGenerator
    from reelforge.script.generator import ScriptGenerator
    from reelforge.audio.tts_engine import TTSEngine
    from reelforge.video_compositor import VideoCompositor

    cfg = load_config(config_path)
    selected_mode = _resolve_mode(cfg, mode)
    logger, log_path = setup_logging(selected_mode, cfg.get("logging", {}).get("dir", "logs"))

    lower_bound, upper_bound, attempts_allowed = _resolve_duration_bounds(
        cfg, min_duration, max_duration, max_retries
    )

    paths = _build_output_paths(cfg, output, run_name)

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

    engine = TTSEngine(cfg)
    caption_gen = CaptionGenerator(cfg)
    compositor = VideoCompositor(cfg)
    research_cfg = cfg.get("research", {})
    research_enabled = bool(research_cfg.get("enabled", False))
    if auto_screenshots is not None:
        research_enabled = bool(auto_screenshots)

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
    min_word_target = 110 if style == "solo" else 100
    max_word_target = 140 if style == "solo" else 130
    model_candidates = list(getattr(generator, "models", [generator.model]))
    model_index = 0

    constraints = (
        f"Keep pace punchy and complete. Target spoken duration between {lower_bound} and {upper_bound} seconds. "
        f"Do not underwrite. End cleanly with a strong closing line."
    )
    enhanced_details = f"{details} {constraints}".strip()

    # Handle custom script (skip LLM generation)
    if custom_script_path:
        logger.info("Using custom script from: %s", custom_script_path)
        with open(custom_script_path, 'r', encoding='utf-8') as f:
            script_text = f.read()

        # Parse MCP format if markers are present
        if mcp_mode and '[SHOW:' in script_text:
            from reelforge.script.types import parse_mcp_output
            script_with_markers = parse_mcp_output(script_text)
            script_text = script_with_markers.dialogue_text
            keyword_map = script_with_markers.keyword_map
            logger.info("Custom script has %d MCP markers", len(keyword_map))

        word_count = len(script_text.split())
        logger.info("Custom script loaded with %d words", word_count)

        # Validate script format for dialogue mode
        if style == "dialogue":
            parsed_dialogue = generator.parse_dialogue(script_text)
            if not parsed_dialogue:
                raise RuntimeError(
                    "Custom script is not in valid dialogue format. "
                    "Expected format: 'A: text' and 'B: text' on separate lines."
                )

            # Check dialogue alternation
            from reelforge.pipeline.quality_gate import _dialogue_is_strictly_alternating
            if not _dialogue_is_strictly_alternating(script_text):
                raise RuntimeError(
                    "Custom dialogue script is not in strict alternating speaker format. "
                    "Speaker A must be followed by speaker B, then A, then B, etc."
                )

        # Save script
        with open(paths["script"], "w", encoding="utf-8") as handle:
            handle.write(script_text)

        # Generate TTS (skip retry loop)
        attempts_used = 1

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
            raise RuntimeError("TTS failed to generate audio from custom script.")

        final_duration = _audio_duration(str(paths["audio"]))
        logger.info("Custom script audio duration: %.2fs", final_duration)

        # Check if duration is in acceptable range
        if not (lower_bound <= final_duration <= upper_bound):
            logger.warning(
                "Custom script duration (%.2fs) is outside target range (%d-%ds). "
                "Consider adjusting your script length.",
                final_duration, lower_bound, upper_bound
            )

        duration_accepted = True
        audio_created = True

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
                        script_text = result.dialogue_text
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
                    raise RuntimeError(
                        f"Could not generate script after {attempts_allowed} attempts. "
                        f"Last failure: {last_failure_reason}"
                    )
                continue
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
                raise RuntimeError(
                    f"No script met minimum length after {attempts_used} attempts. "
                    f"Last attempt had {word_count} words (required at least {min_word_target})."
                )

            with open(paths["script"], "w", encoding="utf-8") as handle:
                handle.write(script_text)

            speaker_timeline = None

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
                        raise RuntimeError("Could not generate strictly alternating dialogue after all attempts.")
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
                    raise RuntimeError(
                        f"Could not generate audio after {attempts_allowed} attempts. "
                        f"Reason: {last_failure_reason}"
                    )
                continue

            # Media-harvest integration (after TTS, before duration check)
            # Only fetch once (keywords should be same across attempts)
            if script_with_markers and keyword_map and not id_to_path:
                media_harvest_enabled = cfg.get("media_harvest", {}).get("enabled", True)
                if media_harvest_enabled:
                    try:
                        from reelforge.media.harvest_client import MediaHarvestClient
                        harvest_client = MediaHarvestClient(cfg)
                        id_to_path = harvest_client.fetch_screenshots(
                            keyword_map=keyword_map,
                            output_dir=paths["run_dir"]
                        )
                        logger.info("Media harvest fetched %d/%d screenshots",
                                   len(id_to_path), len(keyword_map))
                    except ImportError as exc:
                        logger.warning("Media harvest not available: %s", exc)
                    except Exception as exc:
                        logger.warning("Media harvest failed: %s. Using partial results.", exc)
                        # Continue with whatever was fetched (partial results)

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
            raise RuntimeError(
                "Duration target not met and no fallback audio available. "
                f"Last failure: {last_failure_reason}"
            )

    word_captions = caption_gen.generate_captions(str(paths["audio"]))
    caption_gen.save_captions_json(word_captions, str(paths["captions"]))
    formatted_captions = caption_gen.format_captions(word_captions)

    # Early quality check BEFORE expensive video composition
    from reelforge.pipeline.quality_gate import _word_count, _caption_coverage_ratio
    script_word_count = _word_count(script_text)
    caption_word_count = len(word_captions)
    coverage_ratio = _caption_coverage_ratio(script_text, word_captions)

    early_failures: List[str] = []

    # Check script length
    if script_word_count > max_word_target:
        early_failures.append(
            f"Script too long for style '{style}': {script_word_count} words (max {max_word_target})."
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
            logger.info("Resolved %d screenshot markers to timestamps", len(screenshots_data))
        except Exception as exc:
            logger.warning("Marker resolution failed: %s", exc)
            screenshots_data = []

    # LEGACY: Fallback to heuristic research (when MCP disabled or no markers)
    elif research_enabled:
        from reelforge.research.screenshot_researcher import ScreenshotResearcher

        researcher = ScreenshotResearcher(cfg)
        logger.info(
            "Starting screenshot research for topic='%s' style='%s' count_override=%s",
            topic,
            style,
            screenshot_count,
        )
        research_result = researcher.run(
            topic=topic,
            script_text=script_text,
            style=style,
            word_captions=word_captions,
            run_dir=paths["run_dir"],
            screenshot_count_override=screenshot_count,
            seed_urls=seed_urls,
        )
        screenshot_plan_path = research_result.get("plan_path")
        screenshot_target_count = int(research_result.get("requested_count", 0))
        screenshot_effective_target_count = int(research_result.get("effective_target_count", 0))
        screenshot_extracted_targets_count = int(research_result.get("extracted_targets_count", 0))
        screenshot_captured_count = int(research_result.get("captured_count", 0))
        screenshot_failures = list(research_result.get("failures", []))
        screenshot_capture_breakdown = dict(research_result.get("capture_breakdown", {}))
        screenshot_unresolved_targets = list(research_result.get("unresolved_targets", []))
        screenshots_data = [
            item for item in research_result.get("screenshots", []) if item.get("status") == "ok"
        ]
        logger.info(
            "Screenshot research finished: requested=%d effective=%d extracted=%d captured=%d coverage=%.3f",
            screenshot_target_count,
            screenshot_effective_target_count,
            screenshot_extracted_targets_count,
            screenshot_captured_count,
            (screenshot_captured_count / float(screenshot_effective_target_count)) if screenshot_effective_target_count else 0.0,
        )
        if screenshot_failures:
            logger.warning("Screenshot failures: %s", " | ".join(screenshot_failures))

    result_video = compositor.compose_video(
        audio_path=str(paths["audio"]),
        captions_data=formatted_captions,
        output_path=str(paths["video"]),
        background_path=background,
        character_path=character,
        secondary_character_path=secondary_character,
        speaker_timeline=speaker_timeline,
        screenshots_data=screenshots_data,
    )

    size_mb = os.path.getsize(result_video) / (1024 * 1024)
    selected_background = getattr(compositor, "last_background_path", None) or background

    quality = _assess_output_quality(
        script_text=script_text,
        style=style,
        duration_seconds=final_duration,
        min_duration=lower_bound,
        max_duration=upper_bound,
        word_captions=word_captions,
        min_word_target=min_word_target,
        max_word_target=max_word_target,
        screenshot_enabled=research_enabled,
        screenshot_target_count=screenshot_target_count,
        screenshot_captured_count=screenshot_captured_count,
        screenshot_gold_coverage_min=float(research_cfg.get("quality", {}).get("gold_coverage_min", 0.80)),
        screenshot_effective_target_count=screenshot_effective_target_count,
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
        "word_count": quality["script_word_count"],
        "attempts": attempts_used,
        "background": selected_background,
        "selected_background": selected_background,
        "background_requested": background,
        "character": character,
        "secondary_character": secondary_character,
        "auto_screenshots_enabled": research_enabled,
        "screenshot_target_count": screenshot_target_count,
        "effective_screenshot_target_count": screenshot_effective_target_count,
        "extracted_targets_count": screenshot_extracted_targets_count,
        "screenshot_captured_count": screenshot_captured_count,
        "screenshot_coverage_ratio": quality["screenshot_coverage_ratio"],
        "screenshot_plan_path": screenshot_plan_path,
        "screenshot_failures": screenshot_failures,
        "screenshot_unresolved_targets": screenshot_unresolved_targets,
        "screenshot_capture_breakdown": screenshot_capture_breakdown,
        "screenshot_sources": [
            {
                "file": item.get("file"),
                "source_url": item.get("source_url"),
                "source_domain": item.get("source_domain"),
                "start": item.get("start"),
                "end": item.get("end"),
                "target_label": item.get("target_label"),
                "capture_strategy": item.get("capture_strategy"),
            }
            for item in screenshots_data
        ],
        "caption_word_count": quality["caption_word_count"],
        "script_word_count": quality["script_word_count"],
        "caption_coverage_ratio": quality["caption_coverage_ratio"],
        "quality_verdict": quality["quality_verdict"],
        "quality_failures": quality["quality_failures"],
        "log_file": str(log_path),
        "drive_upload_enabled": bool(cfg.get("integrations", {}).get("google_drive", {}).get("enabled", False)),
    }
    defaults_builder = drive_defaults_factory or _drive_upload_defaults
    metadata.update(defaults_builder(cfg))

    if quality["quality_verdict"] == "trash":
        with open(paths["metadata"], "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2)
        raise RuntimeError(
            "Quality gate failed with verdict=trash. "
            f"Failures: {'; '.join(quality['quality_failures'])}"
        )

    with open(paths["metadata"], "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

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

    return {
        "script_path": str(paths["script"]),
        "audio_path": str(paths["audio"]),
        "captions_path": str(paths["captions"]),
        "video_path": str(paths["video"]),
        "metadata_path": str(paths["metadata"]),
        "log_path": str(log_path),
        "duration": final_duration,
        "size_mb": size_mb,
        "quality_verdict": quality["quality_verdict"],
        "drive_upload_status": metadata.get("drive_upload_status"),
    }
