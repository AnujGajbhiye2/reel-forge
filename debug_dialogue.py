#!/usr/bin/env python3
"""Debug script to see raw Gemini dialogue output"""

from reelforge.utils import load_config
from reelforge.script_generator import ScriptGenerator

config = load_config()
generator = ScriptGenerator(config)

# Generate but catch the response before parsing
from reelforge.templates.script_prompts import DIALOGUE_PROMPT

prompt = DIALOGUE_PROMPT.format(
    topic="ChatGPT vs Claude",
    details="Comparing the two leading AI assistants"
)

response = generator.client.chat.completions.create(
    model=generator.model,
    messages=[
        {
            "role": "system",
            "content": "You are a viral short-form content scriptwriter specializing in AI and tech topics."
        },
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=generator.temperature,
    max_tokens=generator.max_tokens
)

raw_text = response.choices[0].message.content.strip()

print("="*60)
print("RAW GEMINI OUTPUT:")
print("="*60)
print(raw_text)
print("\n" + "="*60)
print("CLEANED OUTPUT:")
print("="*60)
cleaned = generator._clean_script_response(raw_text)
print(cleaned)
print("\n" + "="*60)
print("PARSED OUTPUT:")
print("="*60)
parsed = generator.parse_dialogue(cleaned)
print(parsed)
