"""
Essentia TensorFlow Model Inference (Placeholder Discovery)

Automatically discovers input/output tensors and satisfies all placeholders.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf
import essentia.standard as es

logger = logging.getLogger(__name__)

# Global model instances
_models_lock = threading.Lock()
_PREPROCESSOR: Any = None
_BACKBONE_GRAPH: Any = None
_HEAD_GRAPHS: dict[str, Any] = {}
_METADATA: dict[str, Any] = {}
_models_initialized = False

MODELS_DIR = Path(__file__).parent / "models"

MODEL_REGISTRY = {
    "backbone": "discogs-effnet-1.pb",
    "genre": "genre_discogs400-discogs-effnet-1.pb",
    "mood_acoustic": "mood_acoustic-discogs-effnet-1.pb",
    "mood_aggressive": "mood_aggressive-discogs-effnet-1.pb",
    "mood_electronic": "mood_electronic-discogs-effnet-1.pb",
    "mood_happy": "mood_happy-discogs-effnet-1.pb",
    "mood_party": "mood_party-discogs-effnet-1.pb",
    "mood_relaxed": "mood_relaxed-discogs-effnet-1.pb",
    "mood_sad": "mood_sad-discogs-effnet-1.pb",
}

def _load_frozen_graph(pb_path: Path) -> tf.GraphDef:
    with tf.io.gfile.GFile(str(pb_path), "rb") as f:
        graph_def = tf.compat.v1.GraphDef()
        graph_def.ParseFromString(f.read())
    return graph_def

def _ensure_models_loaded() -> None:
    global _PREPROCESSOR, _BACKBONE_GRAPH, _HEAD_GRAPHS, _METADATA, _models_initialized

    if _models_initialized: return

    with _models_lock:
        if _models_initialized: return

        logger.info(f"Loading models from {MODELS_DIR}")
        _PREPROCESSOR = es.TensorflowInputMusiCNN()
        
        for key, filename in MODEL_REGISTRY.items():
            path = MODELS_DIR / filename
            if path.exists():
                graph_def = _load_frozen_graph(path)
                if key == "backbone":
                    _BACKBONE_GRAPH = graph_def
                else:
                    _HEAD_GRAPHS[key] = graph_def
                
                meta_path = path.with_name(filename.replace(".pb", "_metadata.json"))
                if meta_path.exists():
                    with open(meta_path, "r") as f:
                        _METADATA[key] = json.load(f)
                logger.info(f"✓ {key} loaded")

        _models_initialized = True

def initialize_models_globally() -> None:
    _ensure_models_loaded()

def _find_tensors(graph: tf.Graph):
    """
    Finds potential input and output tensors.
    """
    placeholders = [t.name for op in graph.get_operations() if op.type == "Placeholder" for t in op.outputs]
    
    # Primary input is usually the one with mel or Placeholder in name
    primary_input = ""
    for p in placeholders:
        if "mel" in p.lower() or "input" in p.lower() or "placeholder" in p.lower():
            primary_input = p
            break
    if not primary_input and placeholders:
        primary_input = placeholders[0]
        
    # Primary output
    outputs = []
    for op in graph.get_operations():
        for t in op.outputs:
            if t.dtype in [tf.float32, tf.float64]:
                if any(x in t.name for x in ["PartitionedCall", "Softmax", "Sigmoid"]):
                    outputs.append(t.name)
    
    primary_output = ""
    if outputs:
        # Prefer :1 for PartitionedCall
        pcalls_1 = [o for o in outputs if "PartitionedCall" in o and o.endswith(":1")]
        primary_output = pcalls_1[-1] if pcalls_1 else outputs[-1]
    
    return primary_input, primary_output, placeholders

def _run_with_discovery(graph_def: tf.GraphDef, input_value: np.ndarray) -> np.ndarray:
    with tf.Graph().as_default() as g:
        tf.import_graph_def(graph_def, name="model")
        inp_name, out_name, all_placeholders = _find_tensors(g)
        
        with tf.compat.v1.Session(graph=g) as sess:
            feed_dict = {inp_name: input_value}
            # Satisfy other placeholders
            for p in all_placeholders:
                if p != inp_name:
                    tensor = g.get_tensor_by_name(p)
                    if tensor.dtype == tf.string: feed_dict[p] = b""
                    elif tensor.dtype in [tf.float32, tf.float64]: feed_dict[p] = 0.0
                    else: feed_dict[p] = 0
            
            return sess.run(out_name, feed_dict=feed_dict)

def run_full_inference(audio: np.ndarray) -> dict[str, Any]:
    _ensure_models_loaded()
    results = {"genre": {}, "moods": {}, "embedding": None}
    if _BACKBONE_GRAPH is None: return results

    try:
        resampler = es.Resample(inputSampleRate=44100, outputSampleRate=16000)
        audio_16k = resampler(audio)

        mel_frames = []
        for frame in es.FrameGenerator(audio_16k, frameSize=512, hopSize=256, startFromZero=True):
            mel_frames.append(_PREPROCESSOR(frame).flatten())
        
        if not mel_frames: return results
        mel_data = np.array(mel_frames)
        
        patch_size, hop_size = 128, 64
        patches = []
        for i in range(0, len(mel_data) - patch_size + 1, hop_size):
            patches.append(mel_data[i:i+patch_size])
        
        if not patches:
            pad_len = patch_size - len(mel_data)
            patches.append(np.pad(mel_data, ((0, pad_len), (0, 0)), mode='constant'))

        # Fixed batch size processing for backbone
        batch_size = 64
        all_embeddings = []
        for i in range(0, len(patches), batch_size):
            batch = patches[i:i+batch_size]
            actual_len = len(batch)
            if actual_len < batch_size:
                for _ in range(batch_size - actual_len): batch.append(batch[-1])
            
            embeddings = _run_with_discovery(_BACKBONE_GRAPH, np.array(batch))
            all_embeddings.append(embeddings[:actual_len])
                
        track_embedding = np.mean(np.concatenate(all_embeddings, axis=0), axis=0, keepdims=True)
        results["embedding"] = track_embedding.flatten()

        for key, graph_def in _HEAD_GRAPHS.items():
            logits = _run_with_discovery(graph_def, track_embedding)
            probs = logits.flatten()
            
            if key == "genre":
                labels = _METADATA[key].get("classes", [])
                results["genre"] = {labels[i]: float(probs[i]) for i in range(min(len(labels), len(probs)))}
            else:
                mood_name = key.replace("mood_", "")
                results["moods"][mood_name] = float(probs[0])

    except Exception as e:
        logger.error(f"Inference failed: {e}")
        
    return results

def run_genre_inference(audio: np.ndarray, sr: int = 44100) -> dict[str, float]:
    return run_full_inference(audio)["genre"]

def run_mood_inference(audio: np.ndarray, sr: int = 44100) -> dict[str, float]:
    return run_full_inference(audio)["moods"]

def run_embedding_inference(audio: np.ndarray, sr: int = 44100) -> np.ndarray | None:
    return run_full_inference(audio)["embedding"]
