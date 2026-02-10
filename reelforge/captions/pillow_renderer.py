"""
Karaoke-style caption rendering using Pillow for word-by-word highlights.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.video.VideoClip import ImageClip
from typing import List, Dict, Any, Tuple
from pathlib import Path


def render_caption_frame(
    words: List[str],
    active_index: int,
    dimensions: Tuple[int, int],
    font_path: str,
    font_size: int,
    active_color: str,
    inactive_color: str,
    stroke_color: str,
    stroke_width: int
) -> np.ndarray:
    """
    Render a single caption frame with word-by-word highlighting.

    Args:
        words: List of words to render in this frame
        active_index: Index of the currently active (highlighted) word
        dimensions: (width, height) of the frame
        font_path: Path to TTF font file
        font_size: Font size in pixels
        active_color: Hex color for active word (e.g., "#FFD700" for yellow)
        inactive_color: Hex color for inactive words (e.g., "#FFFFFF" for white)
        stroke_color: Hex color for text outline (e.g., "#000000" for black)
        stroke_width: Width of text outline in pixels

    Returns:
        RGBA numpy array (H × W × 4)
    """
    width, height = dimensions

    # Create transparent RGBA image
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Load font
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        # Fallback to default font if custom font fails
        font = ImageFont.load_default()

    # Convert words to uppercase
    words_upper = [w.upper() for w in words]

    # Join words into single line
    text = " ".join(words_upper)

    # Get text bounding box for centering
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate starting X position to center text
    x = (width - text_width) // 2
    y = height // 2 - text_height // 2

    # Draw each word with conditional coloring
    current_x = x
    for i, word_upper in enumerate(words_upper):
        # Choose color based on whether word is active
        color = active_color if i == active_index else inactive_color

        # Draw word with stroke (outline)
        draw.text(
            (current_x, y),
            word_upper,
            font=font,
            fill=color,
            stroke_width=stroke_width,
            stroke_fill=stroke_color
        )

        # Calculate width of this word + space for next word position
        word_bbox = draw.textbbox((0, 0), word_upper + " ", font=font, stroke_width=stroke_width)
        word_width = word_bbox[2] - word_bbox[0]
        current_x += word_width

    # Convert PIL Image to numpy array
    return np.array(img)


def build_karaoke_clips(
    formatted_captions: List[Dict[str, Any]],
    font_path: str,
    config: Dict[str, Any],
    resolution: Tuple[int, int]
) -> List[ImageClip]:
    """
    Build karaoke-style caption clips with word-by-word highlighting.

    Args:
        formatted_captions: List of caption dicts with 'start', 'end', 'text', 'words'
        font_path: Path to TTF font file
        config: Configuration dictionary
        resolution: (width, height) of video

    Returns:
        List of positioned MoviePy ImageClip objects
    """
    caption_config = config.get("captions", {})

    # Get config values with defaults
    font_size = caption_config.get("font_size", 65)
    active_color = caption_config.get("active_color", "#FFD700")  # Yellow
    inactive_color = caption_config.get("inactive_color", "#FFFFFF")  # White
    stroke_color = caption_config.get("stroke_color", "#000000")  # Black
    stroke_width = caption_config.get("stroke_width", 4)
    words_per_group = caption_config.get("words_per_group", 3)
    position_y_ratio = caption_config.get("position_y", 0.62)

    video_width, video_height = resolution
    position_y = int(video_height * position_y_ratio)

    clips = []

    # Process each caption segment
    for caption_segment in formatted_captions:
        words_data = caption_segment.get("words", [])

        if not words_data:
            continue

        # Group words into chunks
        for group_start_idx in range(0, len(words_data), words_per_group):
            group_end_idx = min(group_start_idx + words_per_group, len(words_data))
            word_group = words_data[group_start_idx:group_end_idx]

            # Extract word text for this group
            words_text = [wd["word"] for wd in word_group]

            # Create a clip for each word in the group highlighting that word
            for local_idx, word_data in enumerate(word_group):
                word_start = word_data["start"]
                word_end = word_data["end"]

                # Render frame with this word highlighted
                frame = render_caption_frame(
                    words=words_text,
                    active_index=local_idx,
                    dimensions=(video_width, video_height),
                    font_path=font_path,
                    font_size=font_size,
                    active_color=active_color,
                    inactive_color=inactive_color,
                    stroke_color=stroke_color,
                    stroke_width=stroke_width
                )

                # Create ImageClip for this word's duration
                clip = ImageClip(frame, duration=word_end - word_start)
                clip = clip.set_start(word_start)
                clip = clip.set_position(('center', position_y))

                clips.append(clip)

    return clips
