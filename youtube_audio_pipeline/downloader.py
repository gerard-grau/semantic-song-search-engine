from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yt_dlp

from youtube_audio_pipeline.youtube_utils import canonical_watch_url


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
) -> tuple[bool, str | None, str | None, str | None, str | None]:
    ram_path = ensure_ram_path(ram_disk_path)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(ram_path / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "external_downloader": "aria2c",
        "external_downloader_args": ["-x", "16", "-s", "16", "-k", "1M"],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            title = info.get("title", "Unknown Title")
            video_id = info.get("id")
            resolved_url = info.get("webpage_url")
            if not resolved_url and video_id:
                resolved_url = canonical_watch_url(video_id)
            return True, filepath, title, video_id, resolved_url
    except Exception:
        fallback_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(ram_path / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)
                title = info.get("title", "Unknown Title")
                video_id = info.get("id")
                resolved_url = info.get("webpage_url")
                if not resolved_url and video_id:
                    resolved_url = canonical_watch_url(video_id)
                return True, filepath, title, video_id, resolved_url
        except Exception as exc:
            print(f"❌ Download failed for {url} | Error: {exc}")
            return False, None, None, None, None
