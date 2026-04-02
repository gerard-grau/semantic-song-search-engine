from __future__ import annotations

import argparse
import logging
import os
import time
import queue
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
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

def run_turbo_pipeline(
    urls: list[dict[str, str | None]],
    output_csv: str,
    ram_disk_path: str = "/dev/shm/yt_audio",
    num_downloaders: int = 4, # Parallel downloads
    num_analyzers: int = 6,   # CPU cores
    ml_batch_size: int = 16,
    skip_models: bool = False,
    skip_pitch: bool = False,
) -> tuple[int, int]:
    if not urls: return 0, 0
    total_count = len(urls)
    start_time = time.time()
    
    # Queues
    # Use maxsize to prevent downloading too many songs and filling RAM
    inference_queue = queue.Queue(maxsize=ml_batch_size * 2)
    processed_count = 0
    
    # 1. Parallel Downloaders (ThreadPool is fine here as it's I/O bound)
    def download_task(url_entry):
        return download_to_ram(url_entry['url'], ram_disk_path), url_entry['source_input']

    # 2. Inference Manager (Consumes from the analyzer results)
    def inference_manager(total_to_process):
        nonlocal processed_count
        pending_batch = []
        received = 0
        while received < total_to_process:
            item = inference_queue.get()
            received += 1
            if item is None: continue
            
            pending_batch.append(item)
            if len(pending_batch) >= ml_batch_size:
                _run_batch(pending_batch)
                processed_count += len(pending_batch)
                pending_batch = []
        
        if pending_batch:
            _run_batch(pending_batch)
            processed_count += len(pending_batch)

    def _run_batch(batch):
        list_of_patches = [item[1] for item in batch]
        if not skip_models:
            ml_batch_results = model_inference.run_batch_inference(list_of_patches)
        else:
            ml_batch_results = [{"embedding": None} for _ in batch]
        
        completed_rows = []
        for i, (base_data, _) in enumerate(batch):
            final_row = finalize_song_data(base_data, ml_batch_results[i])
            completed_rows.append(final_row)
            
            idx = processed_count + i + 1
            elapsed = time.time() - start_time
            avg = elapsed / idx
            eta = avg * (total_count - idx)
            print(f"[{idx}/{total_count}] ✅ Processed: {final_row['Title']} | ETA: {format_duration(eta)}")
        
        save_to_dataframe(completed_rows, output_csv)

    # 3. Master Execution Flow
    # We use a ThreadPool for downloads and a ProcessPool for analysis
    # NOTE: Essentia objects cannot be easily pickled for ProcessPool, 
    # so we keep analysis in threads but SCALE the downloaders.
    
    print(f"🚀 Launching Turbo Pipeline: {num_downloaders} Downloaders | {num_analyzers} Analyzers")
    
    with ThreadPoolExecutor(max_workers=num_downloaders + num_analyzers) as executor:
        # Start Inference Manager in background
        inf_thread = threading.Thread(target=inference_manager, args=(total_count,))
        inf_thread.start()
        
        # Helper to analyze and push to queue
        def analyze_and_queue(download_res, source_input):
            success, filepath, metadata = download_res
            if not success or not filepath:
                inference_queue.put(None)
                return
            
            filepath_obj = Path(filepath)
            res = extract_base_features(filepath_obj, metadata, skip_models, skip_pitch)
            if filepath_obj.exists(): filepath_obj.unlink()
            
            if res:
                base_data, ml_patches = res
                base_data["SourceInput"] = source_input
                inference_queue.put((base_data, ml_patches))
            else:
                inference_queue.put(None)

        # Download Queue
        download_futures = []
        for url_entry in urls:
            f = executor.submit(download_task, url_entry)
            download_futures.append(f)
            
        # As downloads finish, submit to analyzer pool
        analysis_futures = []
        for f in as_completed(download_futures):
            download_res, source_input = f.result()
            # Submit to analyzer part of the pool
            af = executor.submit(analyze_and_queue, download_res, source_input)
            analysis_futures.append(af)
            
        inf_thread.join()

    total_time = time.time() - start_time
    print(f"\nTurbo Pipeline finished in {format_duration(total_time)}.")
    return processed_count, processed_count

def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Audio Pipeline Production v1.2.0")
    parser.add_argument("--urls-file", type=str, default="youtube_audio_pipeline/urls.example.txt")
    parser.add_argument("--url", action="append")
    parser.add_argument("--output-csv", type=str, default="data/processed/youtube_song_characteristics.csv")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--downloaders", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--skip-pitch", action="store_true")
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

    run_turbo_pipeline(
        urls, 
        args.output_csv, 
        num_downloaders=args.downloaders,
        num_analyzers=args.workers, 
        ml_batch_size=args.batch_size, 
        skip_models=args.skip_models,
        skip_pitch=args.skip_pitch
    )

if __name__ == "__main__":
    main()
