import pandas as pd
import csv
import re
from pathlib import Path

def get_top_viewed_songs(csv_path, top_n=5000):
    """
    Parses a GA4 'Entrances/Exits' export and returns the top N most viewed songs.
    
    Heuristics from validacio/filter.ipynb are used to identify song pages.
    """
    rows = []
    header = None
    
    # Read the file cleanly
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            
            if header is None:
                header = row
                continue
            
            # The 'Grand total' row usually has a different number of columns or special content
            # Notebook logic: only keep rows with matching header length
            if len(row) == len(header):
                rows.append(row)
    
    df = pd.DataFrame(rows, columns=header)
    
    # Clean up column names (handle BOM if necessary, though utf-8-sig should cover it)
    df = df.rename(columns={df.columns[0]: "title"})
    
    # Convert numeric columns
    df["Views"] = pd.to_numeric(df["Views"], errors="coerce")
    df["Sessions"] = pd.to_numeric(df["Sessions"], errors="coerce")
    
    # Filter valid titles
    df["title"] = df["title"].astype(str).str.strip()
    df = df[df["title"] != ""].copy()
    
    # ---------------------------
    # Filtering Heuristics
    # ---------------------------
    title_series = df["title"]
    
    # Matches: "Song Name, de l'àlbum \"Album Name\" (Artist) - Viasona"
    is_song = (
        title_series.str.contains(r"de l['’]àlbum", case=False, na=False)
        & title_series.str.contains(r"\(.+\)", na=False)
        & title_series.str.contains(r"-\s*Viasona$", case=False, na=False)
    )
    
    # Exclude non-song pages
    not_song = title_series.str.contains(
        r"tota la música|agenda|concerts|notícies|artistes|grups|discografia|"
        r"llistat|llista|cerca|home|inici|cançons en català|enviar lletra|"
        r"vídeos|videoclips|biografia|entrevista|especial",
        case=False,
        na=False
    )
    
    songs_df = df[is_song & ~not_song].copy()
    
    # ---------------------------
    # Extract Song and Artist
    # ---------------------------
    # song_title: Everything before ", de"
    songs_df["song_title"] = songs_df["title"].str.extract(r"^(.*?), de", expand=False)
    
    # artist: The content inside the LAST set of parentheses
    # Example: "Song, de l'àlbum \"Album\" (Artist) - Viasona" -> Artist
    songs_df["artist"] = songs_df["title"].str.extract(r"\(([^)]+)\)[^)]*-\s*Viasona$", expand=False)
    
    # Sort by Views descending
    top_songs = songs_df.sort_values("Views", ascending=False).head(top_n)
    
    return top_songs

if __name__ == "__main__":
    # Test the function
    data_path = Path("validacio/entrances_exits.csv")
    output_csv = Path("validacio/top_5000_songs.csv")
    
    if not data_path.exists():
        print(f"Error: {data_path} not found.")
    else:
        print(f"Testing get_top_viewed_songs with {data_path}...")
        top_5000 = get_top_viewed_songs(data_path, top_n=5000)
        
        print(f"Detected {len(top_5000)} songs in top 5000 request.")
        
        # Save to CSV
        # Selecting and ordering columns for the output
        export_df = top_5000[["song_title", "artist", "title", "Views"]].copy()
        export_df.insert(0, "#", range(1, len(export_df) + 1))
        export_df = export_df.rename(columns={"title": "page_title", "Views": "views"})
        
        export_df.to_csv(output_csv, index=False, encoding="utf-8-sig")
        print(f"Successfully saved results to {output_csv}")

        print("\nTop 10 Most Viewed Songs (Extracted):")
        print("-" * 150)
        print(f"{'#':<3} | {'SONG TITLE':<30} | {'ARTIST':<20} | {'PAGE TITLE':<60} | {'VIEWS':<10}")
        print("-" * 150)
        
        for i, (idx, row) in enumerate(top_5000.head(10).iterrows(), 1):
            song = str(row['song_title'])[:30]
            artist = str(row['artist'])[:20]
            page = str(row['title'])[:60]
            print(f"{i:<3} | {song:<30} | {artist:<20} | {page:<60} | {row['Views']:<10}")
        
        # Validation of count
        expected_limit = 5000
        actual_count = len(top_5000)
        if actual_count > 0:
            print(f"\nVerification: Function returned {actual_count} items (max {expected_limit}).")
        else:
            print("\nVerification FAIL: No songs detected.")
