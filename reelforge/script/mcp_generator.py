"""
MCP-based script generator with screenshot markers.
"""
import logging
import re
from typing import Any, Dict, Optional

from reelforge.script.types import ScriptWithMarkers, parse_mcp_output
from reelforge.script.templates.prompts import MCP_DIALOGUE_PROMPT

logger = logging.getLogger(__name__)


class MCPScriptGenerator:
    """
    Script generator using MCP prompt with OpenAI SDK.

    Generates dialogue scripts with embedded [SHOW:S#] markers for screenshot placement.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MCP generator.

        Args:
            config: Configuration dictionary from config.yaml
        """
        self.config = config
        self.script_config = config.get("script", {})

        # Model configuration
        self.openai_model = self.script_config.get("model", "gpt-4o-mini")
        self.temperature = self.script_config.get("temperature", 0.7)
        self.max_tokens = self.script_config.get("max_tokens", 1000)

        # Compatibility with orchestrator interface
        self.model = self.openai_model
        self.models = [self.model] + self.script_config.get("fallback_models", [])

    def generate(
        self,
        topic: str,
        details: Optional[str] = None,
        style: str = "dialogue",
        websites: Optional[str] = None,
        length: str = "45s",
        profanity: str = "none",
        model: Optional[str] = None,
    ) -> ScriptWithMarkers:
        """
        Generate script with screenshot markers.

        Args:
            topic: Main topic for the reel
            details: Optional additional context
            style: Script style (only "dialogue" supported for MCP)
            websites: Optional comma-separated list of websites/tools to feature
            length: Target length (30s, 45s, 60s)
            profanity: Profanity level (none, light, allowed)
            model: Optional model override

        Returns:
            ScriptWithMarkers with dialogue, keyword map, and marker positions

        Raises:
            RuntimeError: If OpenAI API fails
        """
        if style != "dialogue":
            logger.warning("MCP generator only supports dialogue style, got: %s", style)
            # Continue with dialogue mode anyway

        logger.info("Generating script via direct OpenAI with MCP prompt")
        return self._generate(topic, details, websites, length, profanity, model)

    def _generate(
        self,
        topic: str,
        details: Optional[str],
        websites: Optional[str],
        length: str,
        profanity: str,
        model: Optional[str] = None,
    ) -> ScriptWithMarkers:
        """
        Use OpenAI SDK with embedded MCP prompt.

        Args:
            topic: Main topic
            details: Optional additional context
            websites: Optional comma-separated websites
            length: Target length
            profanity: Profanity level
            model: Optional model override

        Returns:
            Parsed ScriptWithMarkers

        Raises:
            RuntimeError: If OpenAI API fails
        """
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai not installed. Install: pip install openai"
            ) from exc

        # Get API key
        api_key = self.config.get("openai_api_key") or self.config.get("gemini_api_key")
        if not api_key:
            raise RuntimeError(
                "OpenAI API key not found. Set in config.yaml or OPENAI_API_KEY env var"
            )

        # Build prompt with hook library
        import random
        from reelforge.script.hooks import get_random_hooks, get_random_ctas

        # Select random hook category and generate examples
        hook_category = random.choice(["curiosity_gap", "negative_hook", "bold_claim", "controversy"])
        hook_examples = get_random_hooks(hook_category, 3)
        hook_examples_text = "\n".join(f"- {h}" for h in hook_examples)

        # Generate CTA examples
        cta_examples = get_random_ctas("comment_bait", 2)
        cta_examples_text = "\n".join(f"- {c}" for c in cta_examples)

        websites_instruction = ""
        if websites:
            websites_instruction = f"REQUIRED: Must mention and show these specific websites/tools: {websites}"

        # Use upgraded prompt with hook library
        from reelforge.script.templates.prompts import MCP_DIALOGUE_PROMPT_V2

        prompt_text = MCP_DIALOGUE_PROMPT_V2.format(
            length=length,
            topic=topic,
            websites_instruction=websites_instruction,
            profanity=profanity,
            hook_examples=hook_examples_text,
            cta_examples=cta_examples_text,
        )

        if details:
            prompt_text += f"\n\nAdditional context:\n{details}"

        # Call OpenAI (use provided model or default)
        model_to_use = model or self.openai_model
        logger.debug("Calling OpenAI API with model: %s", model_to_use)

        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=model_to_use,
            messages=[
                {"role": "system", "content": "You write viral short-form dialogue scripts with strict formatting."},
                {"role": "user", "content": prompt_text},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        choices = getattr(response, "choices", None) or []
        content = ""
        if choices:
            message = getattr(choices[0], "message", None)
            content = (getattr(message, "content", None) or "").strip()

        if not response or not content:
            raise RuntimeError(
                "OpenAI returned empty response. This may be due to:\n"
                "1. API rate limiting\n"
                "2. Prompt safety filters\n"
                "3. Network issues\n"
                "Try again or check your API quota."
            )

        script_text = content

        if len(script_text) < 50:
            raise RuntimeError(
                f"OpenAI returned very short response ({len(script_text)} chars): {script_text[:100]}\n"
                "This usually indicates a prompt/API issue."
            )

        # Remove markdown code blocks if present
        if script_text.startswith("```"):
            lines = script_text.split('\n')
            script_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else script_text

        # Parse output
        script_with_markers = parse_mcp_output(script_text)
        logger.info("OpenAI generated script with %d markers", len(script_with_markers.keyword_map))

        return script_with_markers

    def parse_dialogue(self, script_text: str) -> Dict[str, list]:
        """
        Parse dialogue script into character lines.

        Args:
            script_text: Script text (may contain [SHOW:S#] markers)

        Returns:
            Dictionary mapping character names to their lines
        """
        dialogue = {}
        lines = script_text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('REEL TITLE:'):
                continue

            # Try multiple formats: A:, [A], (A)
            patterns = [
                r'^([A-Za-z]):\s*(.+)$',  # A: text
                r'^\[([A-Za-z])\]\s*(.+)$',  # [A] text
                r'^\(([A-Za-z])\)\s*(.+)$',  # (A) text
            ]

            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    char, text = match.groups()
                    if char not in dialogue:
                        dialogue[char] = []
                    dialogue[char].append(text)
                    break

        return dialogue

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
        Expand short script while preserving markers.

        Args:
            topic: Topic/subject
            short_script: Script to expand
            style: "dialogue" or "solo"
            min_words: Minimum word count
            max_words: Maximum word count
            details: Optional additional context
            model: Optional model override

        Returns:
            Expanded script text
        """
        # For MCP mode, we regenerate with stricter word count constraints
        # This preserves markers better than trying to expand existing text

        logger.info("Expanding short script by regenerating with stricter constraints")

        # Add word count constraint to details
        constraint = f"CRITICAL: Script must be between {min_words} and {max_words} words. Previous attempt was too short."
        enhanced_details = f"{details or ''}\n{constraint}".strip()

        # Regenerate (this will return ScriptWithMarkers)
        result = self.generate(
            topic=topic,
            details=enhanced_details,
            style=style,
            model=model,
        )

        # Return dialogue text (markers are preserved in the ScriptWithMarkers object)
        return result.dialogue_text
