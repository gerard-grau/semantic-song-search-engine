# YouTube Audio Pipeline Upgrade & Validation Summary

This document summarizes the enhancements made to the YouTube audio pipeline to support advanced ML-based feature extraction.

## 1. Model Integration
The pipeline now utilizes the following Essentia pretrained models, hosted locally in `youtube_audio_pipeline/models/`:

- **Backbone**: `discogs-effnet-1.pb` (EfficientNet-B0 backbone for audio embeddings).
- **Genre Classifier**: `genre_discogs400-discogs-effnet-1.pb` (High-granularity classifier with 400 music styles).
- **Mood Classifiers**: 7 specialized binary heads for `acoustic`, `aggressive`, `electronic`, `happy`, `party`, `relaxed`, and `sad`.

## 2. Technical Enhancements
To support these models, several critical updates were made to `youtube_audio_pipeline/model_inference.py`:

- **Robust Frozen Graph Loading**: Implemented pure TensorFlow session-based loading for `.pb` frozen graphs, as standard `tf.saved_model.load` is incompatible with these specific exports.
- **Mel-Spectrogram Preprocessing**: Integrated Essentia's `TensorflowInputMusiCNN` preprocessor with custom framing logic (512-sample frames, 256-sample hop) to match the model's expected input distribution at 16kHz.
- **Fixed-Batch Processing**: Implemented a patching and batching system to satisfy the fixed batch size (64) requirement of the Discogs-EffNet backbone.
- **Placeholder Discovery**: Added logic to automatically discover input/output tensors and satisfy auxiliary placeholders (e.g., `saver_filename`) with default values to ensure stable execution in TensorFlow 2.x.

## 3. Validation Results
The pipeline was validated against multiple YouTube URLs, confirming successful extraction of:
- **Audio Features**: BPM, Key, Loudness, MFCC, HPCP.
- **Genre Labels**: Granular style labels (e.g., `Electronic---Synth-pop`).
- **Mood Scores**: Probabilities across all 7 dimensions.
- **Embeddings**: 1280-dimensional feature vectors serialized as JSON.

### Sample Output (Verified):
| URL ID | Title | Genre | Mood (Happy/Sad) | Embedding |
| :--- | :--- | :--- | :--- | :--- |
| `dQw4w9WgXcQ` | Never Gonna Give You Up | Electronic---Synth-pop | 0.66 / 0.96 | 1280-dim |
| `9bZkp7q19f0` | GANGNAM STYLE | Electronic---Electro | 0.70 / 0.96 | 1280-dim |

## 4. Maintenance
- **Cleanup**: All temporary logs and experimental scripts have been removed from the workspace root.
- **Persistence**: Final models and metadata are stored in `youtube_audio_pipeline/models/`.
- **Validation Data**: The final test run data is available in `data/processed/full_validation.csv`.
