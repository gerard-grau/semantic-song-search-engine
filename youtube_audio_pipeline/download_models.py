"""
Essentia Model Downloader

Downloads the full production suite of Discogs-EffNet models:
- Backbone (Feature Extractor)
- Genre (Discogs 400)
- Mood & Theme (MTG-Jamendo Multi-task)
- Instrumentation, Voice, Gender, and Timbre heads.
"""

import os
import subprocess
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"
UA = "Mozilla/5.0"

# (Download URL, Target Filename)
MODELS = [
    # Backbone
    ("https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb", "discogs-effnet-1.pb"),
    ("https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.json", "discogs-effnet-1_metadata.json"),
    
    # Genre
    ("https://essentia.upf.edu/models/classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.pb", "genre_discogs400-discogs-effnet-1.pb"),
    ("https://essentia.upf.edu/models/classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.json", "genre_discogs400-discogs-effnet-1_metadata.json"),
    
    # Multi-task Mood/Theme
    ("https://essentia.upf.edu/models/classification-heads/mtg_jamendo_moodtheme/mtg_jamendo_moodtheme-discogs-effnet-1.pb", "mtg_jamendo_moodtheme-discogs-effnet-1.pb"),
    ("https://essentia.upf.edu/models/classification-heads/mtg_jamendo_moodtheme/mtg_jamendo_moodtheme-discogs-effnet-1.json", "mtg_jamendo_moodtheme-discogs-effnet-1_metadata.json"),
    
    # Instrumentation
    ("https://essentia.upf.edu/models/classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1.pb", "mtg_jamendo_instrument-discogs-effnet-1.pb"),
    ("https://essentia.upf.edu/models/classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1.json", "mtg_jamendo_instrument-discogs-effnet-1_metadata.json"),
    
    # Voice/Instrumental
    ("https://essentia.upf.edu/models/classification-heads/voice_instrumental/voice_instrumental-discogs-effnet-1.pb", "voice_instrumental-discogs-effnet-1.pb"),
    ("https://essentia.upf.edu/models/classification-heads/voice_instrumental/voice_instrumental-discogs-effnet-1.json", "voice_instrumental-discogs-effnet-1_metadata.json"),
    
    # Gender
    ("https://essentia.upf.edu/models/classification-heads/gender/gender-discogs-effnet-1.pb", "voice_gender-discogs-effnet-1.pb"),
    ("https://essentia.upf.edu/models/classification-heads/gender/gender-discogs-effnet-1.json", "voice_gender-discogs-effnet-1_metadata.json"),
    
    # Timbre
    ("https://essentia.upf.edu/models/classification-heads/timbre/timbre-discogs-effnet-1.pb", "timbre-discogs-effnet-1.pb"),
    ("https://essentia.upf.edu/models/classification-heads/timbre/timbre-discogs-effnet-1.json", "timbre-discogs-effnet-1_metadata.json"),
]

def download():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"🚀 Downloading {len(MODELS)} model files to {MODELS_DIR}...")
    
    for url, filename in MODELS:
        target = MODELS_DIR / filename
        if target.exists():
            print(f"  [SKIPPED] {filename} (already exists)")
            continue
            
        print(f"  [FETCHING] {filename}...")
        cmd = [
            "wget", "-q", "-4", "--no-check-certificate",
            f"--user-agent={UA}",
            url,
            "-O", str(target)
        ]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            print(f"  ❌ Failed to download {filename}")
            
    print("\n✅ All models ready.")

if __name__ == "__main__":
    download()
