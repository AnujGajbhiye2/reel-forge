"""
Audio mixing for background music and sound effects.
"""

import os
import random
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydub import AudioSegment
import logging

logger = logging.getLogger(__name__)


class AudioMixer:
    """
    Mixes voiceover audio with background music and sound effects.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the audio mixer.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.sfx_dir = Path(config.get("paths", {}).get("sfx_dir", "assets/sfx"))
        self.music_dir = Path(config.get("paths", {}).get("music_dir", "assets/music"))
        self.music_volume_db = config.get("audio", {}).get("music_volume_db", -18)
        self.sfx_volume_db = config.get("audio", {}).get("sfx_volume_db", -6)

    def mix(
        self,
        voiceover_path: str,
        output_path: str,
        sfx_cues: Optional[List[Dict[str, Any]]] = None,
        add_music: bool = True,
    ) -> str:
        """
        Mix voiceover with background music and sound effects.

        Args:
            voiceover_path: Path to voiceover audio file
            output_path: Path to save mixed audio
            sfx_cues: List of SFX cues [{"type": "whoosh", "time_ms": 5000}, ...]
            add_music: Whether to add background music

        Returns:
            Path to output file
        """
        try:
            # Load voiceover
            voiceover = AudioSegment.from_file(voiceover_path)
            duration_ms = len(voiceover)

            mixed = voiceover

            # Add background music if enabled
            if add_music:
                music_track = self._get_random_music()
                if music_track:
                    try:
                        music = AudioSegment.from_file(music_track)

                        # Adjust volume
                        music = music + self.music_volume_db

                        # Loop music to match voiceover duration
                        if len(music) < duration_ms:
                            loops_needed = (duration_ms // len(music)) + 1
                            music = music * loops_needed

                        # Trim to match duration
                        music = music[:duration_ms]

                        # Add fade in/out
                        music = music.fade_in(2000).fade_out(3000)

                        # Overlay music under voiceover
                        mixed = voiceover.overlay(music)
                        logger.info(f"Added background music: {music_track.name}")
                    except Exception as e:
                        logger.warning(f"Failed to add background music: {e}")

            # Add sound effects
            if sfx_cues:
                for cue in sfx_cues:
                    sfx_type = cue.get("type", "pop")
                    time_ms = cue.get("time_ms", 0)

                    if time_ms < 0 or time_ms >= duration_ms:
                        continue

                    sfx_file = self._get_random_sfx(sfx_type)
                    if sfx_file:
                        try:
                            sfx = AudioSegment.from_file(sfx_file)
                            sfx = sfx + self.sfx_volume_db
                            mixed = mixed.overlay(sfx, position=time_ms)
                            logger.debug(f"Added {sfx_type} SFX at {time_ms}ms")
                        except Exception as e:
                            logger.warning(f"Failed to add SFX {sfx_type}: {e}")

            # Export mixed audio
            mixed.export(output_path, format="mp3")
            logger.info(f"Audio mixing complete: {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"Audio mixing failed: {e}")
            # If mixing fails, just copy the original voiceover
            import shutil
            shutil.copy(voiceover_path, output_path)
            return output_path

    def _get_random_music(self) -> Optional[Path]:
        """Get a random background music track."""
        if not self.music_dir.exists():
            logger.warning(f"Music directory not found: {self.music_dir}")
            return None

        music_files = list(self.music_dir.glob("*.mp3")) + list(self.music_dir.glob("*.wav"))
        if not music_files:
            logger.warning(f"No music files found in {self.music_dir}")
            return None

        return random.choice(music_files)

    def _get_random_sfx(self, sfx_type: str) -> Optional[Path]:
        """Get a random sound effect of the specified type."""
        sfx_subdir = self.sfx_dir / sfx_type

        if not sfx_subdir.exists():
            logger.warning(f"SFX directory not found: {sfx_subdir}")
            return None

        sfx_files = list(sfx_subdir.glob("*.mp3")) + list(sfx_subdir.glob("*.wav"))
        if not sfx_files:
            logger.warning(f"No {sfx_type} SFX files found in {sfx_subdir}")
            return None

        return random.choice(sfx_files)
