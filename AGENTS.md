# Repository Guidelines

## Project Structure & Module Organization
ReelForge is a Python CLI project rooted at `main.py` (entrypoint) and the `reelforge/` package.

- `reelforge/cli/`: Click app wiring, command modules, interactive wizard.
- `reelforge/pipeline/`: end-to-end orchestration, outputs, quality gate.
- `reelforge/script/`, `reelforge/audio/`, `reelforge/captions/`, `reelforge/research/`: feature modules.
- `reelforge/media/`, `reelforge/animation/`: marker handling and animation utilities.
- `reelforge/integrations/`: external service adapters (for example Google Drive).
- `reelforge/shared/`, `reelforge/core/`: shared config, logging, run context primitives.
- `tests/`: pytest suite (`test_*.py`).
- `assets/`: fonts, characters, and media inputs.
- `output/`, `logs/`: generated artifacts and runtime logs.

## Build, Test, and Development Commands
Use the project virtual environment before running commands.

```bash
source venv/bin/activate
python main.py --help
python main.py validate
python main.py script -t "Your Topic" -s solo
python main.py generate "Your Topic" -s solo
pytest -v
pytest -m integration -v
```

- `python main.py --help`: list CLI commands.
- `python main.py validate`: verify config and local asset paths.
- `python main.py generate ...`: run end-to-end generation with pipeline defaults.
- `pytest -v`: run unit/local tests.
- `pytest -m integration -v`: run tests that call real services (API keys required).

## Coding Style & Naming Conventions
Follow existing Python style in this repo:

- PEP 8 formatting, 4-space indentation, and clear docstrings for modules/classes.
- Prefer type hints and `from __future__ import annotations` where used.
- Use `snake_case` for functions/modules, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
- Keep CLI command files in `reelforge/cli/commands/` focused on one command each.

No dedicated formatter/linter config is currently checked in; keep style consistent with surrounding code.

## Testing Guidelines
- Framework: `pytest` with optional `integration` marker (`pytest.ini`).
- Name files `test_*.py`; group related assertions in `Test...` classes when useful.
- Keep unit tests deterministic; integration tests should skip gracefully when credentials/config are unavailable.
- Add/update tests with behavioral changes, especially in pipeline, script generation, marker resolution, and integrations.

## Commit & Pull Request Guidelines
Recent commits favor short, imperative subjects (example: `Fix video generation: strip markers before TTS...`).

- Commit message format: concise imperative summary; optional scope prefix is fine.
- PRs should include:
  - what changed and why,
  - testing performed (`pytest -v`, targeted test files),
  - config/credential impacts (`config.yaml`, `.secrets/`),
  - sample output path(s) when behavior affects generated artifacts.

## Security & Configuration Tips
- Never commit secrets. Keep API keys in `config.yaml`/environment locally and OAuth files under `.secrets/`.
- Use `.env.example` as the template for local setup.
