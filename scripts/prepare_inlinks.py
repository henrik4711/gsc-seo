"""
Parse large SF All Inlinks file locally, deduplicate, and save compact version.
Run this before deploying to Railway to avoid uploading 2.4GB.

Usage: python scripts/prepare_inlinks.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.screaming_frog_import import parse_all_inlinks, build_complete_link_map
import json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
INLINKS_FILE = os.path.join(DATA_DIR, "all_inlinks.csv")
OUTPUT_CSV = os.path.join(DATA_DIR, "sf_inlinks_deduped.csv")
OUTPUT_LINKMAP = os.path.join(DATA_DIR, "sf_link_map.json")

if not os.path.exists(INLINKS_FILE):
    print(f"File not found: {INLINKS_FILE}")
    sys.exit(1)

size_mb = os.path.getsize(INLINKS_FILE) / (1024 * 1024)
print(f"Parsing {INLINKS_FILE} ({size_mb:.0f} MB)...")

# Parse with chunked reader (memory efficient)
df = parse_all_inlinks(INLINKS_FILE)
print(f"Result: {len(df):,} unique source->target pairs")

# Save compact CSV
df.to_csv(OUTPUT_CSV, index=False)
csv_mb = os.path.getsize(OUTPUT_CSV) / (1024 * 1024)
print(f"Saved: {OUTPUT_CSV} ({csv_mb:.1f} MB)")

# Build and save link map
print("Building link map...")
link_map = build_complete_link_map(df)
print(f"Link map: {link_map['unique_pages']:,} pages, {link_map['unique_pairs']:,} pairs")

# Save as compact JSON (no indent)
with open(OUTPUT_LINKMAP, "w", encoding="utf-8") as f:
    json.dump(link_map, f, ensure_ascii=False, separators=(",", ":"))
map_mb = os.path.getsize(OUTPUT_LINKMAP) / (1024 * 1024)
print(f"Saved: {OUTPUT_LINKMAP} ({map_mb:.1f} MB)")

print(f"\nReduction: {size_mb:.0f} MB -> {csv_mb:.1f} MB CSV + {map_mb:.1f} MB JSON")
print(f"\nNext: Upload these to Railway volume:")
print(f"  railway volume upload -s /data {OUTPUT_CSV}")
print(f"  railway volume upload -s /data {OUTPUT_LINKMAP}")
