"""
Screaming Frog CSV import — parse All Inlinks + All Pages exports
Provides complete internal link map, technical SEO issues, crawl depth, orphan pages
"""

import io
import pandas as pd
from urllib.parse import urlparse


def _read_csv_flexible(file_content) -> pd.DataFrame:
    """Read CSV with flexible encoding and separator detection."""
    if isinstance(file_content, bytes):
        content = file_content
    else:
        content = file_content.read()

    for encoding in ["utf-8-sig", "utf-8", "utf-16", "latin-1", "cp1252"]:
        try:
            text = content.decode(encoding)
            text = text.lstrip("\ufeff")

            first_line = text.split("\n")[0]
            if "\t" in first_line:
                sep = "\t"
            elif ";" in first_line and "," not in first_line:
                sep = ";"
            else:
                sep = ","

            df = pd.read_csv(io.StringIO(text), sep=sep, on_bad_lines="skip", header=0)
            # Handle duplicate column names by appending suffix
            cols = list(df.columns)
            seen = {}
            new_cols = []
            for c in cols:
                c = c.strip().strip('"').strip()
                if c in seen:
                    seen[c] += 1
                    new_cols.append(f"{c}_{seen[c]}")
                else:
                    seen[c] = 0
                    new_cols.append(c)
            df.columns = new_cols
            if len(df.columns) > 1:
                return df
        except (UnicodeDecodeError, pd.errors.ParserError, LookupError):
            continue

    return pd.DataFrame()


def _detect_csv_format(file_path_or_bytes):
    """Detect encoding and separator from first few KB of a CSV file."""
    if isinstance(file_path_or_bytes, str):
        with open(file_path_or_bytes, "rb") as f:
            head = f.read(8192)
    elif isinstance(file_path_or_bytes, bytes):
        head = file_path_or_bytes[:8192]
    else:
        head = file_path_or_bytes.read(8192)
        file_path_or_bytes.seek(0)

    for encoding in ["utf-8-sig", "utf-8", "utf-16", "latin-1", "cp1252"]:
        try:
            text = head.decode(encoding).lstrip("\ufeff")
            first_line = text.split("\n")[0]
            if "\t" in first_line:
                sep = "\t"
            elif ";" in first_line and "," not in first_line:
                sep = ";"
            else:
                sep = ","
            return encoding, sep
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8", ","


def _map_inlink_columns(columns):
    """Map SF inlink column names to standard names."""
    col_map = {}
    for col in columns:
        cl = col.lower().strip().strip('"')
        if cl in ("source", "from"):
            col_map[col] = "source"
        elif cl in ("destination", "to", "target", "target url"):
            col_map[col] = "target"
        elif cl in ("anchor", "anchor text", "alt text"):
            col_map[col] = "anchor"
        elif cl in ("type", "link type"):
            col_map[col] = "link_type"
        elif cl in ("status code", "status", "http status code"):
            col_map[col] = "status_code"
        elif cl in ("follow", "link path"):
            col_map[col] = "follow"
        # Fuzzy
        elif "source" in cl or "from" in cl:
            col_map.setdefault(col, "source")
        elif "dest" in cl or "target" in cl:
            col_map.setdefault(col, "target")
        elif "anchor" in cl:
            col_map.setdefault(col, "anchor")
        elif "status" in cl and "code" in cl:
            col_map.setdefault(col, "status_code")
    return col_map


