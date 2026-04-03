from __future__ import annotations

import os
import tempfile
import logging
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
    Standard Downloader (No aria2c) - Mono 16kHz WAV.
    """
    ram_path = ensure_ram_path(ram_disk_path)

    # Force 16kHz at the download stage to save CPU later
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(ram_path / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # REMOVED ARIA2C for stealth
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "192",
        }],
        "postprocessor_args": [
            "-ar", "16000",
            "-ac", "1"
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info).rsplit('.', 1)[0] + ".wav"
            
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
