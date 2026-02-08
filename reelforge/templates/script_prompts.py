"""
Prompt templates for script generation.
"""

SOLO_NARRATOR_PROMPT = """You are a viral social media content writer specializing in tech and AI topics.

Create a SHORT 60-second script for a faceless reel on the following topic:
{topic}

STRICT LENGTH REQUIREMENTS:
- MAXIMUM 140 words total (this is CRITICAL - more than 140 words will NOT fit in 60 seconds)
- MINIMUM 110 words total (shorter scripts sound incomplete and under 45 seconds)
- Count every word carefully
- Each sentence should be 5-12 words MAX
- Total: 10-15 sentences

Requirements:
- Write ONLY the narrator's dialogue
- Hook in first 3 seconds (under 10 words)
- FAST-PACED, punchy delivery
- Use simple, conversational language
- Include ONE surprising fact or counterintuitive insight
- End with a strong call-to-action (under 10 words)
- NO stage directions, NO scene descriptions, NO bullet points
- Format: Just the spoken words, separated by newlines for natural pauses

Topic details:
{details}

Write the script now (BETWEEN 110 AND 140 WORDS):"""

DIALOGUE_PROMPT = """You are a viral social media content writer specializing in tech and AI topics.

Create a SHORT 60-second dialogue script for a faceless reel on the following topic:
{topic}

STRICT LENGTH REQUIREMENTS:
- MAXIMUM 130 words total (this is CRITICAL - more than 130 words will NOT fit in 60 seconds)
- MINIMUM 100 words total (shorter scripts often produce under-45-second reels)
- Count every word carefully
- Target: 10-14 total lines
- STRICT alternating format: A then B then A then B
- Each A line should be 5-10 words
- Each B line should be 10-16 words

Requirements:
- Two characters having a conversation
- Character A: Curious/skeptical
- Character B: Knowledgeable/enthusiastic
- Hook in first 3 seconds (under 10 words)
- FAST-PACED, punchy dialogue
- Use simple, conversational language
- Include ONE surprising fact
- End with a strong punchline (under 15 words)

CRITICAL FORMATTING:
- Output ONLY the dialogue lines, nothing else
- NO introductions, NO "Here's the script", NO scene descriptions
- Format: Each line must start with A: or B:
- Example format:
  A: Why is everyone using this tool?
  B: Because it's 10x faster than the competition.
  A: No way, that's insane!

Topic details:
{details}

Output the dialogue now (ONLY dialogue lines using A:/B:, BETWEEN 100 AND 130 WORDS):"""
