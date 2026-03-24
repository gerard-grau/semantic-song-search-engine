from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from youtube_audio_pipeline.analyzer import analyze_and_discard, save_to_dataframe
from youtube_audio_pipeline.downloader import download_to_ram
from youtube_audio_pipeline.youtube_utils import canonical_watch_url, extract_video_id, normalize_youtube_input


def load_urls(urls_file: str | None, urls_cli: list[str] | None) -> list[dict[str, str | None]]:
    raw_values: list[str] = []

    if urls_file:
        with open(urls_file, "r", encoding="utf-8") as handle:
            for line in handle:
                candidate = line.strip()
                if candidate and not candidate.startswith("#"):
                    raw_values.append(candidate)

    if urls_cli:
        raw_values.extend(urls_cli)

    normalized_inputs: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        normalized_url, youtube_id = normalize_youtube_input(raw_value)
        dedupe_key = youtube_id if youtube_id else normalized_url
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized_inputs.append(
            {
                "source_input": raw_value,
                "url": normalized_url,
                "youtube_id": youtube_id,
            }
        )

    return normalized_inputs


def process_single_url(entry: dict[str, str | None], ram_disk_path: str) -> dict[str, object] | None:
    url = entry["url"] or ""
    source_input = entry.get("source_input") or url
    source_youtube_id = entry.get("youtube_id")

    success, filepath, title, downloaded_video_id, resolved_url = download_to_ram(url=url, ram_disk_path=ram_disk_path)
    if not success:
        return None

    youtube_id = downloaded_video_id or source_youtube_id or extract_video_id(resolved_url or url)
    effective_url = resolved_url or (canonical_watch_url(youtube_id) if youtube_id else url)

    song_data = analyze_and_discard(filepath=filepath, url=effective_url, title=title)
    if song_data is None:
        return None

    song_data["YouTubeID"] = youtube_id or ""
    song_data["SourceInput"] = source_input
    return song_data


def run_pipeline(
    urls: list[dict[str, str | None]],
    output_csv: str,
    ram_disk_path: str = "/dev/shm/yt_audio",
    workers: int = 8,
    flush_every: int = 200,
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
        future_map = {executor.submit(process_single_url, url_entry, ram_disk_path): url_entry for url_entry in urls}

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
                        f"BPM: {song_data['BPM']} | Key: {song_data['Key']}"
                    )
                else:
                    print(f"[{idx}/{len(urls)}] ⚠️ Skipped URL/Input: {source_input}")

                if len(batch_results) >= flush_every:
                    save_to_dataframe(batch_results, output_csv=output_csv)
                    saved_count += len(batch_results)
                    batch_results.clear()
            except Exception as exc:
                print(f"[{idx}/{len(urls)}] ❌ Unhandled error for {source_input} | Error: {exc}")

    if batch_results:
        save_to_dataframe(batch_results, output_csv=output_csv)
        saved_count += len(batch_results)
        batch_results.clear()

    return processed_count, saved_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download YouTube audio to RAM disk and extract BPM/Key/Loudness to CSV."
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
        default=min(22, max(1, os.cpu_count() or 1)),
        help="Parallel workers for download + analysis.",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=200,
        help="Write to CSV every N processed songs.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    urls = load_urls(args.urls_file, args.url)
    if not urls:
        print("No URLs found. Provide --urls-file and/or --url.")
        return

    print(f"Starting pipeline for {len(urls)} URL(s) with {args.workers} worker(s)...")
    processed_count, saved_count = run_pipeline(
        urls=urls,
        output_csv=args.output_csv,
        ram_disk_path=args.ram_disk_path,
        workers=args.workers,
        flush_every=args.flush_every,
    )
    print(f"Finished. Successfully processed: {processed_count}. Rows saved: {saved_count}.")


if __name__ == "__main__":
    main()
