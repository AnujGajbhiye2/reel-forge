# ReelForge

## Project Overview

ReelForge is a semi-automated Python-based command-line tool designed to generate "faceless" social media reels (TikToks, Instagram Reels, YouTube Shorts) in the style of popular tech and AI content creators. It automates the process of creating short, engaging videos by combining AI-generated scripts, text-to-speech voiceovers, and various visual elements.

The project is structured as a modular pipeline, with distinct Python scripts for different stages of the video creation process:

- **Script Generation**: Uses AI language models (like Gemini) to generate scripts on a given topic, with options for different styles (solo narrator or dialogue).
- **Text-to-Speech (TTS)**: Converts the generated script into a voiceover using engines like EdgeTTS.
- **Caption Generation**: Creates word-by-word animated captions from the audio.
- **Video Composition**: Assembles the final video, layering a background video (e.g., Minecraft parkour), a character overlay, and the generated captions.

The entire process is orchestrated through a command-line interface built with the `click` library. The project is configured via a `config.yaml` file, allowing users to customize API keys, voice settings, video resolution, and more.

## Building and Running

### Prerequisites

- Python 3.10+
- FFmpeg
- ImageMagick

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd reelforge
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```
3.  **Install the required Python packages:**
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application

The main entry point for the application is `main.py`. You can see all the available commands by running:

```bash
python main.py --help
```

Here are some of the key commands:

-   **`generate`**: The main command to generate a complete reel from a topic.

    ```bash
    python main.py generate "My Awesome Topic" --style solo
    ```

-   **`script`**: Generate only the script.

    ```bash
    python main.py script --topic "My Awesome Topic" --style solo
    ```

-   **`tts`**: Generate only the text-to-speech audio.

    ```bash
    python main.py tts --text "Hello, world!" --output audio.mp3
    ```

-   **`captions`**: Generate captions for an audio file.

    ```bash
    python main.py captions --audio audio.mp3
    ```

-   **`compose`**: Compose a video from its constituent parts.

    ```bash
    python main.py compose --audio audio.mp3 --captions captions.json --output my_video.mp4
    ```

-   **`list-voices`**: List available TTS voices.

    ```bash
    python main.py list-voices
    ```

-   **`validate`**: Validate the `config.yaml` file and check for the existence of required assets.
    ```bash
    python main.py validate
    ```

### Testing

The project uses `pytest` for testing. To run the tests, use the following command:

```bash
pytest
```

## Development Conventions

-   **Styling**: The project uses `black` for code formatting and `isort` for import sorting.
-   **Linting**: The project uses `pylint` for linting.
-   **Commits**: Commit messages should follow the Conventional Commits specification.
-   **Branching**: The project uses the Gitflow branching model.
-   **Dependencies**: All Python dependencies are listed in the `requirements.txt` file.
-   **Configuration**: All configuration is handled through the `config.yaml` file.
-   **Logging**: The project uses the `logging` module for logging, with different logging levels for development and production environments.
-   **CLI**: The command-line interface is built using the `click` library.
-   **Modularity**: The project is highly modular, with each part of the pipeline encapsulated in its own Python script in the `reelforge` directory.
-   **Testing**: The project uses `pytest` for testing, and tests are located in the `tests` directory.

The `reelforge-blueprint.md` file provides a comprehensive overview of the project's architecture and implementation plan. It's a great resource for understanding the project's design and future direction.
