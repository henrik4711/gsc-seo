"""
Update bundled data files from fresh exports.

Place new files in data/ folder, then run:
    python scripts/update_data.py

Files are auto-detected by name pattern:
    - *inlink*          -> SF All Inlinks (parsed + chunked for large files)
    - *internal*        -> SF All Pages
    - *bbl*             -> Ahrefs Best by Links
    - *backlink*        -> Ahrefs Backlinks
    - *organic*keyword* -> Ahrefs Organic Keywords

Output: compressed .gz files in bundled_data/ ready for git push.
After running: git add bundled_data/ && git commit && git push
"""
import sys
import os
import gzip

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
BUNDLED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bundled_data")

os.makedirs(BUNDLED_DIR, exist_ok=True)


def find_file(*patterns):
    if not os.path.isdir(DATA_DIR):
        return None
    for f in sorted(os.listdir(DATA_DIR), key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)), reverse=True):
        fl = f.lower()
        if any(p in fl for p in patterns) and fl.endswith((".csv", ".tsv")):
            return os.path.join(DATA_DIR, f)
    return None


def compress_df(df, output_key):
    gz_path = os.path.join(BUNDLED_DIR, f"{output_key}.csv.gz")
    with gzip.open(gz_path, "wb", compresslevel=9) as f:
        df.to_csv(f, index=False)
    size = os.path.getsize(gz_path) / (1024 * 1024)
    print(f"  -> {output_key}.csv.gz ({size:.1f} MB, {len(df):,} rows)")
    return gz_path


def compress_json(data, output_key):
    import json
    gz_path = os.path.join(BUNDLED_DIR, f"{output_key}.json.gz")
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.open(gz_path, "wb", compresslevel=9) as f:
        f.write(raw)
    size = os.path.getsize(gz_path) / (1024 * 1024)
    print(f"  -> {output_key}.json.gz ({size:.1f} MB)")
    return gz_path


print("=" * 60)
print("UPDATE BUNDLED DATA")
print(f"Looking for files in: {DATA_DIR}")
print("=" * 60)

updated = []

# ── SF All Inlinks (potentially huge) ──
inlinks_file = find_file("inlink")
if inlinks_file:
    from utils.screaming_frog_import import parse_all_inlinks, build_complete_link_map
    size = os.path.getsize(inlinks_file) / (1024 * 1024)
    print(f"\nSF All Inlinks: {os.path.basename(inlinks_file)} ({size:.0f} MB)")
    df = parse_all_inlinks(inlinks_file)
    compress_df(df, "sf_inlinks")
    print("  Building link map...")
    lm = build_complete_link_map(df)
    compress_json(lm, "sf_link_map")
    updated.append("sf_inlinks + sf_link_map")
else:
    print("\nSF All Inlinks: not found (looking for *inlink*.csv)")

# ── SF All Pages ──
pages_file = find_file("internal", "all_pages")
if pages_file:
    from utils.screaming_frog_import import parse_all_pages
    print(f"\nSF All Pages: {os.path.basename(pages_file)}")
    with open(pages_file, "rb") as f:
        df = parse_all_pages(f.read())
    compress_df(df, "sf_pages")
    updated.append("sf_pages")
else:
    print("\nSF All Pages: not found (looking for *internal*.csv or *all_pages*.csv)")

# ── Ahrefs Best by Links ──
bbl_file = find_file("bbl", "best-by-links", "best_by_links")
if bbl_file:
    from utils.ahrefs_import import parse_best_by_links
    print(f"\nAhrefs Best by Links: {os.path.basename(bbl_file)}")
    with open(bbl_file, "rb") as f:
        df = parse_best_by_links(f.read())
    compress_df(df, "ahrefs_best_by_links")
    updated.append("ahrefs_best_by_links")
else:
    print("\nAhrefs Best by Links: not found (looking for *bbl*.csv)")

# ── Ahrefs Backlinks ──
bl_file = find_file("backlink")
if bl_file and "inlink" not in os.path.basename(bl_file).lower():
    from utils.ahrefs_import import parse_backlinks
    print(f"\nAhrefs Backlinks: {os.path.basename(bl_file)}")
    with open(bl_file, "rb") as f:
        df = parse_backlinks(f.read())
    compress_df(df, "ahrefs_backlinks")
    updated.append("ahrefs_backlinks")
else:
    print("\nAhrefs Backlinks: not found (looking for *backlink*.csv)")

# ── Ahrefs Organic Keywords ──
kw_file = find_file("organic-keyword", "organic_keyword")
if kw_file:
    from utils.ahrefs_import import parse_organic_keywords
    print(f"\nAhrefs Organic Keywords: {os.path.basename(kw_file)}")
    with open(kw_file, "rb") as f:
        df = parse_organic_keywords(f.read())
    compress_df(df, "ahrefs_organic_keywords")
    updated.append("ahrefs_organic_keywords")
else:
    print("\nAhrefs Organic Keywords: not found (looking for *organic*keyword*.csv)")

# ── Summary ──
print("\n" + "=" * 60)
if updated:
    print(f"Updated: {', '.join(updated)}")
    print(f"\nNext steps:")
    print(f"  git add bundled_data/")
    print(f"  git commit -m 'Update data exports'")
    print(f"  git push")
    print(f"\nRailway will auto-deploy and decompress on first start.")
else:
    print("No files found to update.")
    print(f"Place CSV exports in: {DATA_DIR}")
