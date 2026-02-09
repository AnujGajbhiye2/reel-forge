"""
Video composition and rendering using MoviePy.
"""

import os
import random
from typing import Dict, Any, List, Optional
from pathlib import Path

try:
    from moviepy import (
        VideoFileClip,
        AudioFileClip,
        ImageClip,
        TextClip,
        ColorClip,
        CompositeVideoClip,
        concatenate_videoclips,
    )
except Exception:  # pragma: no cover - fallback for lightweight test stubs
    try:
        from moviepy.editor import (
            VideoFileClip,
            AudioFileClip,
            ImageClip,
            TextClip,
            ColorClip,
            CompositeVideoClip,
            concatenate_videoclips,
        )
    except Exception:  # pragma: no cover - allows import when moviepy is stubbed
        def _missing_moviepy(*_args, **_kwargs):
            raise ImportError("moviepy is required for video composition operations")

        VideoFileClip = AudioFileClip = ImageClip = TextClip = ColorClip = CompositeVideoClip = _missing_moviepy

        def concatenate_videoclips(*_args, **_kwargs):
            raise ImportError("moviepy is required for video composition operations")

from reelforge.core.logging import get_logger


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
        self.logger = get_logger()
        self.last_background_path: Optional[str] = None

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
    ):
        """
        Process background video (crop to 9:16, loop if needed, trim to duration).

        Args:
            background_path: Path to background video
            duration: Target duration in seconds

        Returns:
            MoviePy VideoClip object
        """
        bg = VideoFileClip(background_path)
        framing_cfg = self.config.get("video", {}).get("framing", {})
        framing_mode = framing_cfg.get("mode", "fit_blur")

        if framing_mode == "fit_blur":
            bg = self._create_fit_blur_background(bg, duration)
        else:
            bg = self._create_center_crop_background(bg)

        # Loop if necessary
        if bg.duration < duration:
            loops_needed = int(duration / bg.duration) + 1
            bg = concatenate_videoclips([bg] * loops_needed)

        # Trim to exact duration
        bg = bg.subclipped(0, duration)

        return bg

    def _create_center_crop_background(self, clip: VideoFileClip):
        target_w, target_h = self.resolution
        x1, y1, x2, y2 = self._compute_center_crop_box(clip.w, clip.h, target_w, target_h)
        cropped = clip.cropped(x1=x1, x2=x2, y1=y1, y2=y2)
        return cropped.resized(self.resolution)

    def _create_fit_blur_background(self, clip: VideoFileClip, duration: float):
        target_w, target_h = self.resolution
        framing_cfg = self.config.get("video", {}).get("framing", {})

        fit_w, fit_h = self._compute_fit_size(clip.w, clip.h, target_w, target_h)
        fg = clip.resized((fit_w, fit_h)).with_position(("center", "center")).with_duration(duration)

        cover_w, cover_h = self._compute_cover_size(clip.w, clip.h, target_w, target_h)
        fill = clip.resized((cover_w, cover_h))
        x1, y1, x2, y2 = self._compute_center_crop_box(fill.w, fill.h, target_w, target_h)
        fill = fill.cropped(x1=x1, x2=x2, y1=y1, y2=y2).resized((target_w, target_h)).with_duration(duration)

        blur_sigma = float(framing_cfg.get("blur_sigma", 18))
        downscale = max(2, min(24, int(round(blur_sigma / 2.0))))
        fill = fill.resized((max(1, target_w // downscale), max(1, target_h // downscale))).resized((target_w, target_h))

        dim_opacity = float(framing_cfg.get("dim_opacity", 0.28))
        dim_layer = ColorClip(size=(target_w, target_h), color=(0, 0, 0)).with_opacity(dim_opacity).with_duration(duration)

        return CompositeVideoClip([fill, dim_layer, fg], size=self.resolution).with_duration(duration)

    @staticmethod
    def _compute_center_crop_box(src_w: int, src_h: int, target_w: int, target_h: int):
        src_aspect = src_w / float(src_h)
        target_aspect = target_w / float(target_h)

        if src_aspect > target_aspect:
            crop_w = int(src_h * target_aspect)
            x1 = max(0, (src_w - crop_w) // 2)
            return x1, 0, x1 + crop_w, src_h

        crop_h = int(src_w / target_aspect)
        y1 = max(0, (src_h - crop_h) // 2)
        return 0, y1, src_w, y1 + crop_h

    @staticmethod
    def _compute_fit_size(src_w: int, src_h: int, target_w: int, target_h: int):
        scale = min(target_w / float(src_w), target_h / float(src_h))
        return max(1, int(src_w * scale)), max(1, int(src_h * scale))

    @staticmethod
    def _compute_cover_size(src_w: int, src_h: int, target_w: int, target_h: int):
        scale = max(target_w / float(src_w), target_h / float(src_h))
        return max(1, int(src_w * scale)), max(1, int(src_h * scale))

    @staticmethod
    def _clamp_caption_y(
        requested_y: int,
        text_h: int,
        top_bound: int,
        bottom_bound: int,
    ) -> int:
        max_y = max(top_bound, bottom_bound - text_h)
        return max(top_bound, min(requested_y, max_y))

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

        safe_zone = self.config.get("captions", {}).get("safe_zone", {})
        top_margin = int(safe_zone.get("top_margin_px", 120))
        bottom_margin = int(safe_zone.get("bottom_margin_px", 300))
        side_margin = int(safe_zone.get("side_margin_px", 80))
        anchor = safe_zone.get("anchor", "upper_middle")
        top_reserved = int(self.config.get("video", {}).get("layout", {}).get("top_reserved_px", 0))
        top_bound = max(top_reserved, top_margin)
        bottom_bound = self.resolution[1] - bottom_margin

        for caption in captions:
            txt = TextClip(
                text=caption['text'].upper(),
                font=font_path,
                font_size=self.config['captions']['font_size'],
                color=self.config['captions']['font_color'],
                stroke_color=self.config['captions']['stroke_color'],
                stroke_width=self.config['captions']['stroke_width'],
                method='caption',
                size=(self.resolution[0] - (2 * side_margin), None),
                margin=(24, 16),
                text_align='center'
            )

            # Position
            position = self.config['captions'].get('position', 'center')
            if anchor == "upper_middle":
                usable_height = max(0, bottom_bound - top_bound - txt.h)
                proposed_y = top_bound + int(usable_height * 0.56)
                y = self._clamp_caption_y(proposed_y, txt.h, top_bound, bottom_bound)
                pos = ('center', y)
            elif position == 'center':
                proposed_y = (self.resolution[1] - txt.h) // 2
                y = self._clamp_caption_y(proposed_y, txt.h, top_bound, bottom_bound)
                pos = ('center', y)
            elif position == 'top':
                y = self._clamp_caption_y(top_bound, txt.h, top_bound, bottom_bound)
                pos = ('center', y)
            else:  # bottom
                proposed_y = bottom_bound - txt.h
                y = self._clamp_caption_y(proposed_y, txt.h, top_bound, bottom_bound)
                pos = ('center', y)

            txt = txt.with_position(pos).with_start(caption['start']).with_duration(caption['end'] - caption['start'])
            clips.append(txt)

        return clips

    @staticmethod
    def _set_opacity(clip: ImageClip, value: float) -> ImageClip:
        """Compatibility helper across MoviePy versions."""
        if hasattr(clip, "with_opacity"):
            return clip.with_opacity(value)
        return clip.set_opacity(value)

    def _create_dialogue_character_clips(
        self,
        character_a_path: str,
        character_b_path: str,
        speaker_timeline: List[Dict[str, Any]],
        duration: float
    ) -> List[ImageClip]:
        """
        Create left/right character overlays with active-speaker emphasis.
        """
        char_cfg = self.config.get("video", {}).get("characters", {})
        left_x_ratio = float(char_cfg.get("left_x_ratio", 0.08))
        right_x_ratio = float(char_cfg.get("right_x_ratio", 0.60))
        bottom_y = int(char_cfg.get("bottom_y_px", 420))
        active_opacity = float(char_cfg.get("active_opacity", 1.0))
        inactive_opacity = float(char_cfg.get("inactive_opacity", 0.08))
        inactive_mode = str(char_cfg.get("inactive_mode", "hidden")).strip().lower()

        speakers = []
        for segment in speaker_timeline:
            spk = segment.get("speaker")
            if spk and spk not in speakers:
                speakers.append(spk)
        primary_speaker = speakers[0] if speakers else None
        secondary_speaker = speakers[1] if len(speakers) > 1 else None

        overlays: List[ImageClip] = []

        for segment in speaker_timeline:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", 0.0))
            clip_duration = max(0.01, min(duration, end) - start)
            if clip_duration <= 0:
                continue

            active_speaker = segment.get("speaker")

            left = ImageClip(character_a_path).with_start(start).with_duration(clip_duration).resized(height=420)
            left = left.with_position((int(self.resolution[0] * left_x_ratio), self.resolution[1] - bottom_y))
            left_active = active_speaker == primary_speaker
            if left_active:
                overlays.append(self._set_opacity(left, active_opacity))
            elif inactive_mode != "hidden":
                overlays.append(self._set_opacity(left, inactive_opacity))

            right = ImageClip(character_b_path).with_start(start).with_duration(clip_duration).resized(height=420)
            right = right.with_position((int(self.resolution[0] * right_x_ratio), self.resolution[1] - bottom_y))
            right_active = active_speaker == secondary_speaker or (secondary_speaker is None and active_speaker != primary_speaker)
            if right_active:
                overlays.append(self._set_opacity(right, active_opacity))
            elif inactive_mode != "hidden":
                overlays.append(self._set_opacity(right, inactive_opacity))

        return overlays

    def create_screenshot_clips(
        self,
        screenshots_data: List[Dict[str, Any]],
        duration: float,
    ) -> List[ImageClip]:
        """
        Create timed screenshot card overlays.
        """
        if not screenshots_data:
            return []

        overlay_cfg = self.config.get("research", {}).get("overlay", {})
        width_ratio = float(overlay_cfg.get("width_ratio", 0.78))
        y_px = int(overlay_cfg.get("y_px", self.config.get("video", {}).get("layout", {}).get("top_reserved_px", 420) - 280))
        crossfade_sec = float(overlay_cfg.get("crossfade_sec", 0.2))

        card_w = max(1, int(self.resolution[0] * width_ratio))
        clips: List[ImageClip] = []

        for shot in screenshots_data:
            if shot.get("status") != "ok":
                continue
            image_path = shot.get("file")
            if not image_path or not os.path.exists(image_path):
                continue

            start = max(0.0, float(shot.get("start", 0.0)))
            end = min(float(duration), float(shot.get("end", duration)))
            clip_duration = max(0.01, end - start)
            if clip_duration <= 0:
                continue

            image = ImageClip(image_path).resized(width=card_w)
            x = (self.resolution[0] - image.w) // 2
            y = max(40, y_px)
            image = image.with_position((x, y)).with_start(start).with_duration(clip_duration)
            if hasattr(image, "with_opacity"):
                image = image.with_opacity(1.0)
            if crossfade_sec > 0 and hasattr(image, "crossfadein") and hasattr(image, "crossfadeout"):
                image = image.crossfadein(crossfade_sec).crossfadeout(crossfade_sec)

            shadow = ColorClip(
                size=(image.w + 26, image.h + 26),
                color=(0, 0, 0),
            ).with_opacity(0.28).with_position((x - 6, y + 10)).with_start(start).with_duration(clip_duration)
            panel = ColorClip(
                size=(image.w + 14, image.h + 14),
                color=(18, 18, 18),
            ).with_opacity(0.55).with_position((x - 7, y - 7)).with_start(start).with_duration(clip_duration)

            clips.extend([shadow, panel, image])

        return clips

    def compose_video(
        self,
        audio_path: str,
        captions_data: List[Dict[str, Any]],
        output_path: str = "output/video.mp4",
        background_path: Optional[str] = None,
        character_path: Optional[str] = None,
        secondary_character_path: Optional[str] = None,
        speaker_timeline: Optional[List[Dict[str, Any]]] = None,
        screenshots_data: Optional[List[Dict[str, Any]]] = None,
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
            self.last_background_path = background_path

            self.logger.info("Using background: %s", os.path.basename(background_path))
            framing_mode = self.config.get("video", {}).get("framing", {}).get("mode", "fit_blur")
            top_reserved = int(self.config.get("video", {}).get("layout", {}).get("top_reserved_px", 0))
            inactive_mode = self.config.get("video", {}).get("characters", {}).get("inactive_mode", "hidden")
            self.logger.info(
                "Compositor layout settings: framing=%s, top_reserved_px=%d, inactive_mode=%s",
                framing_mode,
                top_reserved,
                inactive_mode,
            )
            bg_clip = self.process_background(background_path, duration)

            # Create caption clips
            font_path = self.config['assets']['fonts']['main']
            caption_clips = self.create_caption_clips(captions_data, font_path)

            # Combine all layers
            all_clips = [bg_clip] + caption_clips
            character_clips: List[ImageClip] = []
            screenshot_clips: List[ImageClip] = []

            if (
                character_path
                and secondary_character_path
                and os.path.exists(character_path)
                and os.path.exists(secondary_character_path)
                and speaker_timeline
            ):
                character_clips = self._create_dialogue_character_clips(
                    character_path,
                    secondary_character_path,
                    speaker_timeline,
                    duration
                )
                all_clips = [bg_clip] + character_clips + caption_clips
            elif character_path and os.path.exists(character_path):
                char = ImageClip(character_path).with_duration(duration)
                char = char.resized(height=400)
                char = char.with_position(('center', self.resolution[1] - 450))
                character_clips = [char]
                all_clips.insert(1, char)  # Add after background, before captions

            if screenshots_data:
                screenshot_clips = self.create_screenshot_clips(screenshots_data, duration)
                if screenshot_clips:
                    all_clips = [bg_clip] + character_clips + screenshot_clips + caption_clips

            # Composite
            final = CompositeVideoClip(all_clips, size=self.resolution)
            final = final.with_audio(audio)

            # Render
            self.logger.info("Rendering video to %s", output_path)
            final.write_videofile(
                output_path,
                fps=self.fps,
                codec=self.config['output']['codec'],
                audio_codec=self.config['output']['audio_codec'],
                preset='medium',
                threads=4,
                logger=None,
            )

            # Cleanup
            final.close()
            bg_clip.close()
            audio.close()
            for clip in caption_clips:
                clip.close()
            for clip in character_clips:
                clip.close()
            for clip in screenshot_clips:
                clip.close()

            return Path(output_path)

        except Exception as e:
            raise Exception(f"Video composition failed: {str(e)}")
