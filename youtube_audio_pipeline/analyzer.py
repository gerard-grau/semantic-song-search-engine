from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
import time
from pathlib import Path

import essentia
import essentia.standard as es
import numpy as np
import pandas as pd

from youtube_audio_pipeline import model_inference

# SILENCE: Suppress noisy Essentia "No network created" warnings
essentia.log.infoActive = False
essentia.log.warningActive = False

logger = logging.getLogger(__name__)

# High-level parent genres from Discogs taxonomy
FLATTENED_GENRES = [
    "Blues", "Brass & Military", "Children's", "Classical", "Electronic", 
    "Folk, World, & Country", "Funk / Soul", "Hip Hop", "Jazz", "Latin", 
    "Non-Music", "Pop", "Reggae", "Rock", "Stage & Screen"
]

# Full 56 mood/theme tags from MTG-Jamendo
ALL_MOODS = [
    "action", "adventure", "advertising", "background", "ballad", "calm", "children", 
    "christmas", "commercial", "cool", "corporate", "dark", "deep", "documentary", 
    "drama", "dramatic", "dream", "emotional", "energetic", "epic", "fast", "film", 
    "fun", "funny", "game", "groovy", "happy", "heavy", "holiday", "hopeful", 
    "inspiring", "love", "meditative", "melancholic", "melodic", "motivational", 
    "movie", "nature", "party", "positive", "powerful", "relaxing", "retro", 
    "romantic", "sad", "sexy", "slow", "soft", "soundscape", "space", "sport", 
    "summer", "trailer", "travel", "upbeat", "uplifting"
]

def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))

def extract_base_features(input_data: Path | np.ndarray, metadata: dict, skip_models: bool = False, skip_pitch: bool = False) -> tuple[dict, np.ndarray | None] | None:
    """
    Stage 1: Optimized feature extraction at 16kHz.
    """
    try:
        sample_rate = 16000
        
        if isinstance(input_data, np.ndarray):
            audio = input_data
        else:
            # Load audio at 16kHz
            loader = es.MonoLoader(filename=str(input_data), sampleRate=sample_rate)
            audio = loader()

        # 1. Rhythm & Beats
        rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
        bpm, beats, beats_confidence, _, _ = rhythm_extractor(audio)
        beat_count = len(beats)
        
        # 2. Key & Energy
        key, scale, strength = es.KeyExtractor()(audio)
        overall_loudness = es.Loudness()(audio)
        rms_energy = np.sqrt(np.mean(audio**2))
        dance_alg_val, _ = es.Danceability()(audio)

        # 3. Spectral Loop (Unified for efficiency)
        od_hfc = es.OnsetDetection(method="hfc")
        w = es.Windowing(type="hann")
        fft = es.FFT()
        c2p = es.CartesianToPolar()
        
        det_func = []
        centroids, rolloffs, flatness, mfccs, hpcps = [], [], [], [], []
        mfcc_alg = es.MFCC(numberCoefficients=13, inputSize=513, sampleRate=sample_rate, highFrequencyBound=8000)
        hpcp_alg = es.HPCP(sampleRate=sample_rate)
        peaks_alg = es.SpectralPeaks(sampleRate=sample_rate)

        for frame in es.FrameGenerator(audio, frameSize=1024, hopSize=512):
            mag, phs = c2p(fft(w(frame)))
            det_func.append(od_hfc(mag, phs))
            
            # Sub-sample spectral averages (~1s interval)
            if len(det_func) % 31 == 0:
                m_f = mag.astype(np.float32)
                centroids.append(es.Centroid()(m_f))
                rolloffs.append(es.RollOff()(m_f))
                flatness.append(es.Flatness()(m_f))
                _, m_coeffs = mfcc_alg(m_f)
                mfccs.append(m_coeffs)
                f, m = peaks_alg(m_f)
                hpcps.append(hpcp_alg(f, m))

        onset_times = es.Onsets()(essentia.array([det_func]), [1])
        duration = len(audio) / sample_rate

        # 4. Parallel ML Preprocessing
        ml_patches = None
        if not skip_models:
            ml_patches = model_inference.preprocess_audio(audio)

        # 5. Pitch (Optional)
        res_pitch = {"PitchMeanHz": 0.0, "PitchStdHz": 0.0}
        if not skip_pitch:
            try:
                pitch_vals, pitch_conf = es.PredominantPitchMelodia(sampleRate=sample_rate)(audio)
                valid = pitch_vals[pitch_conf > 0.3]
                res_pitch["PitchMeanHz"] = float(np.mean(valid)) if len(valid) > 0 else 0.0
                res_pitch["PitchStdHz"] = float(np.std(valid)) if len(valid) > 0 else 0.0
            except: pass

        res = {
            "YouTubeID": metadata.get("id", "Unknown"),
            "Title": metadata.get("title", "Unknown"),
            "Uploader": metadata.get("uploader", "Unknown"),
            "Channel": metadata.get("channel", "Unknown"),
            "UploadDate": metadata.get("upload_date", "Unknown"),
            "URL": metadata.get("url", "Unknown"),
            "ViewCount": int(metadata.get("view_count", 0)),
            "LikeCount": int(metadata.get("like_count", 0)),
            "BPM": float(bpm),
            "Key": f"{key} {scale}",
            "Scale": str(scale),
            "KeyStrength": float(strength),
            "Loudness": float(overall_loudness),
            "DurationSeconds": float(duration),
            "RmsEnergy": float(rms_energy),
            "BeatConfidence": float(beats_confidence),
            "BeatCount": int(beat_count),
            "OnsetRate": float(len(onset_times) / duration) if duration > 0 else 0.0,
            "OnsetCount": int(len(onset_times)),
            "RawDanceability": float(dance_alg_val),
            "SpectralCentroidHz": float(np.mean(centroids)) if centroids else 0.0,
            "SpectralRolloffHz": float(np.mean(rolloffs)) if rolloffs else 0.0,
            "SpectralFlatness": float(np.mean(flatness)) if flatness else 0.0,
            "ZeroCrossingRate": float(es.ZeroCrossingRate()(audio)),
            "AvgMFCC": np.mean(mfccs, axis=0) if mfccs else np.zeros(13),
            "AvgHPCP": np.mean(hpcps, axis=0) if hpcps else np.zeros(12),
        }
        res.update(res_pitch)
        return res, ml_patches

    except Exception as e:
        logger.error(f"Base extraction failed: {e}")
        return None

