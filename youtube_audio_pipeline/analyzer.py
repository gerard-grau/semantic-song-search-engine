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

def extract_base_features(filepath: Path, metadata: dict, skip_models: bool = False) -> tuple[dict, np.ndarray | None] | None:
    """
    Stage 1: CPU-intensive feature extraction + Parallel Mel-Preprocessing.
    """
    try:
        sample_rate = 44100
        loader = es.MonoLoader(filename=str(filepath), sampleRate=sample_rate)
        audio = loader()

        # 1. Rhythm & Beats
        rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
        bpm, beats, beats_confidence, _, _ = rhythm_extractor(audio)

        # 2. Onset Detection
        od_hfc = es.OnsetDetection(method="hfc")
        w_od = es.Windowing(type="hann")
        fft_od = es.FFT()
        c2p_od = es.CartesianToPolar()
        onsets_alg = es.Onsets()
        det_func = []
        for frame in es.FrameGenerator(audio, frameSize=1024, hopSize=512):
            mag, phs = c2p_od(fft_od(w_od(frame)))
            det_func.append(od_hfc(mag, phs))
        onset_times = onsets_alg(essentia.array([det_func]), [1])
        onset_count = len(onset_times)

        # 3. Key, Loudness, Energy
        key, scale, strength = es.KeyExtractor()(audio)
        overall_loudness = es.Loudness()(audio)
        duration = len(audio) / sample_rate
        rms_energy = np.sqrt(np.mean(audio**2))
        dance_alg_val, _ = es.Danceability()(audio)

        # 4. Spectral Averages
        centroids, rolloffs, flatness, mfccs, hpcps = [], [], [], [], []
        w = es.Windowing(type="hann")
        fft = es.FFT()
        mfcc_alg = es.MFCC(numberCoefficients=13)
        hpcp_alg = es.HPCP()
        peaks_alg = es.SpectralPeaks()
        
        for frame in es.FrameGenerator(audio, frameSize=2048, hopSize=sample_rate):
            mag = np.abs(fft(w(frame))).astype(np.float32)
            try: centroids.append(es.Centroid()(mag))
            except: pass
            try: rolloffs.append(es.RollOff()(mag))
            except: pass
            try: flatness.append(es.Flatness()(mag))
            except: pass
            try:
                _, m_coeffs = mfcc_alg(mag)
                mfccs.append(m_coeffs)
            except: pass
            try:
                f, m = peaks_alg(mag)
                hpcps.append(hpcp_alg(f, m))
            except: pass

        # 5. Parallel Mel-Preprocessing (Move 16kHz resampling and patch creation here)
        ml_patches = None
        if not skip_models:
            audio_16k = es.Resample(inputSampleRate=sample_rate, outputSampleRate=16000)(audio)
            ml_patches = model_inference.preprocess_audio(audio_16k)

        # 6. Partial Result
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
            "BeatCount": int(len(beats)),
            "OnsetRate": float(onset_count / duration) if duration > 0 else 0.0,
            "OnsetCount": int(onset_count),
            "RawDanceability": float(dance_alg_val),
            "SpectralCentroidHz": float(np.mean(centroids)) if centroids else 0.0,
            "SpectralRolloffHz": float(np.mean(rolloffs)) if rolloffs else 0.0,
            "SpectralFlatness": float(np.mean(flatness)) if flatness else 0.0,
            "ZeroCrossingRate": float(es.ZeroCrossingRate()(audio)),
            "AvgMFCC": np.mean(mfccs, axis=0) if mfccs else np.zeros(13),
            "AvgHPCP": np.mean(hpcps, axis=0) if hpcps else np.zeros(12),
        }
        
        # Pitch (Heavy)
        try:
            pitch_vals, pitch_conf = es.PredominantPitchMelodia(sampleRate=sample_rate)(audio)
            valid = pitch_vals[pitch_conf > 0.3]
            res["PitchMeanHz"] = float(np.mean(valid)) if len(valid) > 0 else 0.0
            res["PitchStdHz"] = float(np.std(valid)) if len(valid) > 0 else 0.0
        except:
            res["PitchMeanHz"], res["PitchStdHz"] = 0.0, 0.0

        return res, ml_patches

    except Exception as e:
        logger.error(f"Base extraction failed: {e}")
        return None

def finalize_song_data(base_data: dict, ml_res: dict) -> dict:
    """
    Stage 3: Merge base features with pre-computed ML results.
    """
    # Parse Genre
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

    # Parse Moods
    mood_theme_probs = ml_res.get("mood_theme", {})
    mood_theme_flat = {f"Mood_{m}": 0.0 for m in ALL_MOODS}
    for m in ALL_MOODS:
        if m in mood_theme_probs: mood_theme_flat[f"Mood_{m}"] = float(mood_theme_probs[m])

    # High-level Proxies
    major_flag = 1.0 if base_data["Scale"].lower() == "major" else 0.35
    c_norm = _clamp(base_data["SpectralCentroidHz"] / 4000.0)
    l_norm = _clamp((base_data["Loudness"] + 45.0) / 45.0)
    valence = _clamp(0.45 * major_flag + 0.35 * c_norm + 0.2 * l_norm)
    
    m_party = mood_theme_flat.get("Mood_party", 0.0)
    m_energetic = mood_theme_flat.get("Mood_energetic", 0.0)
    danceability = _clamp(0.4 * base_data["RawDanceability"] + 0.3 * m_party + 0.2 * m_energetic + 0.1 * base_data["BeatConfidence"])

    # Final Result
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
