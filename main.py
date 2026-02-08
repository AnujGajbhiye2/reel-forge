#!/usr/bin/env python3
"""
ReelForge CLI - Main entry point for the reel generation pipeline.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from reelforge.cli_interactive import launch_interactive_wizard
from reelforge.logging_utils import setup_logging
from reelforge.utils import create_run_paths, load_config


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


def _word_count(text: str) -> int:
    normalized_lines: List[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        # Exclude dialogue speaker labels (e.g., "A:", "PETER:") from word counts.
        line = re.sub(r"^[A-Za-z][A-Za-z0-9_\- ]*:\s*", "", line)
        if line:
            normalized_lines.append(line)
    return len(re.findall(r"[A-Za-z0-9']+", "\n".join(normalized_lines)))


def _caption_coverage_ratio(script_text: str, word_captions: List[Dict[str, Any]]) -> float:
    script_words = _word_count(script_text)
    if script_words == 0:
        return 0.0
    return len(word_captions) / float(script_words)


def _dialogue_is_strictly_alternating(script_text: str) -> bool:
    lines = [line.strip() for line in (script_text or "").splitlines() if line.strip()]
    speakers: List[str] = []
    for line in lines:
        match = re.match(r"^([A-Za-z][A-Za-z0-9_\- ]*):\s+.+$", line)
        if not match:
            return False
        speakers.append(match.group(1).strip())

    if len(set(speakers)) != 2:
        return False

    return all(speakers[i] != speakers[i - 1] for i in range(1, len(speakers)))


def _detect_risky_claims(script_text: str) -> List[str]:
    text = (script_text or "").lower()
    flags: List[str] = []
    claim_triggers = (
        "fun fact",
        "studies show",
        "research says",
        "proven",
        "guaranteed",
        "everyone knows",
        "always",
        "never",
    )
    if any(trigger in text for trigger in claim_triggers):
        flags.append("Script includes high-certainty claim language that may need fact-checking.")

    named_entities = ("bill gates", "elon musk", "openai", "google", "meta", "microsoft")
    if any(entity in text for entity in named_entities) and re.search(r"\b(hired|founded|invented|proved)\b", text):
        flags.append("Script contains named-person/company factual claims requiring verification.")

    return flags


def _assess_output_quality(
    *,
    script_text: str,
    style: str,
    duration_seconds: float,
    min_duration: int,
    max_duration: int,
    word_captions: List[Dict[str, Any]],
    min_word_target: int,
    max_word_target: int,
) -> Dict[str, Any]:
    script_word_count = _word_count(script_text)
    caption_word_count = len(word_captions)
    coverage_ratio = _caption_coverage_ratio(script_text, word_captions)
    failures: List[str] = []
    critical_failures: List[str] = []

    if not (min_duration <= duration_seconds <= max_duration):
        critical_failures.append(
            f"Duration out of target range: {duration_seconds:.2f}s (target {min_duration}-{max_duration}s)."
        )

    if script_word_count < min_word_target:
        failures.append(f"Script too short for style '{style}': {script_word_count} words.")
    if script_word_count > max_word_target:
        failures.append(f"Script too long for style '{style}': {script_word_count} words.")

    if caption_word_count == 0:
        critical_failures.append("No caption words were generated.")
    elif coverage_ratio < 0.75:
        critical_failures.append(
            f"Caption coverage is too low: {caption_word_count}/{script_word_count} ({coverage_ratio:.2f})."
        )
    elif coverage_ratio < 0.90:
        failures.append(
            f"Caption coverage is below gold threshold: {caption_word_count}/{script_word_count} ({coverage_ratio:.2f})."
        )

    if style == "dialogue" and not _dialogue_is_strictly_alternating(script_text):
        critical_failures.append("Dialogue script is not in strict alternating speaker format.")

    failures.extend(_detect_risky_claims(script_text))

    if critical_failures:
        verdict = "trash"
    elif failures:
        verdict = "needs_work"
    else:
        verdict = "gold"

    return {
        "quality_verdict": verdict,
        "quality_failures": critical_failures + failures,
        "script_word_count": script_word_count,
        "caption_word_count": caption_word_count,
        "caption_coverage_ratio": round(coverage_ratio, 3),
    }


def _drive_upload_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    from reelforge.google_drive_uploader import default_drive_metadata

    parent = cfg.get("integrations", {}).get("google_drive", {}).get("parent_folder_id")
    return default_drive_metadata(parent)


def _upload_artifacts_to_drive(
    *,
    cfg: Dict[str, Any],
    logger,
    run_dir: Path,
    video_path: Path,
    metadata_path: Path,
) -> Dict[str, Any]:
    from reelforge.google_drive_uploader import GoogleDriveUploader

    drive_cfg = cfg.get("integrations", {}).get("google_drive", {})
    defaults = _drive_upload_defaults(cfg)
    if not drive_cfg.get("enabled", False):
        return defaults

    upload_files = drive_cfg.get("upload_files", ["video", "metadata"])
    failure_policy = str(drive_cfg.get("failure_policy", "warn")).strip().lower()
    should_fail_on_error = failure_policy == "fail"

    try:
        uploader = GoogleDriveUploader.from_config(cfg)
        logger.info(
            "Uploading run artifacts to Google Drive parent folder %s",
            uploader.parent_folder_id,
        )
        result = uploader.upload_run_artifacts(
            run_dir=run_dir,
            run_folder_name=run_dir.name,
            video_path=video_path,
            metadata_path=metadata_path,
            upload_files=upload_files,
        )
        logger.info(
            "Drive upload success. Folder=%s VideoID=%s MetadataID=%s",
            result.run_folder_path,
            result.video_file_id,
            result.metadata_file_id,
        )
        return GoogleDriveUploader.to_metadata_dict(result)
    except Exception as exc:
        defaults["drive_upload_status"] = "failed"
        defaults["drive_upload_error"] = str(exc)
        logger.warning("Google Drive upload failed: %s", exc)
        if should_fail_on_error:
            raise RuntimeError(f"Google Drive upload failed: {exc}") from exc
        return defaults


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
) -> Dict[str, Any]:
    from reelforge.caption_generator import CaptionGenerator
    from reelforge.script_generator import ScriptGenerator
    from reelforge.tts_engine import TTSEngine
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

    generator = ScriptGenerator(cfg)
    engine = TTSEngine(cfg)
    caption_gen = CaptionGenerator(cfg)
    compositor = VideoCompositor(cfg)

    script_text = ""
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

    for attempt in range(1, attempts_allowed + 1):
        attempts_used = attempt
        logger.info("Duration attempt %d/%d", attempt, attempts_allowed)
        model_in_use = model_candidates[model_index]
        logger.info("Script model: %s", model_in_use)

        try:
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

    result_video = compositor.compose_video(
        audio_path=str(paths["audio"]),
        captions_data=formatted_captions,
        output_path=str(paths["video"]),
        background_path=background,
        character_path=character,
        secondary_character_path=secondary_character,
        speaker_timeline=speaker_timeline,
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
        "caption_word_count": quality["caption_word_count"],
        "script_word_count": quality["script_word_count"],
        "caption_coverage_ratio": quality["caption_coverage_ratio"],
        "quality_verdict": quality["quality_verdict"],
        "quality_failures": quality["quality_failures"],
        "log_file": str(log_path),
        "drive_upload_enabled": bool(cfg.get("integrations", {}).get("google_drive", {}).get("enabled", False)),
    }
    metadata.update(_drive_upload_defaults(cfg))

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


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx: click.Context):
    """
    ReelForge - Semi-automated faceless AI/tech social media reel generator.
    """
    if ctx.invoked_subcommand is not None:
        return

    try:
        cfg = load_config("config.yaml")
        wizard = launch_interactive_wizard(cfg)
    except Exception as exc:
        click.echo(f"Interactive mode unavailable: {exc}", err=True)
        click.echo("Run 'python main.py --help' for CLI commands.")
        return

    if not wizard:
        return

    action = wizard.get("action")
    if action == "list_voices":
        ctx.invoke(list_voices, language="en", gender="all")
        return
    if action == "validate":
        ctx.invoke(validate, config="config.yaml")
        return

    ctx.invoke(
        generate,
        topic=wizard["topic"],
        details=wizard["details"],
        style=wizard["style"],
        background=wizard.get("background"),
        character=wizard.get("character"),
        secondary_character=wizard.get("secondary_character"),
        output=None,
        config="config.yaml",
        mode=wizard.get("mode"),
        min_duration=None,
        max_duration=None,
        max_retries=None,
        run_name=wizard.get("run_name"),
        voice=wizard.get("voice"),
    )


@cli.command()
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
def generate(
    topic: str,
    details: str,
    style: str,
    background: Optional[str],
    character: Optional[str],
    secondary_character: Optional[str],
    output: Optional[str],
    config: str,
    mode: Optional[str],
    min_duration: Optional[int],
    max_duration: Optional[int],
    max_retries: Optional[int],
    run_name: Optional[str],
    voice: Optional[str],
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


@cli.command()
@click.option('--topic', '-t', required=True, help='Topic for the script')
@click.option('--details', '-d', default='', help='Additional topic details')
@click.option('--style', '-s', type=click.Choice(['solo', 'dialogue']), default='solo', help='Script style')
@click.option('--output', '-o', default='script.txt', help='Output file path')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def script(topic: str, details: str, style: str, output: str, config: str):
    """Generate only the script."""
    try:
        from reelforge.script_generator import ScriptGenerator

        cfg = load_config(config)
        generator = ScriptGenerator(cfg)

        script_text = generator.generate(topic, details, style)

        with open(output, 'w', encoding='utf-8') as f:
            f.write(script_text)

        click.echo(f"Script generated and saved to: {output}")

        is_valid, validation_msg = generator.validate_script_length(script_text, style)
        word_count = len(script_text.split())
        estimated_duration = word_count / 2.5
        click.echo(f"Words: {word_count}")
        click.echo(f"Estimated duration: {estimated_duration:.1f} seconds")
        click.echo(validation_msg)

        if not is_valid:
            click.echo("Warning: script likely exceeds target reel duration")

    except ValueError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise click.Abort()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--text', '-t', help='Text to convert to speech')
@click.option('--script', '-s', help='Script file to convert to speech')
@click.option('--output', '-o', default='output/audio.mp3', help='Output audio file path')
@click.option('--voice', '-v', help='Voice ID (optional, uses config default)')
@click.option('--rate', '-r', help='Speech rate (e.g., "+10%", "-5%")')
@click.option('--dialogue', '-d', is_flag=True, help='Script is dialogue format')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def tts(text: Optional[str], script: Optional[str], output: str, voice: Optional[str], rate: Optional[str], dialogue: bool, config: str):
    """Convert text to speech using EdgeTTS."""
    try:
        from reelforge.tts_engine import TTSEngine

        if not text and not script:
            click.echo("Error: Must provide either --text or --script", err=True)
            raise click.Abort()

        cfg = load_config(config)
        engine = TTSEngine(cfg)

        if script:
            if not os.path.exists(script):
                click.echo(f"Error: Script file not found: {script}", err=True)
                raise click.Abort()
            with open(script, 'r', encoding='utf-8') as f:
                text = f.read()

        if dialogue:
            from reelforge.script_generator import ScriptGenerator

            generator = ScriptGenerator.__new__(ScriptGenerator)
            parsed_dialogue = generator.parse_dialogue(text or "")
            if not parsed_dialogue:
                click.echo("Error: Failed to parse dialogue format", err=True)
                raise click.Abort()
            engine.synthesize_dialogue_sync(parsed_dialogue, output)
        else:
            engine.synthesize_sync(text or "", output, voice=voice, rate=rate)

        duration = _audio_duration(output)
        click.echo(f"Audio generated: {output}")
        click.echo(f"Duration: {duration:.1f} seconds")

    except ValueError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise click.Abort()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--audio', '-a', required=True, help='Audio file path')
@click.option('--output', '-o', default=None, help='Output file (JSON or SRT)')
@click.option('--format', '-f', type=click.Choice(['json', 'srt', 'both']), default='both', help='Output format')
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def captions(audio: str, output: Optional[str], format: str, config: str):
    """Generate word-level captions from audio using WhisperX."""
    try:
        from reelforge.caption_generator import CaptionGenerator

        if not os.path.exists(audio):
            click.echo(f"Error: Audio file not found: {audio}", err=True)
            raise click.Abort()

        if output is None:
            base = os.path.splitext(audio)[0]
            output_json = f"{base}_captions.json"
            output_srt = f"{base}_captions.srt"
        else:
            base = os.path.splitext(output)[0]
            output_json = f"{base}.json"
            output_srt = f"{base}.srt"

        cfg = load_config(config)
        generator = CaptionGenerator(cfg)

        word_captions = generator.generate_captions(audio)
        formatted_captions = generator.format_captions(word_captions)

        if format in ['json', 'both']:
            generator.save_captions_json(word_captions, output_json)
            click.echo(f"JSON saved: {output_json}")

        if format in ['srt', 'both']:
            generator.create_srt_subtitles(formatted_captions, output_srt)
            click.echo(f"SRT saved: {output_srt}")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--audio', '-a', required=True, help='Audio file path')
@click.option('--captions', '-c', required=True, help='Captions JSON file path')
@click.option('--background', '-b', help='Background video (random if not specified)')
@click.option('--character', '-ch', help='Primary character image path (optional)')
@click.option('--secondary-character', '-ch2', default=None, help='Secondary character image for dialogue mode')
@click.option('--output', '-o', default='output/video.mp4', help='Output video path')
@click.option('--config', '-cfg', default='config.yaml', help='Path to config file')
def compose(audio: str, captions: str, background: Optional[str], character: Optional[str], secondary_character: Optional[str], output: str, config: str):
    """Compose final video from audio + captions + background."""
    try:
        from reelforge.caption_generator import CaptionGenerator
        from reelforge.video_compositor import VideoCompositor

        if not os.path.exists(audio):
            click.echo(f"Error: Audio file not found: {audio}", err=True)
            raise click.Abort()

        if not os.path.exists(captions):
            click.echo(f"Error: Captions file not found: {captions}", err=True)
            raise click.Abort()

        cfg = load_config(config)

        caption_gen = CaptionGenerator(cfg)
        word_captions = caption_gen.load_captions_json(captions)
        formatted_captions = caption_gen.format_captions(word_captions)

        compositor = VideoCompositor(cfg)
        result = compositor.compose_video(
            audio_path=audio,
            captions_data=formatted_captions,
            output_path=output,
            background_path=background,
            character_path=character,
            secondary_character_path=secondary_character,
            speaker_timeline=None,
        )

        click.echo(f"Video created: {result}")
        size_mb = os.path.getsize(result) / (1024 * 1024)
        click.echo(f"Size: {size_mb:.1f} MB")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()


@cli.command()
@click.argument('topic')
@click.option('--style', '-s', type=click.Choice(['solo', 'dialogue']), default='dialogue', help='Script style')
@click.option('--output', '-o', default=None, help='Output base name')
def quick(topic: str, style: str, output: Optional[str]):
    """Quickly generate script + audio only."""
    try:
        from reelforge.script_generator import ScriptGenerator
        from reelforge.tts_engine import TTSEngine

        if output is None:
            run = create_run_paths("output")
            script_path = str(run.script_path)
            audio_path = str(run.audio_path)
        else:
            script_path = f"{output}_script.txt"
            audio_path = f"{output}_audio.mp3"

        cfg = load_config()

        generator = ScriptGenerator(cfg)
        word_limit = "130 words" if style == "dialogue" else "140 words"
        script_text = generator.generate(topic, f"Keep punchy, max {word_limit} for 60s reel", style)

        os.makedirs(os.path.dirname(script_path) or '.', exist_ok=True)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_text)

        engine = TTSEngine(cfg)
        if style == "dialogue":
            parsed_dialogue = generator.parse_dialogue(script_text)
            engine.synthesize_dialogue_sync(parsed_dialogue, audio_path)
        else:
            engine.synthesize_sync(script_text, audio_path, rate="+20%")

        duration = _audio_duration(audio_path)

        click.echo(f"Done! {duration:.1f}s audio")
        click.echo(f"Script: {script_path}")
        click.echo(f"Audio: {audio_path}")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()


@cli.command(name="list-voices")
@click.option('--language', '-l', default='en', help='Filter by language code (e.g., "en", "es", "fr")')
@click.option('--gender', '-g', type=click.Choice(['Male', 'Female', 'all']), default='all', help='Filter by gender')
def list_voices(language: str, gender: str):
    """List available EdgeTTS voices."""
    try:
        from collections import defaultdict

        from reelforge.tts_engine import TTSEngine

        voices = TTSEngine.list_voices_sync()

        if language:
            voices = [v for v in voices if v['Locale'].startswith(language)]

        if gender != 'all':
            voices = [v for v in voices if v['Gender'] == gender]

        if not voices:
            click.echo(f"No voices found matching criteria (language={language}, gender={gender})")
            return

        click.echo(f"Found {len(voices)} voices:\n")

        by_locale = defaultdict(list)
        for voice in voices:
            by_locale[voice['Locale']].append(voice)

        for locale in sorted(by_locale.keys()):
            click.echo(f"{locale}")
            for voice in by_locale[locale]:
                click.echo(f"  {voice['ShortName']:35s} ({voice['Gender']})")
            click.echo()

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def drive_auth(config: str):
    """Run one-time Google Drive OAuth flow and store token JSON."""
    try:
        from reelforge.google_drive_uploader import GoogleDriveUploader

        cfg = load_config(config)
        uploader = GoogleDriveUploader.from_config(cfg)
        token_path = uploader.authenticate_interactive()
        click.echo(f"Google Drive auth complete. Token saved to: {token_path}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Path to config file')
def validate(config: str):
    """Validate configuration and check assets."""
    try:
        cfg = load_config(config)
        click.echo(f"Configuration loaded from: {config}")

        if cfg.get('gemini_api_key') == 'YOUR_GEMINI_API_KEY_HERE':
            click.echo("Warning: Gemini API key not configured")
        else:
            click.echo("Gemini API key configured")

        backgrounds = cfg['assets']['backgrounds']
        click.echo(f"\nBackground videos: {len(backgrounds)}")
        for bg in backgrounds:
            state = "OK" if Path(bg).exists() else "MISSING"
            click.echo(f"  {state:7s} {bg}")

        characters = cfg['assets']['characters']
        click.echo(f"\nCharacter images: {len(characters)}")
        for char in characters:
            state = "OK" if Path(char).exists() else "MISSING"
            click.echo(f"  {state:7s} {char}")

        font = cfg['assets']['fonts']['main']
        if Path(font).exists():
            click.echo(f"\nFont: {font}")
        else:
            click.echo(f"\nFont missing: {font}")

    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)


if __name__ == '__main__':
    cli()
