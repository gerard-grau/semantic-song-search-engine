from __future__ import annotations

import argparse
import logging
import os
import time
import queue
import threading
import json
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
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

STATE_FILE = "data/processed/pipeline_state.json"

def load_processed_ids() -> set[str]:
    """Loads the set of YouTube IDs that have already been fully processed."""
    if not os.path.exists(STATE_FILE): return set()
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("processed_ids", []))
    except: return set()

def save_processed_id(video_id: str):
    """Appends a single YouTube ID to the state file to mark it as complete."""
    processed = list(load_processed_ids())
    if video_id not in processed:
        processed.append(video_id)
        Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({"processed_ids": processed}, f)

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
    """Saves a single processed row to the CSV using native writer."""
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = output_path.exists()
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists: writer.writeheader()
        writer.writerow(row)

def run_standard_pipeline(
    urls: list[dict[str, str | None]],
    output_csv: str,
    ram_disk_path: str = "/dev/shm/yt_audio",
    num_downloaders: int = 1,
    num_analyzers: int = 1,
    ml_batch_size: int = 16,
    skip_models: bool = False,
    skip_pitch: bool = False
) -> tuple[int, int]:
    if not urls: return 0, 0
    
    processed_ids = load_processed_ids()
    to_process_urls = [u for u in urls if u['youtube_id'] not in processed_ids]
    
    total_count = len(urls)
    already_done = total_count - len(to_process_urls)
    start_time = time.time()
    
    print(f"🚀 Starting Standard Pipeline (v3.1)")
    print(f"📊 Progress: {already_done}/{total_count} already finished.")
    
    if not to_process_urls:
        print("✅ All songs are already processed!")
        return already_done, already_done

    inference_queue = queue.Queue(maxsize=ml_batch_size * 2)
    processed_count = already_done
    
    def download_task(url_entry):
        return download_to_ram(url_entry['url'], ram_disk_path), url_entry['source_input'], url_entry['youtube_id']

    def inference_manager(total_to_process):
        nonlocal processed_count
        pending_batch = []
        received = already_done
        while received < total_count:
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
        for i, (base_data, _, vid_id) in enumerate(batch):
            final_row = finalize_song_data(base_data, ml_batch_results[i])
            completed_rows.append(final_row)
            save_processed_id(vid_id)
            
            idx = (processed_count - already_done) + already_done + i + 1
            elapsed = time.time() - start_time
            avg = elapsed / (idx - already_done)
            eta = avg * (total_count - idx)
            print(f"[{idx}/{total_count}] [{time.strftime('%H:%M:%S')}] ✅ Processed: {final_row['Title']} | ETA: {format_duration(eta)}")
        
        save_to_dataframe(completed_rows, output_csv)

    with ThreadPoolExecutor(max_workers=num_downloaders + num_analyzers) as executor:
        inf_thread = threading.Thread(target=inference_manager, args=(total_count,))
        inf_thread.start()
        
        def analyze_and_queue(download_res, source_input, youtube_id):
            success, filepath, metadata = download_res
            if not success or not filepath:
                inference_queue.put(None)
                return
            
            res = extract_base_features(Path(filepath), metadata, skip_models=skip_models, skip_pitch=skip_pitch)
            if Path(filepath).exists(): Path(filepath).unlink()
            
            if res:
                base_data, ml_patches = res
                base_data["SourceInput"] = source_input
                inference_queue.put((base_data, ml_patches, youtube_id))
            else:
                inference_queue.put(None)

        download_futures = []
        for url_entry in to_process_urls:
            f = executor.submit(download_task, url_entry)
            download_futures.append(f)
            
        for f in as_completed(download_futures):
            download_res, source_input, youtube_id = f.result()
            executor.submit(analyze_and_queue, download_res, source_input, youtube_id)
            
        inf_thread.join()

    total_time = time.time() - start_time
    print(f"\nPipeline finished in {format_duration(total_time)}.")
    return processed_count, processed_count

def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Audio Pipeline Standard Baseline v3.1")
    parser.add_argument("--urls-file", type=str, default="youtube_audio_pipeline/urls.example.txt")
    parser.add_argument("--url", action="append")
    parser.add_argument("--output-csv", type=str, default="data/processed/youtube_song_characteristics.csv")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--downloaders", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=8)
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
    if not args.skip_models:
        model_inference.initialize_models_globally()

    run_standard_pipeline(
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
