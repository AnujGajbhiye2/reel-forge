# AGENTS.md

## Mission
ReelForge produces faceless AI/tech short-form reels from a topic with a semi-automated pipeline:
script -> TTS audio -> word-level captions -> composited vertical video.

## Primary Reference
- `reelforge-blueprint.md` is the source blueprint for architecture, workflow, and quality intent.

## Output Contract
- Format: `1080x1920`, `30fps`, H.264 video with AAC audio.
- Target duration: `45-60s` (default bounds from `config.yaml`).
- Script style:
  - `solo`: one narrator, concise high-retention flow.
  - `dialogue`: strict alternating lines with speaker labels.
- Captions: word-level timing from WhisperX, grouped for readability.

## Quality Bar
- `gold`: all quality gates pass.
- `needs_work`: output is usable but one or more non-critical quality checks fail.
- `trash`: one or more critical quality checks fail; pipeline must fail.

### Critical Failures (trash)
- Duration outside configured target range.
- No caption words generated.
- Caption coverage ratio is too low (`caption_word_count / script_word_count < 0.75`).
- Dialogue output is not strict alternating format when style is `dialogue`.

### Non-Critical Failures (needs_work)
- Caption coverage ratio is below gold threshold (`< 0.90`) but >= 0.75.
- Script word count outside style target range.
- Script includes risky factual-claim language that should be reviewed.

## Metadata Requirements
Each run metadata file must include:
- `selected_background`
- `script_word_count`
- `caption_word_count`
- `caption_coverage_ratio`
- `quality_verdict`
- `quality_failures`
- Existing run context fields (topic, style, duration, attempts, paths/logs)

## Logging Requirements
- Log generation attempts with model, word count, duration, and retry reason.
- Log final quality verdict and quality failures.

## Retry and Fallback Policy
- Use configured script model fallback chain when generation fails or output is too short.
- Retry to meet duration bounds up to configured max retries.
- If duration bounds are not met after retries, use closest-duration attempt only when policy allows; still enforce quality gates.

## Human-in-the-Loop
- This pipeline is semi-automated. Human review in CapCut/DaVinci is expected for final polish.
- Automation should catch obvious regressions before handoff.

## Implementation Notes
- Prefer deterministic validation and explicit failures over silent degradation.
- Preserve run artifacts (`script`, `audio`, `captions`, `metadata`, `log`) for debugging and trend analysis.
