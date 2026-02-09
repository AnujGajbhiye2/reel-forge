"""
Automatic web screenshot discovery and timeline planning.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from reelforge.core.logging import get_logger

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - optional dependency
    try:
        from duckduckgo_search import DDGS  # type: ignore[no-redef]
    except ImportError:
        DDGS = None  # type: ignore[assignment]

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    PlaywrightTimeoutError = Exception  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


class ScreenshotResearcher:
    """
    Finds relevant webpages or images, captures screenshots, and maps them to timing.
    """

    DEFAULT_OFFICIAL_MAP = {
        "claude code": [
            "https://www.anthropic.com/claude-code",
            "https://docs.anthropic.com/",
        ],
        "codex": [
            "https://openai.com/",
            "https://platform.openai.com/docs",
        ],
        "gemini cli": [
            "https://ai.google.dev/",
            "https://deepmind.google/technologies/gemini/",
        ],
        "gemini": [
            "https://deepmind.google/technologies/gemini/",
            "https://ai.google.dev/",
        ],
    }

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.research_cfg = config.get("research", {})
        self.logger = get_logger()

    def run(
        self,
        *,
        topic: str,
        script_text: str,
        style: str,
        word_captions: List[Dict[str, Any]],
        run_dir: Path,
        screenshot_count_override: Optional[int] = None,
        seed_urls: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate screenshot overlays and persist a screenshot plan artifact.
        """
        chunks = self._extract_chunks(script_text=script_text, style=style)
        requested_count = self._requested_count(topic=topic, chunks=chunks, override=screenshot_count_override)
        max_targets = int(self.research_cfg.get("targeting", {}).get("max_targets", 8))
        targets = self._extract_targets(topic=topic, script_text=script_text, max_targets=max_targets)
        extracted_targets_count = len(targets)
        effective_target_count = min(requested_count, extracted_targets_count) if extracted_targets_count > 0 else 0

        if extracted_targets_count == 0:
            fallback_label = self._clean_target_label(topic)
            if fallback_label:
                targets = [self._make_target(fallback_label)]
                extracted_targets_count = 1
                effective_target_count = min(requested_count, 1)

        if not chunks or effective_target_count <= 0:
            plan_path = run_dir / "screenshot_plan.json"
            payload = {
                "topic": topic,
                "requested_count": requested_count,
                "extracted_targets_count": extracted_targets_count,
                "effective_target_count": effective_target_count,
                "captured_count": 0,
                "coverage_ratio": 0.0,
                "target_extraction_mode": "topic_first_script_refine",
                "screenshots": [],
                "failures": ["No usable visual targets extracted from prompt/script."],
                "unresolved_targets": [t.get("label") for t in targets],
                "capture_breakdown": {"official_page": 0, "search_result_page": 0, "image_fallback": 0},
            }
            plan_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return payload | {"plan_path": str(plan_path)}

        selected_targets = targets[:effective_target_count]
        windows = self._chunk_windows(chunks, word_captions)
        target_chunk_indices = self._assign_targets_to_chunks(selected_targets, chunks)

        shots_dir = run_dir / "screenshots"
        shots_dir.mkdir(parents=True, exist_ok=True)

        screenshots: List[Dict[str, Any]] = []
        failures: List[str] = []
        capture_breakdown = {"official_page": 0, "search_result_page": 0, "image_fallback": 0}

        for order, target in enumerate(selected_targets):
            chunk_index = target_chunk_indices[order] if order < len(target_chunk_indices) else order % len(chunks)
            chunk_text = chunks[chunk_index]["text"]
            start, end = windows.get(chunk_index, (0.0, 0.0))
            start, end = self._normalize_window(start, end)

            entry: Dict[str, Any] = {
                "id": order + 1,
                "target_label": target["label"],
                "target_kind": target["kind"],
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "query": target["query"],
                "start": round(start, 3),
                "end": round(end, 3),
                "file": "",
                "source_url": None,
                "source_domain": None,
                "status": "failed",
                "capture_strategy": None,
                "error": None,
            }

            image_path = shots_dir / f"ss_{order + 1:02d}.png"
            attempt_errors: List[str] = []
            captured = False

            official_candidates = self._official_url_candidates(target=target, seed_urls=seed_urls)
            for candidate in official_candidates:
                try:
                    self._capture_url(candidate, image_path)
                    entry.update(
                        {
                            "file": str(image_path),
                            "source_url": candidate,
                            "source_domain": urlparse(candidate).netloc,
                            "status": "ok",
                            "capture_strategy": "official_page",
                            "error": None,
                        }
                    )
                    capture_breakdown["official_page"] += 1
                    captured = True
                    break
                except Exception as exc:  # pragma: no cover - external runtime variability
                    attempt_errors.append(f"official:{candidate}:{exc}")

            if not captured:
                search_candidates = self._discover_page_candidates(query=target["query"], seed_urls=seed_urls)
                for candidate in search_candidates:
                    try:
                        self._capture_url(candidate, image_path)
                        entry.update(
                            {
                                "file": str(image_path),
                                "source_url": candidate,
                                "source_domain": urlparse(candidate).netloc,
                                "status": "ok",
                                "capture_strategy": "search_result_page",
                                "error": None,
                            }
                        )
                        capture_breakdown["search_result_page"] += 1
                        captured = True
                        break
                    except Exception as exc:  # pragma: no cover - external runtime variability
                        attempt_errors.append(f"search:{candidate}:{exc}")

            if not captured and bool(self.research_cfg.get("fallbacks", {}).get("enable_image_search", True)):
                image_candidates = self._discover_image_candidates(query=target["query"])
                for candidate in image_candidates:
                    try:
                        self._capture_image_url(candidate, image_path)
                        entry.update(
                            {
                                "file": str(image_path),
                                "source_url": candidate,
                                "source_domain": urlparse(candidate).netloc,
                                "status": "ok",
                                "capture_strategy": "image_fallback",
                                "error": None,
                            }
                        )
                        capture_breakdown["image_fallback"] += 1
                        captured = True
                        break
                    except Exception as exc:  # pragma: no cover - external runtime variability
                        attempt_errors.append(f"image:{candidate}:{exc}")

            if not captured:
                reason = (
                    f"Unable to capture target '{target['label']}' "
                    f"after {len(attempt_errors)} attempts."
                )
                entry["error"] = reason
                failures.append(reason)
                self.logger.warning("Screenshot target failed: %s", reason)
            else:
                self.logger.info(
                    "Screenshot target success label='%s' strategy=%s source=%s",
                    target["label"],
                    entry.get("capture_strategy"),
                    entry.get("source_url"),
                )

            screenshots.append(entry)

        captured_count = sum(1 for item in screenshots if item.get("status") == "ok")
        coverage_ratio = (captured_count / float(effective_target_count)) if effective_target_count else 0.0
        unresolved_targets = [item["target_label"] for item in screenshots if item.get("status") != "ok"]

        payload = {
            "topic": topic,
            "requested_count": requested_count,
            "extracted_targets_count": extracted_targets_count,
            "effective_target_count": effective_target_count,
            "captured_count": captured_count,
            "coverage_ratio": round(coverage_ratio, 3),
            "target_extraction_mode": "topic_first_script_refine",
            "screenshots": screenshots,
            "failures": failures,
            "unresolved_targets": unresolved_targets,
            "capture_breakdown": capture_breakdown,
        }
        plan_path = run_dir / "screenshot_plan.json"
        plan_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["plan_path"] = str(plan_path)
        return payload

    def _extract_targets(self, *, topic: str, script_text: str, max_targets: int) -> List[Dict[str, Any]]:
        targets: List[Dict[str, Any]] = []
        seen: set[str] = set()

        comparison_parts = self._extract_comparison_parts(topic)
        for label in comparison_parts:
            normalized = self._normalize_key(label)
            if normalized in seen:
                continue
            targets.append(self._make_target(label))
            seen.add(normalized)

        list_size = self._extract_topic_list_size(topic)
        if list_size is not None:
            for label in self._extract_ranked_items_from_script(script_text, limit=list_size):
                normalized = self._normalize_key(label)
                if normalized in seen:
                    continue
                targets.append(self._make_target(label, kind="book"))
                seen.add(normalized)

        if not targets:
            candidates = self._extract_named_phrases(script_text)
            for label in candidates:
                normalized = self._normalize_key(label)
                if normalized in seen:
                    continue
                targets.append(self._make_target(label))
                seen.add(normalized)
                if len(targets) >= max_targets:
                    break

        if not targets:
            cleaned = self._clean_target_label(topic)
            if cleaned:
                targets.append(self._make_target(cleaned))

        return targets[:max_targets]

    def _extract_comparison_parts(self, topic: str) -> List[str]:
        raw = topic or ""
        lowered = raw.lower()
        if " vs " not in lowered and " versus " not in lowered:
            return []

        text = re.sub(r"\b(showdown|comparison|compare|which one|reigns supreme)\b", "", raw, flags=re.IGNORECASE)
        parts = re.split(r"\b(?:vs\.?|versus)\b|/|\\|\||,", text, flags=re.IGNORECASE)
        cleaned: List[str] = []
        for part in parts:
            label = self._clean_target_label(part)
            if label:
                cleaned.append(label)
        return cleaned

    def _extract_ranked_items_from_script(self, script_text: str, limit: int) -> List[str]:
        lines = [line.strip() for line in (script_text or "").splitlines() if line.strip()]
        items: List[str] = []

        numbered = re.compile(r"^(?:[A-Za-z][A-Za-z0-9_\- ]*:\s*)?(?:#?\d+[\)\.\-:]\s*)(.+)$")
        for line in lines:
            match = numbered.match(line)
            if match:
                label = self._clean_target_label(match.group(1))
                if label:
                    items.append(label)
            if len(items) >= limit:
                return items[:limit]

        quoted = re.findall(r"[\"'“”]([^\"'“”]{3,80})[\"'“”]", script_text or "")
        for q in quoted:
            label = self._clean_target_label(q)
            if label and label not in items:
                items.append(label)
            if len(items) >= limit:
                return items[:limit]

        for phrase in self._extract_named_phrases(script_text):
            if phrase not in items:
                items.append(phrase)
            if len(items) >= limit:
                return items[:limit]

        return items[:limit]

    def _extract_named_phrases(self, text: str) -> List[str]:
        if not text:
            return []

        phrases: List[str] = []
        pattern = re.compile(r"\b([A-Z][A-Za-z0-9\+\-]*(?:\s+[A-Z][A-Za-z0-9\+\-]*){0,3})\b")
        for match in pattern.finditer(text):
            label = self._clean_target_label(match.group(1))
            if label:
                phrases.append(label)

        # include lowercase branded terms from topic/script
        keyword_pattern = re.compile(r"\b([a-z0-9][a-z0-9\-_]{2,30}\s+(?:cli|code|sdk|api))\b", re.IGNORECASE)
        for match in keyword_pattern.finditer(text):
            label = self._clean_target_label(match.group(1))
            if label:
                phrases.append(label)

        deduped: List[str] = []
        seen: set[str] = set()
        for phrase in phrases:
            key = self._normalize_key(phrase)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(phrase)
        return deduped

    def _make_target(self, label: str, kind: str = "tool") -> Dict[str, Any]:
        cleaned = self._clean_target_label(label)
        return {
            "label": cleaned,
            "kind": kind,
            "aliases": self._aliases_for(cleaned),
            "query": self._build_target_query(cleaned, kind),
            "official_url_candidates": self._official_map_urls(cleaned),
        }

    @staticmethod
    def _clean_target_label(value: str) -> str:
        text = (value or "").strip()
        text = re.sub(r"^[\-\*\d\)\.\s#]+", "", text)
        text = re.sub(r"\b(?:official site|showdown|comparison|reigns supreme|which one)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip(" ,.-")
        return text

    @staticmethod
    def _normalize_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

    def _aliases_for(self, label: str) -> List[str]:
        aliases = [label]
        normalized = self._normalize_key(label)
        if normalized == "gemini cli":
            aliases.extend(["google gemini cli", "gemini command line"])
        if normalized == "codex":
            aliases.extend(["openai codex"])
        return aliases

    def _build_target_query(self, label: str, kind: str) -> str:
        suffix = "official site"
        if kind == "book":
            suffix = "book cover"
        elif "cli" in label.lower():
            suffix = "official docs"
        return f"{label} {suffix}".strip()

    def _official_map_urls(self, label: str) -> List[str]:
        merged_map: Dict[str, List[str]] = {}
        merged_map.update(self.DEFAULT_OFFICIAL_MAP)
        cfg_map = self.research_cfg.get("fallbacks", {}).get("official_url_map", {})
        for key, urls in cfg_map.items():
            merged_map[self._normalize_key(key)] = list(urls)

        normalized = self._normalize_key(label)
        if normalized in merged_map:
            return list(merged_map[normalized])

        guesses: List[str] = []
        slug = re.sub(r"[^a-z0-9]+", "", normalized)
        if slug:
            guesses.append(f"https://{slug}.com")
            guesses.append(f"https://www.{slug}.com")
        if "cli" in normalized or "open source" in normalized:
            repo = normalized.replace(" ", "-")
            guesses.append(f"https://github.com/{repo}")
        return guesses

    def _requested_count(
        self,
        *,
        topic: str,
        chunks: List[Dict[str, Any]],
        override: Optional[int],
    ) -> int:
        count_cfg = self.research_cfg.get("count", {})
        minimum = int(count_cfg.get("min", 3))
        maximum = int(count_cfg.get("max", 6))
        default_count = int(count_cfg.get("default", 5))

        if override is not None:
            return max(1, min(maximum, int(override)))

        list_size = self._extract_topic_list_size(topic)
        if list_size is not None:
            return max(1, min(maximum, list_size))

        return max(1, min(maximum, min(default_count, max(1, len(chunks), minimum))))

    @staticmethod
    def _extract_topic_list_size(topic: str) -> Optional[int]:
        match = re.search(r"\b(?:top|best)\s+(\d{1,2})\b", (topic or "").lower())
        if not match:
            return None
        return int(match.group(1))

    def _official_url_candidates(self, *, target: Dict[str, Any], seed_urls: Optional[Sequence[str]]) -> List[str]:
        urls: List[str] = []
        for candidate in target.get("official_url_candidates", []):
            if self._is_usable_url(candidate) and candidate not in urls:
                urls.append(candidate)

        for raw in (seed_urls or []):
            if not self._is_usable_url(raw):
                continue
            label_key = self._normalize_key(target.get("label", ""))
            if label_key and any(token in raw.lower() for token in label_key.split()):
                if raw not in urls:
                    urls.append(raw)

        return urls

    def _discover_page_candidates(self, *, query: str, seed_urls: Optional[Sequence[str]]) -> List[str]:
        limit = int(self.research_cfg.get("discovery", {}).get("max_results_per_query", 8))
        preferred_domains = [
            d.lower() for d in self.research_cfg.get("discovery", {}).get("preferred_domains", [])
        ]
        urls: List[str] = []

        for raw in (seed_urls or []):
            if self._is_usable_url(raw) and raw not in urls:
                urls.append(raw)

        if DDGS is not None:
            try:
                with DDGS() as ddgs:
                    for result in ddgs.text(query, max_results=limit):  # pragma: no cover - network dependent
                        candidate = (result or {}).get("href")
                        if self._is_usable_url(candidate) and candidate not in urls:
                            urls.append(candidate)
                        if len(urls) >= limit:
                            break
            except Exception as exc:  # pragma: no cover - network dependent
                self.logger.warning("Search discovery failed for query '%s': %s", query, exc)

        def rank(url: str) -> Tuple[int, int]:
            domain = urlparse(url).netloc.lower()
            trusted = int(any(pref in domain for pref in preferred_domains))
            officialish = int(any(key in domain for key in ("docs", "github", "wikipedia")))
            return (-(trusted + officialish), len(domain))

        ranked = sorted(urls, key=rank)
        return ranked[:limit]

    def _discover_image_candidates(self, *, query: str) -> List[str]:
        limit = int(self.research_cfg.get("fallbacks", {}).get("image_search_max_results", 6))
        urls: List[str] = []
        if DDGS is None:
            return urls
        try:
            with DDGS() as ddgs:
                for result in ddgs.images(query, max_results=limit):  # pragma: no cover - network dependent
                    candidate = (result or {}).get("image")
                    if self._is_usable_image_url(candidate) and candidate not in urls:
                        urls.append(candidate)
                    if len(urls) >= limit:
                        break
        except Exception as exc:  # pragma: no cover - network dependent
            self.logger.warning("Image discovery failed for query '%s': %s", query, exc)
        return urls

    @staticmethod
    def _is_usable_url(url: Optional[str]) -> bool:
        if not url or not isinstance(url, str):
            return False
        if not url.startswith(("http://", "https://")):
            return False
        lowered = url.lower()
        blocked_tokens = (
            "youtube.com/watch",
            "facebook.com",
            "instagram.com",
            "tiktok.com",
            "accounts.google.com",
            "login",
            "signup",
        )
        return not any(token in lowered for token in blocked_tokens)

    @staticmethod
    def _is_usable_image_url(url: Optional[str]) -> bool:
        if not url or not isinstance(url, str):
            return False
        return url.startswith(("http://", "https://"))

    def _capture_url(self, url: str, output_path: Path) -> None:
        if sync_playwright is None:
            raise RuntimeError("Playwright is not installed. Install 'playwright' and run browser setup.")

        browser_cfg = self.research_cfg.get("browser", {})
        headless = bool(browser_cfg.get("headless", True))
        timeout_ms = int(browser_cfg.get("nav_timeout_ms", 15000))
        viewport = {"width": 1280, "height": 720}

        with sync_playwright() as playwright:  # pragma: no cover - external runtime dependency
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(viewport=viewport)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                self._dismiss_cookie_popups(page)
                page.screenshot(path=str(output_path), full_page=False)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(f"Navigation timeout for {url}: {exc}") from exc
            finally:
                context.close()
                browser.close()

    @staticmethod
    def _capture_image_url(url: str, output_path: Path) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:  # pragma: no cover - network dependent
            data = response.read()
        if not data:
            raise RuntimeError(f"Empty image response from {url}")
        output_path.write_bytes(data)

    @staticmethod
    def _dismiss_cookie_popups(page) -> None:  # pragma: no cover - external runtime dependency
        selectors = (
            "button:has-text('Accept all')",
            "button:has-text('Accept')",
            "button:has-text('I agree')",
            "button:has-text('Got it')",
        )
        for selector in selectors:
            try:
                el = page.locator(selector).first
                if el and el.is_visible(timeout=300):
                    el.click(timeout=500)
                    break
            except Exception:
                continue

    def _extract_chunks(self, *, script_text: str, style: str) -> List[Dict[str, Any]]:
        lines = [line.strip() for line in (script_text or "").splitlines() if line.strip()]
        chunks: List[Dict[str, Any]] = []

        if style == "dialogue":
            for line in lines:
                text = re.sub(r"^[A-Za-z][A-Za-z0-9_\- ]*:\s*", "", line).strip()
                if text:
                    chunks.append({"text": text, "word_count": self._word_count(text)})
            return chunks

        sentences = re.split(r"(?<=[.!?])\s+", " ".join(lines))
        for sentence in sentences:
            text = sentence.strip()
            if not text:
                continue
            chunks.append({"text": text, "word_count": self._word_count(text)})

        return self._merge_tiny_chunks(chunks, min_words=5)

    @staticmethod
    def _merge_tiny_chunks(chunks: List[Dict[str, Any]], min_words: int) -> List[Dict[str, Any]]:
        if not chunks:
            return []
        merged: List[Dict[str, Any]] = []
        for chunk in chunks:
            if merged and chunk["word_count"] < min_words:
                merged[-1]["text"] = f"{merged[-1]['text']} {chunk['text']}".strip()
                merged[-1]["word_count"] += chunk["word_count"]
            else:
                merged.append(dict(chunk))
        return merged

    def _chunk_windows(
        self,
        chunks: List[Dict[str, Any]],
        word_captions: List[Dict[str, Any]],
    ) -> Dict[int, Tuple[float, float]]:
        windows: Dict[int, Tuple[float, float]] = {}
        if not chunks:
            return windows

        if not word_captions:
            span = 60.0 / float(len(chunks))
            for idx in range(len(chunks)):
                windows[idx] = (idx * span, (idx + 1) * span)
            return windows

        total_words = sum(max(1, int(chunk.get("word_count", 1))) for chunk in chunks)
        caption_count = len(word_captions)
        cursor = 0

        for idx, chunk in enumerate(chunks):
            chunk_words = max(1, int(chunk.get("word_count", 1)))
            allocation = max(1, int(round((chunk_words / float(total_words)) * caption_count)))
            next_cursor = min(caption_count, cursor + allocation)
            if idx == len(chunks) - 1:
                next_cursor = caption_count
            if next_cursor <= cursor:
                next_cursor = min(caption_count, cursor + 1)

            first = word_captions[cursor]
            last = word_captions[next_cursor - 1]
            windows[idx] = (float(first.get("start", 0.0)), float(last.get("end", first.get("start", 0.0))))
            cursor = next_cursor
            if cursor >= caption_count:
                cursor = caption_count - 1

        return windows

    def _assign_targets_to_chunks(
        self,
        targets: List[Dict[str, Any]],
        chunks: List[Dict[str, Any]],
    ) -> List[int]:
        if not targets:
            return []
        if not chunks:
            return [0] * len(targets)

        assigned: List[int] = []
        used: set[int] = set()
        for target in targets:
            t_tokens = set(self._normalize_key(target.get("label", "")).split())
            scored: List[Tuple[int, int]] = []
            for idx, chunk in enumerate(chunks):
                c_tokens = set(self._normalize_key(chunk.get("text", "")).split())
                overlap = len(t_tokens.intersection(c_tokens))
                scored.append((overlap, idx))
            scored.sort(reverse=True)
            chosen = None
            for overlap, idx in scored:
                if idx in used:
                    continue
                if overlap > 0:
                    chosen = idx
                    break
            if chosen is None:
                for _overlap, idx in scored:
                    if idx not in used:
                        chosen = idx
                        break
            if chosen is None:
                chosen = len(assigned) % len(chunks)
            assigned.append(chosen)
            used.add(chosen)
        return assigned

    def _normalize_window(self, start: float, end: float) -> Tuple[float, float]:
        overlay_cfg = self.research_cfg.get("overlay", {})
        min_show = float(overlay_cfg.get("min_show_sec", 2.0))
        max_show = float(overlay_cfg.get("max_show_sec", 8.0))
        if end <= start:
            return start, start + min_show
        duration = end - start
        if duration < min_show:
            end = start + min_show
        elif duration > max_show:
            end = start + max_show
        return start, end

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"[A-Za-z0-9']+", text or ""))
