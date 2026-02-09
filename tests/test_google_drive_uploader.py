from pathlib import Path

import pytest

from reelforge.integrations.google_drive.uploader import GoogleDriveUploader, _extract_folder_id


def test_extract_folder_id_from_url():
    value = "https://drive.google.com/drive/folders/1rw-msgfUfL1K8PFEZs4eKvKKE4bmWQ82"
    assert _extract_folder_id(value) == "1rw-msgfUfL1K8PFEZs4eKvKKE4bmWQ82"


def test_extract_folder_id_from_plain_id():
    assert _extract_folder_id("abcDEF123_-") == "abcDEF123_-"


def test_extract_folder_id_raises_for_invalid():
    with pytest.raises(ValueError):
        _extract_folder_id("https://drive.google.com/drive/u/0/my-drive")


def test_date_parts_use_run_timestamp_when_present():
    run_dir = Path("output/run_20260208_153000")
    assert GoogleDriveUploader._date_parts_for_run(run_dir) == ("2026", "02", "08")


def test_date_parts_fallback_when_no_timestamp():
    run_dir = Path("output/custom-name")
    year, month, day = GoogleDriveUploader._date_parts_for_run(run_dir)
    assert len(year) == 4
    assert len(month) == 2
    assert len(day) == 2


def test_from_config_reads_drive_settings():
    cfg = {
        "integrations": {
            "google_drive": {
                "parent_folder_id": "my_folder_123",
                "oauth": {
                    "token_path": ".secrets/token.json",
                    "client_secret_path": ".secrets/client_secret.json",
                },
                "retries": {"max_attempts": 4, "backoff_seconds": 1.5},
            }
        }
    }
    uploader = GoogleDriveUploader.from_config(cfg)
    assert uploader.parent_folder_id == "my_folder_123"
    assert uploader.token_path == Path(".secrets/token.json")
    assert uploader.client_secret_path == Path(".secrets/client_secret.json")
    assert uploader.max_attempts == 4
    assert uploader.retry_backoff_seconds == 1.5
