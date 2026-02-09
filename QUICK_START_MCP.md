# Quick Start: MCP + Media-Harvest Integration

## Installation

### 1. Install Media-Harvest (Required)
```bash
cd /home/anuj/projects/screen-scraper
pip install -e .
```

### 2. Verify Installation
```bash
python -c "from media_harvest import harvest; print('✅ Media-harvest installed')"
```

### 3. Check MCP Server (Optional)
```bash
ls /home/anuj/.claude/mcp-servers/reelforge-writer/server.py
# If not found, will fall back to direct Gemini (still works!)
```

## Basic Usage

### Generate a Reel (MCP Mode - Default)
```bash
python main.py generate \
  -t "Cursor vs Windsurf vs Copilot" \
  --websites "cursor.sh,windsurf.ai,github.com/features/copilot"
```

**What happens:**
1. MCP generates dialogue with screenshot markers
2. EdgeTTS creates audio
3. WhisperX generates word timestamps
4. Media-harvest fetches high-quality screenshots
5. Markers are resolved to exact video timestamps
6. Final video is composed with screenshots at precise moments

### Generate with Custom Length
```bash
python main.py generate \
  -t "Top 5 AI Coding Tools" \
  --websites "cursor.sh,github.com/features/copilot,codeium.com" \
  --length 60s
```

### Generate with Legacy Mode
```bash
python main.py generate \
  -t "Your Topic" \
  --disable-mcp
```

## Configuration Quick Check

```bash
# Verify config loads
python -c "from reelforge.shared.config import load_config; cfg = load_config('config.yaml'); print('MCP:', cfg['script']['use_mcp'], '| Harvest:', cfg['media_harvest']['enabled'])"
```

Expected output:
```
MCP: True | Harvest: True
```

## Troubleshooting

### Media-Harvest Not Installed
**Error:** `ImportError: media-harvest not installed`

**Fix:**
```bash
cd /home/anuj/projects/screen-scraper
pip install -e .
```

### MCP Server Not Found
**Log:** `MCP server not found at ..., will use direct Gemini fallback`

**Status:** ✅ This is fine! Direct Gemini mode works well.

**Optional Fix:**
```bash
# Check MCP server path in config.yaml
grep mcp_server_path config.yaml
```

### No Screenshots Appearing
**Check logs:**
```bash
tail -50 logs/$(ls -t logs/ | head -1)
```

**Look for:**
- "MCP generated X screenshot markers"
- "Media harvest fetched X/Y screenshots"
- "Resolved X screenshot markers to timestamps"

## CLI Options Reference

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--websites` | TEXT | None | Comma-separated websites/tools to feature |
| `--length` | 30s\|45s\|60s | 45s | Target video length |
| `--profanity` | none\|light\|allowed | none | Profanity level |
| `--disable-mcp` | FLAG | false | Use legacy script generator |

## Configuration Keys

### MCP Settings (`config.yaml`)
```yaml
script:
  use_mcp: true
  mcp_server_path: "/path/to/server.py"
  mcp_python_path: "/path/to/python"
  mcp_timeout_seconds: 30
```

### Media Harvest Settings (`config.yaml`)
```yaml
media_harvest:
  enabled: true
  harvest_config:
    mode: "safe"
    transform_preset: "vertical_9_16"
    timeout_seconds: 30
  screenshot_duration_seconds: 4.0
```

## Verification Commands

```bash
# Test imports
python -c "from reelforge.script.mcp_generator import MCPScriptGenerator; print('✅ MCP OK')"

# Test media-harvest
python -c "from media_harvest import harvest; print('✅ Harvest OK')"

# Run unit tests
pytest tests/test_mcp_integration.py -v

# Run full test suite
pytest tests/ -v

# Verify CLI
python main.py generate --help | grep -A2 "websites"
```

## Example Workflows

### Tech Tool Comparison
```bash
python main.py generate \
  -t "Cursor vs GitHub Copilot: Which AI coding assistant is better?" \
  --websites "cursor.sh,github.com/features/copilot" \
  --length 45s \
  -s dialogue
```

### Product Review
```bash
python main.py generate \
  -t "Is Claude Code worth using in 2026?" \
  --websites "claude.ai/code,docs.anthropic.com" \
  --length 60s
```

### Quick Test (No Screenshots)
```bash
python main.py generate \
  -t "Test Video" \
  --disable-mcp \
  --no-auto-screenshots
```

## Performance Tips

1. **Enable caching** (default: enabled in config)
2. **Specific websites**: Use `--websites` for faster harvesting
3. **Shorter timeouts**: Reduce `timeout_seconds` for quicker partial results
4. **Reuse runs**: Cached screenshots persist across runs

## Status Indicators

| Message | Meaning | Action |
|---------|---------|--------|
| "Using MCP script generator" | ✅ MCP mode active | None |
| "Using legacy script generator" | ⚠️ MCP disabled | Optional: check config |
| "MCP generated X markers" | ✅ Markers found | None |
| "Media harvest fetched X/Y" | ✅ Screenshots acquired | None |
| "Resolved X markers to timestamps" | ✅ Timing set | None |
| "Using partial results" | ⚠️ Timeout, but OK | Consider increasing timeout |
| "media-harvest not installed" | ❌ Missing dependency | Install media-harvest |

## Documentation

- **Full Guide**: `docs/MCP_INTEGRATION.md`
- **Implementation Summary**: `INTEGRATION_COMPLETE.md`
- **Main README**: `README.md`
- **Blueprint**: `reelforge-blueprint.md`

## Support

If you encounter issues:

1. Check logs: `tail -50 logs/$(ls -t logs/ | head -1)`
2. Verify config: `python main.py validate`
3. Test media-harvest: `python -c "from media_harvest import harvest"`
4. Try legacy mode: `--disable-mcp`
5. Review docs: `docs/MCP_INTEGRATION.md`

## Quick Commands Summary

```bash
# Generate reel with MCP + media-harvest (default)
python main.py generate -t "Your Topic" --websites "example.com"

# Generate with legacy mode
python main.py generate -t "Your Topic" --disable-mcp

# Install media-harvest
cd /home/anuj/projects/screen-scraper && pip install -e .

# Run tests
pytest tests/test_mcp_integration.py -v

# Check config
python -c "from reelforge.shared.config import load_config; print(load_config('config.yaml')['script']['use_mcp'])"

# View help
python main.py generate --help
```

---

**Ready to generate reels with precise screenshot timing!** 🎬
