"""
Data structures for MCP script generation with screenshot markers.
"""
import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class MarkerPosition:
    """Location of a [SHOW:S#] marker in the dialogue script."""
    marker_id: str      # "S1", "S2", etc.
    character: str      # "A" or "B"
    line_index: int     # Which dialogue line (0-indexed)
    word_offset: int    # Word position within that line


@dataclass
class ScriptWithMarkers:
    """MCP-generated script with embedded screenshot markers."""
    dialogue_text: str                      # Full script with [SHOW:S#] markers
    keyword_map: Dict[str, str]             # {S1: "cursor", S2: "codex"}
    marker_positions: List[MarkerPosition]  # Parsed marker locations


_DIALOGUE_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_\- ]*):\s+(.+)$")
_KEYWORD_LINE_RE = re.compile(r"\bS\d+\s*=")
_HEADING_LINE_RE = re.compile(
    r"^(?:\d+\s*[\.\)]\s*)?(?:DIALOGUE SCRIPT|MEDIA HARVESTER KEYWORDS|OUTPUT FORMAT)\b",
    flags=re.IGNORECASE,
)


def sanitize_dialogue_script(raw_text: str) -> str:
    """
    Keep only valid dialogue lines and remove wrapper/template noise.

    Args:
        raw_text: Raw model output containing dialogue and optional wrapper text

    Returns:
        Newline-separated dialogue lines (speaker-prefixed)
    """
    if not raw_text:
        return ""

    cleaned_lines: List[str] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            continue
        if line.upper().startswith("REEL TITLE:"):
            continue
        if _HEADING_LINE_RE.match(line):
            continue
        if _KEYWORD_LINE_RE.search(line):
            continue

        match = _DIALOGUE_LINE_RE.match(line)
        if not match:
            continue

        speaker, body = match.groups()
        cleaned_lines.append(f"{speaker.strip()}: {body.strip()}")

    return "\n".join(cleaned_lines)


def parse_mcp_output(raw_text: str) -> ScriptWithMarkers:
    """
    Parse MCP server output to extract dialogue and keyword mappings.

    Expected format:
    ```
    A: Hello [SHOW:S1] world
    B: This is [SHOW:S2] cool

    S1=cursor, S2=codex
    ```

    Args:
        raw_text: Raw output from MCP server

    Returns:
        ScriptWithMarkers with parsed dialogue, keyword map, and marker positions
    """
    lines = raw_text.strip().split("\n")
    keyword_map: Dict[str, str] = {}

    for line in lines:
        if _KEYWORD_LINE_RE.search(line):
            keyword_map.update(extract_keyword_map(line))

    dialogue_text = sanitize_dialogue_script(raw_text)

    # Find marker positions
    marker_positions = find_marker_positions(dialogue_text)

    return ScriptWithMarkers(
        dialogue_text=dialogue_text,
        keyword_map=keyword_map,
        marker_positions=marker_positions
    )


def extract_keyword_map(keyword_line: str) -> Dict[str, str]:
    """
    Extract keyword definitions from MCP output.

    Example: "S1=cursor, S2=codex" -> {"S1": "cursor", "S2": "codex"}

    Args:
        keyword_line: Line containing keyword definitions

    Returns:
        Dictionary mapping marker IDs to keywords
    """
    keyword_map = {}

    for match in re.finditer(r"(S\d+)\s*=\s*([^,]+)", keyword_line, flags=re.IGNORECASE):
        marker_id = match.group(1).upper().strip()
        keyword = match.group(2).strip()
        if marker_id and keyword:
            keyword_map[marker_id] = keyword

    return keyword_map


def find_marker_positions(dialogue_text: str) -> List[MarkerPosition]:
    """
    Locate all [SHOW:S#] markers in dialogue text.

    Args:
        dialogue_text: Script text with embedded markers

    Returns:
        List of MarkerPosition objects with location metadata
    """
    import re

    marker_positions = []
    lines = dialogue_text.split('\n')

    for line_idx, line in enumerate(lines):
        # Extract character (A: or B:)
        if ':' not in line:
            continue

        character = line.split(':', 1)[0].strip()
        dialogue_part = line.split(':', 1)[1].strip()

        # Find all [SHOW:S#] markers in this line
        pattern = r'\[SHOW:(S\d+)\]'
        for match in re.finditer(pattern, dialogue_part):
            marker_id = match.group(1)

            # Calculate word offset (count words before marker)
            text_before_marker = dialogue_part[:match.start()]
            # Remove other markers from word count
            text_before_marker = re.sub(r'\[SHOW:S\d+\]', '', text_before_marker)
            words_before = len(text_before_marker.split())

            marker_positions.append(MarkerPosition(
                marker_id=marker_id,
                character=character,
                line_index=line_idx,
                word_offset=words_before
            ))

    return marker_positions
