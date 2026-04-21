#!/bin/bash

# Navigate to project root
cd "$(dirname "$0")"

# Run the Standard Sequential Engine
echo "🚀 Starting YouTube Audio Pipeline v3.1 (STANDARD BASELINE)..."
.venv/bin/python3 -m youtube_audio_pipeline.main "$@"
