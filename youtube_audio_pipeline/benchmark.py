from __future__ import annotations

import argparse
import csv
import os
import platform
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

from youtube_audio_pipeline.main import load_urls, run_pipeline


def parse_workers(workers_arg: str) -> list[int]:
    parsed: list[int] = []
    for chunk in workers_arg.split(","):
        token = chunk.strip()
        if not token:
            continue
        value = int(token)
        if value > 0:
            parsed.append(value)
    unique_sorted = sorted(set(parsed))
    if not unique_sorted:
        raise ValueError("No valid worker values were provided.")
    return unique_sorted


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_benchmark_row(output_file: Path, row: dict[str, object]) -> None:
    ensure_parent(output_file)

    fieldnames = [
        "timestamp_utc",
        "host",
        "python_version",
        "cpu_count",
        "workers",
        "repeat_index",
        "input_urls",
        "processed_count",
        "saved_count",
        "success_rate",
        "duration_seconds",
        "urls_per_second",
        "flush_every",
        "ram_disk_path",
        "urls_file",
        "result_csv",
    ]

    write_header = not output_file.exists()
    with output_file.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark youtube_audio_pipeline.main on this server to choose the best worker count."
    )
    parser.add_argument(
        "--urls-file",
        type=str,
        default="youtube_audio_pipeline/urls.example.txt",
        help="Path to URL list file (one URL per line).",
    )
    parser.add_argument(
        "--max-urls",
        type=int,
        default=10,
        help="Use only the first N URLs for benchmark runs.",
    )
    parser.add_argument(
        "--workers-list",
        type=str,
        default="1,2,4,8,12,16,22",
        help="Comma-separated worker values to test.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="How many repeats per worker value.",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=200,
        help="Flush size for run_pipeline.",
    )
    parser.add_argument(
        "--ram-disk-path",
        type=str,
        default="/dev/shm/yt_audio",
        help="RAM-disk location for temporary audio files.",
    )
    parser.add_argument(
        "--benchmark-csv",
        type=str,
        default="data/processed/youtube_pipeline_benchmark.csv",
        help="Benchmark summary CSV output path.",
    )
    parser.add_argument(
        "--result-prefix",
        type=str,
        default="data/processed/bench_runs/yt_features",
        help="Per-run output CSV prefix.",
    )
    parser.add_argument(
        "--keep-run-csv",
        action="store_true",
        help="Keep per-run feature CSV outputs (otherwise they are deleted after each run).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    urls = load_urls(args.urls_file, None)
    if not urls:
        print("No URLs loaded. Check --urls-file.")
        return

    if args.max_urls > 0:
        urls = urls[: args.max_urls]

    workers_list = parse_workers(args.workers_list)
    repeats = max(1, args.repeats)

    benchmark_csv = Path(args.benchmark_csv)
    host = socket.gethostname()
    python_version = platform.python_version()
    cpu_count = os.cpu_count() or 1

    print(
        f"Benchmarking {len(urls)} URL(s) on host={host} cpu={cpu_count} "
        f"workers={workers_list} repeats={repeats}"
    )

    for workers in workers_list:
        for repeat_index in range(1, repeats + 1):
            run_csv = Path(f"{args.result_prefix}.w{workers}.r{repeat_index}.csv")
            ensure_parent(run_csv)
            if run_csv.exists():
                run_csv.unlink()

            start = time.perf_counter()
            processed_count, saved_count = run_pipeline(
                urls=urls,
                output_csv=str(run_csv),
                ram_disk_path=args.ram_disk_path,
                workers=workers,
                flush_every=args.flush_every,
            )
            duration = time.perf_counter() - start

            input_count = len(urls)
            success_rate = (processed_count / input_count) if input_count else 0.0
            urls_per_second = (processed_count / duration) if duration > 0 else 0.0

            row = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "host": host,
                "python_version": python_version,
                "cpu_count": cpu_count,
                "workers": workers,
                "repeat_index": repeat_index,
                "input_urls": input_count,
                "processed_count": processed_count,
                "saved_count": saved_count,
                "success_rate": round(success_rate, 4),
                "duration_seconds": round(duration, 3),
                "urls_per_second": round(urls_per_second, 4),
                "flush_every": args.flush_every,
                "ram_disk_path": args.ram_disk_path,
                "urls_file": args.urls_file,
                "result_csv": str(run_csv),
            }
            append_benchmark_row(benchmark_csv, row)

            print(
                f"workers={workers} repeat={repeat_index} "
                f"processed={processed_count}/{input_count} "
                f"duration={duration:.2f}s urls/s={urls_per_second:.3f}"
            )

            if not args.keep_run_csv and run_csv.exists():
                run_csv.unlink()

    print(f"Benchmark completed. Summary written to: {benchmark_csv}")


if __name__ == "__main__":
    main()
