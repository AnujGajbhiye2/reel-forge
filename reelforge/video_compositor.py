"""
Video composition and rendering using MoviePy.
"""

import os
import random
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    from moviepy import VideoFileClip, AudioFileClip, ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips


class VideoCompositor:
    """
    Composes final video from background, audio, captions, and character overlays.

    This module handles:
    - Background video selection and processing
    - Audio track integration
    - Caption overlay
    - Character image overlay
    - Final video rendering
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the video compositor.

        Args:
            config: Configuration dictionary containing video settings
        """
        self.config = config
        self.resolution = (
            config['video']['resolution']['width'],
            config['video']['resolution']['height']
        )
        self.fps = config['video']['fps']
        self.duration = config['video']['duration']
        self.backgrounds = config['assets']['backgrounds']
        self.characters = config['assets']['characters']

    def select_background(self, seed: Optional[int] = None) -> str:
        """
        Select a random background video.

        Args:
            seed: Optional random seed for reproducibility

        Returns:
            Path to selected background video
        """
        if seed is not None:
            random.seed(seed)

        available = [bg for bg in self.backgrounds if os.path.exists(bg)]

        if not available:
            raise FileNotFoundError("No background videos found")

        return random.choice(available)

    def process_background(
        self,
        background_path: str,
        duration: float
    ) -> VideoFileClip:
        """
        Process background video (crop to 9:16, loop if needed, trim to duration).

        Args:
            background_path: Path to background video
            duration: Target duration in seconds

        Returns:
            MoviePy VideoClip object
        """
        bg = VideoFileClip(background_path)

        # Calculate crop for 9:16 aspect ratio
        target_aspect = 9 / 16
        current_aspect = bg.h / bg.w

        if current_aspect > target_aspect:
            # Video is taller, crop height
            new_h = int(bg.w * target_aspect)
            y_center = bg.h // 2
            bg = bg.cropped(y1=y_center - new_h // 2, y2=y_center + new_h // 2)
        else:
            # Video is wider, crop width
            new_w = int(bg.h / target_aspect)
            x_center = bg.w // 2
            bg = bg.cropped(x1=x_center - new_w // 2, x2=x_center + new_w // 2)

        # Resize to target resolution
        bg = bg.resized(self.resolution)

        # Loop if necessary
        if bg.duration < duration:
            loops_needed = int(duration / bg.duration) + 1
            bg = concatenate_videoclips([bg] * loops_needed)

        # Trim to exact duration
        bg = bg.subclipped(0, duration)

        return bg

    def create_caption_clips(
        self,
        captions: List[Dict[str, Any]],
        font_path: str
    ) -> List[TextClip]:
        """
        Create text clips from caption data.

        Args:
            captions: Formatted caption data with 'text', 'start', 'end'
            font_path: Path to font file

        Returns:
            List of TextClip objects
        """
        clips = []

        for caption in captions:
            txt = TextClip(
                text=caption['text'].upper(),
                font=font_path,
                font_size=self.config['captions']['font_size'],
                color=self.config['captions']['font_color'],
                stroke_color=self.config['captions']['stroke_color'],
                stroke_width=self.config['captions']['stroke_width'],
                method='caption',
                size=(self.resolution[0] - 100, None),
                text_align='center'
            )

            # Position
            position = self.config['captions'].get('position', 'center')
            if position == 'center':
                pos = ('center', 'center')
            elif position == 'top':
                pos = ('center', 100)
            else:  # bottom
                pos = ('center', self.resolution[1] - 300)

            txt = txt.with_position(pos).with_start(caption['start']).with_duration(caption['end'] - caption['start'])
            clips.append(txt)

        return clips

    def compose_video(
        self,
        audio_path: str,
        captions_data: List[Dict[str, Any]],
        output_path: str = "output/video.mp4",
        background_path: Optional[str] = None,
        character_path: Optional[str] = None
    ) -> Path:
        """
        Compose final video from all components.

        Args:
            audio_path: Path to audio file
            captions_data: Caption data (from CaptionGenerator)
            output_path: Path for output video
            background_path: Optional specific background (random if None)
            character_path: Optional character overlay

        Returns:
            Path to rendered video file
        """
        try:
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

            # Load audio to get duration
            audio = AudioFileClip(audio_path)
            duration = audio.duration

            # Select and process background
            if background_path is None:
                background_path = self.select_background()

            print(f"Using background: {os.path.basename(background_path)}")
            bg_clip = self.process_background(background_path, duration)

            # Create caption clips
            font_path = self.config['assets']['fonts']['main']
            caption_clips = self.create_caption_clips(captions_data, font_path)

            # Combine all layers
            all_clips = [bg_clip] + caption_clips

            # Add character if provided
            if character_path and os.path.exists(character_path):
                char = ImageClip(character_path).with_duration(duration)
                char = char.resized(height=400)
                char = char.with_position(('center', self.resolution[1] - 450))
                all_clips.insert(1, char)  # Add after background, before captions

            # Composite
            final = CompositeVideoClip(all_clips, size=self.resolution)
            final = final.with_audio(audio)

            # Render
            print(f"Rendering video...")
            final.write_videofile(
                output_path,
                fps=self.fps,
                codec=self.config['output']['codec'],
                audio_codec=self.config['output']['audio_codec'],
                preset='medium',
                threads=4
            )

            # Cleanup
            final.close()
            bg_clip.close()
            audio.close()
            for clip in caption_clips:
                clip.close()

            return Path(output_path)

        except Exception as e:
            raise Exception(f"Video composition failed: {str(e)}")
