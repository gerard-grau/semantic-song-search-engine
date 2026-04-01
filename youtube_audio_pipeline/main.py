from __future__ import annotations

import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from youtube_audio_pipeline.analyzer import analyze_and_discard, save_to_dataframe
from youtube_audio_pipeline.downloader import download_to_ram
from youtube_audio_pipeline.youtube_utils import (
    canonical_watch_url,
    extract_video_id,
    normalize_youtube_input,
)
from youtube_audio_pipeline import model_inference

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_urls(urls_file: str) -> list[dict[str, str | None]]:
    urls = []
    urls_path = Path(urls_file)
    if not urls_path.exists():
        return []

    with open(urls_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            url, video_id = normalize_youtube_input(line)
            urls.append({"url": url, "youtube_id": video_id, "source_input": line})
    return urls


def process_single_url(
    entry: dict[str, str | None], ram_disk_path: str, skip_models: bool = False
) -> dict | None:
    url = entry.get("url")
    if not url:
        return None

    source_input = entry.get("source_input") or url
    
    # download_to_ram now returns (success, filepath, metadata_dict)
    success, filepath, metadata = download_to_ram(url=url, ram_disk_path=ram_disk_path)
    if not success or metadata is None:
        return None

    # Use metadata from downloader
    filepath_obj = Path(filepath)
    song_data = analyze_and_discard(
        filepath=filepath_obj, 
        metadata=metadata,
        skip_models=skip_models
    )
    
    # Cleanup after analysis
    if filepath_obj.exists():
        filepath_obj.unlink()

    if song_data is None:
        return None

    song_data["SourceInput"] = source_input
    return song_data


def run_pipeline(
    urls: list[dict[str, str | None]],
    output_csv: str,
    ram_disk_path: str = "/dev/shm/yt_audio",
    workers: int = 8,
    flush_every: int = 200,
    skip_models: bool = False,
) -> tuple[int, int]:
    if not urls:
        print("No URLs provided.")
        return 0, 0

    workers = max(1, workers)
    workers = min(workers, max(1, os.cpu_count() or 1))

    processed_count = 0
    saved_count = 0
    batch_results: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(process_single_url, url_entry, ram_disk_path, skip_models): url_entry 
            for url_entry in urls
        }

        for idx, future in enumerate(as_completed(future_map), start=1):
            url_entry = future_map[future]
            source_input = url_entry.get("source_input") or url_entry.get("url") or "unknown"
            try:
                song_data = future.result()
                if song_data:
                    processed_count += 1
                    batch_results.append(song_data)
                    print(
                        f"[{idx}/{len(urls)}] ✅ Processed: {song_data['Title']} | "
                        f"BPM: {song_data.get('BPM', 0.0):.1f} | Key: {song_data.get('Key', 'N/A')}"
                    )
                else:
                    print(f"[{idx}/{len(urls)}] ⚠️ Skipped URL/Input: {source_input}")

                if len(batch_results) >= flush_every:
                    save_to_dataframe(batch_results, output_csv=output_csv)
                    saved_count += len(batch_results)
                    batch_results.clear()
            except Exception as exc:
                print(f"[{idx}/{len(urls)}] ❌ Unhandled error for {source_input} | Error: {exc}")
                logger.exception("Unexpected error in pipeline:")

    if batch_results:
        save_to_dataframe(batch_results, output_csv=output_csv)
        saved_count += len(batch_results)
        batch_results.clear()

    return processed_count, saved_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download YouTube audio to RAM disk and extract musical features "
            "with enriched ML models."
        )
    )
    parser.add_argument(
        "--urls-file",
        type=str,
        default="youtube_audio_pipeline/urls.example.txt",
        help="Path to a text file with one YouTube URL per line.",
    )
    parser.add_argument(
        "--url",
        action="append",
        help="Optional URL argument; can be repeated.",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default="data/processed/youtube_song_characteristics.csv",
        help="Destination CSV path.",
    )
    parser.add_argument(
        "--ram-disk-path",
        type=str,
        default="/dev/shm/yt_audio",
        help="RAM path for temporary audio files.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of concurrent workers.",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=10,
        help="Flush results to CSV every N songs.",
    )
    parser.add_argument(
        "--skip-models",
        action="store_true",
        help="Skip ML model inference.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    urls = []
    if args.url:
        for u in args.url:
            norm_url, vid_id = normalize_youtube_input(u)
            urls.append({"url": norm_url, "youtube_id": vid_id, "source_input": u})

    if args.urls_file and os.path.exists(args.urls_file):
        urls.extend(load_urls(args.urls_file))

    if not urls:
        print("Error: No URLs found. Provide --url or a valid --urls-file.")
        return

    if not args.skip_models:
        print("Initializing Essentia models (genre, mood, embeddings, etc.)...")
        model_inference.initialize_models_globally()
        print("✓ Models ready")

    processed_count, saved_count = run_pipeline(
        urls=urls,
        output_csv=args.output_csv,
        ram_disk_path=args.ram_disk_path,
        workers=args.workers,
        flush_every=args.flush_every,
        skip_models=args.skip_models,
    )
    print(f"Finished. Successfully processed: {processed_count}. Rows saved: {saved_count}.")


if __name__ == "__main__":
    main()
