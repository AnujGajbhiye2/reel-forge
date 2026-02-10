"""
Expression mapping for character pose switching based on dialogue content.
"""

from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


# Keywords that trigger specific expressions
EXPRESSION_KEYWORDS = {
    "surprised": ["what", "really", "no way", "wait", "seriously", "whoa", "omg", "damn"],
    "happy": ["amazing", "awesome", "love", "great", "perfect", "nice", "fantastic", "cool"],
    "explaining": ["because", "actually", "basically", "means", "works", "so", "therefore", "see"],
    "smug": ["told you", "obviously", "easy", "simple", "better", "duh", "clearly"],
}


def get_expression(line: str, speaker: str, available_poses: List[str]) -> str:
    """
    Determine expression/pose based on dialogue line content.

    Args:
        line: Dialogue line text
        speaker: Speaker ID (A or B)
        available_poses: List of available pose names for this character

    Returns:
        Pose name to use (defaults to "talking" or "neutral" if available)
    """
    line_lower = line.lower()

    # Check for keyword matches
    for expression, keywords in EXPRESSION_KEYWORDS.items():
        if expression in available_poses:
            for keyword in keywords:
                if keyword in line_lower:
                    return expression

    # Default to talking if available, otherwise neutral
    if "talking" in available_poses:
        return "talking"
    elif "neutral" in available_poses:
        return "neutral"
    elif available_poses:
        return available_poses[0]

    return "neutral"


def scan_character_poses(character_dir: Path) -> List[str]:
    """
    Scan character directory for available pose files.

    Args:
        character_dir: Path to character directory

    Returns:
        List of pose names (without .png extension)
    """
    if not character_dir.exists() or not character_dir.is_dir():
        logger.warning(f"Character directory not found: {character_dir}")
        return []

    poses = []
    for file in character_dir.glob("*.png"):
        pose_name = file.stem
        poses.append(pose_name)

    logger.debug(f"Found {len(poses)} poses in {character_dir}: {poses}")
    return poses


def get_character_pose_path(
    character_dir: Path,
    pose_name: str,
    available_poses: List[str]
) -> Optional[Path]:
    """
    Get path to specific character pose file.

    Args:
        character_dir: Path to character directory
        pose_name: Desired pose name
        available_poses: List of available poses

    Returns:
        Path to pose file, or None if not found
    """
    if pose_name in available_poses:
        pose_path = character_dir / f"{pose_name}.png"
        if pose_path.exists():
            return pose_path

    # Fallback to first available pose
    if available_poses:
        fallback_path = character_dir / f"{available_poses[0]}.png"
        if fallback_path.exists():
            logger.debug(f"Pose '{pose_name}' not found, using fallback: {available_poses[0]}")
            return fallback_path

    return None
