# MCP + Media-Harvest Integration

## Overview

The ReelForge pipeline now integrates with the MCP (Model Context Protocol) server and media-harvest project to enable:

1. **Automated script generation** with embedded screenshot markers
2. **High-quality screenshot acquisition** via media-harvest
3. **Precise timestamp placement** based on dialogue markers
4. **Graceful fallbacks** at multiple levels

## Architecture

### Data Flow

```
User Input → MCP Script Gen → TTS → Captions → Media Harvest → Marker Resolution → Video Composition
```

### Components

#### 1. MCP Script Generator (`reelforge/script/mcp_generator.py`)

Generates dialogue scripts with embedded `[SHOW:S#]` markers and keyword definitions.

**Two modes:**
- **MCP Subprocess**: Calls MCP server via stdio (primary)
- **Direct Gemini**: Uses embedded prompt template (fallback)

**Example output:**
```
A: Check out Cursor [SHOW:S1] for AI coding
B: And don't forget Codex [SHOW:S2] either

S1=cursor, S2=codex
```

#### 2. Media Harvest Client (`reelforge/media/harvest_client.py`)

Bridge to the media-harvest project for fetching screenshots.

**Features:**
- Maps keywords to high-quality screenshots/images
- Supports partial results on timeout (30s default)
- Uses vertical 9:16 transform preset for reels
- Caches results for reuse

#### 3. Marker Resolver (`reelforge/media/marker_resolver.py`)

Maps `[SHOW:S#]` markers to exact video timestamps using WhisperX word-level captions.

**Strategy:**
1. Parse marker positions in dialogue (line index + word offset)
2. Count cumulative words to find word caption index
3. Use word's timestamp as screenshot start time
4. Add configured duration (default 4 seconds)

#### 4. Pipeline Orchestrator (Modified)

Integration points in `reelforge/pipeline/orchestrator.py`:

- **Line 58**: Generator selection (MCP vs legacy)
- **Line 99**: Script generation with marker extraction
- **Line 219**: Media-harvest call after TTS
- **Line 270**: Marker resolution before video composition

## Configuration

### Enable MCP Mode

In `config.yaml`:

```yaml
script:
  use_mcp: true  # Default ON
  mcp_server_path: "/home/anuj/.claude/mcp-servers/reelforge-writer/server.py"
  mcp_python_path: "/home/anuj/.claude/mcp-servers/reelforge-writer/venv/bin/python"
  mcp_timeout_seconds: 30
```

### Media Harvest Settings

```yaml
media_harvest:
  enabled: true
  project_path: "/home/anuj/projects/screen-scraper"

  harvest_config:
    mode: "safe"  # Fallback to web images when screenshots fail
    transform_preset: "vertical_9_16"  # Match reel dimensions
    timeout_seconds: 30
    retry_attempts: 3
    enable_cache: true
    assets_per_entity: 1

  screenshot_duration_seconds: 4.0
  min_duration_seconds: 2.0
  max_duration_seconds: 6.0
```

## Usage

### CLI Commands

**Basic usage (MCP enabled by default):**
```bash
python main.py generate \
  -t "Cursor vs Windsurf vs Copilot" \
  --websites "cursor.sh,windsurf.ai,github.com/features/copilot" \
  --length 45s
```

**Disable MCP (use legacy generator):**
```bash
python main.py generate \
  -t "Your Topic" \
  --disable-mcp
```

**Profanity control:**
```bash
python main.py generate \
  -t "Your Topic" \
  --profanity light  # Options: none, light, allowed
```

### New CLI Options

- `--websites TEXT`: Comma-separated websites/tools to feature
- `--length [30s|45s|60s]`: Target video length (default: 45s)
- `--profanity [none|light|allowed]`: Profanity level (default: none)
- `--disable-mcp`: Disable MCP, use legacy script generator

## Fallback Hierarchy

### Level 1: MCP + Media-Harvest (Ideal)
- MCP generates script with markers
- Media-harvest fetches high-quality screenshots
- Precise timing via marker resolution

### Level 2: Direct Gemini + Media-Harvest
- MCP server unavailable, use embedded prompt template
- Media-harvest fetches screenshots
- Precise timing via marker resolution

### Level 3: Legacy Mode
- MCP disabled via `--disable-mcp` or `use_mcp: false`
- Falls back to existing `ScreenshotResearcher`
- Heuristic timing based on keyword extraction

### Level 4: No Screenshots
- All screenshot methods disabled
- Generate video without screenshots
- Log warnings

## Error Handling

### Partial Results

Media-harvest timeouts are handled gracefully:
```python
try:
    id_to_path = harvest_client.fetch_screenshots(...)
except Exception as exc:
    logger.warning("Media harvest failed: %s. Using partial results.", exc)
    # Continue with whatever was fetched
```

