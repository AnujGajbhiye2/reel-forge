"""
Data structures for MCP script generation with screenshot markers.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


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
    lines = raw_text.strip().split('\n')

    # Find the keyword definition line (contains "S1=")
    keyword_line_idx = None
    for idx, line in enumerate(lines):
        if '=' in line and any(f'S{i}=' in line for i in range(1, 10)):
            keyword_line_idx = idx
            break

    if keyword_line_idx is None:
        # No keywords found, return plain dialogue
        dialogue_text = raw_text.strip()
        return ScriptWithMarkers(
            dialogue_text=dialogue_text,
            keyword_map={},
            marker_positions=[]
        )

    # Split into dialogue and keyword sections
    dialogue_lines = lines[:keyword_line_idx]
    keyword_line = lines[keyword_line_idx]

    # Clean up dialogue (remove empty lines and REEL TITLE lines)
    dialogue_lines = [
        line for line in dialogue_lines
        if line.strip() and not line.strip().startswith('REEL TITLE:')
    ]
    dialogue_text = '\n'.join(dialogue_lines)

    # Extract keyword map
    keyword_map = extract_keyword_map(keyword_line)

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

    # Split by comma and parse each definition
    parts = keyword_line.split(',')
    for part in parts:
        part = part.strip()
        if '=' not in part:
            continue

        marker_id, keyword = part.split('=', 1)
        marker_id = marker_id.strip()
        keyword = keyword.strip()

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
