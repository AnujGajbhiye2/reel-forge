"""
Tests for script generation module.
"""

import pytest
from reelforge.script_generator import ScriptGenerator


class TestScriptGenerator:
    """Test script generation functionality."""

    def test_init_without_api_key(self):
        """Test that ScriptGenerator raises error without API key."""
        config = {
            'gemini_api_key': 'YOUR_GEMINI_API_KEY_HERE',
            'script': {
                'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
                'model': 'gemini-2.0-flash',
                'temperature': 0.7,
                'max_tokens': 1000
            }
        }

        with pytest.raises(ValueError, match="Gemini API key not configured"):
            ScriptGenerator(config)

    def test_init_with_api_key(self):
        """Test that ScriptGenerator initializes with valid API key."""
        config = {
            'gemini_api_key': 'test-api-key-123',
            'script': {
                'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
                'model': 'gemini-2.0-flash',
                'temperature': 0.7,
                'max_tokens': 1000
            }
        }

        generator = ScriptGenerator(config)
        assert generator.api_key == 'test-api-key-123'
        assert generator.model == 'gemini-2.0-flash'
        assert generator.temperature == 0.7

    def test_parse_dialogue_with_brackets(self):
        """Test parsing dialogue with [CHARACTER] format."""
        config = {
            'gemini_api_key': 'test-key',
            'script': {
                'base_url': 'https://test.com',
                'model': 'test',
                'temperature': 0.7,
                'max_tokens': 1000
            }
        }

        generator = ScriptGenerator(config)

        script_text = """
[PETER] Why is everyone talking about this AI tool?
[STEWIE] Because it generates images faster than Midjourney and it's completely free.
[PETER] Wait, free? How good can it be?
[STEWIE] Actually better than most paid tools. It uses the latest diffusion models.
        """

        dialogue = generator.parse_dialogue(script_text)

        assert 'PETER' in dialogue
        assert 'STEWIE' in dialogue
        assert len(dialogue['PETER']) == 2
        assert len(dialogue['STEWIE']) == 2
        assert 'Why is everyone talking' in dialogue['PETER'][0]
        assert 'faster than Midjourney' in dialogue['STEWIE'][0]

    def test_parse_dialogue_with_colons_only(self):
        """Test parsing dialogue with CHARACTER: format."""
        config = {
            'gemini_api_key': 'test-key',
            'script': {
                'base_url': 'https://test.com',
                'model': 'test',
                'temperature': 0.7,
                'max_tokens': 1000
            }
        }

        generator = ScriptGenerator(config)

        script_text = """
PETER: This AI can code an entire app?
STEWIE: In under five minutes. Just describe what you want.
PETER: That's insane!
        """

        dialogue = generator.parse_dialogue(script_text)

        assert 'PETER' in dialogue
        assert 'STEWIE' in dialogue
        assert 'code an entire app' in dialogue['PETER'][0]
        assert 'five minutes' in dialogue['STEWIE'][0]

    def test_format_dialogue(self):
        """Test formatting dialogue dict back to text."""
        config = {
            'gemini_api_key': 'test-key',
            'script': {
                'base_url': 'https://test.com',
                'model': 'test',
                'temperature': 0.7,
                'max_tokens': 1000
            }
        }

        generator = ScriptGenerator(config)

        dialogue = {
            'PETER': ['Line one', 'Line three'],
            'STEWIE': ['Line two', 'Line four']
        }

        formatted = generator._format_dialogue(dialogue)

        assert 'PETER: Line one' in formatted
        assert 'STEWIE: Line two' in formatted
        assert 'PETER: Line three' in formatted
        assert 'STEWIE: Line four' in formatted


# Integration test (requires valid API key)
@pytest.mark.integration
class TestScriptGeneratorIntegration:
    """Integration tests that require a valid API key."""

    def test_generate_solo_script(self):
        """Test solo script generation with real API."""
        from reelforge.utils import load_config

        try:
            config = load_config('config.yaml')

            # Skip if API key not configured
            if config.get('gemini_api_key') == 'YOUR_GEMINI_API_KEY_HERE':
                pytest.skip("Gemini API key not configured")

            generator = ScriptGenerator(config)
            script = generator.generate_solo_script(
                topic="ChatGPT-4",
                details="The latest AI model from OpenAI"
            )

            assert len(script) > 100
            assert isinstance(script, str)

        except FileNotFoundError:
            pytest.skip("config.yaml not found")

    def test_generate_dialogue_script(self):
        """Test dialogue script generation with real API."""
        from reelforge.utils import load_config

        try:
            config = load_config('config.yaml')

            # Skip if API key not configured
            if config.get('gemini_api_key') == 'YOUR_GEMINI_API_KEY_HERE':
                pytest.skip("Gemini API key not configured")

            generator = ScriptGenerator(config)
            dialogue = generator.generate_dialogue_script(
                topic="Cursor IDE",
                details="AI-powered code editor"
            )

            assert isinstance(dialogue, dict)
            assert len(dialogue) > 0

        except FileNotFoundError:
            pytest.skip("config.yaml not found")
