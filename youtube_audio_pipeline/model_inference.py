"""
Essentia TensorFlow Model Inference (CPU-Native v3.0)
Hardcoded for CPU stability to bypass NVIDIA driver issues.
"""

from __future__ import annotations

import json
import logging
import threading
import os
from pathlib import Path
from typing import Any

# --- FORCE CPU MODE ---
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3" # Silence all TF logs
# ----------------------

import numpy as np
import tensorflow as tf
import essentia.standard as es

logger = logging.getLogger(__name__)

# Global model instances
_models_lock = threading.Lock()
_PREPROCESSOR: Any = None
_BACKBONE_SESS: tf.compat.v1.Session = None
_HEAD_SESSIONS: dict[str, tuple[tf.compat.v1.Session, str, str, list[str]]] = {}
_METADATA: dict[str, Any] = {}
_models_initialized = False

# Global address references
_INP_B, _OUT_B, _PHELDS_B = "", "", []

MODELS_DIR = Path(__file__).parent / "models"

MODEL_REGISTRY = {
    "backbone": "discogs-effnet-1.pb",
    "genre": "genre_discogs400-discogs-effnet-1.pb",
    "mood_theme": "mtg_jamendo_moodtheme-discogs-effnet-1.pb",
    "instrumentation": "mtg_jamendo_instrument-discogs-effnet-1.pb",
    "voice_instrumental": "voice_instrumental-discogs-effnet-1.pb",
    "voice_gender": "voice_gender-discogs-effnet-1.pb",
    "timbre": "timbre-discogs-effnet-1.pb",
}

def _load_frozen_graph(pb_path: Path) -> tf.GraphDef:
    with tf.io.gfile.GFile(str(pb_path), "rb") as f:
        graph_def = tf.compat.v1.GraphDef()
        graph_def.ParseFromString(f.read())
    return graph_def

def _find_tensors(graph: tf.Graph):
    placeholders = [t.name for op in graph.get_operations() if op.type == "Placeholder" for t in op.outputs]
    primary_input = ""
    for p in placeholders:
        if "mel" in p.lower() or "input" in p.lower() or "placeholder" in p.lower():
            primary_input = p
            break
    if not primary_input and placeholders:
        primary_input = placeholders[0]
        
    outputs = []
    for op in graph.get_operations():
        for t in op.outputs:
            if t.dtype in [tf.float32, tf.float64]:
                if any(x in t.name for x in ["PartitionedCall", "Softmax", "Sigmoid"]):
                    outputs.append(t.name)
    
    primary_output = ""
    if outputs:
        pcalls_1 = [o for o in outputs if "PartitionedCall" in o and o.endswith(":1")]
        primary_output = pcalls_1[-1] if pcalls_1 else outputs[-1]
    
    return primary_input, primary_output, placeholders

def _ensure_models_loaded() -> None:
    global _PREPROCESSOR, _models_initialized
    global _BACKBONE_SESS, _HEAD_SESSIONS, _METADATA
    global _INP_B, _OUT_B, _PHELDS_B

    if _models_initialized: return

    with _models_lock:
        if _models_initialized: return

        logger.info(f"Initializing CPU-Native Inference Engine from {MODELS_DIR}")
        _PREPROCESSOR = es.TensorflowInputMusiCNN()
        
        for key, filename in MODEL_REGISTRY.items():
            path = MODELS_DIR / filename
            if not path.exists(): continue
            
            graph_def = _load_frozen_graph(path)
            graph = tf.Graph()
            with graph.as_default():
                tf.import_graph_def(graph_def, name="model")
                inp, out, phelds = _find_tensors(graph)
                
                # Standard CPU Session (No GPU config needed)
                sess = tf.compat.v1.Session(graph=graph)
                
                if key == "backbone":
                    _BACKBONE_SESS = sess
                    _INP_B, _OUT_B, _PHELDS_B = inp, out, phelds
                else:
                    _HEAD_SESSIONS[key] = (sess, inp, out, phelds)
            
            meta_path = path.with_name(filename.replace(".pb", "_metadata.json"))
            if meta_path.exists():
                with open(meta_path, "r") as f:
                    _METADATA[key] = json.load(f)
            logger.info(f"✓ {key} model initialized")

        _models_initialized = True

