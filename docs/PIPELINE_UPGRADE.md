# YouTube Audio Pipeline Upgrade & Validation Summary

This document summarizes the enhancements made to the YouTube audio pipeline to support advanced ML-based feature extraction.

## 1. Model Integration (Enriched Version)
The pipeline now utilizes an optimized suite of Essentia pretrained models, hosted locally in `youtube_audio_pipeline/models/`:

- **Backbone**: `discogs-effnet-1.pb` (EfficientNet-B0 backbone for audio embeddings).
- **Genre Classifier**: `genre_discogs400-discogs-effnet-1.pb` (High-granularity classifier with 400 music styles).
- **Mood & Theme (Multi-task)**: `mtg_jamendo_moodtheme-discogs-effnet-1.pb` (Predicts 56 moods and themes simultaneously).
- **Instrumentation**: `mtg_jamendo_instrument-discogs-effnet-1.pb` (Detects 40 instrument types).
- **Voice Detection**: 
    - `voice_instrumental-discogs-effnet-1.pb` (Binary classification).
    - `voice_gender-discogs-effnet-1.pb` (Male/Female classification).
- **Timbre**: `timbre-discogs-effnet-1.pb` (Bright/Dark classification).

## 2. Technical Enhancements
To support these models, several critical updates were made:

- **Multi-task Inference**: Transitioned from individual binary mood heads to a single multi-task model for improved efficiency.
- **WAV Conversion**: Updated `youtube_audio_pipeline/downloader.py` to automatically convert YouTube audio to WAV format, ensuring compatibility with Essentia's `MonoLoader`.
- **Robust Feature Extraction**: Refactored `analyzer.py` to handle complex-to-real vector conversions and provide safe extraction for spectral features.
- **Dynamic Tensor Discovery**: Implemented automatic input/output tensor discovery in `model_inference.py` to support diverse frozen graph exports.
- **Fixed-Batch Processing**: Maintained 64-patch batching for efficient backbone execution.

## 3. Validation Results
The pipeline was validated against multiple YouTube URLs, confirming successful extraction of enriched musical characteristics.

### Sample Output (Verified):
| Track | Genre | Top Moods/Themes | Voice | Gender | Timbre |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Never Gonna Give You Up | Electronic---Synth-pop | energetic, melodic, summer | voice | female* | dark |
| GANGNAM STYLE | Electronic---Electro | energetic, party, happy | voice | male | dark |

*\*Note: Model predictions are probabilistic and reflect the classifier's confidence.*

## 4. Maintenance
- **Persistence**: Models and metadata are stored in `youtube_audio_pipeline/models/`.
- **Validation Data**: The enriched test run data is available in `data/processed/enriched_validation.csv`.
