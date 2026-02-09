# Custom Script Feature - Bypass Unreliable LLM Generation

## Problem Solved

Gemini LLM generation has been unreliable:
- ❌ 2.5-pro often returns empty responses
- ❌ Falls back to 2.5-flash, then 2.0-flash
- ❌ Inconsistent script quality
- ❌ Wasted API quota and time

**Solution:** You can now provide your own script and keywords, completely bypassing LLM generation.

## How It Works

### Option 1: Interactive Wizard (Easiest)

```bash
python main.py
```

1. Select "Generate a new reel"
2. Choose "dialogue" style
3. Answer **"Yes"** to *"Do you want to provide your own script?"*
4. Paste your **entire script** including REEL TITLE (optional) and keywords
5. Press **Ctrl+D** (Linux/Mac) or **Ctrl+Z** (Windows) when done
6. Continue with the wizard as normal

**✨ New:** You can now paste everything in one go - the REEL TITLE line is automatically filtered out!

The wizard will show:
```
Script Source: Custom (user-provided)  [in yellow]
```

### Option 2: CLI with File

```bash
python main.py generate \
  -t "Your Topic" \
  --custom-script path/to/your_script.txt \
  -s dialogue
```

## Script Format

### For Dialogue Mode with MCP Markers (Recommended)

```
REEL TITLE: Your Catchy Title

A: First line from speaker A
B: Response from speaker B with marker [SHOW:S1]
A: Next line from A
B: Another line with second marker [SHOW:S2]
A: Continuing the dialogue
B: Final punchline [SHOW:S3]

S1=keyword1, S2=keyword2, S3=keyword3
```

### Rules:

1. **Strict Alternation:** A → B → A → B (never A → A or B → B)
2. **MCP Markers:** Use `[SHOW:S1]`, `[SHOW:S2]`, etc. inline
3. **Keyword Line:** Last line must be `S1=subject, S2=subject, ...`
4. **Marker IDs:** Must match between dialogue and keyword line
5. **Word Count:** Aim for 100-160 words for 45-60 second videos

### Example (Complete)

See `example_custom_script.txt`:

```
REEL TITLE: Top 5 Software Engineering Books

A: Yo, what are the must-read books for devs?
B: Alright, listen up! [SHOW:S1] Let Us C is where legends are born.
A: C language? That's ancient!
B: Ancient but gold. Then there's Clean Code [SHOW:S2] for writing maintainable stuff.
A: What about design patterns?
B: Design Principles [SHOW:S3] covers that perfectly. OOP done right.
A: Any JavaScript books?
B: JavaScript for Dummies [SHOW:S4] is actually fire for beginners.
A: What's number five?
B: Code Complete [SHOW:S5]! The bible of software construction.
A: Damn, that's a solid list!
B: Go read them and level up your code game!

S1=Let Us C, S2=Clean Code, S3=Design Principles, S4=JavaScript for Dummies, S5=Code Complete
```

## What Happens

1. ✅ Your script is validated (format, alternation, markers)
2. ✅ Script is saved to output folder
3. ✅ TTS generates audio from dialogue
4. ✅ Media-harvest fetches screenshots for S1, S2, S3, etc.
5. ✅ Markers are resolved to timestamps in audio
6. ✅ Video is composed with screenshots appearing at marker positions
7. ✅ Quality gate validates the result

**Pipeline skips entirely:** The unreliable LLM retry loop with 5 attempts and fallback models.

## Benefits

| LLM Generation | Custom Script |
|---------------|---------------|
| ❌ API failures | ✅ Immediate |
| ❌ Rate limiting | ✅ No API needed |
| ❌ Inconsistent quality | ✅ Full control |
| ❌ 5 retry attempts | ✅ One-shot |
| ❌ Wasted time/quota | ✅ Reliable |

## Tips for Writing Good Scripts

1. **Hook in first 2 seconds:** A's first line should grab attention
2. **Natural conversation:** Read it out loud to test flow
3. **Marker placement:** Put markers AFTER mentioning the subject
   - ✅ "Clean Code [SHOW:S2] is essential"
   - ❌ "[SHOW:S2] Clean Code is essential"
4. **Pacing:** Keep lines punchy (5-15 words per line)
5. **Comedy:** Build to a punchline or satisfying conclusion
6. **Technical accuracy:** You control claims, no LLM hallucinations

## Validation

When you provide a custom script, ReelForge validates:

- ✅ Dialogue alternation (strict A → B → A → B)
- ✅ Script format (A: and B: labels)
- ✅ Marker format ([SHOW:S#])
- ✅ Keyword line format (S1=subject, S2=subject)

**If validation fails, you'll get a clear error message immediately** - no wasted rendering time!

## Duration Warning

If your custom script produces audio outside the 45-60s target range, you'll see:

```
⚠️  Custom script duration (72.5s) is outside target range (45-60s).
    Consider adjusting your script length.
```

The video will still be generated, but you should edit your script for better results.

## Media-Harvest Integration

Your keyword line (e.g., `S1=Clean Code, S2=Cursor`) is passed directly to media-harvest:

1. Media-harvest searches for each keyword
2. Downloads relevant screenshots/images
3. Screenshots appear at marker positions in the video

**Note:** Make sure media-harvest is installed:
```bash
cd /home/anuj/projects/screen-scraper && pip install -e .
```

## Troubleshooting

### "Custom script is not in valid dialogue format"
- Make sure each line starts with `A:` or `B:`
- Check for typos (e.g., `a:` lowercase won't work)

### "Custom dialogue script is not in strict alternating speaker format"
- Never have two consecutive A lines or two consecutive B lines
- Pattern must be A → B → A → B → A → B...
- **Note:** REEL TITLE lines are automatically filtered out, so they won't cause validation errors

### "Media harvest not available"
- Install media-harvest: `cd /home/anuj/projects/screen-scraper && pip install -e .`

### No screenshots appearing
- Check marker IDs match keyword line (S1 in `[SHOW:S1]` must match `S1=subject`)
- Verify keyword line is at the end of the script
- Check media-harvest logs for fetch failures

## Examples in Action

**Test the example script:**
```bash
python main.py generate \
  -t "Software Engineering Books" \
  --custom-script example_custom_script.txt \
  -s dialogue \
  -ch assets/characters/character.png \
  -ch2 assets/characters/character-2.png
```

**Expected output:**
- ✅ Script validated immediately
- ✅ Audio generated in ~30 seconds
- ✅ 5 screenshots fetched from media-harvest
- ✅ Video composition with perfectly timed screenshots
- ✅ Total time: ~10 minutes (vs. 15+ minutes with LLM retries)

## Summary

Custom script mode gives you:
1. **Reliability** - No LLM failures
2. **Control** - Exact dialogue and timing
3. **Speed** - Skip retry loops
4. **Quality** - Validate your own content
5. **Integration** - Works with MCP markers and media-harvest

**When to use:**
- LLM generation is failing/unreliable
- You have specific content requirements
- You want consistent, repeatable results
- You're batch-generating multiple reels
