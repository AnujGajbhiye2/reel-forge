"""
Marker-to-timestamp resolution for screenshot placement.
"""
import logging
from typing import Any, Dict, List

from reelforge.script.types import ScriptWithMarkers

logger = logging.getLogger(__name__)


class MarkerResolver:
    """
    Resolves [SHOW:S#] markers to exact video timestamps.

    Maps marker positions in dialogue to word-level caption timestamps.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize marker resolver.

        Args:
            config: Configuration dictionary from config.yaml
        """
        self.config = config
        screenshots_cfg = config.get("screenshots", config.get("media_harvest", {}))
        self.default_duration = screenshots_cfg.get("duration_seconds", 4.0)
        self.min_duration = screenshots_cfg.get("min_duration_seconds", 2.0)
        self.max_duration = screenshots_cfg.get("max_duration_seconds", 6.0)

    def resolve_markers_to_timestamps(
        self,
        script_with_markers: ScriptWithMarkers,
        word_captions: List[Dict[str, Any]],
        id_to_path: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """
        Map markers to timestamps for VideoCompositor.

        Args:
            script_with_markers: Parsed script with marker positions
            word_captions: WhisperX word-level timestamps
                Format: [{"word": "hello", "start": 0.5, "end": 0.8}, ...]
            id_to_path: Mapping of marker IDs to file paths
                Format: {"S1": "/path/cursor.png", "S2": "/path/codex.png"}

        Returns:
            Screenshots data for VideoCompositor:
            [{"id": 1, "file": "/path/cursor.png", "start": 2.45, "end": 5.32, "status": "ok"}]
        """
        screenshots_data = []

        if not script_with_markers.marker_positions:
            logger.info("No markers to resolve")
            return screenshots_data

        if not word_captions:
            logger.warning("No word captions available for marker resolution")
            return screenshots_data

        # Build dialogue line structure for word counting
        dialogue_lines = self._parse_dialogue_lines(script_with_markers.dialogue_text)

        for marker_pos in script_with_markers.marker_positions:
            if marker_pos.marker_id not in id_to_path:
                logger.warning("No screenshot found for marker %s", marker_pos.marker_id)
                continue

            # Find word caption index for this marker
            target_word_index = self._find_word_index_for_marker(
                marker_pos,
                dialogue_lines,
                word_captions
            )

            if target_word_index is None:
                logger.warning("Could not resolve timestamp for marker %s", marker_pos.marker_id)
                continue

            # Calculate display duration
            start = word_captions[target_word_index]["start"]
            end = start + self.default_duration

            # Clamp to audio bounds
            audio_end = word_captions[-1]["end"] if word_captions else start + self.default_duration
            end = min(end, audio_end)

            # Ensure minimum duration
            if end - start < self.min_duration:
                end = start + self.min_duration
                end = min(end, audio_end)

            screenshots_data.append({
                "id": len(screenshots_data) + 1,
                "marker_id": marker_pos.marker_id,
                "file": id_to_path[marker_pos.marker_id],
                "start": start,
                "end": end,
                "status": "ok",
            })

            logger.info("Resolved marker %s to timestamp %.2f-%.2f",
                       marker_pos.marker_id, start, end)

        return screenshots_data

    def _parse_dialogue_lines(self, dialogue_text: str) -> List[Dict[str, Any]]:
        """
        Parse dialogue text into structured lines.

        Args:
            dialogue_text: Script with "A:" and "B:" prefixes

        Returns:
            List of dialogue lines with metadata:
            [{"character": "A", "text": "hello world", "words": ["hello", "world"]}, ...]
        """
        import re

        lines = dialogue_text.split('\n')
        dialogue_lines = []

        for line in lines:
            line = line.strip()
            if not line or ':' not in line:
                continue

            character = line.split(':', 1)[0].strip()
            text = line.split(':', 1)[1].strip()

            # Remove [SHOW:S#] markers for word counting
            text_clean = re.sub(r'\[SHOW:S\d+\]', '', text)
            words = text_clean.split()

            dialogue_lines.append({
                "character": character,
                "text": text,
                "text_clean": text_clean,
                "words": words,
            })

        return dialogue_lines

    def _find_word_index_for_marker(
        self,
        marker_pos,
        dialogue_lines: List[Dict[str, Any]],
        word_captions: List[Dict[str, Any]],
    ) -> int | None:
        """
        Find the word caption index corresponding to a marker position.

        Strategy:
        1. Count cumulative words across dialogue lines up to marker's line
        2. Add marker's word_offset within that line
        3. Return corresponding word caption index

        Args:
            marker_pos: MarkerPosition object
            dialogue_lines: Parsed dialogue lines
            word_captions: WhisperX word-level timestamps

        Returns:
            Index into word_captions array, or None if not found
        """
        if marker_pos.line_index >= len(dialogue_lines):
            logger.warning("Marker line_index %d exceeds dialogue lines count %d",
                          marker_pos.line_index, len(dialogue_lines))
            return None

        # Count cumulative words up to (but not including) marker's line
        cumulative_words = 0
        for i in range(marker_pos.line_index):
            cumulative_words += len(dialogue_lines[i]["words"])

        # Add word offset within marker's line
        target_word_index = cumulative_words + marker_pos.word_offset

        # Validate against word_captions length
        if target_word_index >= len(word_captions):
            logger.warning("Calculated word index %d exceeds captions count %d",
                          target_word_index, len(word_captions))
            # Fall back to last word
            return len(word_captions) - 1

        return target_word_index
