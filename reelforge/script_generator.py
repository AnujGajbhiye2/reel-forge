"""
Script generation module using LLM APIs.
"""

import re
from typing import Dict, Any, Optional
from reelforge.logging_utils import get_logger

from reelforge.templates.script_prompts import SOLO_NARRATOR_PROMPT, DIALOGUE_PROMPT


class ScriptGenerator:
    """
    Generates video scripts using Gemini models.

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

        primary_model = config['script']['model']
        fallback_models = config['script'].get('fallback_models', [])
        if not isinstance(fallback_models, list):
            fallback_models = []
        self.models = [m for i, m in enumerate([primary_model, *fallback_models]) if m and m not in [primary_model, *fallback_models][:i]]
        self.model = self.models[0]
        self.temperature = config['script']['temperature']
        self.max_tokens = config['script']['max_tokens']
        self.logger = get_logger()
        self.provider = config.get("script", {}).get("provider", "gemini")

        self._sdk = None
        self._sdk_types = None
        self._client = None

    def _ensure_genai_client(self) -> None:
        if self.provider != "gemini":
            raise ValueError(f"Unsupported script provider '{self.provider}'. Expected 'gemini'.")

        if self._client is not None:
            return

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for Gemini script generation. "
                "Install with: pip install google-genai"
            ) from exc

        self._sdk = genai
        self._sdk_types = types
        self._client = genai.Client(api_key=self.api_key)

    def _extract_genai_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        candidates = getattr(response, "candidates", None) or []
        extracted = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if content is None:
                continue
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    extracted.append(part_text.strip())

        return "\n".join(extracted).strip()

    # Backward-compatible name used in tests and older code paths.
    def _extract_text_content(self, response: Any) -> str:
        return self._extract_genai_text(response)

    def _response_debug_summary(self, response: Any) -> str:
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return "no candidates in response"

        first = candidates[0]
        finish_reason = getattr(first, "finish_reason", None)
        finish_message = getattr(first, "finish_message", None)

        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", None)
            completion_tokens = getattr(usage, "candidates_token_count", None)
            total_tokens = getattr(usage, "total_token_count", None)
            usage_str = (
                f"usage(prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens})"
            )
        else:
            usage_str = "usage=unknown"

        return f"finish_reason={finish_reason}, finish_message={finish_message}, {usage_str}"

    def _generate_with_gemini(self, prompt: str, model: Optional[str] = None) -> str:
        self._ensure_genai_client()
        gen_cfg = self._sdk_types.GenerateContentConfig(
            system_instruction="You are a viral short-form content scriptwriter specializing in AI and tech topics.",
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )

        response = self._client.models.generate_content(
            model=model or self.model,
            contents=prompt,
            config=gen_cfg,
        )
        return self._extract_genai_text(response), response

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

    def generate(
        self,
        topic: str,
        details: Optional[str] = None,
        style: str = "solo",
        model: Optional[str] = None,
    ) -> str:
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
            return self.generate_solo_script(topic, details, model=model)
        elif style == "dialogue":
            script_dict = self.generate_dialogue_script(topic, details, model=model)
            # Convert dict back to formatted text for TTS
            return self._format_dialogue(script_dict)
        else:
            raise ValueError(f"Invalid style: {style}. Must be 'solo' or 'dialogue'")

    def generate_solo_script(
        self,
        topic: str,
        details: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
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
            self.logger.debug("Prompt sent to model %s: %s", model or self.model, prompt)
            script, response = self._generate_with_gemini(prompt=prompt, model=model)
            if not script:
                raise ValueError(
                    "Empty script response from model "
                    f"({self._response_debug_summary(response)})"
                )
            return script

        except Exception as e:
            raise Exception(f"Script generation failed: {str(e)}")

    def generate_dialogue_script(
        self,
        topic: str,
        details: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, list]:
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
            self.logger.debug("Prompt sent to model %s: %s", model or self.model, prompt)
            script_text, response = self._generate_with_gemini(prompt=prompt, model=model)
            if not script_text:
                raise ValueError(
                    "Empty dialogue response from model "
                    f"({self._response_debug_summary(response)})"
                )
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

    def expand_short_script(
        self,
        topic: str,
        short_script: str,
        style: str,
        min_words: int,
        max_words: int,
        details: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Expand an undersized script while preserving style and format.
        """
        if style == "dialogue":
            prompt = (
                "You are rewriting a short-form dialogue script.\n"
                f"Topic: {topic}\n"
                f"Target length: {min_words}-{max_words} words\n"
                "Rules:\n"
                "- Keep exactly two speakers labelled A and B\n"
                "- Output ONLY dialogue lines in strict alternating format:\n"
                "  A: ...\n"
                "  B: ...\n"
                "- Write 10-14 lines total\n"
                "- Keep each A line short (5-10 words)\n"
                "- Keep each B line informative (10-16 words)\n"
                "- No scene descriptions, no bullets, no extra text\n\n"
                f"Additional details:\n{details or ''}\n\n"
                f"Script to expand:\n{short_script}\n\n"
                "Rewrite now."
            )
        else:
            prompt = (
                "You are rewriting a short-form narrator script.\n"
                f"Topic: {topic}\n"
                f"Target length: {min_words}-{max_words} words\n"
                "Rules:\n"
                "- Output ONLY spoken lines\n"
                "- Use 10-15 short lines\n"
                "- No bullets, no scene descriptions\n\n"
                f"Additional details:\n{details or ''}\n\n"
                f"Script to expand:\n{short_script}\n\n"
                "Rewrite now."
            )

        try:
            self.logger.debug("Prompt sent to model %s: %s", model or self.model, prompt)
            expanded, response = self._generate_with_gemini(prompt=prompt, model=model)
            if not expanded:
                raise ValueError(
                    "Empty expansion response from model "
                    f"({self._response_debug_summary(response)})"
                )

            if style == "dialogue":
                parsed = self.parse_dialogue(self._clean_script_response(expanded))
                if not parsed:
                    raise ValueError("Expanded dialogue could not be parsed")
                return self._format_dialogue(parsed)

            return expanded
        except Exception as e:
            raise Exception(f"Script expansion failed: {str(e)}")

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
            if re.match(
                r'(\[[A-Za-z][A-Za-z0-9\s_-]*\]\s*.+|\([A-Za-z][A-Za-z0-9\s_-]*\)\s*.+|[A-Za-z][A-Za-z0-9\s_-]*:\s*.+)',
                line,
            ):
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
            match = re.match(r'\[([A-Za-z][A-Za-z0-9\s_-]*)\]\s*(.+)', line)
            if not match:
                # Try to match CHARACTER: format (including single letters)
                match = re.match(r'([A-Za-z][A-Za-z0-9\s_-]*):\s*(.+)', line)
            if not match:
                # Try to match (CHARACTER) format (including single letters)
                match = re.match(r'\(([A-Za-z][A-Za-z0-9\s_-]*)\)\s*(.+)', line)

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
