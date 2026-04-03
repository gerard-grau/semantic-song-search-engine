#!/bin/bash

# Navigate to project root
cd "$(dirname "$0")/.."

# Run the CPU-Native Stealth Engine
echo "🚀 Starting YouTube Audio Pipeline v3.0 (CPU-NATIVE)..."
.venv/bin/python3 -m youtube_audio_pipeline.main "$@"
