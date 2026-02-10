"""
Tests for MCP integration components.
"""
import pytest
from reelforge.script.types import (
    MarkerPosition,
    ScriptWithMarkers,
    extract_keyword_map,
    find_marker_positions,
    parse_mcp_output,
    sanitize_dialogue_script,
)


class TestExtractKeywordMap:
    """Tests for keyword map extraction."""

    def test_simple_keywords(self):
        """Test extracting simple keyword definitions."""
        keyword_line = "S1=cursor, S2=codex"
        result = extract_keyword_map(keyword_line)
        assert result == {"S1": "cursor", "S2": "codex"}

    def test_keywords_with_spaces(self):
        """Test keywords with extra whitespace."""
        keyword_line = "S1 = cursor , S2 = codex"
        result = extract_keyword_map(keyword_line)
        assert result == {"S1": "cursor", "S2": "codex"}

    def test_keywords_with_multiple_words(self):
        """Test keywords that are phrases."""
        keyword_line = "S1=cursor ai, S2=github copilot"
        result = extract_keyword_map(keyword_line)
        assert result == {"S1": "cursor ai", "S2": "github copilot"}

    def test_empty_keyword_line(self):
        """Test empty keyword line."""
        result = extract_keyword_map("")
        assert result == {}

    def test_malformed_keyword_line(self):
        """Test malformed keyword line (no equals sign)."""
        result = extract_keyword_map("S1 cursor, S2 codex")
        assert result == {}


class TestFindMarkerPositions:
    """Tests for marker position finding."""

    def test_single_marker(self):
        """Test finding a single marker."""
        dialogue = "A: Hello [SHOW:S1] world"
        positions = find_marker_positions(dialogue)
        assert len(positions) == 1
        assert positions[0].marker_id == "S1"
        assert positions[0].character == "A"
        assert positions[0].line_index == 0
        assert positions[0].word_offset == 1  # After "Hello"

    def test_multiple_markers_same_line(self):
        """Test finding multiple markers in one line."""
        dialogue = "A: Check [SHOW:S1] this [SHOW:S2] out"
        positions = find_marker_positions(dialogue)
        assert len(positions) == 2
        assert positions[0].marker_id == "S1"
        assert positions[0].word_offset == 1
        assert positions[1].marker_id == "S2"
        assert positions[1].word_offset == 2

    def test_multiple_markers_different_lines(self):
        """Test finding markers across multiple lines."""
        dialogue = """A: Hello [SHOW:S1] world
B: This is [SHOW:S2] cool"""
        positions = find_marker_positions(dialogue)
        assert len(positions) == 2
        assert positions[0].marker_id == "S1"
        assert positions[0].character == "A"
        assert positions[0].line_index == 0
        assert positions[1].marker_id == "S2"
        assert positions[1].character == "B"
        assert positions[1].line_index == 1

    def test_marker_at_line_start(self):
        """Test marker at the beginning of a line."""
        dialogue = "A: [SHOW:S1] Hello world"
        positions = find_marker_positions(dialogue)
        assert len(positions) == 1
        assert positions[0].word_offset == 0

    def test_no_markers(self):
        """Test dialogue with no markers."""
        dialogue = "A: Hello world\nB: This is cool"
        positions = find_marker_positions(dialogue)
        assert len(positions) == 0


