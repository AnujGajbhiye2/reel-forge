"""
Caption generation and synchronization using WhisperX.
"""

import os
import json
import torch
import warnings
from importlib import metadata

# Suppress deprecation warnings from dependencies
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

# Fix for WhisperX/PyTorch compatibility with newer PyTorch versions
try:
    import omegaconf
    torch.serialization.add_safe_globals([
        omegaconf.listconfig.ListConfig,
        omegaconf.dictconfig.DictConfig,
        omegaconf.base.Container,
        omegaconf.base.ContainerMetadata,
        omegaconf.base.Node
    ])
except Exception:
    pass  # Older PyTorch versions don't need this

import whisperx
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path


class CaptionGenerator:
    """
    Generates word-level captions synchronized with audio using WhisperX.

    This module handles:
    - Audio transcription with word-level timestamps
    - Caption formatting and styling
    - Word-by-word animation data generation
    """

    def __init__(self, config: Dict[str, Any], device: Optional[str] = None):
        """
        Initialize the caption generator.

        Args:
            config: Configuration dictionary containing caption settings
            device: "cuda" for GPU, "cpu" for CPU. Auto-detects if None.
        """
        self.config = config
        self.font_size = config['captions']['font_size']
        self.font_color = config['captions']['font_color']
        self.stroke_color = config['captions']['stroke_color']
        self.stroke_width = config['captions']['stroke_width']
        self.position = config['captions']['position']
        self.max_words_per_line = config['captions']['max_words_per_line']
        self.animation = config['captions']['animation']

        # Device selection
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        self._validate_runtime_stack()

    @staticmethod
    def _validate_runtime_stack() -> None:
        """
        Warn when runtime stack drifts from pinned/tested versions.
        """
        pinned_versions = {
            "torch": "2.8.0",
            "torchaudio": "2.8.0",
            "pyannote.audio": "3.4.0",
        }
        mismatches = []

        for package_name, expected in pinned_versions.items():
            try:
                installed = metadata.version(package_name)
            except metadata.PackageNotFoundError:
                mismatches.append(f"{package_name}=<missing> (expected {expected})")
                continue

            if installed != expected:
                mismatches.append(f"{package_name}={installed} (expected {expected})")

        if mismatches:
            warnings.warn(
                "Caption runtime stack differs from tested pins: "
                + ", ".join(mismatches),
                RuntimeWarning,
            )

    def generate_captions(self, audio_path: str) -> List[Dict[str, Any]]:
        """
        Generate word-level captions from audio file using WhisperX.

        Args:
            audio_path: Path to audio file

        Returns:
            List of caption dictionaries with word-level timing
            Example: [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": "world", "start": 0.5, "end": 1.0}
            ]

        Raises:
            Exception: If transcription fails
        """
        try:
            # Workaround for PyTorch 2.8 weights_only=True default
            original_load = torch.load
            torch.load = lambda *args, **kwargs: original_load(*args, **{**kwargs, 'weights_only': False})

            try:
                # Load WhisperX model
                model = whisperx.load_model(
                    "base",
                    self.device,
                    compute_type=self.compute_type
                )
            finally:
                # Restore original torch.load
                torch.load = original_load

            # Load and transcribe audio
            audio = whisperx.load_audio(audio_path)
            result = model.transcribe(audio, batch_size=16)

            # Align for word-level timestamps
            model_a, metadata = whisperx.load_align_model(
                language_code="en",
                device=self.device
            )

            aligned = whisperx.align(
                result["segments"],
                model_a,
                metadata,
                audio,
                self.device,
                return_char_alignments=False
            )

            # Extract word segments
            word_segments = []
            for segment in aligned["segments"]:
                for word_info in segment.get("words", []):
                    if "start" in word_info and "end" in word_info:
                        word_segments.append({
                            "word": word_info["word"].strip(),
                            "start": float(word_info["start"]),
                            "end": float(word_info["end"])
                        })

            return word_segments

        except Exception as e:
            raise Exception(f"Caption generation failed: {str(e)}")

    def format_captions(
        self,
        captions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Format captions for display with proper line breaks.

        Groups words according to max_words_per_line setting.

        Args:
            captions: Raw word-level caption data

        Returns:
            Formatted caption data with line groupings
            Example: [
                {"text": "Hello world", "start": 0.0, "end": 1.0, "words": [...]},
                {"text": "How are you", "start": 1.0, "end": 2.0, "words": [...]}
            ]
        """
        formatted = []
        words_per_line = self.max_words_per_line

        for i in range(0, len(captions), words_per_line):
            group = captions[i:i + words_per_line]

            if group:
                formatted.append({
                    "text": " ".join(w["word"] for w in group),
                    "start": group[0]["start"],
                    "end": group[-1]["end"],
                    "words": group
                })

        return formatted

    def save_captions_json(
        self,
        captions: List[Dict[str, Any]],
        output_path: str
    ) -> Path:
        """
        Save captions to JSON file.

        Args:
            captions: Caption data
            output_path: Path to save JSON file

        Returns:
            Path to saved file
        """
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(captions, f, indent=2, ensure_ascii=False)

        return Path(output_path)

    def load_captions_json(self, json_path: str) -> List[Dict[str, Any]]:
        """
        Load captions from JSON file.

        Args:
            json_path: Path to JSON file

        Returns:
            Caption data
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def create_srt_subtitles(
        self,
        captions: List[Dict[str, Any]],
        output_path: str
    ) -> Path:
        """
        Create SRT subtitle file from captions.

        Args:
            captions: Formatted caption data
            output_path: Path to save SRT file

        Returns:
            Path to SRT file
        """
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            for i, caption in enumerate(captions, 1):
                start_time = self._format_srt_time(caption["start"])
                end_time = self._format_srt_time(caption["end"])

                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{caption['text']}\n\n")

        return Path(output_path)

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Convert seconds to SRT time format HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
