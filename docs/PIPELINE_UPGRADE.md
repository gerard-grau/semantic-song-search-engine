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
- **Genre Aggregation & Flattening**: 
    - Aggregated 400 subgenres into **15 high-level Parent Categories** (Electronic, Rock, Pop, etc.).
    - Added individual **FLOAT** columns for each Parent Category (e.g., `Genre_Rock`, `Genre_Electronic`).
    - Added `GenreTopParent` for high-level classification.
    - Simplified `GenreProbsJson` to store only the **Top 5 specific subgenres**, drastically reducing CSV size and escaping issues.
- **Flattened Mood Structure**: Selected the 12 most representative mood/theme tags and flattened them into individual **FLOAT** columns (e.g., `Mood_happy`, `Mood_energetic`).
- **Robust Feature Extraction**: Refactored `analyzer.py` to safely handle complex-to-real vector conversions and provide robust extraction for spectral features.
- **Fixed-Batch Processing**: Maintained 64-patch batching for efficient backbone execution.

## 3. Validation Results
The pipeline was validated against multiple YouTube URLs, confirming successful extraction of enriched characteristics in a structured format.

### Sample Output Structure (Verified):
| Track | GenreTopParent | ViewCount | Mood_happy | Genre_Rock | Voice | Timbre |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Never Gonna Give You Up | Electronic | 1.7B+ | 0.052 | 0.026 | voice | dark |
| GANGNAM STYLE | Electronic | 5.1B+ | 0.102 | 0.015 | voice | dark |

*\*Note: Scores reflect probabilistic confidence. For multi-label models, the sum of parent genres may exceed 1.0.*

## 4. Maintenance
- **Persistence**: Models and metadata are stored in `youtube_audio_pipeline/models/`.
- **Validation Data**: The final aggregated test data is available in `data/processed/genre_aggregation_test.csv`.
- **Database Mapping**: The CSV headers are designed to map directly to MariaDB `FLOAT`, `INT`, and `TEXT` types.
