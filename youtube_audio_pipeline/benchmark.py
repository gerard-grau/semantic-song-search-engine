import subprocess
import time
from itertools import product
from pathlib import Path

# --- CONFIGURATION ---
URLS_FILE = "youtube_audio_pipeline/urls.benchmark.txt"
TEMP_CSV = "data/processed/temp_bench.csv"

# --- HYPERPARAMETER GRID ---
DOWNLOADERS = [12, 24, 32]
WORKERS = [4, 6, 8]
BATCH_SIZES = [8, 16, 32]

# Get expected count (excluding comments and empty lines)
with open(URLS_FILE, "r") as f:
    EXPECTED_COUNT = len([line for line in f if line.strip() and not line.startswith("#")])

results = []

print(f"📊 Starting benchmark. Expected songs per run: {EXPECTED_COUNT}")
print(f"{'DL':<5} | {'Work':<5} | {'BS':<5} | {'Status':<10} | {'Total Time':<10}")
print("-" * 55)

for d, w, b in product(DOWNLOADERS, WORKERS, BATCH_SIZES):
    # Prepare Command
    cmd = [
        ".venv/bin/python3", "-m", "youtube_audio_pipeline.main",
        "--urls-file", URLS_FILE,
        "--downloaders", str(d),
        "--workers", str(w),
        "--batch-size", str(b),
        "--output-csv", TEMP_CSV,
        "--skip-pitch"
    ]
    
    if Path("cookies.txt").exists():
        cmd.extend(["--cookies", "cookies.txt"])
    
    Path(TEMP_CSV).unlink(missing_ok=True)
    
    start = time.time()
    process = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - start
    
    # Validation: Count rows in output CSV (subtract 1 for header)
    actual_count = 0
    if Path(TEMP_CSV).exists():
        with open(TEMP_CSV, "r") as f:
            actual_count = len(f.readlines()) - 1
    
    status = "✅ OK" if actual_count == EXPECTED_COUNT else f"⚠️ {actual_count}/{EXPECTED_COUNT}"
    
    if process.returncode == 0 and actual_count == EXPECTED_COUNT:
        print(f"{d:<5} | {w:<5} | {b:<5} | {status:<10} | {duration:>9.2f}s")
        results.append((duration, d, w, b))
    else:
        print(f"{d:<5} | {w:<5} | {b:<5} | {status:<10} | ❌ FAILED")

if results:
    best = min(results)
    print("-" * 55)
    print(f"🏆 BEST SETTINGS: {best[0]:.2f}s")
    print(f"   --downloaders {best[1]} --workers {best[2]} --batch-size {best[3]}")
    
    print(f"\n🚀 Recommended Command:")
    print(f".venv/bin/python3 -m youtube_audio_pipeline.main --downloaders {best[1]} --workers {best[2]} --batch-size {best[3]} --skip-pitch")