class TestParseMCPOutput:
    """Tests for full MCP output parsing."""

    def test_complete_mcp_output(self):
        """Test parsing complete MCP output."""
        raw_text = """A: Check out Cursor [SHOW:S1] today
B: And don't forget Codex [SHOW:S2] either

S1=cursor, S2=codex"""
        result = parse_mcp_output(raw_text)

        assert isinstance(result, ScriptWithMarkers)
        assert "A: Check out Cursor [SHOW:S1] today" in result.dialogue_text
        assert "B: And don't forget Codex [SHOW:S2] either" in result.dialogue_text
        assert result.keyword_map == {"S1": "cursor", "S2": "codex"}
        assert len(result.marker_positions) == 2

    def test_mcp_output_no_keywords(self):
        """Test parsing MCP output without keyword definitions."""
        raw_text = """A: Hello world
B: This is cool"""
        result = parse_mcp_output(raw_text)

        assert result.dialogue_text == "A: Hello world\nB: This is cool"
        assert result.keyword_map == {}
        assert len(result.marker_positions) == 0

    def test_mcp_output_with_empty_lines(self):
        """Test parsing MCP output with extra blank lines."""
        raw_text = """A: Check out Cursor [SHOW:S1]

B: And Codex [SHOW:S2]

S1=cursor, S2=codex"""
        result = parse_mcp_output(raw_text)

        # Empty lines should be filtered out
        assert "A: Check out Cursor [SHOW:S1]" in result.dialogue_text
        assert "B: And Codex [SHOW:S2]" in result.dialogue_text
        assert result.keyword_map == {"S1": "cursor", "S2": "codex"}

    def test_mcp_output_strips_wrapper_lines_without_keywords(self):
        raw_text = """1. DIALOGUE SCRIPT
A: Hello world
B: This is cool
MEDIA HARVESTER KEYWORDS"""
        result = parse_mcp_output(raw_text)
        assert result.dialogue_text == "A: Hello world\nB: This is cool"
        assert result.keyword_map == {}

    def test_mcp_output_parses_keyword_line_with_label_prefix(self):
        raw_text = """A: First line [SHOW:S1]
B: Second line [SHOW:S2]
MEDIA HARVESTER KEYWORDS: S1=cursor, S2=codex"""
        result = parse_mcp_output(raw_text)
        assert result.keyword_map == {"S1": "cursor", "S2": "codex"}
        assert len(result.marker_positions) == 2


class TestDialogueSanitization:
    def test_sanitize_dialogue_script_keeps_only_speaker_lines(self):
        raw_text = """```text
REEL TITLE: Test
1. DIALOGUE SCRIPT
A: Line one
Some random prose
B: Line two [SHOW:S1]
2. MEDIA HARVESTER KEYWORDS
S1=cursor
```"""
        cleaned = sanitize_dialogue_script(raw_text)
        assert cleaned == "A: Line one\nB: Line two [SHOW:S1]"


class TestMarkerResolver:
    """Tests for MarkerResolver timestamp calculation."""

    def test_resolve_single_marker(self):
        """Test resolving a single marker to timestamp."""
        from reelforge.media.marker_resolver import MarkerResolver

        config = {
            "media_harvest": {
                "screenshot_duration_seconds": 4.0,
                "min_duration_seconds": 2.0,
                "max_duration_seconds": 6.0,
            }
        }
        resolver = MarkerResolver(config)

        script_with_markers = ScriptWithMarkers(
            dialogue_text="A: Hello [SHOW:S1] world",
            keyword_map={"S1": "cursor"},
            marker_positions=[
                MarkerPosition(marker_id="S1", character="A", line_index=0, word_offset=1)
            ],
        )

        word_captions = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0},
            {"word": "amazing", "start": 1.1, "end": 1.5},
            {"word": "stuff", "start": 1.6, "end": 2.0},
            {"word": "here", "start": 2.1, "end": 5.0},
        ]

        id_to_path = {"S1": "/path/cursor.png"}

        screenshots_data = resolver.resolve_markers_to_timestamps(
            script_with_markers, word_captions, id_to_path
        )

        assert len(screenshots_data) == 1
        assert screenshots_data[0]["file"] == "/path/cursor.png"
        assert screenshots_data[0]["start"] == 0.6  # Start of "world"
        assert screenshots_data[0]["end"] == 4.6  # Start + 4 seconds (not clamped)

    def test_resolve_missing_screenshot(self):
        """Test resolving marker when screenshot is missing."""
        from reelforge.media.marker_resolver import MarkerResolver

        config = {"media_harvest": {"screenshot_duration_seconds": 4.0}}
        resolver = MarkerResolver(config)

        script_with_markers = ScriptWithMarkers(
            dialogue_text="A: Hello [SHOW:S1] world",
            keyword_map={"S1": "cursor"},
            marker_positions=[
                MarkerPosition(marker_id="S1", character="A", line_index=0, word_offset=1)
            ],
        )

        word_captions = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0},
        ]

        id_to_path = {}  # No screenshot for S1

        screenshots_data = resolver.resolve_markers_to_timestamps(
            script_with_markers, word_captions, id_to_path
        )

        assert len(screenshots_data) == 0

    def test_resolve_multiple_markers(self):
        """Test resolving multiple markers across dialogue lines."""
        from reelforge.media.marker_resolver import MarkerResolver

        config = {"media_harvest": {"screenshot_duration_seconds": 3.0}}
        resolver = MarkerResolver(config)

        script_with_markers = ScriptWithMarkers(
            dialogue_text="A: Check Cursor [SHOW:S1] out\nB: And Codex [SHOW:S2] too",
            keyword_map={"S1": "cursor", "S2": "codex"},
            marker_positions=[
                MarkerPosition(marker_id="S1", character="A", line_index=0, word_offset=2),
                MarkerPosition(marker_id="S2", character="B", line_index=1, word_offset=2),
            ],
        )

        word_captions = [
            {"word": "Check", "start": 0.0, "end": 0.3},
            {"word": "Cursor", "start": 0.4, "end": 0.7},
            {"word": "out", "start": 0.8, "end": 1.0},
            {"word": "And", "start": 1.1, "end": 1.3},
            {"word": "Codex", "start": 1.4, "end": 1.7},
            {"word": "too", "start": 1.8, "end": 2.0},
        ]

        id_to_path = {"S1": "/path/cursor.png", "S2": "/path/codex.png"}

        screenshots_data = resolver.resolve_markers_to_timestamps(
            script_with_markers, word_captions, id_to_path
        )

        assert len(screenshots_data) == 2
        assert screenshots_data[0]["file"] == "/path/cursor.png"
        assert screenshots_data[0]["start"] == 0.8  # Start of "out"
        assert screenshots_data[1]["file"] == "/path/codex.png"
        assert screenshots_data[1]["start"] == 1.8  # Start of "too"


