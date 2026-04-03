# YouTube Audio Pipeline: CPU-Native Stealth (v3.0)

This document provides a technical overview of the v3.0 "CPU-Native" architecture, designed for maximum stability and resilience when processing large datasets (10,000+ songs).

---

## 🚀 The CPU-Native Pivot (v3.0)

We have transitioned from GPU-accelerated processing to **Pure CPU Execution**. While the GPU offered theoretical speed, the NVIDIA L4 driver environment proved unstable for long-running, intermittent tasks. 

### 💎 Why v3.0 is the best version yet:
1.  **Rock-Solid Stability**: By bypassing the NVIDIA drivers entirely, we have eliminated 100% of the memory allocation and cuDNN initialization crashes.
2.  **Simplified Environment**: No more `LD_LIBRARY_PATH` hacks or complex bash exports. The engine runs natively in any standard Python environment.
3.  **High-Fidelity Accuracy preserved**: Even on CPU, you get the full **Melodia Pitch Tracking** and 6x high-resolution spectral math.
4.  **Implicit Stealth**: The CPU processing time (~8s/song) acts as a natural "human-like" delay that helps prevent YouTube bot detection.

---

## 🕵️ Key Features

### 1. Resiliency & Hibernate Mode
The engine detects bot-challenges (`Sign in to confirm you're not a bot`). 
*   **Action**: On detection, the system enters **Hibernate Mode** for 5 minutes.
*   **Result**: Prevents IP blacklisting and allows rate-limit buckets to reset.

### 2. Persistent State Saver
Progress is tracked in `data/processed/pipeline_state.json`.
*   **Action**: Every successful track is logged.
*   **Result**: Automatic resume support. If the process is interrupted, it skips finished tracks instantly upon restart.

---

## 🚀 Usage Guide

### Recommended Execution:
We recommend running the engine inside a **`tmux`** session to prevent interruption if your SSH connection drops.

```bash
# Start the CPU-Native Stealth Engine
./youtube_audio_pipeline/youtube_pipeline.sh
```

### Capacity:
*   **Steady State Speed**: ~8-10 seconds per song.
*   **Hourly Throughput**: ~350-400 songs per hour.
*   **Full 10k Run**: ~25-30 Hours (Perfect for a single weekend run).
