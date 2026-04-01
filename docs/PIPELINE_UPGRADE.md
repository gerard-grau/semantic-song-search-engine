# YouTube Audio Pipeline Upgrade & Validation Summary

This document summarizes the enhancements made to the YouTube audio pipeline to support advanced ML-based feature extraction and database-optimized data structures.

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
To support these models and prepare for database ingestion (e.g., MariaDB), the following updates were made:

- **Multi-task Inference**: Transitioned from individual binary mood heads to a single multi-task model for improved efficiency.
- **WAV Conversion**: Updated `youtube_audio_pipeline/downloader.py` to automatically convert YouTube audio to WAV format, ensuring 100% compatibility with Essentia's `MonoLoader`.
- **Enriched Metadata**: Captured rich YouTube metrics including `ViewCount`, `LikeCount`, `Uploader`, and `UploadDate` to facilitate popularity-based searching.
- **Flattened Data Structure**: Selected the 12 most representative mood/theme tags and flattened them into individual **FLOAT** columns (e.g., `Mood_happy`, `Mood_energetic`). This enables direct SQL filtering without parsing JSON blobs.
- **Robust Feature Extraction**: Refactored `analyzer.py` to safely handle complex-to-real vector conversions and provide robust extraction for spectral features (BPM, Key, Loudness, etc.).
- **Fixed-Batch Processing**: Implemented a patching and batching system to satisfy the fixed batch size (64) requirement of the Discogs-EffNet backbone.

## 3. Validation Results
The pipeline was validated against multiple YouTube URLs, confirming successful extraction of enriched characteristics in a structured format.

### Sample Output Structure (Verified):
| Track | ViewCount | Genre | Mood_happy | Mood_energetic | Voice | Timbre |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Never Gonna Give You Up | 1.7B+ | Electronic---Synth-pop | 0.052 | 0.146 | voice | dark |
| GANGNAM STYLE | 5.1B+ | Electronic---Electro | 0.102 | 0.334 | voice | dark |

*\*Note: Scores reflect probabilistic confidence from 0.0 to 1.0.*

## 4. Maintenance
- **Persistence**: Models and metadata are stored in `youtube_audio_pipeline/models/`.
- **Validation Data**: The final structured test data is available in `data/processed/final_structure_test.csv`.
- **Database Mapping**: The CSV headers are designed to map directly to MariaDB `FLOAT`, `INT`, and `TEXT` types.