class TestReelTitleFiltering:
    """Tests for REEL TITLE line filtering."""

    def test_reel_title_filtered_from_dialogue(self):
        """Test that REEL TITLE is removed from dialogue text."""
        mcp_output = """REEL TITLE: Books That Refactor Your Brain
A: Stop scrolling. Your code is bad.
B: That sounded personal.
A: It is. Top 5 books, speedrun edition.

S1=cursor, S2=codex"""

        result = parse_mcp_output(mcp_output)

        # REEL TITLE should not be in dialogue text
        assert "REEL TITLE" not in result.dialogue_text

        # Dialogue should only contain A: and B: lines
        lines = [line.strip() for line in result.dialogue_text.split('\n') if line.strip()]
        assert all(line.startswith('A:') or line.startswith('B:') for line in lines)
        assert len(lines) == 3  # Three dialogue lines

    def test_reel_title_with_markers(self):
        """Test REEL TITLE filtering with MCP markers present."""
        mcp_output = """REEL TITLE: Your Title
A: First line [SHOW:S1] here
B: Second line [SHOW:S2] there

S1=cursor, S2=codex"""

        result = parse_mcp_output(mcp_output)

        # REEL TITLE filtered
        assert "REEL TITLE" not in result.dialogue_text

        # Markers preserved
        assert "[SHOW:S1]" in result.dialogue_text
        assert "[SHOW:S2]" in result.dialogue_text

        # Keyword map parsed
        assert result.keyword_map == {"S1": "cursor", "S2": "codex"}

        # Marker positions found
        assert len(result.marker_positions) == 2

    def test_alternating_validation_with_reel_title(self):
        """Test that dialogue alternation validation handles REEL TITLE lines."""
        from reelforge.pipeline.quality_gate import _dialogue_is_strictly_alternating

        # Script with REEL TITLE should be handled gracefully
        script_with_title = """REEL TITLE: Test
A: First line
B: Second line
A: Third line"""

        # Should skip REEL TITLE and validate dialogue alternation
        result = _dialogue_is_strictly_alternating(script_with_title)
        assert result is True

    def test_no_reel_title_still_works(self):
        """Test that scripts without REEL TITLE still work."""
        mcp_output = """A: First line
B: Second line

S1=cursor"""

        result = parse_mcp_output(mcp_output)

        # Should parse normally
        assert len(result.dialogue_text.strip().split('\n')) == 2
        assert result.keyword_map == {"S1": "cursor"}
