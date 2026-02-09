"""
Interactive terminal UI for ReelForge.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _require_tui_deps():
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        import questionary
    except ImportError as exc:
        raise RuntimeError(
            "Interactive mode requires 'rich' and 'questionary'. "
            "Install dependencies from requirements.txt."
        ) from exc

    return Console(), Panel, Table, questionary


def launch_interactive_wizard(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Show a guided terminal wizard.

    Returns:
        A dictionary of options for generation, or None when user exits.
    """
    console, Panel, Table, questionary = _require_tui_deps()

    console.print(
        Panel.fit(
            "[bold cyan]"
            "  ____           _ ______                    \n"
            " |  _ \\ ___  ___| |  ___|__  _ __ __ _  ___ \n"
            " | |_) / _ \\/ _ \\ | |_ / _ \\| '__/ _` |/ _ \\\n"
            " |  _ <  __/  __/ |  _| (_) | | | (_| |  __/\n"
            " |_| \\_\\___|\\___|_|_|  \\___/|_|  \\__, |\\___|\n"
            "                                 |___/       \n"
            "[/bold cyan]"
            "[green]Create short-form reels from a guided terminal flow[/green]",
            title="Welcome",
            border_style="bright_blue",
        )
    )

    mode = questionary.select(
        "What would you like to do?",
        choices=[
            "Generate a new reel",
            "List available voices",
            "Validate configuration",
            "Exit",
        ],
    ).ask()

    if mode in {None, "Exit"}:
        return None

    if mode == "List available voices":
        return {"action": "list_voices"}

    if mode == "Validate configuration":
        return {"action": "validate"}

    style = questionary.select(
        "Select script style",
        choices=["dialogue", "solo"],
        default="dialogue",
    ).ask()

    # Ask if user wants to provide custom script
    use_custom_script = questionary.confirm(
        "Do you want to provide your own script? (Recommended if LLM generation is unreliable)",
        default=False,
    ).ask()

    custom_script_content = None
    custom_script_path = None

    if use_custom_script:
        console.print("\n[bold yellow]Custom Script Format:[/bold yellow]")
        console.print("[cyan]Paste everything including REEL TITLE (optional) and keywords:[/cyan]")
        console.print("")
        console.print("  REEL TITLE: Your Title Here")
        console.print("  A: First line here")
        console.print("  B: Second line with [SHOW:S1] marker")
        console.print("  A: Third line")
        console.print("  B: Fourth line with [SHOW:S2] marker")
        console.print("")
        console.print("  S1=cursor, S2=codex, S3=windsurf")
        console.print("\n[dim]Paste your script (press Ctrl+D or Ctrl+Z when done):[/dim]\n")

        import sys
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass

        custom_script_content = "\n".join(lines)

        if not custom_script_content.strip():
            console.print("[red]No script provided, falling back to LLM generation[/red]")
            use_custom_script = False
        else:
            # Save to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
                f.write(custom_script_content)
                custom_script_path = f.name
            console.print(f"[green]✓ Custom script saved ({len(custom_script_content)} chars)[/green]\n")

    # Auto-extract topic from REEL TITLE if custom script provided
    topic = None
    if use_custom_script and custom_script_content:
        import re
        match = re.search(r'REEL TITLE:\s*(.+)', custom_script_content)
        if match:
            topic = match.group(1).strip()
            console.print(f"[green]✓ Topic auto-extracted from REEL TITLE:[/green] {topic}\n")

    # Only prompt for topic if not auto-extracted
    if not topic:
        topic = questionary.text("Enter your reel topic").ask()
        if not topic:
            return None

    details = questionary.text("Optional details/context (press Enter to skip)", default="").ask() or ""

    backgrounds = config.get("assets", {}).get("backgrounds", [])
    background_choices = ["Random"] + backgrounds
    background = questionary.select("Choose background", choices=background_choices, default="Random").ask()
    background = None if background == "Random" else background

    voices = []
    tts_cfg = config.get("tts", {})
    default_voice = tts_cfg.get("voice", "en-US-AndrewNeural")
    voices.append(default_voice)
    voices.extend(["en-US-AndrewNeural", "en-US-GuyNeural", "en-US-JennyNeural", "en-US-AriaNeural"])
    deduped_voices = []
    for voice in voices:
        if voice not in deduped_voices:
            deduped_voices.append(voice)

    selected_voice = questionary.select(
        "Choose primary voice",
        choices=deduped_voices,
        default=default_voice,
    ).ask()

    characters = config.get("assets", {}).get("characters", [])
    character = questionary.select(
        "Choose character A",
        choices=["None"] + characters,
        default=characters[0] if characters else "None",
    ).ask()
    character = None if character == "None" else character

    secondary_character = None
    if style == "dialogue":
        secondary_character = questionary.select(
            "Choose character B",
            choices=["None"] + characters,
            default=characters[1] if len(characters) > 1 else "None",
        ).ask()
        secondary_character = None if secondary_character == "None" else secondary_character

    mode_choice = questionary.select("Run mode", choices=["dev", "prod"], default=config.get("app", {}).get("mode", "dev")).ask()

    research_cfg = config.get("research", {})
    research_enabled_default = bool(research_cfg.get("enabled", False))

    # Check if MCP mode is enabled
    script_cfg = config.get("script", {})
    use_mcp = script_cfg.get("use_mcp_generator", False)

    if use_mcp:
        # MCP mode uses media-harvest automatically, don't confuse with legacy research
        auto_screenshots = False
    else:
        auto_screenshots = questionary.confirm(
            "Enable legacy screenshot research? (Note: MCP mode uses media-harvest automatically)",
            default=research_enabled_default,
        ).ask()

    screenshot_count = None
    seed_urls = []
    if auto_screenshots:
        count_value = questionary.text(
            "Screenshot count override (press Enter to use auto)",
            default="",
            validate=lambda text: (not text.strip()) or text.strip().isdigit() or "Enter a number or leave blank",
        ).ask()
        if count_value and count_value.strip():
            screenshot_count = int(count_value.strip())

        seed_input = questionary.text(
            "Optional trusted seed URLs (comma-separated)",
            default="",
        ).ask() or ""
        seed_urls = [u.strip() for u in seed_input.split(",") if u.strip()]

    run_name = questionary.text("Optional run name (used in output folder suffix)", default="").ask() or None

    summary = Table(title="Generation Summary")
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="green")
    summary.add_row("Topic", topic)
    summary.add_row("Style", style)
    if use_custom_script:
        summary.add_row("Script Source", "[bold yellow]Custom (user-provided)[/bold yellow]")
    else:
        summary.add_row("Script Source", "LLM Generated")
    summary.add_row("Background", background or "Random")
    summary.add_row("Voice", selected_voice)
    summary.add_row("Character A", character or "None")
    if style == "dialogue":
        summary.add_row("Character B", secondary_character or "None")
    summary.add_row("Mode", mode_choice)
    summary.add_row("Auto Screenshots", "Yes" if auto_screenshots else "No")
    if auto_screenshots:
        summary.add_row("Screenshot Count", str(screenshot_count) if screenshot_count is not None else "Auto")
        summary.add_row("Seed URLs", str(len(seed_urls)))
    summary.add_row("Run Name", run_name or "-")
    console.print(summary)

    confirmed = questionary.confirm("Start generation with these settings?", default=True).ask()
    if not confirmed:
        return None

    return {
        "action": "generate",
        "topic": topic,
        "details": details,
        "style": style,
        "background": background,
        "voice": selected_voice,
        "character": character,
        "secondary_character": secondary_character,
        "mode": mode_choice,
        "run_name": run_name,
        "auto_screenshots": auto_screenshots,
        "screenshot_count": screenshot_count,
        "seed_urls": seed_urls,
        "custom_script_path": custom_script_path,
    }
