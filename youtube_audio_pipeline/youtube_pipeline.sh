#!/bin/bash

# Navigate to project root
cd "$(dirname "$0")/.."

# 1. Clear GPU memory (safety first)
pkill -9 python 2>/dev/null || true

# 2. Export GPU library paths
export LD_LIBRARY_PATH=$(pwd)/.venv/nvidia_fix:$(.venv/bin/python3 -c 'import os, sys; from glob import glob; print(":".join(set(os.path.dirname(p) for p in glob(sys.prefix + "/lib/python*/site-packages/nvidia/*/lib/*.so*"))))'):/usr/lib/x86_64-linux-gnu:/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# 3. Force Memory Growth (the proven fix)
export TF_FORCE_GPU_ALLOW_GROWTH=true
export TF_CPP_MIN_LOG_LEVEL=2

# 4. Run the Stealth Baseline (Default: 1 worker, 1 downloader)
echo "🚀 Starting YouTube Audio Pipeline v2.3 (STEALTH BASELINE)..."
.venv/bin/python3 -m youtube_audio_pipeline.main "$@"
