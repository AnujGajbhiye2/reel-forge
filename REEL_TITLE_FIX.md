# REEL TITLE Support Fix (2026-02-09)

## Problem
Users wanted to paste their entire script in one go, including:
- `REEL TITLE: Your Title Here`
- Dialogue lines (A: and B:)
- Media-harvest keywords (S1=subject, S2=subject)

But the validation was failing with:
```
Custom dialogue script is not in strict alternating speaker format
```

## Root Cause
1. `parse_mcp_output()` was not filtering out "REEL TITLE:" lines
2. `_dialogue_is_strictly_alternating()` treated "REEL TITLE" as a speaker name
3. This caused validation to fail because there were 3 speakers instead of 2

## Solution
Made 3 changes:

### 1. Parser Fix (`reelforge/script/types.py`)
```python
# Clean up dialogue (remove empty lines and REEL TITLE lines)
dialogue_lines = [
    line for line in dialogue_lines
    if line.strip() and not line.strip().startswith('REEL TITLE:')
]
```

### 2. Validation Fix (`reelforge/pipeline/quality_gate.py`)
```python
# Skip REEL TITLE lines (defense in depth)
if line.startswith('REEL TITLE:'):
    continue
```

### 3. UI Update (`reelforge/cli/interactive/wizard.py`)
Updated instructions to show that REEL TITLE is supported:
```
Paste everything including REEL TITLE (optional) and keywords:

  REEL TITLE: Your Title Here
  A: First line here
  ...
```

## User Experience Now

Users can paste their script in this format:
```
REEL TITLE: Books That Refactor Your Brain
A: Stop scrolling. Your code is bad. Mine too. These books fix that.
B: That sounded personal.
A: It is. Top 5 software engineering books, speedrun edition.
...

S1=Let Us C book,S2=Clean Code book,S3=Software Design Principles book,...
```

The system automatically:
1. ✅ Filters out "REEL TITLE:" line
2. ✅ Parses dialogue (A: and B: lines)
3. ✅ Extracts keywords (S1=, S2=, ...)
4. ✅ Validates strict alternation
5. ✅ Proceeds with generation

## Testing
Added 4 new tests in `tests/test_mcp_integration.py`:
- `test_reel_title_filtered_from_dialogue`
- `test_reel_title_with_markers`
- `test_alternating_validation_with_reel_title`
- `test_no_reel_title_still_works`

All tests pass: **29/29** ✅

## Files Modified
- `reelforge/script/types.py` - Parser filtering
- `reelforge/pipeline/quality_gate.py` - Validation skip
- `reelforge/cli/interactive/wizard.py` - UI instructions + auto-extract topic from REEL TITLE
- `tests/test_mcp_integration.py` - New test cases
- `CUSTOM_SCRIPT_FEATURE.md` - Documentation update

## Update (Topic Auto-Extraction)
The wizard now automatically extracts the topic from "REEL TITLE:" line:
- If REEL TITLE is present → uses it as topic (no prompt)
- If REEL TITLE is missing → prompts user for topic

This means users paste **ONE input only** and don't have to type the topic twice!

## Backward Compatibility
✅ Scripts without REEL TITLE still work
✅ All existing tests pass
✅ No breaking changes
