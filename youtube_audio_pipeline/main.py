from __future__ import annotations

import argparse
import logging
import os
import time
import queue
import threading
from pathlib import Path

from youtube_audio_pipeline.analyzer import extract_base_features, finalize_song_data, save_to_dataframe
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

def run_production_pipeline(
    urls: list[dict[str, str | None]],
    output_csv: str,
    ram_disk_path: str = "/dev/shm/yt_audio",
    num_analyzers: int = 4,
    ml_batch_size: int = 4,
    skip_models: bool = False,
) -> tuple[int, int]:
    if not urls: return 0, 0
    total_count = len(urls)
    start_time = time.time()
    
    download_queue = queue.Queue(maxsize=10)
    # The queue now holds (base_data, ml_patches)
    inference_queue = queue.Queue(maxsize=ml_batch_size * 2)
    processed_count = 0
    
    # 1. Producer: Downloader
    def downloader_worker():
        for url_entry in urls:
            success, filepath, metadata = download_to_ram(url_entry['url'], ram_disk_path)
            if success: download_queue.put((filepath, metadata, url_entry['source_input']))
            else: download_queue.put(None)
        for _ in range(num_analyzers): download_queue.put("DONE")

    # 2. Consumer 1: Parallel Base Extraction + Parallel ML Preprocessing
    def analyzer_worker():
        while True:
            item = download_queue.get()
            if item == "DONE": break
            if item is None: continue
            
            filepath, metadata, source_input = item
            filepath_obj = Path(filepath)
            
            # extract_base_features now returns (res_dict, ml_patches)
            res = extract_base_features(filepath_obj, metadata, skip_models)
            if filepath_obj.exists(): filepath_obj.unlink()
            
            if res:
                base_data, ml_patches = res
                base_data["SourceInput"] = source_input
                inference_queue.put((base_data, ml_patches))
        inference_queue.put("DONE")

    # 3. Consumer 2: Batch ML Inference (Pure Matrix Math)
    def inference_manager():
        nonlocal processed_count
        active_analyzers = num_analyzers
        pending_batch = []
        
        while active_analyzers > 0:
            try:
                item = inference_queue.get(timeout=1)
                if item == "DONE":
                    active_analyzers -= 1
                    continue
                pending_batch.append(item)
                
                if len(pending_batch) >= ml_batch_size:
                    _run_batch(pending_batch)
                    processed_count += len(pending_batch)
                    pending_batch = []
            except queue.Empty:
                if pending_batch:
                    _run_batch(pending_batch)
                    processed_count += len(pending_batch)
                    pending_batch = []

    def _run_batch(batch):
        # ml_patches are already computed in parallel!
        list_of_patches = [item[1] for item in batch]
        
        # ML Inference
        if not skip_models:
            ml_batch_results = model_inference.run_batch_inference(list_of_patches)
        else:
            ml_batch_results = [{} for _ in batch]
        
        # Merge and Save
        completed_rows = []
        for i, (base_data, _) in enumerate(batch):
            final_row = finalize_song_data(base_data, ml_batch_results[i])
            completed_rows.append(final_row)
            
            # Calculate ETA
            elapsed = time.time() - start_time
            avg = elapsed / (processed_count + i + 1)
            eta = avg * (total_count - (processed_count + i + 1))
            print(f"[{processed_count + i + 1}/{total_count}] ✅ Processed: {final_row['Title']} | ETA: {format_duration(eta)}")
        
        save_to_dataframe(completed_rows, output_csv)

    # Start Threads
    d_thread = threading.Thread(target=downloader_worker)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls-file", type=str, default="youtube_audio_pipeline/urls.example.txt")
    parser.add_argument("--url", action="append")
    parser.add_argument("--output-csv", type=str, default="data/processed/youtube_song_characteristics.csv")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--skip-models", action="store_true")
    args = parser.parse_args()

    urls = []
    if args.url:
        for u in args.url:
            u_norm, vid_id = normalize_youtube_input(u)
            urls.append({"url": u_norm, "youtube_id": vid_id, "source_input": u})
    if args.urls_file and os.path.exists(args.urls_file):
        urls.extend(load_urls(args.urls_file))

    if not urls: return
    if not args.skip_models: model_inference.initialize_models_globally()

    run_production_pipeline(
        urls, 
        args.output_csv, 
        num_analyzers=args.workers, 
        ml_batch_size=args.batch_size, 
        skip_models=args.skip_models
    )

if __name__ == "__main__":
    main()
