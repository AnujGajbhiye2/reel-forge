from pathlib import Path

from reelforge.research.screenshot_researcher import ScreenshotResearcher


def _cfg():
    return {
        "research": {
            "enabled": True,
            "count": {"min": 3, "max": 6, "default": 5},
            "targeting": {"entity_source": "topic_first_script_refine", "max_targets": 8},
            "discovery": {
                "max_results_per_query": 4,
                "preferred_domains": ["wikipedia.org", "docs."],
            },
            "fallbacks": {
                "enable_image_search": True,
                "image_search_max_results": 4,
                "official_url_map": {
                    "codex": ["https://example.com/codex"],
                },
            },
            "overlay": {
                "min_show_sec": 2.0,
                "max_show_sec": 8.0,
            },
            "browser": {"headless": True, "nav_timeout_ms": 1000},
        }
    }


def test_requested_count_uses_top_n_when_in_range():
    researcher = ScreenshotResearcher(_cfg())
    chunks = [{"text": "a", "word_count": 3}] * 10
    assert researcher._requested_count(topic="Top 5 software books", chunks=chunks, override=None) == 5


def test_extract_comparison_targets():
    researcher = ScreenshotResearcher(_cfg())
    targets = researcher._extract_targets(
        topic="Claude Code vs Codex vs Gemini CLI showdown",
        script_text="A: quick compare",
        max_targets=8,
    )
    labels = [t["label"].lower() for t in targets]
    assert "claude code" in labels
    assert "codex" in labels
    assert "gemini cli" in labels


def test_run_uses_effective_target_count_when_extracted_less_than_requested(monkeypatch, tmp_path: Path):
    researcher = ScreenshotResearcher(_cfg())

    monkeypatch.setattr(
        researcher,
        "_extract_targets",
        lambda topic, script_text, max_targets: [
            researcher._make_target("Claude Code"),
            researcher._make_target("Codex"),
            researcher._make_target("Gemini CLI"),
        ],
    )
    monkeypatch.setattr(researcher, "_discover_page_candidates", lambda query, seed_urls: [])
    monkeypatch.setattr(researcher, "_discover_image_candidates", lambda query: ["https://img.example/a.png"])

    def fake_capture_image(url, path):
        path.write_bytes(f"capture:{url}".encode("utf-8"))

    monkeypatch.setattr(researcher, "_capture_image_url", fake_capture_image)
    monkeypatch.setattr(researcher, "_capture_url", lambda url, path: (_ for _ in ()).throw(RuntimeError("skip")))

    result = researcher.run(
        topic="top 5 ai coding assistants",
        script_text="A: Claude Code is secure.\nB: Codex is fast.\nA: Gemini CLI is broad.",
        style="dialogue",
        word_captions=[{"word": "w", "start": 0.0, "end": 0.2}] * 30,
        run_dir=tmp_path,
        screenshot_count_override=5,
        seed_urls=None,
    )

    assert result["requested_count"] == 5
    assert result["effective_target_count"] == 3
    assert result["captured_count"] == 3
    assert result["capture_breakdown"]["image_fallback"] == 3
    assert Path(result["plan_path"]).exists()
    assert all(item["status"] == "ok" for item in result["screenshots"])


def test_run_prefers_official_map_before_search(monkeypatch, tmp_path: Path):
    researcher = ScreenshotResearcher(_cfg())
    monkeypatch.setattr(
        researcher,
        "_extract_targets",
        lambda topic, script_text, max_targets: [researcher._make_target("Codex")],
    )
    monkeypatch.setattr(researcher, "_discover_page_candidates", lambda query, seed_urls: [])
    monkeypatch.setattr(researcher, "_discover_image_candidates", lambda query: [])

    captured_urls = []

    def fake_capture(url, path):
        captured_urls.append(url)
        path.write_bytes(b"ok")

    monkeypatch.setattr(researcher, "_capture_url", fake_capture)

    result = researcher.run(
        topic="codex",
        script_text="Codex helps with coding.",
        style="solo",
        word_captions=[{"word": "w", "start": 0.0, "end": 0.2}] * 10,
        run_dir=tmp_path,
        screenshot_count_override=1,
        seed_urls=None,
    )

    assert result["captured_count"] == 1
    assert captured_urls[0] == "https://example.com/codex"
    assert result["screenshots"][0]["capture_strategy"] == "official_page"
