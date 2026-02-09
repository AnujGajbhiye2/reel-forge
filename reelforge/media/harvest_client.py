"""
Media-harvest client for fetching screenshots and images.
"""
import logging
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlencode
import json
import urllib.request

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
        self.imagery_cfg = config.get("imagery", {})
        self.min_quality_score = float(self.imagery_cfg.get("min_quality_score", 0.7))
        self.last_fetch_report: Dict[str, Dict[str, Any]] = {}

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

        self.last_fetch_report = {}

        try:
            # Call media-harvest
            result = self.harvest(prompt, self.harvest_config)

            if not result or not result.assets:
                logger.warning("Media-harvest returned no assets")
                return {}

            # Map assets back to marker IDs
            id_to_path: Dict[str, str] = {}
            for marker_id, keyword in keyword_map.items():
                # Find matching assets (case-insensitive match on entity name)
                matching_assets = [
                    asset for asset in result.assets
                    if asset.entity_name and asset.entity_name.lower() == keyword.lower()
                ]

                if matching_assets:
                    # Pick best asset (highest score)
                    best_asset = max(matching_assets, key=lambda a: a.score if a.score else 0)
                    score = float(best_asset.score or 0.0)
                    if score >= self.min_quality_score:
                        id_to_path[marker_id] = str(best_asset.local_path)
                        self.last_fetch_report[marker_id] = {
                            "path": str(best_asset.local_path),
                            "source": "media_harvest",
                            "source_url": None,
                            "score": score,
                            "keyword": keyword,
                        }
                        logger.info("Mapped %s -> %s (score: %.2f)", marker_id, keyword, score)
                    else:
                        logger.warning(
                            "Low-quality asset for %s (%s) with score %.2f < %.2f; trying fallback",
                            marker_id, keyword, score, self.min_quality_score
                        )
                else:
                    logger.warning("No asset found for %s (%s)", marker_id, keyword)

            # Free fallback for unresolved markers via Wikimedia Commons.
            unresolved = [marker_id for marker_id in keyword_map if marker_id not in id_to_path]
            for marker_id in unresolved:
                keyword = keyword_map[marker_id]
                fallback = self._download_wikimedia_image(keyword=keyword, output_dir=output_dir, marker_id=marker_id)
                if fallback:
                    id_to_path[marker_id] = fallback["path"]
                    self.last_fetch_report[marker_id] = {
                        "path": fallback["path"],
                        "source": "wikimedia_commons",
                        "source_url": fallback["source_url"],
                        "score": None,
                        "keyword": keyword,
                    }
                    logger.info("Fallback mapped %s -> %s (wikimedia)", marker_id, keyword)
                else:
                    self.last_fetch_report[marker_id] = {
                        "path": None,
                        "source": "missing",
                        "source_url": None,
                        "score": None,
                        "keyword": keyword,
                    }

            logger.info("Successfully fetched %d/%d screenshots", len(id_to_path), len(keyword_map))
            return id_to_path

        except Exception as exc:
            logger.error("Media-harvest failed: %s", exc)
            # Re-raise to allow orchestrator to handle partial results
            raise

    def _download_wikimedia_image(
        self,
        *,
        keyword: str,
        output_dir: Path,
        marker_id: str,
    ) -> Dict[str, str] | None:
        """Download first suitable Wikimedia Commons image for keyword."""
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": keyword,
            "gsrnamespace": 6,
            "gsrlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url|size",
        }
        endpoint = "https://commons.wikimedia.org/w/api.php?" + urlencode(params)
        try:
            with urllib.request.urlopen(endpoint, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("Wikimedia lookup failed for '%s': %s", keyword, exc)
            return None

        pages = (payload.get("query") or {}).get("pages") or {}
        candidates = []
        for page in pages.values():
            info_list = page.get("imageinfo") or []
            if not info_list:
                continue
            info = info_list[0]
            width = int(info.get("width") or 0)
            height = int(info.get("height") or 0)
            if width < 640 or height < 640:
                continue
            url = info.get("url")
            if not url:
                continue
            candidates.append((width * height, url))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        image_url = candidates[0][1]
        extension = Path(image_url.split("?")[0]).suffix.lower() or ".jpg"
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            extension = ".jpg"

        destination_dir = Path(output_dir) / "screenshots"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{marker_id.lower()}_wikimedia{extension}"
        try:
            urllib.request.urlretrieve(image_url, destination)
        except Exception as exc:
            logger.warning("Wikimedia download failed for '%s': %s", keyword, exc)
            return None

        return {"path": str(destination), "source_url": image_url}
