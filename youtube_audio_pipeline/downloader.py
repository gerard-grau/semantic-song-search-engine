from __future__ import annotations

import os
import tempfile
import logging
import uuid
from pathlib import Path

import yt_dlp

logger = logging.getLogger(__name__)

def ensure_ram_path(ram_disk_path: str = "/dev/shm/yt_audio") -> Path:
    preferred = Path(ram_disk_path)
    if preferred.parent.exists():
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred

    fallback = Path(tempfile.gettempdir()) / "yt_audio"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def download_to_ram(
    url: str,
    ram_disk_path: str = "/dev/shm/yt_audio",
) -> tuple[bool, str | None, dict | None]:
    """
    Fast-WAV Strategy: Pull native audio and use a HIGH-SPEED PCM conversion.
    PCM is the fastest to encode because it uses no compression math.
    """
    ram_path = ensure_ram_path(ram_disk_path)
    
    unique_id = str(uuid.uuid4())
    temp_template = str(ram_path / f"{unique_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": temp_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "external_downloader": "aria2c",
        "external_downloader_args": ["-x", "16", "-s", "16", "-k", "1M"],
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }],
        "postprocessor_args": [
            "-ar", "16000",
            "-ac", "1",
            "-acodec", "pcm_s16le" # FASTEST: No compression math
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = str(ram_path / f"{unique_id}.wav")
            
            metadata = {
                "id": info.get("id"),
                "title": info.get("title", "Unknown Title"),
                "url": info.get("webpage_url") or url,
                "uploader": info.get("uploader"),
                "channel": info.get("channel"),
                "upload_date": info.get("upload_date"),
                "view_count": info.get("view_count", 0),
                "like_count": info.get("like_count", 0),
                "duration": info.get("duration"),
                "categories": info.get("categories", []),
                "tags": info.get("tags", []),
            }
            
            return True, filepath, metadata
    except Exception as e:
        logger.warning(f"Download failed for {url}: {e}")
        return False, None, None