### Missing Dependencies

If media-harvest is not installed:
```
ImportError: media-harvest not installed.
Install from: cd /home/anuj/projects/screen-scraper && pip install -e .
```

## Testing

### Run MCP Integration Tests
```bash
pytest tests/test_mcp_integration.py -v
```

### Run Workflow Tests
```bash
pytest tests/test_mcp_workflow.py -v
```

### Full Test Suite
```bash
pytest tests/ -v
```

## Data Structures

### ScriptWithMarkers

```python
@dataclass
class ScriptWithMarkers:
    dialogue_text: str              # Full script with [SHOW:S#] markers
    keyword_map: Dict[str, str]     # {S1: "cursor", S2: "codex"}
    marker_positions: List[MarkerPosition]
```

### MarkerPosition

```python
@dataclass
class MarkerPosition:
    marker_id: str      # "S1", "S2", etc.
    character: str      # "A" or "B"
    line_index: int     # Which dialogue line (0-indexed)
    word_offset: int    # Word position within that line
```

### Screenshots Data

Passed to `VideoCompositor`:
```python
[
    {
        "id": 1,
        "file": "/path/cursor.png",
        "start": 2.45,
        "end": 6.45,
        "status": "ok"
    },
    ...
]
```

## File Structure

### New Files
```
reelforge/
├── script/
│   ├── types.py              # Data structures for markers
│   └── mcp_generator.py      # MCP integration logic
├── media/
│   ├── __init__.py
│   ├── harvest_client.py     # Media-harvest bridge
│   └── marker_resolver.py    # Timestamp resolution
tests/
├── test_mcp_integration.py   # Unit tests for MCP components
└── test_mcp_workflow.py      # Integration tests
```

### Modified Files
```
config.yaml                   # Added MCP and media_harvest sections
reelforge/pipeline/orchestrator.py  # Integration points
reelforge/cli/commands/generate.py  # New CLI options
reelforge/script/templates/prompts.py  # MCP prompt template
requirements.txt              # Media-harvest dependency note
```

## Performance

### Typical Timings

- MCP script generation: 3-8 seconds
- Media-harvest (3 keywords): 10-30 seconds (with cache: <1s)
- Marker resolution: <100ms

### Optimization Tips

1. **Enable caching**: Set `enable_cache: true` in media_harvest config
2. **Reduce timeout**: Lower `timeout_seconds` for faster partial results
3. **Limit keywords**: Fewer markers = faster harvest
4. **Reuse runs**: Cache persists across runs in `.cache/media-harvest/`

## Troubleshooting

### MCP Server Not Found

**Error:**
```
MCP server not found at /path/server.py, will use direct Gemini fallback
```

**Solution:**
- Verify MCP server path in config.yaml
- Check that MCP server exists and is executable

### Media-Harvest Import Error

**Error:**
```
media-harvest not installed
```

**Solution:**
```bash
cd /home/anuj/projects/screen-scraper
pip install -e .
```

### Screenshots Not Appearing

**Checklist:**
1. Verify `media_harvest.enabled: true` in config
2. Check logs for "MCP generated X screenshot markers"
3. Verify "Media harvest fetched X/Y screenshots"
4. Confirm "Resolved X screenshot markers to timestamps"
5. Check output video has screenshot overlays

### Marker Resolution Failures

**Symptoms:**
- "Could not resolve timestamp for marker S1"

**Causes:**
- Marker position exceeds word caption array
- Empty word captions
- Mismatched dialogue structure

**Debug:**
```python
# Check marker positions
from reelforge.script.types import parse_mcp_output
result = parse_mcp_output(script_text)
print(result.marker_positions)
```

## Best Practices

1. **Specific websites**: Use `--websites` for targeted screenshot fetching
2. **Review markers**: Check generated scripts for sensible marker placement
3. **Test fallbacks**: Occasionally test with `--disable-mcp` to verify legacy mode
4. **Monitor timing**: Adjust `screenshot_duration_seconds` based on content density
5. **Cache management**: Clear `.cache/media-harvest/` when screenshots become stale

## Future Enhancements

- [ ] Support for custom screenshot URLs (bypass media-harvest)
- [ ] Dynamic duration based on sentence length
- [ ] Multiple screenshots per marker (carousel effect)
- [ ] Screenshot priority/ranking in overlay
- [ ] MCP streaming for faster response
- [ ] Media-harvest result preview before video composition

## References

- MCP Server: `/home/anuj/.claude/mcp-servers/reelforge-writer/`
- Media-Harvest: `/home/anuj/projects/screen-scraper/`
- ReelForge Blueprint: `reelforge-blueprint.md`
- Architecture Docs: `docs/architecture/reorg-plan.md`
