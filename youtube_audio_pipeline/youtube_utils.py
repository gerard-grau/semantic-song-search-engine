from __future__ import annotations

import re

YOUTUBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


def canonical_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def extract_video_id(value: str | None) -> str | None:
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    if YOUTUBE_ID_PATTERN.fullmatch(text):
        return text

    patterns = [
        r"youtube\.com/watch\?[^\s]*v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube-nocookie\.com/embed/([A-Za-z0-9_-]{11})",
        r"v=([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None


def normalize_youtube_input(value: str) -> tuple[str, str | None]:
    text = value.strip()
    video_id = extract_video_id(text)
    if video_id:
        return canonical_watch_url(video_id), video_id
    return text, None
