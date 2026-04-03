# YouTube Audio Pipeline (v3.0 CPU-Native)

A resilient, high-fidelity audio processing engine designed to extract 131 musical features and 1280-dim embeddings from YouTube URLs while respecting platform rate limits.

## 🕵️ v3.0 CPU-Native Stealth Architecture

This module has been refactored for **Maximum Stability**. It bypasses unstable GPU drivers and aggressive multi-threading to ensure a reliable 10,000+ song run without IP bans or crashes.

### Core Principles:
- **CPU-Native Stability**: Explicitly disables GPU initialization to prevent driver and memory allocation errors.
- **Resiliency Over Speed**: Processes songs one-by-one to mimic human behavior and stay under the ~300 videos/hour guest rate limit.
- **Self-Healing**: Automatically detects bot challenges and enters **Hibernate Mode** (5-minute pause) to let rate-limit buckets reset.
- **Persistence**: Tracks progress in `pipeline_state.json` allowing for seamless resumes after interruptions or server reboots.

## 💎 High-Fidelity Extraction

Since the pipeline is network-throttled, it utilizes the available CPU time to perform exhaustive musical analysis:

- **PredominantPitchMelodia**: Lead-pitch tracking for accurate melodic contours.
- **High-Res Spectral Mapping**: Captures timbral features with 6x higher temporal resolution than v1.0.
- **Precision Resampling**: High-quality source audio is resampled in-memory by Essentia's C++ core for maximum accuracy.

## 🚀 Usage

### Recommended Execution (via tmux)
We recommend running inside a `tmux` session so the process continues if your SSH connection drops.

```bash
# 1. Enter tmux
tmux new -s music_run

# 2. Start the engine
./youtube_audio_pipeline/youtube_pipeline.sh
```

### 🛠️ Manual Control
You can also run the module directly via Python:
```bash
.venv/bin/python3 -m youtube_audio_pipeline.main --batch-size 8
```

## 📦 Requirements
- **Python 3.10+**
- **FFmpeg**: Required for audio decoding.
- **Essentia & TensorFlow**: Handled via `requirements.txt`.
- *Note: `aria2c` is no longer required and has been removed for stealth.*
