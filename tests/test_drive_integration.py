from pathlib import Path
import sys
import types

# Stub moviepy for lightweight test environments before importing main.
moviepy_stub = types.SimpleNamespace(AudioFileClip=object)
sys.modules.setdefault("moviepy", moviepy_stub)
sys.modules.setdefault("moviepy.editor", moviepy_stub)

from main import _drive_upload_defaults, _upload_artifacts_to_drive


def test_drive_upload_defaults_with_parsable_folder_id():
    cfg = {
        "integrations": {
            "google_drive": {
                "parent_folder_id": "https://drive.google.com/drive/folders/abc123_XYZ",
            }
        }
    }
    result = _drive_upload_defaults(cfg)
    assert result["drive_upload_status"] == "skipped"
    assert result["drive_parent_folder_id"] == "abc123_XYZ"


def test_upload_artifacts_to_drive_returns_skipped_when_disabled():
    cfg = {"integrations": {"google_drive": {"enabled": False, "parent_folder_id": "folder123"}}}

    class Logger:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

    result = _upload_artifacts_to_drive(
        cfg=cfg,
        logger=Logger(),
        run_dir=Path("output/run_20260208_153000"),
        video_path=Path("output/video.mp4"),
        metadata_path=Path("output/metadata.json"),
    )
    assert result["drive_upload_status"] == "skipped"


def test_upload_artifacts_to_drive_warn_policy_on_failure(monkeypatch):
    cfg = {
        "integrations": {
            "google_drive": {
                "enabled": True,
                "parent_folder_id": "folder123",
                "failure_policy": "warn",
            }
        }
    }

    class Logger:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

    class StubUploader:
        parent_folder_id = "folder123"

        @classmethod
        def from_config(cls, _cfg):
            return cls()

        def upload_run_artifacts(self, **_kwargs):
            raise RuntimeError("upload failed")

    import reelforge.integrations.google_drive.uploader as gdu

    monkeypatch.setattr("main._drive_upload_defaults", lambda _cfg: {
        "drive_upload_status": "skipped",
        "drive_parent_folder_id": "folder123",
        "drive_run_folder_id": None,
        "drive_run_folder_path": None,
        "drive_video_file_id": None,
        "drive_video_link": None,
        "drive_metadata_file_id": None,
        "drive_metadata_link": None,
        "drive_upload_error": None,
    })
    monkeypatch.setattr(gdu, "GoogleDriveUploader", StubUploader)

    result = _upload_artifacts_to_drive(
        cfg=cfg,
        logger=Logger(),
        run_dir=Path("output/run_20260208_153000"),
        video_path=Path("output/video.mp4"),
        metadata_path=Path("output/metadata.json"),
    )
    assert result["drive_upload_status"] == "failed"
    assert "upload failed" in result["drive_upload_error"]


def test_upload_artifacts_to_drive_fail_policy_raises(monkeypatch):
    cfg = {
        "integrations": {
            "google_drive": {
                "enabled": True,
                "parent_folder_id": "folder123",
                "failure_policy": "fail",
            }
        }
    }

    class Logger:
        def info(self, *_args, **_kwargs):
            pass

        def warning(self, *_args, **_kwargs):
            pass

    class StubUploader:
        parent_folder_id = "folder123"

        @classmethod
        def from_config(cls, _cfg):
            return cls()

        def upload_run_artifacts(self, **_kwargs):
            raise RuntimeError("upload failed")

    import reelforge.integrations.google_drive.uploader as gdu

    monkeypatch.setattr(gdu, "GoogleDriveUploader", StubUploader)
    try:
        _upload_artifacts_to_drive(
            cfg=cfg,
            logger=Logger(),
            run_dir=Path("output/run_20260208_153000"),
            video_path=Path("output/video.mp4"),
            metadata_path=Path("output/metadata.json"),
        )
        assert False, "Expected RuntimeError for failure_policy=fail"
    except RuntimeError as exc:
        assert "Google Drive upload failed" in str(exc)
