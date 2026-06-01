"""
Prepare bundled_data files for one site (mshop.se / mshop.dk / mshop.eu).

This script started as an inlinks-only deduplicator but now produces the
full set of 6 bundled files that the Railway services unpack at boot:

  sf_inlinks_<site>.csv.gz       - deduped (SF "All Inlinks" raw is huge; this is the small version)
  sf_link_map_<site>.json.gz     - pre-aggregated per-URL link map
  sf_pages_<site>.csv.gz         - SF "All Pages" / Internal HTML, just gzipped
  ahrefs_best_by_links_<site>.csv.gz
  ahrefs_backlinks_<site>.csv.gz
  ahrefs_organic_keywords_<site>.csv.gz

## What it does NOT do

- It does NOT switch git branches. Run it on whichever branch you want;
  the output files end up in bundled_data/ as new (untracked) files.
  Git will let them follow you when you `git checkout mshop-eu` etc.
- It does NOT commit or push. After it finishes it prints exactly the
  git commands you should run for the chosen site.

## Inputs

Place your raw exports in `data/` with these names. Any missing file is
skipped with a note — you can refresh just the SF crawl without re-doing
Ahrefs and vice versa:

  data/all_inlinks_<site>.csv             (SF "All Inlinks" Bulk Export)
  data/sf_pages_<site>.csv                (SF Internal → HTML export)
  data/ahrefs_best_by_links_<site>.csv    (Ahrefs Best by Links)
  data/ahrefs_backlinks_<site>.csv        (Ahrefs Backlinks, Live+Dofollow)
  data/ahrefs_organic_keywords_<site>.csv (Ahrefs Organic Keywords)

The `<site>`-suffix protects you from confusing SE and EU data when
multiple sites are staged at the same time.

## Usage

    python scripts/prepare_inlinks.py --site eu
    python scripts/prepare_inlinks.py                  (interactive prompt)
    python scripts/prepare_inlinks.py --site dk --data-dir D:/seo-exports

After it finishes, follow the printed git instructions to land the
files on the correct site-branch.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time

# Add repo root to sys.path so we can `from utils.* import ...` when the
# script is run directly (`python scripts/prepare_inlinks.py`).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.screaming_frog_import import (  # noqa: E402
    parse_all_inlinks,
    build_complete_link_map,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_DIR = os.path.join(REPO_ROOT, "data")
DEFAULT_OUTPUT_DIR = os.path.join(REPO_ROOT, "bundled_data")
SUPPORTED_SITES = ("se", "dk", "eu")

SITE_DESCRIPTIONS = {
    "se": "mshop.se   (main branch + main Railway service)",
    "dk": "mshop.dk   (mshop-dk branch + mshop-dk Railway service)",
    "eu": "mshop.eu   (mshop-eu branch + mshop-eu Railway service)",
}

# Per-input-file routing.  Each entry:
#   logical key       : (input_filename_template, output_filename_template, processor)
# Processor is the function applied to the raw input before gzipping.
# A `None` processor means "just gzip the raw CSV as-is".
PIPELINE: list[tuple[str, str, str, str | None]] = [
    # logical key,         input template,                      output template,                             processor
    ("inlinks_dedup",      "all_inlinks_{site}.csv",            "sf_inlinks_{site}.csv.gz",                  "dedupe_inlinks"),
    ("inlinks_link_map",   "(derived from inlinks)",            "sf_link_map_{site}.json.gz",                "link_map_only"),
    ("sf_pages",           "sf_pages_{site}.csv",               "sf_pages_{site}.csv.gz",                    None),
    ("ahrefs_bbl",         "ahrefs_best_by_links_{site}.csv",   "ahrefs_best_by_links_{site}.csv.gz",        None),
    ("ahrefs_backlinks",   "ahrefs_backlinks_{site}.csv",       "ahrefs_backlinks_{site}.csv.gz",            None),
    ("ahrefs_keywords",    "ahrefs_organic_keywords_{site}.csv","ahrefs_organic_keywords_{site}.csv.gz",     None),
]


def _fmt_mb(path: str) -> str:
    if not os.path.exists(path):
        return "(missing)"
    mb = os.path.getsize(path) / (1024 * 1024)
    if mb < 1:
        return f"{mb * 1024:.0f} KB"
    return f"{mb:.1f} MB"


def _prompt_for_site() -> str:
    print("Hvilket site forbereder du data for?")
    for code in SUPPORTED_SITES:
        print(f"  {code}  ->  {SITE_DESCRIPTIONS[code]}")
    while True:
        choice = input("Site code [se/dk/eu]: ").strip().lower()
        if choice in SUPPORTED_SITES:
            return choice
        print(f"  '{choice}' er ikke en gyldig kode. Prøv igen (eller Ctrl+C for at afbryde).")


def _gzip_file(src_path: str, dest_path: str) -> None:
    """Stream-copy + gzip. Safe for multi-GB files; never loads whole file in memory."""
    tmp_path = dest_path + ".part"
    with open(src_path, "rb") as src, gzip.open(tmp_path, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
    os.replace(tmp_path, dest_path)


def _gzip_bytes(data: bytes, dest_path: str) -> None:
    tmp_path = dest_path + ".part"
    with gzip.open(tmp_path, "wb", compresslevel=6) as dst:
        dst.write(data)
    os.replace(tmp_path, dest_path)


def _process_inlinks(input_path: str, output_dir: str, site: str) -> dict | None:
    """Dedupe inlinks + build link map, write both gzipped outputs.

    Returns a dict with `inlinks_path`, `link_map_path`, `pair_count`,
    `unique_pages`, or None if input is missing.
    """
    if not os.path.exists(input_path):
        return None

    raw_mb = os.path.getsize(input_path) / (1024 * 1024)
    print(f"  Reading {os.path.basename(input_path)} ({raw_mb:.0f} MB) — streaming via parse_all_inlinks...")
    t0 = time.time()

    # parse_all_inlinks accepts a file path string and streams; safe for 2GB+ inputs.
    df = parse_all_inlinks(input_path)
    print(f"    Deduped to {len(df):,} unique source->target pairs ({time.time() - t0:.0f}s).")

    inlinks_out = os.path.join(output_dir, f"sf_inlinks_{site}.csv.gz")
    link_map_out = os.path.join(output_dir, f"sf_link_map_{site}.json.gz")

    # Write deduped CSV → gzipped
    print(f"  Writing {os.path.basename(inlinks_out)}...")
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    _gzip_bytes(csv_bytes, inlinks_out)
    print(f"    {_fmt_mb(inlinks_out)} gzipped.")

    # Build + write link map JSON → gzipped
    print(f"  Building link map...")
    link_map = build_complete_link_map(df)
    unique_pages = link_map.get("unique_pages", 0)
    unique_pairs = link_map.get("unique_pairs", 0)
    print(f"    {unique_pages:,} pages, {unique_pairs:,} pairs.")

    print(f"  Writing {os.path.basename(link_map_out)}...")
    map_bytes = json.dumps(link_map, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _gzip_bytes(map_bytes, link_map_out)
    print(f"    {_fmt_mb(link_map_out)} gzipped.")

    return {
        "inlinks_path": inlinks_out,
        "link_map_path": link_map_out,
        "pair_count": len(df),
        "unique_pages": unique_pages,
        "raw_mb": raw_mb,
    }


def _process_passthrough(input_path: str, output_path: str) -> dict | None:
    """Just gzip the raw file into bundled_data with the new name.

    Used for sf_pages and the 3 Ahrefs files — they need no preprocessing,
    only renaming + gzipping for the site-specific bundle.
    """
    if not os.path.exists(input_path):
        return None
    print(f"  Reading {os.path.basename(input_path)} ({_fmt_mb(input_path)})...")
    _gzip_file(input_path, output_path)
    print(f"  Wrote {os.path.basename(output_path)} ({_fmt_mb(output_path)}).")
    return {"path": output_path}


def _print_next_steps(site: str, produced: list[str]) -> None:
    if not produced:
        print("\nNo files were produced (no inputs matched). Place your raw exports in data/ with the right names and try again.")
        return

    target_branch = "main" if site == "se" else f"mshop-{site}"
    rel = lambda p: os.path.relpath(p, REPO_ROOT).replace("\\", "/")

    print("\n" + "=" * 60)
    print(f"Done. {len(produced)} bundled file(s) written for mshop.{site}:")
    for path in produced:
        print(f"  {rel(path)}    {_fmt_mb(path)}")

    print("\nNext: land them on the right branch and push to Railway.")
    if site == "se":
        print("  mshop.se data goes directly on main (the SE service tracks main).")
        print()
        print("  git add " + " ".join(rel(p) for p in produced))
        print(f"  git commit -m \"Refresh bundled data for mshop.se\"")
        print("  git push origin main")
    else:
        print(f"  mshop.{site} data goes on the {target_branch} branch.")
        print(f"  The files are currently untracked in your working tree — they will follow you to the other branch.")
        print()
        print(f"  git checkout {target_branch}")
        print(f"  git pull origin {target_branch}")
        print("  git add " + " ".join(rel(p) for p in produced))
        print(f"  git commit -m \"Refresh bundled data for mshop.{site}\"")
        print(f"  git push origin {target_branch}")
        print(f"  git checkout main      # return to where you started")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare bundled_data files for one site (mshop.se/dk/eu).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/prepare_inlinks.py --site eu\n"
            "  python scripts/prepare_inlinks.py                 (asks interactively)\n"
            "  python scripts/prepare_inlinks.py --site dk --data-dir D:/seo-exports"
        ),
    )
    parser.add_argument(
        "--site",
        choices=SUPPORTED_SITES,
        help="Site code: se / dk / eu. Asks interactively if omitted.",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help=f"Directory containing raw input CSVs (default: {os.path.relpath(DEFAULT_DATA_DIR, REPO_ROOT)})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write the gzipped bundled files (default: {os.path.relpath(DEFAULT_OUTPUT_DIR, REPO_ROOT)})",
    )
    args = parser.parse_args(argv)

    site = args.site or _prompt_for_site()
    data_dir = os.path.abspath(args.data_dir)
    output_dir = os.path.abspath(args.output_dir)

    if not os.path.isdir(data_dir):
        print(f"ERROR: data dir does not exist: {data_dir}")
        return 2

    os.makedirs(output_dir, exist_ok=True)

    print(f"\nPreparing bundled data for: mshop.{site}")
    print(f"  Reading inputs from: {data_dir}")
    print(f"  Writing outputs to:  {output_dir}")
    print()

    # Quick survey: which inputs exist?
    print("Detected raw inputs:")
    survey: dict[str, str | None] = {}
    for logical, in_tmpl, _out_tmpl, _proc in PIPELINE:
        if logical == "inlinks_link_map":
            continue  # derived from inlinks; no separate input file
        in_path = os.path.join(data_dir, in_tmpl.format(site=site))
        if os.path.exists(in_path):
            survey[logical] = in_path
            print(f"  + {os.path.basename(in_path)}    {_fmt_mb(in_path)}")
        else:
            survey[logical] = None
            print(f"  - {in_tmpl.format(site=site)}   (missing — skipping)")

    if not any(survey.values()):
        print("\nNo input files found — nothing to do. Drop your raw CSVs in data/ with the _<site>.csv suffix.")
        return 1

    print()
    produced: list[str] = []

    # 1. Inlinks (dedup + link map)
    if survey.get("inlinks_dedup"):
        print(f"== SF Inlinks ({os.path.basename(survey['inlinks_dedup'])}) ==")
        result = _process_inlinks(survey["inlinks_dedup"], output_dir, site)
        if result:
            produced.append(result["inlinks_path"])
            produced.append(result["link_map_path"])
        print()

    # 2-5. Pass-through files (just gzip + rename)
    for logical, in_tmpl, out_tmpl, processor in PIPELINE:
        if logical in ("inlinks_dedup", "inlinks_link_map"):
            continue  # handled above
        if not survey.get(logical):
            continue
        out_path = os.path.join(output_dir, out_tmpl.format(site=site))
        print(f"== {logical} ({os.path.basename(survey[logical])}) ==")
        result = _process_passthrough(survey[logical], out_path)
        if result:
            produced.append(out_path)
        print()

    _print_next_steps(site, produced)
    return 0


if __name__ == "__main__":
    sys.exit(main())
