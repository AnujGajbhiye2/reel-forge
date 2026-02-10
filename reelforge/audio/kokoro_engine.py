"""
Kokoro TTS engine for higher quality voice synthesis.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import tempfile

logger = logging.getLogger(__name__)


class KokoroTTSEngine:
    """
    TTS engine using Kokoro-82M for natural-sounding voices.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Kokoro TTS engine.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        tts_cfg = config.get("tts", {})

        self.voice_a = tts_cfg.get("kokoro_voice_a", "am_adam")
        self.voice_b = tts_cfg.get("kokoro_voice_b", "af_heart")
        self.lang = tts_cfg.get("kokoro_lang", "a")  # American English

        # Try to import kokoro
        try:
            from kokoro import KPipeline
            import soundfile as sf
            self.KPipeline = KPipeline
            self.sf = sf

            # Initialize pipeline
            self.pipeline = KPipeline(lang_code=self.lang)
            logger.info("Kokoro TTS initialized successfully")

        except ImportError as e:
            raise RuntimeError(
                "Kokoro not installed. Install: pip install kokoro soundfile"
            ) from e

    def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None
    ) -> Path:
        """
        Generate speech from text.

        Args:
            text: Text to synthesize
            output_path: Path to save audio
            voice: Voice ID (uses voice_a if not specified)

        Returns:
            Path to generated audio file
        """
        try:
            voice_id = voice or self.voice_a

            # Generate audio
            audio_chunks = list(self.pipeline(text, voice=voice_id))

            # Concatenate chunks
            if not audio_chunks:
                raise RuntimeError("Kokoro generated no audio chunks")

            # Kokoro returns audio as numpy arrays at 24kHz
            import numpy as np
            audio_data = np.concatenate(audio_chunks)

            # Save as MP3 (convert via temporary WAV)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                self.sf.write(tmp_path, audio_data, 24000)

            # Convert WAV to MP3 using pydub
            from pydub import AudioSegment
            audio = AudioSegment.from_wav(tmp_path)
            audio.export(output_path, format="mp3")

            # Clean up temp file
            Path(tmp_path).unlink(missing_ok=True)

            logger.info(f"Kokoro generated audio: {output_path}")
            return Path(output_path)

        except Exception as e:
            logger.error(f"Kokoro generation failed: {e}")
            raise RuntimeError(f"Kokoro TTS generation failed: {e}") from e

    def generate_dialogue(
        self,
        script: str,
        output_path: str
    ) -> Tuple[Path, Optional[List[Dict[str, Any]]]]:
        """
        Generate dialogue audio with alternating voices.

        Args:
            script: Dialogue script with A:/B: prefixes
            output_path: Path to save audio

        Returns:
            Tuple of (audio path, speaker timeline)
        """
        try:
            from pydub import AudioSegment
            import re

            # Parse dialogue lines
            lines = script.strip().split('\n')
            dialogue_segments = []
            speaker_timeline = []

            current_time_ms = 0
            pause_ms = 200  # Pause between speakers

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Extract speaker and text
                match = re.match(r'^([AB]):\s*(.+)$', line, re.IGNORECASE)
                if not match:
                    continue

                speaker = match.group(1).upper()
                text = match.group(2).strip()

                # Select voice based on speaker
                voice = self.voice_a if speaker == 'A' else self.voice_b

                # Generate audio for this line
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp_path = tmp.name

                line_path = self.generate(text, tmp_path, voice=voice)
                line_audio = AudioSegment.from_mp3(str(line_path))

                # Add to segments
                dialogue_segments.append(line_audio)

                # Track speaker timeline
                duration_s = len(line_audio) / 1000.0
                speaker_timeline.append({
                    "speaker": speaker,
                    "start": current_time_ms / 1000.0,
                    "end": (current_time_ms + len(line_audio)) / 1000.0,
                    "text": text
                })

                current_time_ms += len(line_audio)

                # Add pause between speakers
                if dialogue_segments:
                    dialogue_segments.append(AudioSegment.silent(duration=pause_ms))
                    current_time_ms += pause_ms

                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)

            # Concatenate all segments
            if not dialogue_segments:
                raise RuntimeError("No dialogue lines parsed from script")

            final_audio = dialogue_segments[0]
            for segment in dialogue_segments[1:]:
                final_audio += segment

            # Export as MP3
            final_audio.export(output_path, format="mp3")

            logger.info(f"Kokoro generated dialogue: {output_path}")
            return Path(output_path), speaker_timeline

        except Exception as e:
            logger.error(f"Kokoro dialogue generation failed: {e}")
            raise RuntimeError(f"Kokoro dialogue generation failed: {e}") from e

    def synthesize_sync(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> Path:
        """
        Synchronous synthesis (matches TTSEngine interface).

        Args:
            text: Text to synthesize
            output_path: Path to save audio
            voice: Voice ID (ignored, uses config)
            rate: Speech rate (ignored for Kokoro)
            pitch: Pitch adjustment (ignored for Kokoro)

        Returns:
            Path to generated audio
        """
        return self.generate(text, output_path, voice=voice)

    def synthesize_dialogue_sync(
        self,
        dialogue: Dict[str, List[str]],
        output_path: str,
        voice_mapping: Optional[Dict[str, str]] = None,
        return_timeline: bool = False
    ) -> Tuple[Path, Optional[List[Dict[str, Any]]]]:
        """
        Synchronous dialogue synthesis (matches TTSEngine interface).

        Args:
            dialogue: Dictionary mapping speakers to lines
            output_path: Path to save audio
            voice_mapping: Optional voice mapping (ignored)
            return_timeline: Whether to return speaker timeline

        Returns:
            Tuple of (audio path, speaker timeline if requested)
        """
        # Convert dialogue dict to script format
        script_lines = []
        for speaker, lines in dialogue.items():
            for line in lines:
                script_lines.append(f"{speaker}: {line}")

        script = '\n'.join(script_lines)
        path, timeline = self.generate_dialogue(script, output_path)

        if return_timeline:
            return path, timeline
        return path, None
