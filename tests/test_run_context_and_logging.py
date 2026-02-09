from pathlib import Path

from reelforge.core.logging import setup_logging
from reelforge.core.run_context import create_run_paths, slugify_name


def test_slugify_name():
    assert slugify_name("Top 5 Software Engineering Books!") == "top-5-software-engineering-books"


def test_create_run_paths(tmp_path: Path):
    run = create_run_paths(output_dir=str(tmp_path), run_name="My Reel")

    assert run.run_dir.exists()
    assert run.run_dir.parent == tmp_path
    assert run.script_path.parent == run.run_dir
    assert run.audio_path.parent == run.run_dir
    assert run.captions_path.parent == run.run_dir
    assert run.video_path.parent == run.run_dir
    assert run.metadata_path.parent == run.run_dir


def test_setup_logging_creates_file(tmp_path: Path):
    logger, log_path = setup_logging(mode="prod", logs_dir=str(tmp_path))
    logger.info("test-log-entry")

    assert log_path.exists()
    assert log_path.parent == tmp_path
    assert "reelforge_" in log_path.name
