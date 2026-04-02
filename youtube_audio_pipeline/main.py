from __future__ import annotations

import argparse
import logging
import os
import time
import queue
import threading
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from youtube_audio_pipeline.analyzer import extract_base_features, finalize_song_data
from youtube_audio_pipeline.downloader import download_to_ram
from youtube_audio_pipeline.youtube_utils import normalize_youtube_input
from youtube_audio_pipeline import model_inference

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def load_urls(urls_file: str) -> list[dict[str, str | None]]:
    urls = []
    urls_path = Path(urls_file)
    if not urls_path.exists(): return []
    with open(urls_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            url, video_id = normalize_youtube_input(line)
            urls.append({"url": url, "youtube_id": video_id, "source_input": line})
    return urls

def format_duration(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0: return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0: return f"{minutes}m {secs}s"
    else: return f"{secs}s"

def save_row_to_csv(row: dict, output_csv: str):
    """
    Saves a single row to CSV using the standard library (faster than pandas).
    """
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    file_exists = output_path.exists()
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def run_production_pipeline(
    urls: list[dict[str, str | None]],
    output_csv: str,
    ram_disk_path: str = "/dev/shm/yt_audio",
    num_downloaders: int = 4,
    num_analyzers: int = 6,
    ml_batch_size: int = 16,
    skip_models: bool = False,
    skip_pitch: bool = False,
    cookies_path: str | None = None
) -> tuple[int, int]:
    if not urls: return 0, 0
    total_count = len(urls)
    start_time = time.time()
    
    # ... rest of code ...
    
    analysis_queue = queue.Queue(maxsize=num_analyzers * 2)
    inference_queue = queue.Queue(maxsize=ml_batch_size * 2)
    processed_count = 0

    # --- Worker 1: The Downloader (Producer) ---
    def downloader_manager():
        with ThreadPoolExecutor(max_workers=num_downloaders) as pool:
            futures = []
            for url_entry in urls:
                f = pool.submit(download_to_ram, url_entry['url'], ram_disk_path, cookies_path)
                futures.append((f, url_entry['source_input']))
            
            for f, source_input in futures:
                try:
                    success, filepath, metadata = f.result()
                    if success:
                        analysis_queue.put((filepath, metadata, source_input))
                    else:
                        analysis_queue.put(None)
                except Exception as e:
                    logger.error(f"Download task failed: {e}")
                    analysis_queue.put(None)
        
        # Signal analyzers we are done
        for _ in range(num_analyzers):
            analysis_queue.put("DONE")

    # --- Worker 2: The Analyzer (CPU Intensive) ---
    def analyzer_worker():
        while True:
            item = analysis_queue.get()
            if item == "DONE": break
            if item is None: 
                inference_queue.put(None)
                continue
            
            filepath, metadata, source_input = item
            try:
                res = extract_base_features(Path(filepath), metadata, skip_models, skip_pitch)
                # Cleanup unique file immediately
                if os.path.exists(filepath): os.remove(filepath)
                
                if res:
                    base_data, patches = res
                    base_data["SourceInput"] = source_input
                    inference_queue.put((base_data, patches))
                else:
                    inference_queue.put(None)
            except Exception as e:
                logger.error(f"Analysis failed for {source_input}: {e}")
                inference_queue.put(None)
        
        # Signal inference manager
        inference_queue.put("DONE")

    # --- Worker 3: The Inference Manager (GPU & Disk) ---
    def inference_manager():
        nonlocal processed_count
        active_analyzers = num_analyzers
        pending_batch = []
        last_inference_time = time.time()
        
        while active_analyzers > 0:
            try:
                item = inference_queue.get(timeout=1.0)
                if item == "DONE":
                    active_analyzers -= 1
                    continue
                if item is not None:
                    pending_batch.append(item)
            except queue.Empty:
                if pending_batch:
                    _run_batch(pending_batch)
                    processed_count += len(pending_batch)
                    pending_batch = []
                    last_inference_time = time.time()
                continue

            # Heartbeat logic
            if len(pending_batch) >= ml_batch_size or (pending_batch and time.time() - last_inference_time > 2.0):
                _run_batch(pending_batch)
                processed_count += len(pending_batch)
                pending_batch = []
                last_inference_time = time.time()

        if pending_batch:
            _run_batch(pending_batch)
            processed_count += len(pending_batch)

    def _run_batch(batch):
        list_of_patches = [item[1] for item in batch]
        if not skip_models:
            ml_batch_results = model_inference.run_batch_inference(list_of_patches)
        else:
            ml_batch_results = [{"embedding": None} for _ in batch]
        
        for i, (base_data, _) in enumerate(batch):
            final_row = finalize_song_data(base_data, ml_batch_results[i])
            save_row_to_csv(final_row, output_csv)
            
            idx = processed_count + i + 1
            elapsed = time.time() - start_time
            avg = elapsed / idx
            eta = avg * (total_count - idx)
            print(f"[{idx}/{total_count}] ✅ Processed: {final_row['Title']} | ETA: {format_duration(eta)}")

    # 🚀 Start all threads
    d_thread = threading.Thread(target=downloader_manager)
    a_threads = [threading.Thread(target=analyzer_worker) for _ in range(num_analyzers)]
    i_thread = threading.Thread(target=inference_manager)

    d_thread.start()
    for t in a_threads: t.start()
    i_thread.start()

    d_thread.join()
    for t in a_threads: t.join()
    i_thread.join()

    total_time = time.time() - start_time
    print(f"\nProduction Pipeline finished in {format_duration(total_time)}.")
    return processed_count, processed_count

def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Audio Pipeline Production v1.4.0")
    parser.add_argument("--urls-file", type=str, default="youtube_audio_pipeline/urls.example.txt")
    parser.add_argument("--url", action="append")
    parser.add_argument("--output-csv", type=str, default="data/processed/youtube_song_characteristics.csv")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--downloaders", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--skip-pitch", action="store_true")
    parser.add_argument("--cookies", type=str, help="Path to cookies.txt file for YouTube authentication.")
    args = parser.parse_args()

    urls = []
    if args.url:
        for u in args.url:
            u_norm, vid_id = normalize_youtube_input(u)
            urls.append({"url": u_norm, "youtube_id": vid_id, "source_input": u})
    
    if args.urls_file:
        if os.path.exists(args.urls_file):
            urls.extend(load_urls(args.urls_file))
        else:
            logger.warning(f"URLs file not found: {args.urls_file}")

    if not urls:
        print("❌ Error: No URLs provided. Use --url [URL] or --urls-file [PATH].")
        return

    if not args.skip_models:
        model_inference.initialize_models_globally()

    run_production_pipeline(
        urls, 
        args.output_csv, 
        num_downloaders=args.downloaders,
        num_analyzers=args.workers, 
        ml_batch_size=args.batch_size, 
        skip_models=args.skip_models,
        skip_pitch=args.skip_pitch,
        cookies_path=args.cookies
    )

if __name__ == "__main__":
    main()
