# Model Integration Guide (v3.0 CPU-Native)

Technical reference for Essentia pretrained model loading and inference in the YouTube audio pipeline.

## Overview

The pipeline integrates multiple Essentia pretrained TensorFlow models using the **EfficientNet** backbone:

1. **Genre Classification** (`genre_discogs400`): Predicts 400+ specific genres.
2. **Mood Classification** (56 tags): MTG-Jamendo mood and theme probabilities.
3. **Instrumentation**: Detects presence of different musical instruments.
4. **Voice/Instrumental**: Binary classification of vocal presence.
5. **Timbre**: Analyzes the overall "color" of the sound.
6. **Audio Embedding** (`discogs-effnet-1`): 1280-dimensional feature extractor.

## Architecture

### Model Loading Strategy (CPU-Native)

**Stability First:** Following instability with virtualized GPU drivers, the engine is now hardcoded for **Pure CPU Execution**. 
- Models are initialized globally at application startup using Singleton sessions.
- In-memory patches are chunked into groups of 64 to satisfy hardcoded model input shapes.

### Code Flow

```
main.py:main()
   ├─ load_urls()
   ├─ initialize_models_globally()
   │   └─ model_inference.py
   │       └─ _ensure_models_loaded()
   │           ├─ Load discogs-effnet.pb (Backbone)
   │           └─ Load 6 Head models (Genre, Mood, etc.)
   └─ run_stealth_pipeline()
       └─ Linear Loop (1 song at a time)
           └─ extract_base_features()
               ├─ Extract Melodia Pitch + Spectral Detail
               ├─ run_batch_inference() (Chunked 64-patch)
               └─ Return combined dict → CSV
```

## Model Initialization

### `initialize_models_globally() → None`

Called once at startup. Loads all models into memory and verifies sessions.

**Side Effects:**
- Populates global Singleton sessions (`_BACKBONE_SESS`, etc.)
- Logs "✓ [model] model initialized" to console.
- **FORCES CPU**: Automatically sets `CUDA_VISIBLE_DEVICES="-1"` to prevent GPU crashes.

## Performance (CPU Mode)

### Per-Song Inference

For a standard 4-minute song:
- **Audio feature extraction**: ~2.0–4.0s (Melodia + High-Res Spectral)
- **Model inference**: ~4.0–6.0s (TensorFlow on CPU)
- **Total end-to-end**: ~8–12s per song.

### Memory Requirements

- **Total Resident Model Memory**: ~2.5 GB.
- **Total Machine RAM Recommended**: 8 GB+.

## Integration with analyzer.py

The `extract_base_features()` function in `analyzer.py` handles the coordination:
1. Loads audio via Essentia `MonoLoader` (16kHz).
2. Performs rhythmic and harmonic analysis (including Melodia).
3. Computes Mel-spectrogram patches.
4. Passes patches to `model_inference.run_batch_inference()`.
5. Merges results into a single 131-column dictionary.

## References

- **Essentia Documentation:** http://essentia.upf.edu/documentation/
- **Essentia Model Zoo:** http://essentia.upf.edu/models/
- **Discogs Dataset:** https://www.discogs.com
