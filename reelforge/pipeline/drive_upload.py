"""Google Drive upload helpers used by pipeline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional


def _drive_upload_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    from reelforge.integrations.google_drive.uploader import default_drive_metadata

    parent = cfg.get("integrations", {}).get("google_drive", {}).get("parent_folder_id")
    return default_drive_metadata(parent)


def _upload_artifacts_to_drive(
    *,
    cfg: Dict[str, Any],
    logger,
    run_dir: Path,
    video_path: Path,
    metadata_path: Path,
    defaults_factory: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    from reelforge.integrations.google_drive.uploader import GoogleDriveUploader

    drive_cfg = cfg.get("integrations", {}).get("google_drive", {})
    defaults_builder = defaults_factory or _drive_upload_defaults
    defaults = defaults_builder(cfg)
    if not drive_cfg.get("enabled", False):
        return defaults

    upload_files = drive_cfg.get("upload_files", ["video", "metadata"])
    failure_policy = str(drive_cfg.get("failure_policy", "warn")).strip().lower()
    should_fail_on_error = failure_policy == "fail"

    try:
        uploader = GoogleDriveUploader.from_config(cfg)
        logger.info(
            "Uploading run artifacts to Google Drive parent folder %s",
            uploader.parent_folder_id,
        )
        result = uploader.upload_run_artifacts(
            run_dir=run_dir,
            run_folder_name=run_dir.name,
            video_path=video_path,
            metadata_path=metadata_path,
            upload_files=upload_files,
        )
        logger.info(
            "Drive upload success. Folder=%s VideoID=%s MetadataID=%s",
            result.run_folder_path,
            result.video_file_id,
            result.metadata_file_id,
        )
        return GoogleDriveUploader.to_metadata_dict(result)
    except Exception as exc:
        defaults["drive_upload_status"] = "failed"
        defaults["drive_upload_error"] = str(exc)
        logger.warning("Google Drive upload failed: %s", exc)
        if should_fail_on_error:
            raise RuntimeError(f"Google Drive upload failed: {exc}") from exc
        return defaults
