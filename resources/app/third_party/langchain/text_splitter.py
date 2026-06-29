# text_splitter.py
from __future__ import annotations

import re
from typing import List

# Split AFTER 。！？!? or at one-or-more newlines; consume trailing whitespace
_SPLIT_RE = re.compile(r'(?<=[。！？!?])\s*|\n+')


def split_into_scenes(text: str, max_chars: int = 200) -> List[str]:
    """
    Split text into storyboard scene groups (1–2 sentences each).

    Rules:
    - Sentence boundaries: 。！？!? or newlines
    - Prefer groups of 2; if combined length > max_chars, keep 1 per group
    - Empty tokens are skipped
    """
    raw = _SPLIT_RE.split(text)
    sentences = [s.strip() for s in raw if s.strip()]

    scenes: List[str] = []
    i = 0
    while i < len(sentences):
        s1 = sentences[i]
        if i + 1 < len(sentences):
            combined = s1 + sentences[i + 1]
            if len(combined) <= max_chars:
                scenes.append(combined)
                i += 2
                continue
        scenes.append(s1)
        i += 1
    return scenes
