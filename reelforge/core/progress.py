"""Terminal stage progress helpers."""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator

import click

try:
    from rich.console import Console
except ImportError:  # pragma: no cover - optional dependency
    Console = None  # type: ignore[assignment]


class StageReporter:
    """Simple stage reporter with optional rich spinner."""

    def __init__(self, *, enabled: bool = True):
        self.enabled = bool(enabled)
        self.console = Console() if (self.enabled and Console is not None) else None

    @contextmanager
    def stage(self, label: str) -> Iterator[None]:
        start = perf_counter()
        if self.console is not None:
            with self.console.status(f"[bold cyan]{label}...[/bold cyan]", spinner="dots"):
                yield
        else:
            click.echo(f"{label}...")
            yield

        elapsed = perf_counter() - start
        click.echo(f"{label} done ({elapsed:.1f}s)")