def initialize_models_globally() -> None:
    _ensure_models_loaded()

def _run_sess(sess: tf.compat.v1.Session, inp_name: str, out_name: str, phelds: list[str], val: np.ndarray) -> np.ndarray:
    graph = sess.graph
    feed_dict = {inp_name: val}
    for p in phelds:
        if p != inp_name:
            tensor = graph.get_tensor_by_name(p)
            if tensor.dtype == tf.string: feed_dict[p] = b""
            elif tensor.dtype in [tf.float32, tf.float64]: feed_dict[p] = 0.0
            else: feed_dict[p] = 0
    return sess.run(out_name, feed_dict=feed_dict)

def preprocess_audio(audio_16k: np.ndarray) -> np.ndarray:
    """Converts 16kHz audio to mel patches [n, 128, 96]."""
    _ensure_models_loaded()
    mel_frames = [_PREPROCESSOR(f).flatten() for f in es.FrameGenerator(audio_16k, frameSize=512, hopSize=256, startFromZero=True)]
    if not mel_frames: return np.array([])
    mel_data = np.array(mel_frames)
    
    patch_size, hop_size = 128, 64
    patches = [mel_data[i:i+patch_size] for i in range(0, len(mel_data) - patch_size + 1, hop_size)]
    if not patches:
        patches = [np.pad(mel_data, ((0, patch_size - len(mel_data)), (0, 0)), mode='constant')]
    return np.array(patches)

def run_batch_inference(list_of_patches: list[np.ndarray]) -> list[dict[str, Any]]:
    """
    Vectorized batch inference with 64-patch chunking for fixed-size models.
    """
    _ensure_models_loaded()
    if not list_of_patches: return []
    if _BACKBONE_SESS is None: return [{k: {} for k in MODEL_REGISTRY if k != "backbone"} for _ in list_of_patches]

    # 1. Flatten all patches into one big list
    all_patches = []
    track_patch_ranges = []
    current_idx = 0
    for patches in list_of_patches:
        count = len(patches)
        all_patches.extend(patches)
        track_patch_ranges.append((current_idx, current_idx + count))
        current_idx += count

    # 2. Backbone Inference (CHUNKED into 64 for fixed-model compatibility)
    CHUNK_SIZE = 64
    all_patches_np = np.array(all_patches)
    total_to_process = len(all_patches_np)
    all_embs = []
    
    for i in range(0, total_to_process, CHUNK_SIZE):
        chunk = all_patches_np[i : i + CHUNK_SIZE]
        actual_len = len(chunk)
        
        # PADDING: If chunk < 64, pad with zeros to satisfy the model
        if actual_len < CHUNK_SIZE:
            padding = np.zeros((CHUNK_SIZE - actual_len, 128, 96), dtype=np.float32)
            chunk = np.vstack([chunk, padding])
        
        chunk_embs = _run_sess(_BACKBONE_SESS, _INP_B, _OUT_B, _PHELDS_B, chunk)
        # Store only the real results (discard padding)
        all_embs.append(chunk_embs[:actual_len])
    
    combined_embs = np.concatenate(all_embs, axis=0)

    # 3. Aggregate Embeddings per Track and Run Heads
    final_results = []
    for start, end in track_patch_ranges:
        track_patches_embs = combined_embs[start:end]
        track_embedding = np.mean(track_patches_embs, axis=0, keepdims=True)
        
        res: dict[str, Any] = {"embedding": track_embedding.flatten()}
        
        for key, (sess, inp, out, phelds) in _HEAD_SESSIONS.items():
            # Heads are flexible, we can run them on the single track embedding
            logits = _run_sess(sess, inp, out, phelds, track_embedding)
            probs = logits.flatten()
            labels = _METADATA.get(key, {}).get("classes", [])
            if labels:
                res[key] = {labels[i]: float(probs[i]) for i in range(min(len(labels), len(probs)))}
            else:
                res[key] = {"score": float(probs[0])}
        
        final_results.append(res)

    return final_results
