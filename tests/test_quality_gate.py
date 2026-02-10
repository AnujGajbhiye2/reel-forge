from main import (
    _assess_output_quality,
    _caption_coverage_ratio,
    _detect_risky_claims,
    _dialogue_is_strictly_alternating,
)


def test_dialogue_strictly_alternating_true():
    script = """A: First line here\nB: Reply line here\nA: Another line\nB: Final line"""
    assert _dialogue_is_strictly_alternating(script) is True


def test_dialogue_strictly_alternating_false_when_same_speaker_twice():
    script = """A: First line\nA: Second line\nB: Third line"""
    assert _dialogue_is_strictly_alternating(script) is False


def test_caption_coverage_ratio():
    script = "one two three four five"
    captions = [{"word": "one"}, {"word": "two"}, {"word": "three"}, {"word": "four"}]
    ratio = _caption_coverage_ratio(script, captions)
    assert ratio == 0.8


def test_detect_risky_claims_flags_high_certainty_fact_language():
    script = "Fun fact: Bill Gates proved this always works for everyone."
    failures = _detect_risky_claims(script)
    assert len(failures) >= 1


def test_assess_output_quality_gold():
    script = "A: hello world\nB: this is a valid short script\nA: now we keep alternating\nB: and avoid risky claims"
    captions = [{"word": "w"}] * 18
    result = _assess_output_quality(
        script_text=script,
        style="dialogue",
        duration_seconds=50.0,
        min_duration=45,
        max_duration=60,
        word_captions=captions,
        min_word_target=10,
        max_word_target=40,
    )
    assert result["quality_verdict"] == "gold"
    assert result["quality_failures"] == []


def test_assess_output_quality_needs_work_for_sub_gold_caption_coverage():
    script = "A: one two three four five six seven eight nine ten\nB: one two three four five six seven eight nine ten"
    captions = [{"word": "w"}] * 15
    result = _assess_output_quality(
        script_text=script,
        style="dialogue",
        duration_seconds=52.0,
        min_duration=45,
        max_duration=60,
        word_captions=captions,
        min_word_target=10,
        max_word_target=50,
    )
    assert result["quality_verdict"] == "needs_work"


def test_assess_output_quality_trash_for_critical_coverage_failure():
    script = "A: one two three four five six seven eight nine ten\nB: one two three four five six seven eight nine ten"
    captions = [{"word": "w"}] * 6
    result = _assess_output_quality(
        script_text=script,
        style="dialogue",
        duration_seconds=52.0,
        min_duration=45,
        max_duration=60,
        word_captions=captions,
        min_word_target=10,
        max_word_target=50,
    )
    assert result["quality_verdict"] == "trash"


def test_assess_output_quality_needs_work_for_screenshot_shortfall():
    script = "A: one two three four five six seven eight nine ten\nB: one two three four five six seven eight nine ten"
    captions = [{"word": "w"}] * 20
    result = _assess_output_quality(
        script_text=script,
        style="dialogue",
        duration_seconds=52.0,
        min_duration=45,
        max_duration=60,
        word_captions=captions,
        min_word_target=10,
        max_word_target=50,
        screenshot_enabled=True,
        screenshot_target_count=5,
        screenshot_captured_count=3,
        screenshot_gold_coverage_min=0.8,
    )
    assert result["quality_verdict"] == "needs_work"
    assert result["screenshot_coverage_ratio"] == 0.6


def test_assess_output_quality_uses_effective_target_count_denominator():
    script = "A: one two three four five six seven eight nine ten\nB: one two three four five six seven eight nine ten"
    captions = [{"word": "w"}] * 20
    result = _assess_output_quality(
        script_text=script,
        style="dialogue",
        duration_seconds=52.0,
        min_duration=45,
        max_duration=60,
        word_captions=captions,
        min_word_target=10,
        max_word_target=50,
        screenshot_enabled=True,
        screenshot_target_count=5,
        screenshot_effective_target_count=3,
        screenshot_captured_count=2,
        screenshot_gold_coverage_min=0.8,
    )
    assert result["quality_verdict"] == "needs_work"
    assert result["screenshot_coverage_ratio"] == 0.667


def test_assess_output_quality_allows_small_dialogue_word_overrun():
    # 79 words per line => 158 words total (8 over the dialogue target of 150).
    line = " ".join(["word"] * 79)
    script = f"A: {line}\nB: {line}"
    captions = [{"word": "w"}] * 158
    result = _assess_output_quality(
        script_text=script,
        style="dialogue",
        duration_seconds=52.0,
        min_duration=45,
        max_duration=60,
        word_captions=captions,
        min_word_target=120,
        max_word_target=150,
    )
    assert result["quality_verdict"] == "gold"
    assert result["quality_failures"] == []
