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


def analyze_and_discard(
    filepath: Path,
    url: str,
    title: str = "Unknown",
    skip_models: bool = False,
) -> dict | None:
    """
    Extracts audio characteristics and ML features from a local audio file,
    and returns them as a dictionary. The caller is responsible for cleanup.
    """
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
        
        # Move potentially complex spectral features to safe extraction
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
            
            # Use raw FFT for pitch
            pitch_extractor = es.PitchYinFFT()
            pitches = []
            for f in es.FrameGenerator(audio, frameSize=2048, hopSize=1024):
                p, c = pitch_extractor(fft(w(f)))
                if c > 0.5: pitches.append(p)
            pitch_mean = float(np.mean(pitches)) if pitches else 0.0
            pitch_std = float(np.std(pitches)) if pitches else 0.0

            # Use magnitude for others
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
        if not skip_models:
            full_res = model_inference.run_full_inference(audio)
            
            genre_probs = full_res["genre"]
            genre_top_label, genre_top_confidence = max(genre_probs.items(), key=lambda x: x[1]) if genre_probs else ("Unknown", 0.0)
            
            mood_theme_probs = full_res["mood_theme"]
            top_moods = sorted(mood_theme_probs.items(), key=lambda x: x[1], reverse=True)[:5]
            top_moods_str = ", ".join([f"{m} ({s:.2f})" for m, s in top_moods])
            
            inst_probs = full_res["instrumentation"]
            top_inst = sorted(inst_probs.items(), key=lambda x: x[1], reverse=True)[:3]
            top_inst_str = ", ".join([f"{i} ({s:.2f})" for i, s in top_inst])
            
            voice_res = full_res["voice_instrumental"]
            voice_inst_label = max(voice_res.items(), key=lambda x: x[1])[0] if voice_res else "unknown"
            
            gender_res = full_res["voice_gender"]
            gender_label = max(gender_res.items(), key=lambda x: x[1])[0] if gender_res else "unknown"
            
            timbre_res = full_res["timbre"]
            timbre_label = max(timbre_res.items(), key=lambda x: x[1])[0] if timbre_res else "unknown"
            
            embedding = full_res["embedding"]
            embedding_json = json.dumps(embedding.tolist()) if embedding is not None else "[]"
        else:
            genre_top_label, genre_top_confidence, genre_probs = "Unknown", 0.0, {}
            mood_theme_probs = {}
            top_moods_str, top_inst_str = "", ""
            voice_inst_label, gender_label, timbre_label = "unknown", "unknown", "unknown"
            embedding_json = "[]"

        # 3. Combine results
        result = {
            "URL": url,
            "Title": title,
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
            "MfccStdJson": "[]",
            "HpcpMeanJson": hpcp_json,
            "GenreTopLabel": genre_top_label,
            "GenreTopConfidence": genre_top_confidence,
            "GenreProbsJson": json.dumps(genre_probs),
            "MoodThemeSummary": top_moods_str,
            "MoodThemeProbsJson": json.dumps(mood_theme_probs),
            "InstrumentationSummary": top_inst_str,
            "VoiceInstrumental": voice_inst_label,
            "VoiceGender": gender_label,
            "Timbre": timbre_label,
            "DiscogsEmbeddingJson": embedding_json,
        }

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
