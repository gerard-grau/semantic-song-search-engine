# YouTube Audio Pipeline

High-throughput module to download YouTube audio URLs directly into RAM and extract:

- BPM
- Key
- Loudness

The output is stored in CSV format for downstream processing.

## Why this module is fast

- Downloads native audio stream (`bestaudio/best`), no MP3 conversion.
- Uses `/dev/shm` as RAM-disk to avoid SSD I/O bottlenecks.
- Integrates `yt-dlp` with `aria2c` (`-x 16 -s 16 -k 1M`) for accelerated transfer.
- Uses C++-backed `essentia.standard` for high-performance feature extraction.
- Enforces analyze-and-delete so temporary files are removed immediately.

Compatibility note:

- If the downloaded codec is not directly readable by Essentia in your environment, the analyzer performs a temporary in-RAM conversion to mono 44.1kHz WAV using `ffmpeg`, analyzes it, and deletes both files immediately.

## Files

- [downloader.py](downloader.py): download to RAM-disk
- [analyzer.py](analyzer.py): feature extraction and guaranteed cleanup
- [main.py](main.py): CLI runner with parallel processing and batch CSV flushes
- [benchmark.py](benchmark.py): server-side throughput benchmark to tune worker count
- [urls.example.txt](urls.example.txt): sample URL input file
- [urls.benchmark.example.txt](urls.benchmark.example.txt): benchmark URL sample

## Requirements

### System packages

- `aria2`
- `ffmpeg`

Ubuntu install command:

```bash
sudo apt update && sudo apt install -y aria2 ffmpeg
```


### Python packages

Install from repository root:

```bash
pip install -r requirements.txt
```

Note: this module is optimized for Linux (`/dev/shm`). On non-Linux systems it automatically falls back to the OS temp directory.

## Basic usage

From repository root:

```bash
python -m youtube_audio_pipeline.main --urls-file youtube_audio_pipeline/urls.example.txt
```

Shorthand (equivalent):

```bash
python -m youtube_audio_pipeline --urls-file youtube_audio_pipeline/urls.example.txt
```

Important:

- Prefer `python -m ...` execution from the repository root.
- Avoid `python main.py` from inside [youtube_audio_pipeline](youtube_audio_pipeline), because package imports are not reliably resolvable in that mode.

CSV output default:

- `data/processed/youtube_song_characteristics.csv`

## Common options

```bash
python -m youtube_audio_pipeline.main \
  --urls-file path/to/urls.txt \
  --output-csv data/processed/my_features.csv \
  --ram-disk-path /dev/shm/yt_audio \
  --workers 22 \
  --flush-every 250
```

Add ad-hoc URLs without editing a file:

```bash
python -m youtube_audio_pipeline.main \
  --url "https://www.youtube.com/watch?v=..." \
  --url "https://www.youtube.com/watch?v=..."
```

## Notes

- If `/dev/shm` is unavailable, the downloader falls back to the OS temp directory.
- This module assumes URL access rights and legal usage are handled by the operator.
- For very large runs, monitor RAM usage and tune `--workers`.

## Benchmark on the target server

Because performance is machine-dependent, benchmark on the same server where production runs will execute.

Example benchmark run (10 URLs, 1 repeat):

```bash
python -m youtube_audio_pipeline.benchmark \
  --urls-file youtube_audio_pipeline/urls.benchmark.example.txt \
  --max-urls 10 \
  --workers-list 1,2,4,8,12,16,22 \
  --repeats 1 \
  --flush-every 200
```

Benchmark summary output:

- `data/processed/youtube_pipeline_benchmark.csv`

How to choose workers:

- Prefer the highest `urls_per_second`.
- Require `success_rate` close to `1.0`.
- If success rate drops at high workers, choose the best stable lower value.

Keep per-run feature CSVs for inspection:

```bash
python -m youtube_audio_pipeline.benchmark \
  --urls-file youtube_audio_pipeline/urls.benchmark.example.txt \
  --keep-run-csv
```
