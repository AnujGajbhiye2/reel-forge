"""
Media-harvest client for fetching screenshots and images.
"""
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class MediaHarvestClient:
    """
    Bridge to media-harvest project for screenshot acquisition.

    Fetches high-quality screenshots/images based on keyword queries.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize media-harvest client.

        Args:
            config: Configuration dictionary from config.yaml

        Raises:
            ImportError: If media-harvest is not installed
        """
        self.config = config
        self.harvest_config_dict = config.get("media_harvest", {}).get("harvest_config", {})

        # Verify media-harvest is installed
        try:
            from media_harvest import harvest, HarvestConfig, Mode
            self.harvest = harvest
            self.HarvestConfig = HarvestConfig
            self.Mode = Mode
        except ImportError as exc:
            raise ImportError(
                "media-harvest not installed. Install from: "
                "cd /home/anuj/projects/screen-scraper && pip install -e ."
            ) from exc

        self.harvest_config = self._build_harvest_config()

    def _build_harvest_config(self):
        """Build HarvestConfig from YAML settings."""
        # Map mode string to enum
        mode_str = self.harvest_config_dict.get("mode", "safe")
        mode_map = {
            "safe": self.Mode.SAFE,
            "open": self.Mode.OPEN,
            "strict": self.Mode.STRICT,
        }
        mode = mode_map.get(mode_str, self.Mode.SAFE)

        # Get other config values
        transform_preset = self.harvest_config_dict.get("transform_preset", "vertical_9_16")
        timeout_seconds = self.harvest_config_dict.get("timeout_seconds", 30)
        retry_attempts = self.harvest_config_dict.get("retry_attempts", 3)
        enable_cache = self.harvest_config_dict.get("enable_cache", True)
        cache_dir = self.harvest_config_dict.get("cache_dir", ".cache/media-harvest")
        assets_per_entity = self.harvest_config_dict.get("assets_per_entity", 1)

        return self.HarvestConfig(
            mode=mode,
            transform_preset=transform_preset,
            timeout_seconds=timeout_seconds,
            retry_attempts=retry_attempts,
            enable_cache=enable_cache,
            cache_dir=Path(cache_dir),
            assets_per_entity=assets_per_entity,
        )

    def fetch_screenshots(
        self,
        keyword_map: Dict[str, str],
        output_dir: Path,
    ) -> Dict[str, str]:
        """
        Fetch screenshots for keywords.

        Args:
            keyword_map: Mapping of marker IDs to keywords
                Example: {"S1": "cursor", "S2": "codex"}
            output_dir: Directory for saving screenshots

        Returns:
            Mapping of marker IDs to local file paths:
            {"S1": "/path/to/cursor.png", "S2": "/path/to/codex.png"}

        Raises:
            Exception: If media-harvest fails completely (no partial results)
        """
        if not keyword_map:
            logger.info("No keywords to fetch")
            return {}

        # Build query from keywords
        keyword_list = list(keyword_map.values())
        prompt = ", ".join(keyword_list)

        logger.info("Fetching screenshots for: %s", prompt)

        try:
            # Call media-harvest
            result = self.harvest(prompt, self.harvest_config)

            if not result or not result.assets:
                logger.warning("Media-harvest returned no assets")
                return {}

            # Map assets back to marker IDs
            id_to_path = {}
            for marker_id, keyword in keyword_map.items():
                # Find matching assets (case-insensitive match on entity name)
                matching_assets = [
                    asset for asset in result.assets
                    if asset.entity_name and asset.entity_name.lower() == keyword.lower()
                ]

                if matching_assets:
                    # Pick best asset (highest score)
                    best_asset = max(matching_assets, key=lambda a: a.score if a.score else 0)
                    id_to_path[marker_id] = str(best_asset.local_path)
                    logger.info("Mapped %s -> %s (score: %.2f)",
                               marker_id, keyword, best_asset.score or 0)
                else:
                    logger.warning("No asset found for %s (%s)", marker_id, keyword)

            logger.info("Successfully fetched %d/%d screenshots", len(id_to_path), len(keyword_map))
            return id_to_path

        except Exception as exc:
            logger.error("Media-harvest failed: %s", exc)
            # Re-raise to allow orchestrator to handle partial results
            raise
