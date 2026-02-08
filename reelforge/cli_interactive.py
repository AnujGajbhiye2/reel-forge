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

    run_name = questionary.text("Optional run name (used in output folder suffix)", default="").ask() or None

    summary = Table(title="Generation Summary")
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="green")
    summary.add_row("Topic", topic)
    summary.add_row("Style", style)
    summary.add_row("Background", background or "Random")
    summary.add_row("Voice", selected_voice)
    summary.add_row("Character A", character or "None")
    if style == "dialogue":
        summary.add_row("Character B", secondary_character or "None")
    summary.add_row("Mode", mode_choice)
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
    }