def finalize_song_data(base_data: dict, ml_res: dict) -> dict:
    genre_probs = ml_res.get("genre", {})
    genre_top_label, genre_top_confidence = "Unknown", 0.0
    genre_top_parent = "Unknown"
    genre_parent_flat = {f"Genre_{g.replace(' ', '').replace(',', '').replace('&', 'And').replace('/', 'Or')}": 0.0 for g in FLATTENED_GENRES}
    
    if genre_probs:
        genre_top_label, genre_top_confidence = max(genre_probs.items(), key=lambda x: x[1])
        parent_scores = {}
        for label, score in genre_probs.items():
            parent = label.split("---")[0]
            parent_scores[parent] = parent_scores.get(parent, 0.0) + score
        genre_top_parent = max(parent_scores.items(), key=lambda x: x[1])[0]
        for g in FLATTENED_GENRES:
            col_name = f"Genre_{g.replace(' ', '').replace(',', '').replace('&', 'And').replace('/', 'Or')}"
            if g in parent_scores: genre_parent_flat[col_name] = float(parent_scores[g])

    mood_theme_probs = ml_res.get("mood_theme", {})
    mood_theme_flat = {f"Mood_{m}": 0.0 for m in ALL_MOODS}
    for m in ALL_MOODS:
        if m in mood_theme_probs: mood_theme_flat[f"Mood_{m}"] = float(mood_theme_probs[m])

    major_flag = 1.0 if base_data["Scale"].lower() == "major" else 0.35
    c_norm = _clamp(base_data["SpectralCentroidHz"] / 4000.0)
    l_norm = _clamp((base_data["Loudness"] + 45.0) / 45.0)
    valence = _clamp(0.45 * major_flag + 0.35 * c_norm + 0.2 * l_norm)
    
    m_party = mood_theme_flat.get("Mood_party", 0.0)
    m_energetic = mood_theme_flat.get("Mood_energetic", 0.0)
    danceability = _clamp(0.4 * base_data["RawDanceability"] + 0.3 * m_party + 0.2 * m_energetic + 0.1 * base_data["BeatConfidence"])

    result = {
        "YouTubeID": base_data["YouTubeID"],
        "Title": base_data["Title"],
        "Uploader": base_data["Uploader"],
        "Channel": base_data["Channel"],
        "UploadDate": base_data["UploadDate"],
        "URL": base_data["URL"],
        "ViewCount": base_data["ViewCount"],
        "LikeCount": base_data["LikeCount"],
        "BPM": base_data["BPM"],
        "Key": base_data["Key"],
        "KeyStrength": base_data["KeyStrength"],
        "Loudness": base_data["Loudness"],
        "DurationSeconds": base_data["DurationSeconds"],
        "RmsEnergy": base_data["RmsEnergy"],
        "BeatConfidence": base_data["BeatConfidence"],
        "BeatCount": base_data["BeatCount"],
        "OnsetRate": base_data["OnsetRate"],
        "OnsetCount": base_data["OnsetCount"],
        "Danceability": float(danceability),
        "Valence": float(valence),
        "SpectralCentroidHz": base_data["SpectralCentroidHz"],
        "SpectralRolloffHz": base_data["SpectralRolloffHz"],
        "SpectralFlatness": base_data["SpectralFlatness"],
        "PitchMeanHz": base_data["PitchMeanHz"],
        "PitchStdHz": base_data["PitchStdHz"],
        "ZeroCrossingRate": base_data["ZeroCrossingRate"],
        "GenreTopParent": genre_top_parent,
        "GenreTopLabel": genre_top_label,
        "GenreTopConfidence": genre_top_confidence,
        "VoiceInstrumental": max(ml_res.get("voice_instrumental", {}).items(), key=lambda x: x[1])[0] if ml_res.get("voice_instrumental") else "unknown",
        "VoiceGender": max(ml_res.get("voice_gender", {}).items(), key=lambda x: x[1])[0] if ml_res.get("voice_gender") else "unknown",
        "Timbre": max(ml_res.get("timbre", {}).items(), key=lambda x: x[1])[0] if ml_res.get("timbre") else "unknown",
    }
    
    result.update(mood_theme_flat)
    result.update(genre_parent_flat)
    for i, v in enumerate(base_data["AvgMFCC"]): result[f"MFCC_{i+1}"] = float(v)
    for i, v in enumerate(base_data["AvgHPCP"]): result[f"HPCP_{i+1}"] = float(v)
    result["GenreProbsJson"] = json.dumps(dict(sorted(genre_probs.items(), key=lambda x: x[1], reverse=True)[:5]))
    result["DiscogsEmbeddingJson"] = json.dumps(ml_res["embedding"].tolist()) if ml_res.get("embedding") is not None else "[]"

    return result

def save_to_dataframe(results_list: list[dict], output_csv: str) -> None:
    if not results_list: return
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results_list)
    df.to_csv(output_path, mode="a", header=not output_path.exists(), index=False)
