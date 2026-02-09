"""Quality gate and script/caption validation helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List


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
        # Skip REEL TITLE lines (defense in depth - should be filtered earlier)
        if line.startswith('REEL TITLE:'):
            continue
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
    screenshot_enabled: bool = False,
    screenshot_target_count: int = 0,
    screenshot_captured_count: int = 0,
    screenshot_gold_coverage_min: float = 0.80,
    screenshot_effective_target_count: int = 0,
    custom_script: bool = False,
) -> Dict[str, Any]:
    script_word_count = _word_count(script_text)
    caption_word_count = len(word_captions)
    coverage_ratio = _caption_coverage_ratio(script_text, word_captions)
    failures: List[str] = []
    critical_failures: List[str] = []

    # For custom scripts, duration/word count are soft warnings, not critical failures.
    # The user wrote the script themselves and already got a clear warning.
    duration_tolerance = 3 if custom_script else 0
    effective_min = min_duration - duration_tolerance
    effective_max = max_duration + duration_tolerance

    if not (effective_min <= duration_seconds <= effective_max):
        if custom_script:
            failures.append(
                f"Duration outside target range: {duration_seconds:.2f}s (target {min_duration}-{max_duration}s)."
            )
        else:
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

    screenshot_coverage_ratio = 0.0
    denominator = screenshot_effective_target_count if screenshot_effective_target_count > 0 else screenshot_target_count
    if screenshot_enabled and denominator > 0:
        screenshot_coverage_ratio = screenshot_captured_count / float(denominator)
        if screenshot_coverage_ratio < screenshot_gold_coverage_min:
            failures.append(
                "Screenshot coverage is below gold threshold: "
                f"{screenshot_captured_count}/{denominator} ({screenshot_coverage_ratio:.2f})."
            )

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
        "screenshot_coverage_ratio": round(screenshot_coverage_ratio, 3),
    }
