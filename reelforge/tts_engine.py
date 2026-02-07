"""
Text-to-speech engine using EdgeTTS.
"""

import asyncio
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
import edge_tts

try:
    from moviepy.editor import AudioFileClip, concatenate_audioclips
except ImportError:
    from moviepy import AudioFileClip, concatenate_audioclips


class TTSEngine:
    """
    Text-to-speech synthesis using Microsoft EdgeTTS.

    This module handles:
    - Converting text to speech using EdgeTTS
    - Support for multiple voices
    - Voice parameter customization (rate, pitch)
    - Audio file generation
    - Dialogue synthesis with multiple voices
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the TTS engine.

        Args:
            config: Configuration dictionary containing TTS settings
        """
        self.config = config
        self.voice = config['tts']['voice']
        self.rate = config['tts'].get('rate', '+0%')
        self.pitch = config['tts'].get('pitch', '+0Hz')

    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> Path:
        """
        Synthesize speech from text using EdgeTTS.

        Args:
            text: Text to convert to speech
            output_path: Path to save audio file
            voice: Optional voice override (uses config default if not provided)
            rate: Optional rate override (e.g., "+10%", "-5%")
            pitch: Optional pitch override (e.g., "+5Hz", "-10Hz")

        Returns:
            Path to generated audio file

        Raises:
            Exception: If TTS synthesis fails
        """
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        # Use provided parameters or fall back to config defaults
        voice_to_use = voice or self.voice
        rate_to_use = rate or self.rate
        pitch_to_use = pitch or self.pitch

        try:
            # Create EdgeTTS communicate object
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_to_use,
                rate=rate_to_use,
                pitch=pitch_to_use
            )

            # Save audio file
            await communicate.save(output_path)

            return Path(output_path)

        except Exception as e:
            raise Exception(f"TTS synthesis failed: {str(e)}")

    def synthesize_sync(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None
    ) -> Path:
        """
        Synchronous wrapper for synthesize().

        Args:
            text: Text to convert to speech
            output_path: Path to save audio file
            voice: Optional voice override
            rate: Optional rate override
            pitch: Optional pitch override

        Returns:
            Path to generated audio file
        """
        return asyncio.run(self.synthesize(text, output_path, voice, rate, pitch))

    async def synthesize_dialogue(
        self,
        dialogue: Dict[str, list],
        output_path: str,
        voice_mapping: Optional[Dict[str, str]] = None
    ) -> Path:
        """
        Synthesize dialogue with different voices for each character.

        Creates individual audio files for each line, then concatenates them
        into a single audio file with proper timing.

        Args:
            dialogue: Dictionary mapping character names to their lines
            output_path: Path to save final concatenated audio file
            voice_mapping: Optional mapping of character names to voice IDs
                          Example: {"A": "en-US-GuyNeural", "B": "en-US-JennyNeural"}

        Returns:
            Path to generated audio file

        Raises:
            Exception: If TTS synthesis fails
        """
        # Default voice mapping if not provided
        if voice_mapping is None:
            voice_mapping = {
                "A": "en-US-GuyNeural",      # Male voice for character A
                "B": "en-US-JennyNeural",    # Female voice for character B
            }

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path) or '.'
        os.makedirs(output_dir, exist_ok=True)

        # Create temp directory for individual line audio files
        temp_dir = os.path.join(output_dir, 'temp_dialogue')
        os.makedirs(temp_dir, exist_ok=True)

        try:
            # Generate audio for each line
            temp_files = []
            audio_clips = []

            # Get all characters and interleave their lines
            all_chars = list(dialogue.keys())
            max_lines = max(len(lines) for lines in dialogue.values())

            line_index = 0
            for i in range(max_lines):
                for char in all_chars:
                    if i < len(dialogue[char]):
                        text = dialogue[char][i]
                        voice = voice_mapping.get(char, self.voice)

                        # Create temp file for this line
                        temp_file = os.path.join(temp_dir, f'line_{line_index:03d}.mp3')
                        temp_files.append(temp_file)

                        # Synthesize this line
                        await self.synthesize(text, temp_file, voice=voice)

                        # Load audio clip
                        audio_clips.append(AudioFileClip(temp_file))

                        line_index += 1

            # Concatenate all audio clips
            final_audio = concatenate_audioclips(audio_clips)
            final_audio.write_audiofile(output_path, codec='mp3')

            # Clean up
            final_audio.close()
            for clip in audio_clips:
                clip.close()

            # Remove temp files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

            # Remove temp directory if empty
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)

            return Path(output_path)

        except Exception as e:
            raise Exception(f"Dialogue TTS synthesis failed: {str(e)}")

    def synthesize_dialogue_sync(
        self,
        dialogue: Dict[str, list],
        output_path: str,
        voice_mapping: Optional[Dict[str, str]] = None
    ) -> Path:
        """
        Synchronous wrapper for synthesize_dialogue().

        Args:
            dialogue: Dictionary mapping character names to their lines
            output_path: Path to save final audio file
            voice_mapping: Optional voice mapping

        Returns:
            Path to generated audio file
        """
        return asyncio.run(self.synthesize_dialogue(dialogue, output_path, voice_mapping))

    @staticmethod
    async def list_voices() -> List[Dict[str, str]]:
        """
        List all available EdgeTTS voices.

        Returns:
            List of voice dictionaries with 'Name', 'Gender', 'Locale' keys
        """
        voices = await edge_tts.list_voices()
        return voices

    @staticmethod
    def list_voices_sync() -> List[Dict[str, str]]:
        """
        Synchronous wrapper for list_voices().

        Returns:
            List of voice dictionaries
        """
        return asyncio.run(TTSEngine.list_voices())

    @staticmethod
    def get_english_voices() -> List[Dict[str, str]]:
        """
        Get only English voices from EdgeTTS.

        Returns:
            List of English voice dictionaries
        """
        all_voices = TTSEngine.list_voices_sync()
        return [v for v in all_voices if v['Locale'].startswith('en-')]
