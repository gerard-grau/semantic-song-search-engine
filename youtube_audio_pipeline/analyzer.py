from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
from pathlib import Path

import essentia
import essentia.standard as es
import numpy as np
import pandas as pd

from youtube_audio_pipeline import model_inference

logger = logging.getLogger(__name__)

# Core moods/themes to flatten into columns for easy querying
FLATTENED_MOODS = [
    "happy", "sad", "dark", "energetic", "relaxing", 
    "melodic", "emotional", "party", "romantic", 
    "summer", "upbeat", "calm"
]

# High-level parent genres from Discogs taxonomy
FLATTENED_GENRES = [
    "Blues", "Brass & Military", "Children's", "Classical", "Electronic", 
    "Folk, World, & Country", "Funk / Soul", "Hip Hop", "Jazz", "Latin", 
    "Non-Music", "Pop", "Reggae", "Rock", "Stage & Screen"
]

def analyze_and_discard(
    filepath: Path,
    metadata: dict,
    skip_models: bool = False,
) -> dict | None:
    """
    Extracts audio characteristics and ML features from a local audio file,
    and returns them as a dictionary. The caller is responsible for cleanup.
    """
    url = metadata.get("url", "Unknown URL")
    title = metadata.get("title", "Unknown Title")
    
    try:
        # 1. Extract audio characteristics using Essentia
        sample_rate = 44100
        loader = es.MonoLoader(filename=str(filepath), sampleRate=sample_rate)
        audio = loader()

        # Rhythm
        rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
        bpm, beats, beats_confidence, _, _ = rhythm_extractor(audio)

        # Key
        key_extractor = es.KeyExtractor()
        key, scale, strength = key_extractor(audio)

        # Loudness
        loudness_extractor = es.Loudness()
        loudness = loudness_extractor(audio)

        duration = len(audio) / sample_rate
        rms_energy = np.sqrt(np.mean(audio**2))

        # Proxy for onsets
        onset_count = len(beats)
        onset_rate = onset_count / duration if duration > 0 else 0

        # High-level features
        danceability_extractor = es.Danceability()
        danceability, _ = danceability_extractor(audio)
        valence = 0.0 

        # Spectral features
        zcr = es.ZeroCrossingRate()(audio)
        
        mfcc_json = "[]"
        hpcp_json = "[]"
        spec_centroid = 0.0
        spec_rolloff = 0.0
        spec_flatness = 0.0
        pitch_mean = 0.0
        pitch_std = 0.0

        try:
            w = es.Windowing(type="hann")
            fft = es.FFT()
            frame = audio[:1024]
            if len(frame) < 1024: frame = np.pad(frame, (0, 1024 - len(frame)))
            
            pitch_extractor = es.PitchYinFFT()
            pitches = []
            for f in es.FrameGenerator(audio, frameSize=2048, hopSize=1024):
                p_spec = fft(w(f))
                p, c = pitch_extractor(p_spec)
                if c > 0.5: pitches.append(p)
            pitch_mean = float(np.mean(pitches)) if pitches else 0.0
            pitch_std = float(np.std(pitches)) if pitches else 0.0

            mag = np.abs(fft(w(frame))).astype(np.float32)
            spec_centroid = float(es.Centroid()(mag))
            spec_rolloff = float(es.RollOff()(mag))
            spec_flatness = float(es.Flatness()(mag))
            
            _, mfcc_coeffs = es.MFCC()(mag)
            mfcc_json = json.dumps(mfcc_coeffs.tolist())
            hpcp_coeffs = es.HPCP()(mag)
            hpcp_json = json.dumps(hpcp_coeffs.tolist())
        except Exception as e:
            logger.debug(f"Spectral feature extraction failed: {e}")

        # 2. Extract ML Model Features
        mood_theme_flat = {f"Mood_{m}": 0.0 for m in FLATTENED_MOODS}
        genre_parent_flat = {f"Genre_{g.replace(' ', '').replace(',', '').replace('&', 'And').replace('/', 'Or')}": 0.0 for g in FLATTENED_GENRES}
        
        if not skip_models:
            full_res = model_inference.run_full_inference(audio)
            
            # Parse Genre (with aggregation and simplification)
            genre_probs = full_res["genre"]
            if genre_probs:
                # Top specific label
                genre_top_label, genre_top_confidence = max(genre_probs.items(), key=lambda x: x[1])
                
                # Aggregate by Parent
                parent_scores = {}
                for label, score in genre_probs.items():
                    parent = label.split("---")[0]
                    parent_scores[parent] = parent_scores.get(parent, 0.0) + score
                
                # Top Parent
                genre_top_parent = max(parent_scores.items(), key=lambda x: x[1])[0]
                
                # Flatten Parent Genres
                for g in FLATTENED_GENRES:
                    col_name = f"Genre_{g.replace(' ', '').replace(',', '').replace('&', 'And').replace('/', 'Or')}"
                    if g in parent_scores:
                        genre_parent_flat[col_name] = float(parent_scores[g])
                
                # Truncate specific JSON to top 5
                top_5_specific = dict(sorted(genre_probs.items(), key=lambda x: x[1], reverse=True)[:5])
                genre_probs_json = json.dumps(top_5_specific)
            else:
                genre_top_label, genre_top_confidence = "Unknown", 0.0
                genre_top_parent = "Unknown"
                genre_probs_json = "{}"
            
            # Parse Mood & Theme (Multi-task)
            mood_theme_probs = full_res["mood_theme"]
            top_moods = sorted(mood_theme_probs.items(), key=lambda x: x[1], reverse=True)[:5]
            top_moods_str = ", ".join([f"{m} ({s:.2f})" for m, s in top_moods])
            
            # Flatten selected moods
            for m in FLATTENED_MOODS:
                if m in mood_theme_probs:
                    mood_theme_flat[f"Mood_{m}"] = float(mood_theme_probs[m])
            
            inst_probs = full_res["instrumentation"]
            top_inst = sorted(inst_probs.items(), key=lambda x: x[1], reverse=True)[:3]
            top_inst_str = ", ".join([f"{i} ({s:.2f})" for i, s in top_inst])
            
            voice_res = full_res["voice_instrumental"]
            voice_inst_label = max(voice_res.items(), key=lambda x: x[1])[0] if voice_res else "unknown"
            
            gender_res = full_res["voice_gender"]
            gender_label = max(gender_res.items(), key=lambda x: x[1])[0] if gender_res else "unknown"
            
            # Parse Timbre
            timbre_res = full_res["timbre"]
            timbre_label = max(timbre_res.items(), key=lambda x: x[1])[0] if timbre_res else "unknown"
            
            # Embedding
            embedding = full_res["embedding"]
            embedding_json = json.dumps(embedding.tolist()) if embedding is not None else "[]"
        else:
            genre_top_label, genre_top_confidence, genre_probs_json = "Unknown", 0.0, "{}"
            genre_top_parent = "Unknown"
            mood_theme_probs = {}
            top_moods_str, top_inst_str = "", ""
            voice_inst_label, gender_label, timbre_label = "unknown", "unknown", "unknown"
            embedding_json = "[]"

        # 3. Combine results
        result = {
            "URL": url,
            "Title": title,
            "YouTubeID": metadata.get("id", "Unknown"),
            "Uploader": metadata.get("uploader", "Unknown"),
            "Channel": metadata.get("channel", "Unknown"),
            "UploadDate": metadata.get("upload_date", "Unknown"),
            "ViewCount": int(metadata.get("view_count", 0)),
            "LikeCount": int(metadata.get("like_count", 0)),
            "BPM": float(bpm),
            "Key": f"{key} {scale}",
            "KeyStrength": float(strength),
            "Loudness": float(loudness),
            "DurationSeconds": float(duration),
            "RmsEnergy": float(rms_energy),
            "BeatConfidence": float(beats_confidence),
            "BeatCount": int(len(beats)),
            "OnsetRate": float(onset_rate),
            "OnsetCount": int(onset_count),
            "Danceability": float(danceability),
            "Valence": float(valence),
            "SpectralCentroidHz": spec_centroid,
            "SpectralRolloffHz": spec_rolloff,
            "SpectralFlatness": spec_flatness,
            "PitchMeanHz": pitch_mean,
            "PitchStdHz": pitch_std,
            "ZeroCrossingRate": float(zcr),
            "MfccMeanJson": mfcc_json,
            "HpcpMeanJson": hpcp_json,
            "GenreTopLabel": genre_top_label,
            "GenreTopParent": genre_top_parent,
            "GenreTopConfidence": genre_top_confidence,
            "GenreProbsJson": genre_probs_json,
            "MoodThemeSummary": top_moods_str,
            "MoodThemeProbsJson": json.dumps(mood_theme_probs),
            "InstrumentationSummary": top_inst_str,
            "VoiceInstrumental": voice_inst_label,
            "VoiceGender": gender_label,
            "Timbre": timbre_label,
            "DiscogsEmbeddingJson": embedding_json,
        }
        
        # Add flattened columns
        result.update(mood_theme_flat)
        result.update(genre_parent_flat)

        return result

    except Exception as e:
        logger.error(f"Analysis failed for {url}: {e}")
        return None


def save_to_dataframe(results_list: list[dict], output_csv: str) -> None:
    if not results_list: return
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results_list)
    if output_path.exists():
        df.to_csv(output_path, mode="a", header=False, index=False)
    else:
        df.to_csv(output_path, index=False)
