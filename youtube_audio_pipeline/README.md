# YouTube Audio Pipeline (v3.1 Standard)

A resilient, high-fidelity audio processing engine designed to extract 131 musical features and 1280-dim embeddings from YouTube URLs.

## ⚙️ v3.1 Sequential Architecture

This module is designed for **Maximum Reliability**. It uses a sequential processing model to ensure stable resource usage and high-fidelity results across large datasets.

### Core Principles:
- **System Integrity**: Processes songs one-by-one to maintain consistent memory and CPU profiles.
- **CPU-Native Execution**: Hardcoded for CPU stability to ensure 100% uptime on any server environment.
- **Persistence**: Tracks progress in `pipeline_state.json` allowing for seamless resumes after interruptions.
- **High-Accuracy Extraction**: Utilizes lead-pitch tracking (Melodia) and high-resolution spectral mapping.

## 📦 Extracted Features

The pipeline produces a comprehensive dataset including:
- **Rhythmic**: BPM, BeatCount, BeatConfidence, OnsetRate.
- **Harmonic**: Key, Scale, PitchMeanHz, PitchStdHz, 12-bin HPCPs.
- **Timbral**: Spectral Centroid, Flatness, Rolloff, 13 MFCCs.
- **Classifications**: 56 Mood/Theme tags, 15 Parent Genres, Voice/Instrumental detection.
- **Embeddings**: 1280-dimensional Discogs-EFFNet vectors.

## 🚀 Usage

### Recommended Execution
```bash
./youtube_audio_pipeline/youtube_pipeline.sh
```

### Requirements
- **Python 3.10+**
- **FFmpeg**: Required for audio decoding.
- **Essentia & TensorFlow**: Standard dependencies for feature extraction.
