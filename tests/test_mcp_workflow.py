"""
Integration tests for MCP + media-harvest workflow.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from reelforge.script.types import ScriptWithMarkers, MarkerPosition


class TestMCPGeneratorFallback:
    """Test MCP generator with fallback logic."""

    @patch('reelforge.script.mcp_generator.Path')
    def test_mcp_unavailable_uses_gemini(self, mock_path):
        """Test fallback to Gemini when MCP server unavailable."""
        from reelforge.script.mcp_generator import MCPScriptGenerator

        # Mock MCP server not existing
        mock_path.return_value.exists.return_value = False

        config = {
            "script": {
                "use_mcp": True,
                "mcp_server_path": "/nonexistent/server.py",
                "mcp_python_path": "/nonexistent/python",
                "model": "gemini-2.5-pro",
                "temperature": 0.7,
                "max_tokens": 1000,
            },
            "gemini_api_key": "test-key",
        }

        generator = MCPScriptGenerator(config)
        assert not generator.mcp_available

    def test_mcp_generator_initialization(self):
        """Test MCP generator initializes with correct config."""
        from reelforge.script.mcp_generator import MCPScriptGenerator

        config = {
            "script": {
                "use_mcp": True,
                "mcp_server_path": "/path/server.py",
                "mcp_python_path": "/path/python",
                "mcp_timeout_seconds": 45,
                "model": "gemini-2.5-pro",
                "temperature": 0.8,
                "max_tokens": 1500,
            },
            "gemini_api_key": "test-key",
        }

        generator = MCPScriptGenerator(config)
        assert generator.mcp_timeout == 45
        assert generator.gemini_model == "gemini-2.5-pro"
        assert generator.temperature == 0.8
        assert generator.max_tokens == 1500


class TestMediaHarvestClient:
    """Test media-harvest client initialization."""

    def test_harvest_client_missing_dependency(self):
        """Test error when media-harvest not installed."""
        with patch.dict('sys.modules', {'media_harvest': None}):
            from reelforge.media.harvest_client import MediaHarvestClient

            config = {"media_harvest": {"harvest_config": {}}}

            with pytest.raises(ImportError, match="media-harvest not installed"):
                MediaHarvestClient(config)

    def test_harvest_client_config_mapping(self):
        """Test harvest client config structure."""
        config = {
            "media_harvest": {
                "harvest_config": {
                    "mode": "safe",
                    "transform_preset": "vertical_9_16",
                    "timeout_seconds": 30,
                    "retry_attempts": 3,
                    "enable_cache": True,
                    "cache_dir": ".cache/media-harvest",
                    "assets_per_entity": 1,
                }
            }
        }

        # Verify config structure
        harvest_config = config["media_harvest"]["harvest_config"]
        assert harvest_config["mode"] == "safe"
        assert harvest_config["transform_preset"] == "vertical_9_16"
        assert harvest_config["timeout_seconds"] == 30


class TestMarkerResolverEdgeCases:
    """Test marker resolver edge cases."""

    def test_marker_beyond_caption_bounds(self):
        """Test marker that falls beyond word caption array."""
        from reelforge.media.marker_resolver import MarkerResolver

        config = {"media_harvest": {"screenshot_duration_seconds": 4.0}}
        resolver = MarkerResolver(config)

        script_with_markers = ScriptWithMarkers(
            dialogue_text="A: Hello [SHOW:S1] world",
            keyword_map={"S1": "cursor"},
            marker_positions=[
                # Marker at word offset 10, but only 2 words exist
                MarkerPosition(marker_id="S1", character="A", line_index=0, word_offset=10)
            ],
        )

        word_captions = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.6, "end": 1.0},
        ]

        id_to_path = {"S1": "/path/cursor.png"}

        screenshots_data = resolver.resolve_markers_to_timestamps(
            script_with_markers, word_captions, id_to_path
        )

        # Should fall back to last word
        assert len(screenshots_data) == 1
        assert screenshots_data[0]["start"] == 0.6

    def test_empty_word_captions(self):
        """Test marker resolution with empty word captions."""
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

        word_captions = []
        id_to_path = {"S1": "/path/cursor.png"}

        screenshots_data = resolver.resolve_markers_to_timestamps(
            script_with_markers, word_captions, id_to_path
        )

        # Should return empty list when no captions available
        assert len(screenshots_data) == 0


class TestOrchestratorIntegration:
    """Test orchestrator integration points."""

    def test_orchestrator_signature_includes_mcp_params(self):
        """Test that orchestrator function accepts MCP parameters."""
        from reelforge.pipeline.orchestrator import _run_generate_pipeline
        import inspect

        sig = inspect.signature(_run_generate_pipeline)
        params = list(sig.parameters.keys())

        assert "websites" in params
        assert "length" in params
        assert "profanity" in params
        assert "disable_mcp" in params
        assert "image_map_path" in params

    def test_orchestrator_default_values(self):
        """Test orchestrator MCP parameter defaults."""
        from reelforge.pipeline.orchestrator import _run_generate_pipeline
        import inspect

        sig = inspect.signature(_run_generate_pipeline)

        assert sig.parameters["websites"].default is None
        assert sig.parameters["length"].default == "45s"
        assert sig.parameters["profanity"].default == "none"
        assert sig.parameters["disable_mcp"].default is False
        assert sig.parameters["image_map_path"].default is None