def parse_all_inlinks(file_content) -> pd.DataFrame:
    """
    Parse Screaming Frog "All Inlinks" export.
    Memory-efficient: streams in chunks for large files (>100MB).
    Deduplicates source→target pairs to reduce memory.
    Returns: DataFrame with source, target, anchor, link_type, status_code, follow
    """
    from utils.ui_helpers import normalize_url

    is_file_path = isinstance(file_content, str) and len(file_content) < 500 and not file_content.startswith("http")
    is_large = False
    if is_file_path:
        import os
        is_large = os.path.getsize(file_content) > 100_000_000  # >100MB

    if is_large:
        return _parse_inlinks_chunked(file_content)

    # Standard path for smaller files
    df = _read_csv_flexible(file_content)
    if df.empty:
        return df

    col_map = _map_inlink_columns(df.columns)
    df = df.rename(columns=col_map)

    if "source" not in df.columns or "target" not in df.columns:
        url_cols = []
        for col in df.columns:
            sample = df[col].dropna().head(10).astype(str)
            if sample.str.contains(r"https?://", case=False).any():
                url_cols.append(col)
        if len(url_cols) >= 2:
            df = df.rename(columns={url_cols[0]: "source", url_cols[1]: "target"})
        else:
            return pd.DataFrame()

    df["source"] = df["source"].astype(str).str.strip()
    df["target"] = df["target"].astype(str).str.strip()
    df = df[df["source"].str.contains(r"https?://", case=False, na=False)].copy()
    df = df[df["target"].str.contains(r"https?://", case=False, na=False)].copy()
    df["source"] = df["source"].apply(normalize_url)
    df["target"] = df["target"].apply(normalize_url)

    for col, default in [("anchor", ""), ("status_code", 200), ("link_type", "Hyperlink"), ("follow", "Follow")]:
        if col not in df.columns:
            df[col] = default
    df["anchor"] = df["anchor"].fillna("").astype(str)
    df["status_code"] = pd.to_numeric(df["status_code"], errors="coerce").fillna(200).astype(int)

    return df[["source", "target", "anchor", "link_type", "status_code", "follow"]].copy()


def _parse_inlinks_chunked(file_path: str, chunk_size: int = 200_000) -> pd.DataFrame:
    """
    Memory-efficient inlinks parser for large files (>100MB).
    Reads in chunks, keeps only needed columns, deduplicates as it goes.
    """
    import os
    from utils.ui_helpers import normalize_url

    encoding, sep = _detect_csv_format(file_path)
    size_mb = os.path.getsize(file_path) / (1024 * 1024)

    # Read just header to map columns
    header_df = pd.read_csv(file_path, encoding=encoding, sep=sep, nrows=0, on_bad_lines="skip")
    col_map = _map_inlink_columns(header_df.columns)

    # Determine which columns to load — only first match per target name
    needed_originals = []
    seen_mapped = set()
    for orig, mapped in col_map.items():
        if mapped in ("source", "target", "anchor", "link_type", "status_code", "follow"):
            if mapped not in seen_mapped:
                needed_originals.append(orig)
                seen_mapped.add(mapped)
    if not needed_originals:
        return pd.DataFrame()

    # Check source+target are mappable
    if "source" not in seen_mapped or "target" not in seen_mapped:
        return pd.DataFrame()

    # Build rename map for only the columns we load
    rename_map = {orig: col_map[orig] for orig in needed_originals}

    # Stream chunks
    chunks = []
    seen_pairs = set()
    total_rows = 0
    kept_rows = 0

    reader = pd.read_csv(
        file_path, encoding=encoding, sep=sep,
        usecols=needed_originals,
        chunksize=chunk_size,
        on_bad_lines="skip",
        low_memory=True,
        dtype=str,
    )

    for chunk in reader:
        chunk = chunk.rename(columns=rename_map)
        total_rows += len(chunk)

        # Filter to valid URLs
        src = chunk["source"].astype(str)
        tgt = chunk["target"].astype(str)
        mask = src.str.contains(r"https?://", case=False, na=False) & tgt.str.contains(r"https?://", case=False, na=False)
        chunk = chunk[mask].copy()

        # Normalize URLs
        chunk["source"] = chunk["source"].str.strip().apply(normalize_url)
        chunk["target"] = chunk["target"].str.strip().apply(normalize_url)

        # Deduplicate: vectorized — create pair key and filter
        chunk["_pair"] = chunk["source"] + "→" + chunk["target"]
        new_mask = ~chunk["_pair"].isin(seen_pairs)
        new_chunk = chunk[new_mask].copy()
        seen_pairs.update(new_chunk["_pair"].tolist())
        new_chunk = new_chunk.drop(columns=["_pair"])

        if not new_chunk.empty:
            chunks.append(new_chunk)
            kept_rows += len(new_chunk)

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True)

    # Fill missing columns
    for col, default in [("anchor", ""), ("link_type", "Hyperlink"), ("status_code", "200"), ("follow", "Follow")]:
        if col not in df.columns:
            df[col] = default

    df["anchor"] = df["anchor"].fillna("").astype(str)
    df["status_code"] = pd.to_numeric(df["status_code"], errors="coerce").fillna(200).astype(int)

    # Ensure column order
    out_cols = [c for c in ["source", "target", "anchor", "link_type", "status_code", "follow"] if c in df.columns]

    print(f"Inlinks: {total_rows:,} total rows -> {kept_rows:,} unique source->target pairs ({size_mb:.0f} MB file)")
    return df[out_cols].copy()


