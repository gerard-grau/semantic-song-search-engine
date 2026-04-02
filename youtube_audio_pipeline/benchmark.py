import subprocess
import time
from itertools import product
from pathlib import Path

# --- CONFIGURATION ---
URLS_FILE = "youtube_audio_pipeline/urls.benchmark.txt" # Finalized internal path
OUTPUT_CSV = "data/processed/benchmark_results.csv"

# --- HYPERPARAMETER GRID ---
DOWNLOADERS = [12, 24, 32]
WORKERS = [4, 6, 8]
BATCH_SIZES = [8, 16, 32]

results = []

print(f"{'DL':<5} | {'Work':<5} | {'BS':<5} | {'Total Time':<10}")
print("-" * 40)

for d, w, b in product(DOWNLOADERS, WORKERS, BATCH_SIZES):
    # Prepare Command
    cmd = [
        ".venv/bin/python3", "-m", "youtube_audio_pipeline.main",
        "--urls-file", URLS_FILE,
        "--downloaders", str(d),
        "--workers", str(w),
        "--batch-size", str(b),
        "--output-csv", "data/processed/temp_bench.csv",
        "--skip-pitch"
    ]
    
    # Cleanup previous temp file
    Path("data/processed/temp_bench.csv").unlink(missing_ok=True)
    
    start = time.time()
    # Run the pipeline
    process = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - start
    
    if process.returncode == 0:
        print(f"{d:<5} | {w:<5} | {b:<5} | {duration:>9.2f}s")
        results.append((duration, d, w, b))
    else:
        print(f"{d:<5} | {w:<5} | {b:<5} | ❌ FAILED")

if results:
    best = min(results)
    print("-" * 40)
    print(f"🏆 BEST SETTINGS: {best[0]:.2f}s")
    print(f"   --downloaders {best[1]} --workers {best[2]} --batch-size {best[3]}")
    
    # Final recommendation
    print(f"\n🚀 Recommended Command:")
    print(f".venv/bin/python3 -m youtube_audio_pipeline.main --downloaders {best[1]} --workers {best[2]} --batch-size {best[3]} --skip-pitch")
