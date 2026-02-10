"""
Audio-reactive character animation for synchronized bobbing/bouncing.
"""

import numpy as np
from pathlib import Path
from typing import Optional, Any
from pydub import AudioSegment
import logging

logger = logging.getLogger(__name__)


class CharacterAnimator:
    """
    Animates character clips with audio-reactive bobbing motion.
    """

    def __init__(self, config: dict):
        """
        Initialize the character animator.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        character_cfg = config.get("character", {})
        self.animation_type = character_cfg.get("animation", "bounce")
        self.bounce_pixels = int(character_cfg.get("bounce_pixels", 15))
        self.window_ms = 100  # Audio analysis window size

    def load_audio_amplitude(self, audio_path: str) -> tuple:
        """
        Load audio file and compute amplitude envelope.

        Args:
            audio_path: Path to audio file

        Returns:
            Tuple of (sample_rate, amplitude_data as numpy array)
        """
        try:
            # Load audio with pydub
            audio = AudioSegment.from_file(audio_path)

            # Convert to mono if stereo
            if audio.channels > 1:
                audio = audio.set_channels(1)

            # Get sample rate
            sample_rate = audio.frame_rate

            # Convert to numpy array (int16)
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)

            # Normalize to 0-1 range
            if len(samples) > 0:
                max_val = np.max(np.abs(samples))
                if max_val > 0:
                    samples = np.abs(samples) / max_val
                else:
                    samples = np.zeros_like(samples)

            return sample_rate, samples

        except Exception as e:
            logger.warning(f"Failed to load audio amplitude: {e}")
            # Return dummy data if audio loading fails
            return 44100, np.zeros(44100)

    def get_amplitude(self, t: float, rate: int, audio_data: np.ndarray) -> float:
        """
        Get normalized amplitude at time t.

        Args:
            t: Time in seconds
            rate: Sample rate
            audio_data: Amplitude data array

        Returns:
            Normalized amplitude (0-1)
        """
        if len(audio_data) == 0:
            return 0.0

        # Convert time to sample index
        center_idx = int(t * rate)

        # Calculate window size in samples
        window_samples = int(self.window_ms * rate / 1000)

        # Get window around center
        start_idx = max(0, center_idx - window_samples // 2)
        end_idx = min(len(audio_data), center_idx + window_samples // 2)

        if start_idx >= end_idx:
            return 0.0

        # Calculate RMS amplitude in window
        window = audio_data[start_idx:end_idx]
        rms = np.sqrt(np.mean(window ** 2))

        return float(rms)

    def animate_clip(
        self,
        character_clip: Any,
        audio_path: str,
        base_x: int,
        base_y: int
    ) -> Any:
        """
        Apply audio-reactive animation to character clip.

        Args:
            character_clip: MoviePy ImageClip
            audio_path: Path to audio file for amplitude analysis
            base_x: Base X position
            base_y: Base Y position

        Returns:
            Animated clip with reactive position
        """
        if self.animation_type == "none":
            # No animation, return static position
            return character_clip.set_position((base_x, base_y))

        try:
            # Load audio amplitude data
            rate, audio_data = self.load_audio_amplitude(audio_path)

            # Create position function that responds to audio
            def position_func(t):
                amplitude = self.get_amplitude(t, rate, audio_data)
                # Scale amplitude to bounce range
                bounce = int(amplitude * self.bounce_pixels)
                # Move up when amplitude is high (subtract from y)
                return (base_x, base_y - bounce)

            # Apply position function to clip
            return character_clip.set_position(position_func)

        except Exception as e:
            logger.warning(f"Animation failed, using static position: {e}")
            return character_clip.set_position((base_x, base_y))
