"""
Script generation module using LLM APIs.
"""

import re
from typing import Dict, Any, Optional
from openai import OpenAI

from reelforge.templates.script_prompts import SOLO_NARRATOR_PROMPT, DIALOGUE_PROMPT


class ScriptGenerator:
    """
    Generates video scripts using LLM APIs (Gemini via OpenAI-compatible endpoint).

    This module handles:
    - Solo narrator scripts
    - Two-character dialogue scripts
    - Topic expansion and script refinement
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the script generator.

        Args:
            config: Configuration dictionary containing API keys and model settings
        """
        self.config = config
        self.api_key = config.get('gemini_api_key')

        if not self.api_key or self.api_key == 'YOUR_GEMINI_API_KEY_HERE':
            raise ValueError(
                "Gemini API key not configured. "
                "Please set 'gemini_api_key' in config.yaml. "
                "Get your key from: https://aistudio.google.com/app/apikey"
            )

        self.base_url = config['script']['base_url']
        self.model = config['script']['model']
        self.temperature = config['script']['temperature']
        self.max_tokens = config['script']['max_tokens']

        # Initialize OpenAI client with Gemini endpoint
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def validate_script_length(self, script: str, style: str = "solo") -> tuple[bool, str]:
        """
        Validate script length for 60-second target.

        Args:
            script: Generated script text
            style: Script style (solo or dialogue)

        Returns:
            Tuple of (is_valid, message)
        """
        word_count = len(script.split())

        # Target: 140 words for solo, 130 for dialogue
        max_words = 140 if style == "solo" else 130
        ideal_min = max_words - 20
        ideal_max = max_words

        if word_count > ideal_max + 30:
            return False, f"Script too long: {word_count} words (max: {ideal_max}). Will exceed 60 seconds."
        elif word_count > ideal_max:
            return True, f"Script slightly long: {word_count} words (ideal: {ideal_min}-{ideal_max}). May exceed 60 seconds."
        elif word_count < ideal_min - 20:
            return True, f"Script too short: {word_count} words (ideal: {ideal_min}-{ideal_max}). May be under 50 seconds."
        else:
            return True, f"Script length good: {word_count} words (ideal: {ideal_min}-{ideal_max})"

    def generate(self, topic: str, details: Optional[str] = None, style: str = "solo") -> str:
        """
        Generate a reel script from a topic.

        Args:
            topic: The main topic (e.g., "DeepAI platform")
            details: Optional extra context (links, features, tool description)
            style: "solo" for single narrator, "dialogue" for two-character format

        Returns:
            Script text ready for TTS

        Raises:
            ValueError: If style is invalid or API key not configured
            Exception: If API call fails
        """
        if style == "solo":
            return self.generate_solo_script(topic, details)
        elif style == "dialogue":
            script_dict = self.generate_dialogue_script(topic, details)
            # Convert dict back to formatted text for TTS
            return self._format_dialogue(script_dict)
        else:
            raise ValueError(f"Invalid style: {style}. Must be 'solo' or 'dialogue'")

    def generate_solo_script(self, topic: str, details: Optional[str] = None) -> str:
        """
        Generate a solo narrator script.

        Args:
            topic: Main topic for the video
            details: Additional context or specific points to cover

        Returns:
            Generated script text

        Raises:
            ValueError: If API key is not configured
            Exception: If API call fails
        """
        prompt = SOLO_NARRATOR_PROMPT.format(
            topic=topic,
            details=details or ""
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a viral short-form content scriptwriter specializing in AI and tech topics."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            script = response.choices[0].message.content.strip()
            return script

        except Exception as e:
            raise Exception(f"Script generation failed: {str(e)}")

    def generate_dialogue_script(self, topic: str, details: Optional[str] = None) -> Dict[str, list]:
        """
        Generate a two-character dialogue script.

        Args:
            topic: Main topic for the video
            details: Additional context or specific points to cover

        Returns:
            Dictionary with character names as keys and line lists as values
            Example: {"Character A": ["line1", "line2"], "Character B": ["line1", "line2"]}

        Raises:
            ValueError: If API key is not configured or dialogue parsing fails
            Exception: If API call fails
        """
        prompt = DIALOGUE_PROMPT.format(
            topic=topic,
            details=details or ""
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a viral short-form content scriptwriter specializing in AI and tech topics."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            script_text = response.choices[0].message.content.strip()
            # Clean up any preamble text
            cleaned_text = self._clean_script_response(script_text)
            parsed = self.parse_dialogue(cleaned_text)

            if not parsed:
                raise ValueError(
                    f"Failed to parse dialogue. LLM returned:\n{cleaned_text[:200]}...\n\n"
                    "Expected format: [CHARACTER] line or CHARACTER: line"
                )

            return parsed

        except Exception as e:
            raise Exception(f"Dialogue script generation failed: {str(e)}")

    def _clean_script_response(self, text: str) -> str:
        """
        Clean up LLM response by removing preamble and scene directions.

        Args:
            text: Raw response from LLM

        Returns:
            Cleaned text with only dialogue
        """
        lines = text.split('\n')
        cleaned_lines = []
        started = False

        for line in lines:
            line = line.strip()

            # Skip empty lines at the start
            if not started and not line:
                continue

            # Skip common preamble phrases
            if any(phrase in line.lower() for phrase in [
                "here's the script",
                "here's a script",
                "okay, here's",
                "[scene start]",
                "[scene end]",
                "**(visual:",
                "**[scene"
            ]):
                continue

            # Start capturing when we see a character label (including single letters)
            # Matches: [A], [PETER], PETER:, etc.
            if re.match(r'[\[\(]?[A-Z][A-Z\s]*[\]\)]?\s*.+', line):
                started = True

            if started:
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def parse_dialogue(self, script_text: str) -> Dict[str, list]:
        """
        Parse dialogue script into character lines.

        Supports formats:
        - [CHARACTER] line or [A] line
        - CHARACTER: line or A: line
        - (CHARACTER) line or (A) line

        Args:
            script_text: Raw script text with character labels

        Returns:
            Dictionary mapping character names to their lines
        """
        dialogue = {}

        # Split by lines and process each
        lines = script_text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try to match [CHARACTER] format (including single letters)
            match = re.match(r'\[([A-Z][A-Z\s]*)\]\s*(.+)', line)
            if not match:
                # Try to match CHARACTER: format (including single letters)
                match = re.match(r'([A-Z][A-Z\s]*):\s*(.+)', line)
            if not match:
                # Try to match (CHARACTER) format (including single letters)
                match = re.match(r'\(([A-Z][A-Z\s]*)\)\s*(.+)', line)

            if match:
                character = match.group(1).strip()
                text = match.group(2).strip()

                if character not in dialogue:
                    dialogue[character] = []

                dialogue[character].append(text)

        return dialogue

    def _format_dialogue(self, dialogue: Dict[str, list]) -> str:
        """
        Format dialogue dictionary back to text.

        Args:
            dialogue: Dictionary mapping character names to their lines

        Returns:
            Formatted dialogue text
        """
        if not dialogue:
            return ""

        output_lines = []
        # Interleave dialogue assuming alternating speakers
        all_chars = list(dialogue.keys())
        max_line_count = max(len(char_lines) for char_lines in dialogue.values())

        for i in range(max_line_count):
            for char in all_chars:
                if i < len(dialogue[char]):
                    output_lines.append(f"{char}: {dialogue[char][i]}")

        return "\n".join(output_lines)
