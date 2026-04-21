# YouTube Audio Pipeline: Sequential Baseline (v3.1)

This document provides a technical overview of the v3.1 "Sequential" architecture, designed for maximum stability and consistent high-fidelity processing of audio datasets.

---

## 🚀 The Sequential Pivot (v3.1)

We have transitioned to a **Sequential Baseline** model. While parallel processing offers theoretical throughput, the sequential approach ensures maximum system stability and prevents resource contention during long-running tasks.

### 💎 Key Features:
1.  **System Stability**: Processes songs one-by-one to ensure 100% reliable execution and prevent memory or network congestion.
2.  **CPU-Native Design**: Explicitly optimized for CPU-only environments to bypass the complexities of virtualized GPU driver management.
3.  **High-Fidelity Accuracy**: Utilizes precision algorithms including **Melodia Pitch Tracking** and high-resolution spectral analysis for peak data quality.
4.  **Persistent State**: Tracks progress in `pipeline_state.json` to support automatic resumes after system reboots or interruptions.

---

## 🛠️ Usage Guide

### Recommended Execution:
We recommend running the engine inside a **`tmux`** session for persistent background execution.

```bash
# Start the Standard Sequential Engine
./youtube_audio_pipeline/youtube_pipeline.sh
```

### Capacity & Performance:
*   **Throughput**: ~350-400 songs per hour.
*   **Consistency**: Extremely high. The engine is designed for "Set and Forget" operation over several days.
*   **Maintenance**: Fully automated resume and state management.