def parse_all_pages(file_content) -> pd.DataFrame:
    """
    Parse Screaming Frog "All Pages" / "Internal All" export.
    Expected columns: Address, Status Code, Title, Meta Description, H1, Word Count, Crawl Depth, etc.
    """
    df = _read_csv_flexible(file_content)
    if df.empty:
        return df

    # Map SF columns to standard names — only first match per target name
    col_map = {}
    used_targets = set()

    def _map(col_name, target):
        if target not in used_targets:
            col_map[col_name] = target
            used_targets.add(target)

    for col in df.columns:
        cl = col.lower().strip()
        if cl in ("address", "url", "page url"):
            _map(col, "url")
        elif cl in ("status code", "http status code"):
            _map(col, "status_code")
        elif cl in ("title 1", "title"):
            _map(col, "title")
        elif cl in ("title 1 length", "title length"):
            _map(col, "title_length")
        elif cl in ("meta description 1", "meta description"):
            _map(col, "meta_description")
        elif cl in ("meta description 1 length", "meta description length"):
            _map(col, "meta_description_length")
        elif cl in ("h1-1", "h1", "h1 1"):
            _map(col, "h1")
        elif cl in ("word count"):
            _map(col, "word_count")
        elif cl in ("crawl depth"):
            _map(col, "crawl_depth")
        elif cl in ("inlinks"):
            _map(col, "inlinks")
        elif cl in ("outlinks"):
            _map(col, "outlinks")
        elif cl in ("unique inlinks"):
            _map(col, "unique_inlinks")
        elif cl in ("unique outlinks"):
            _map(col, "unique_outlinks")
        elif cl in ("indexability"):
            _map(col, "indexability")
        elif cl in ("indexability status"):
            _map(col, "indexability_status")
        elif cl in ("canonical link element 1", "canonical"):
            _map(col, "canonical")
        elif cl in ("redirect url", "redirect uri"):
            _map(col, "redirect_url")
        elif cl in ("content type", "content"):
            _map(col, "content_type")
        elif cl in ("size (bytes)", "size"):
            _map(col, "size_bytes")
        elif cl in ("response time"):
            _map(col, "response_time")
        # Fuzzy fallbacks — only if not already mapped
        elif "canonical" in cl:
            _map(col, "canonical")
        elif "redirect" in cl and "url" in cl:
            _map(col, "redirect_url")
        elif "word" in cl and "count" in cl:
            _map(col, "word_count")
        elif "crawl" in cl and "depth" in cl:
            _map(col, "crawl_depth")

    df = df.rename(columns=col_map)

    if "url" not in df.columns:
        for col in df.columns:
            sample = df[col].dropna().head(10).astype(str)
            if sample.str.contains(r"https?://", case=False).any():
                df = df.rename(columns={col: "url"})
                break
        else:
            return pd.DataFrame()

    df["url"] = df["url"].astype(str).str.strip()
    df = df[df["url"].str.contains(r"https?://", case=False, na=False)].copy()

    # Normalize URLs at the source
    from utils.ui_helpers import normalize_url
    df["url"] = df["url"].apply(normalize_url)

    # Convert numeric columns
    for col in ["status_code", "word_count", "crawl_depth", "inlinks", "unique_inlinks",
                "outlinks", "unique_outlinks", "title_length", "meta_description_length", "size_bytes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    if "response_time" in df.columns:
        df["response_time"] = pd.to_numeric(df["response_time"], errors="coerce").fillna(0)

    return df


def _norm_url(u: str) -> str:
    """Normalize URL — delegates to the canonical system-wide normalizer."""
    from utils.ui_helpers import normalize_url
    return normalize_url(u)


def analyze_crawl_data(pages_df: pd.DataFrame, inlinks_df: pd.DataFrame, site_domain: str = "",
                       gsc_data=None, page_authority=None, sf_all_pages=None) -> dict:
    """
    Analyze SF data to find technical SEO issues.
    Cross-checks orphans with GSC impressions, Ahrefs backlinks, and SF All Pages inlinks
    to filter out false positives.
    Returns structured issues dict.
    """
    issues = {
        "broken_links": [],       # Links pointing to 4xx/5xx pages
        "redirect_chains": [],    # Pages that redirect
        "orphan_pages": [],       # Pages with 0 inlinks
        "deep_pages": [],         # Crawl depth > 3
        "thin_pages": [],         # Word count < 100
        "missing_meta": [],       # Missing title or description
        "non_indexable": [],      # Pages blocked from indexing
        "slow_pages": [],         # Response time > 2s
    }

    if pages_df.empty:
        return issues

    # Filter to site domain if provided
    if site_domain:
        pages_df = pages_df[pages_df["url"].str.contains(site_domain, case=False, na=False)].copy()

    # ── Broken links (4xx, 5xx) ───────────────────────────────────
    if "status_code" in pages_df.columns:
        broken = pages_df[pages_df["status_code"].between(400, 599)]
        for _, row in broken.iterrows():
            issues["broken_links"].append({
                "url": row["url"],
                "status_code": int(row["status_code"]),
                "action": f"Fix or remove this page — it returns {int(row['status_code'])}",
            })

    # ── Redirects ─────────────────────────────────────────────────
    if "status_code" in pages_df.columns:
        redirects = pages_df[pages_df["status_code"].between(300, 399)]
        for _, row in redirects.iterrows():
            redirect_to = row.get("redirect_url", "")
            issues["redirect_chains"].append({
                "url": row["url"],
                "status_code": int(row["status_code"]),
                "redirect_to": str(redirect_to) if pd.notna(redirect_to) else "",
                "action": f"Update internal links pointing to this URL — it redirects ({int(row['status_code'])})",
            })

    # ── Orphan pages (0 inlinks) — cross-checked with GSC + Ahrefs + SF All Pages ──
    if not inlinks_df.empty:
        linked_targets = set(inlinks_df["target"].apply(_norm_url))

        # Build cross-check sets to filter false orphans
        nav_linked = set()  # SF All Pages says has inlinks > 0
        google_found = set()  # GSC has impressions
        has_backlinks = set()  # Ahrefs has referring domains

        # SF All Pages check (separate from inlinks export)
        if sf_all_pages is not None and hasattr(sf_all_pages, "iterrows"):
            for _, sf_row in sf_all_pages.iterrows():
                sf_url = str(sf_row.get("url", ""))
                sf_inlinks = sf_row.get("inlinks", 0) or sf_row.get("unique_inlinks", 0)
                try:
                    if sf_inlinks and int(sf_inlinks) > 0:
                        nav_linked.add(_norm_url(sf_url))
                except (ValueError, TypeError):
                    pass

        # GSC check
        if gsc_data is not None and hasattr(gsc_data, "groupby"):
            gsc_pages = gsc_data.groupby("page")["impressions"].sum()
            for page_url, impr in gsc_pages.items():
                if impr > 0:
                    google_found.add(_norm_url(page_url))

        # Ahrefs check
        if page_authority is not None and hasattr(page_authority, "iterrows"):
            for _, pa_row in page_authority.iterrows():
                rd = pa_row.get("referring_domains", 0)
                try:
                    if rd and int(rd) > 0:
                        has_backlinks.add(_norm_url(str(pa_row.get("page", ""))))
                except (ValueError, TypeError):
                    pass

        html_pages = pages_df[
            (pages_df.get("status_code", pd.Series(dtype=int)).between(200, 299)) |
            (~pages_df.columns.isin(["status_code"]))
        ]
        for _, row in html_pages.iterrows():
            norm = _norm_url(row["url"])
            inlink_count = row.get("unique_inlinks", row.get("inlinks", -1))
            if inlink_count == 0 or (inlink_count == -1 and norm not in linked_targets):

                # Skip if SF All Pages shows this page has inlinks (nav/menu links)
                if norm in nav_linked:
                    continue

                # Classify severity based on cross-check
                in_google = norm in google_found
                in_ahrefs = norm in has_backlinks

                if not in_google and not in_ahrefs:
                    severity = "CRITICAL"
                    action = "Truly orphaned — no internal links, not in Google, no backlinks. Add links from related pages urgently."
                elif not in_google:
                    severity = "HIGH"
                    action = "No internal links and not in Google (has external backlinks). Add internal links to help Google discover it."
                elif not in_ahrefs:
                    severity = "MEDIUM"
                    action = "No content links — Google found it via sitemap but has no backlinks. Add contextual internal links."
                else:
                    severity = "LOW"
                    action = "No content links (only nav/sitemap) — add contextual links from related pages for SEO value."

                issues["orphan_pages"].append({
                    "url": row["url"],
                    "severity": severity,
                    "in_google": in_google,
                    "has_backlinks": in_ahrefs,
                    "action": action,
                })

    # ── Deep pages (crawl depth > 3) ──────────────────────────────
    if "crawl_depth" in pages_df.columns:
        deep = pages_df[pages_df["crawl_depth"] > 3]
        for _, row in deep.iterrows():
            issues["deep_pages"].append({
                "url": row["url"],
                "crawl_depth": int(row["crawl_depth"]),
                "action": f"This page is {int(row['crawl_depth'])} clicks from the homepage. Move it closer (max 3) by adding links from higher-level pages.",
            })

    # ── Thin pages (word count < 100) ─────────────────────────────
    if "word_count" in pages_df.columns:
        thin = pages_df[(pages_df["word_count"] < 100) & (pages_df["word_count"] > 0)]
        if "status_code" in pages_df.columns:
            thin = thin[thin["status_code"].between(200, 299)]
        for _, row in thin.iterrows():
            issues["thin_pages"].append({
                "url": row["url"],
                "word_count": int(row["word_count"]),
                "action": f"Only {int(row['word_count'])} words — add meaningful content or noindex if this page has no SEO value.",
            })

    # ── Missing meta ──────────────────────────────────────────────
    if "title" in pages_df.columns:
        no_title = pages_df[pages_df["title"].isna() | (pages_df["title"].astype(str).str.strip() == "")]
        if "status_code" in pages_df.columns:
            no_title = no_title[no_title["status_code"].between(200, 299)]
        for _, row in no_title.iterrows():
            issues["missing_meta"].append({
                "url": row["url"],
                "issue": "missing_title",
                "action": "This page has NO title tag — add one with the primary keyword.",
            })

    if "meta_description" in pages_df.columns:
        no_desc = pages_df[pages_df["meta_description"].isna() | (pages_df["meta_description"].astype(str).str.strip() == "")]
        if "status_code" in pages_df.columns:
            no_desc = no_desc[no_desc["status_code"].between(200, 299)]
        for _, row in no_desc.iterrows():
            issues["missing_meta"].append({
                "url": row["url"],
                "issue": "missing_description",
                "action": "This page has NO meta description — add one to improve CTR in search results.",
            })

    # ── Non-indexable ─────────────────────────────────────────────
    if "indexability" in pages_df.columns:
        non_idx = pages_df[pages_df["indexability"].astype(str).str.lower() == "non-indexable"]
        for _, row in non_idx.iterrows():
            reason = row.get("indexability_status", "")
            issues["non_indexable"].append({
                "url": row["url"],
                "reason": str(reason) if pd.notna(reason) else "",
                "action": f"This page is non-indexable ({reason}). If it should rank, fix the blocking issue.",
            })

    # ── Slow pages ────────────────────────────────────────────────
    if "response_time" in pages_df.columns:
        slow = pages_df[pages_df["response_time"] > 2.0]
        for _, row in slow.iterrows():
            issues["slow_pages"].append({
                "url": row["url"],
                "response_time": round(float(row["response_time"]), 2),
                "action": f"Response time {row['response_time']:.1f}s — optimize server response, compress images, enable caching.",
            })

    # ── Canonical mismatches ────────────────────────────────────
    issues["canonical_issues"] = []
    if "canonical" in pages_df.columns:
        for _, row in pages_df.iterrows():
            canon = str(row.get("canonical", "")).strip()
            page_url = str(row.get("url", "")).strip()
            if canon and canon != "nan" and _norm_url(canon) != _norm_url(page_url):
                issues["canonical_issues"].append({
                    "url": page_url,
                    "canonical": canon,
                    "action": f"Canonical points to {canon} — this page's signals go to the canonical. If this page should rank independently, fix the canonical tag.",
                })

    # ── Faceted/parameter URLs (Magento 1.9 specific) ────────────
    issues["faceted_urls"] = []
    param_patterns = ["?", "SID=", "dir=", "limit=", "mode=", "order=", "p=", "product_list"]
    raw_url_col = "URL Encoded Address" if "URL Encoded Address" in pages_df.columns else "url"
    for _, row in pages_df.iterrows():
        raw_url = str(row.get(raw_url_col, ""))
        if any(p in raw_url for p in param_patterns):
            issues["faceted_urls"].append({
                "url": row.get("url", raw_url),
                "raw_url": raw_url,
                "action": "URL contains filter/sort/pagination parameters — block via robots.txt or set noindex to prevent crawl waste.",
            })

    # ── Near-duplicate content ───────────────────────────────────
    issues["near_duplicates"] = []
    if "No. Near Duplicates" in pages_df.columns:
        for _, row in pages_df.iterrows():
            n_dupes = row.get("No. Near Duplicates", 0)
            try:
                n_dupes = int(float(n_dupes)) if pd.notna(n_dupes) else 0
            except (ValueError, TypeError):
                n_dupes = 0
            if n_dupes > 0:
                closest = row.get("Closest Near Duplicate Match", "")
                issues["near_duplicates"].append({
                    "url": row["url"],
                    "duplicate_count": n_dupes,
                    "closest_match": str(closest) if pd.notna(closest) else "",
                    "action": f"{n_dupes} near-duplicate(s). Closest: {closest}. Consolidate or add canonical.",
                })

    return issues


def build_complete_link_map(inlinks_df: pd.DataFrame) -> dict:
    """
    Build a compact internal link map from SF inlinks data.
    Memory-efficient: deduplicates and stores only unique source→target pairs.
    Returns: {
        "links_from": { url: [{"target": ..., "anchor": ...}] },
        "links_to": { url: [{"source": ..., "anchor": ...}] },
        "anchor_quality": { url: {"total": N, "descriptive": N, "generic": N, "empty": N} },
        "total_links": int,
        "unique_pages": int,
        "unique_pairs": int,
    }
    """
    links_from = {}  # url -> list of unique outgoing links
    links_to = {}    # url -> list of unique incoming links
    anchor_quality = {}  # url -> anchor text quality stats
    seen_pairs = set()

    # Generic/useless anchor texts (multiple languages)
    generic_anchors = {
        "", "click here", "read more", "learn more", "here", "link",
        "klicka här", "läs mer", "mer info", "se mer", "visa",
        "klik her", "læs mere", "se mere",
    }

    for _, row in inlinks_df.iterrows():
        source = str(row["source"])
        target = str(row["target"])
        anchor = str(row.get("anchor", "")).strip()
        pair = (source, target)

        # Deduplicate: one entry per source→target pair (keep first anchor)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        # Links FROM source
        if source not in links_from:
            links_from[source] = []
        links_from[source].append({"target": target, "anchor": anchor})

        # Links TO target
        if target not in links_to:
            links_to[target] = []
        links_to[target].append({"source": source, "anchor": anchor})

        # Anchor quality stats for target page
        if target not in anchor_quality:
            anchor_quality[target] = {"total": 0, "descriptive": 0, "generic": 0, "empty": 0}
        aq = anchor_quality[target]
        aq["total"] += 1
        if not anchor:
            aq["empty"] += 1
        elif anchor.lower() in generic_anchors or len(anchor) < 3:
            aq["generic"] += 1
        else:
            aq["descriptive"] += 1

    return {
        "links_from": links_from,
        "links_to": links_to,
        "anchor_quality": anchor_quality,
        "total_links": len(inlinks_df),
        "unique_pairs": len(seen_pairs),
        "unique_pages": len(set(list(links_from.keys()) + list(links_to.keys()))),
    }
