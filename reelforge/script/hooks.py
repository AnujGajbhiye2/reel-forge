"""
Hook templates and CTAs for viral short-form content.
"""

import random
from typing import List


# Hook templates organized by type
HOOK_TEMPLATES = {
    "curiosity_gap": [
        "Nobody's talking about this AI that {capability}",
        "There's a secret {thing} that {result}",
        "I found an AI tool that {impressive_action}",
        "This changes everything about {topic}",
        "You won't believe what this AI just did",
    ],
    "negative_hook": [
        "STOP using {old_thing} right now",
        "Delete {popular_tool} immediately",
        "If you're still using {thing}, you're doing it wrong",
        "This is why {thing} is actually terrible",
        "Everyone's making this mistake with {topic}",
    ],
    "bold_claim": [
        "This free AI is better than {expensive_tool}",
        "{new_thing} just replaced {old_thing}",
        "This will make {profession} obsolete",
        "{tool} is 10x faster than {competitor}",
        "I tested {thing} for 30 days and here's what happened",
    ],
    "controversy": [
        "Programmers are going to hate this",
        "This is illegal in most companies",
        "{big_company} doesn't want you to know this",
        "I got fired for using this AI tool",
        "This violates {platform}'s terms of service",
    ],
    "comparison": [
        "{tool_a} vs {tool_b}: the winner is shocking",
        "I tried all the {category} tools so you don't have to",
        "Ranking every {thing} from worst to best",
        "{new_tool} destroys {old_tool} in every test",
        "The ultimate {category} tier list",
    ],
}


# Call-to-action templates
CTA_TEMPLATES = {
    "comment_bait": [
        "Which one would you pick? Comment below.",
        "Let me know in the comments which {option} you prefer",
        "Drop your favorite {thing} in the comments",
        "Am I wrong? Tell me in the comments",
        "What did I miss? Comment your picks",
    ],
    "follow_bait": [
        "Follow for part 2",
        "Follow me for more {topic} content",
        "Part 2 dropping tomorrow, follow so you don't miss it",
        "I'm testing {thing} next, follow to see the results",
        "Follow for the full tutorial",
    ],
    "save_bait": [
        "Save this before it gets taken down",
        "Bookmark this for later, you'll need it",
        "Save this list, trust me",
        "You'll want to come back to this",
    ],
    "engagement": [
        "Like if you agree",
        "Share this with someone who needs to see it",
        "Tag someone who still uses {old_thing}",
        "Send this to your {role} friend",
    ],
}


def get_random_hooks(category: str, count: int = 3) -> List[str]:
    """
    Get random hook templates from a specific category.

    Args:
        category: Hook category (curiosity_gap, negative_hook, bold_claim, etc.)
        count: Number of hooks to return

    Returns:
        List of hook template strings
    """
    if category not in HOOK_TEMPLATES:
        raise ValueError(f"Unknown hook category: {category}")

    hooks = HOOK_TEMPLATES[category]
    return random.sample(hooks, min(count, len(hooks)))


def get_random_ctas(category: str, count: int = 2) -> List[str]:
    """
    Get random CTA templates from a specific category.

    Args:
        category: CTA category (comment_bait, follow_bait, save_bait, engagement)
        count: Number of CTAs to return

    Returns:
        List of CTA template strings
    """
    if category not in CTA_TEMPLATES:
        raise ValueError(f"Unknown CTA category: {category}")

    ctas = CTA_TEMPLATES[category]
    return random.sample(ctas, min(count, len(ctas)))


def get_all_hook_categories() -> List[str]:
    """Get list of all available hook categories."""
    return list(HOOK_TEMPLATES.keys())


def get_all_cta_categories() -> List[str]:
    """Get list of all available CTA categories."""
    return list(CTA_TEMPLATES.keys())
