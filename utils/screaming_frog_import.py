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

            df = pd.read_csv(io.StringIO(text), sep=sep, on_bad_lines="skip")
            df.columns = [c.strip().strip('"').strip() for c in df.columns]
            if len(df.columns) > 1:
                return df
        except (UnicodeDecodeError, pd.errors.ParserError, LookupError):
            continue

    return pd.DataFrame()


def parse_all_inlinks(file_content) -> pd.DataFrame:
    """
    Parse Screaming Frog "All Inlinks" export.
    Expected columns: Source, Destination, Anchor, Type, Status Code, etc.
    Returns: DataFrame with source, target, anchor, link_type, status_code
    """
    df = _read_csv_flexible(file_content)
    if df.empty:
        return df

    col_map = {}
    for col in df.columns:
        cl = col.lower().strip()
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
        elif cl in ("path type", "link position"):
            col_map[col] = "link_position"
        # Fuzzy fallbacks
        elif "source" in cl or "from" in cl:
            col_map.setdefault(col, "source")
        elif "dest" in cl or "target" in cl or "to" == cl:
            col_map.setdefault(col, "target")
        elif "anchor" in cl:
            col_map.setdefault(col, "anchor")
        elif "status" in cl and "code" in cl:
            col_map.setdefault(col, "status_code")

    df = df.rename(columns=col_map)

    # Must have source + target
    if "source" not in df.columns or "target" not in df.columns:
        # Try to find URL-like columns
        url_cols = []
        for col in df.columns:
            sample = df[col].dropna().head(10).astype(str)
            if sample.str.contains(r"https?://", case=False).any():
                url_cols.append(col)
        if len(url_cols) >= 2:
            df = df.rename(columns={url_cols[0]: "source", url_cols[1]: "target"})
        elif len(url_cols) == 1:
            return pd.DataFrame()
        else:
            return pd.DataFrame()

    # Clean URLs
    df["source"] = df["source"].astype(str).str.strip()
    df["target"] = df["target"].astype(str).str.strip()

    # Filter to internal links only (same domain)
    df = df[df["source"].str.contains(r"https?://", case=False, na=False)].copy()
    df = df[df["target"].str.contains(r"https?://", case=False, na=False)].copy()

    # Fill missing columns
    if "anchor" not in df.columns:
        df["anchor"] = ""
    if "status_code" not in df.columns:
        df["status_code"] = 200
    if "link_type" not in df.columns:
        df["link_type"] = "Hyperlink"
    if "follow" not in df.columns:
        df["follow"] = "Follow"

    df["anchor"] = df["anchor"].fillna("").astype(str)
    df["status_code"] = pd.to_numeric(df["status_code"], errors="coerce").fillna(200).astype(int)

    return df[["source", "target", "anchor", "link_type", "status_code", "follow"]].copy()


def parse_all_pages(file_content) -> pd.DataFrame:
    """
    Parse Screaming Frog "All Pages" / "Internal All" export.
    Expected columns: Address, Status Code, Title, Meta Description, H1, Word Count, Crawl Depth, etc.
    """
    df = _read_csv_flexible(file_content)
    if df.empty:
        return df

    col_map = {}
    for col in df.columns:
        cl = col.lower().strip()
        if cl in ("address", "url", "page url"):
            col_map[col] = "url"
        elif cl in ("status code", "http status code"):
            col_map[col] = "status_code"
        elif cl in ("title 1", "title"):
            col_map[col] = "title"
        elif cl in ("title 1 length", "title length"):
            col_map[col] = "title_length"
        elif cl in ("meta description 1", "meta description"):
            col_map[col] = "meta_description"
        elif cl in ("meta description 1 length", "meta description length"):
            col_map[col] = "meta_description_length"
        elif cl in ("h1-1", "h1", "h1 1"):
            col_map[col] = "h1"
        elif cl in ("word count"):
            col_map[col] = "word_count"
        elif cl in ("crawl depth"):
            col_map[col] = "crawl_depth"
        elif cl in ("inlinks"):
            col_map[col] = "inlinks"
        elif cl in ("outlinks"):
            col_map[col] = "outlinks"
        elif cl in ("unique inlinks"):
            col_map[col] = "unique_inlinks"
        elif cl in ("unique outlinks"):
            col_map[col] = "unique_outlinks"
        elif cl in ("indexability"):
            col_map[col] = "indexability"
        elif cl in ("indexability status"):
            col_map[col] = "indexability_status"
        elif cl in ("canonical link element 1", "canonical"):
            col_map[col] = "canonical"
        elif cl in ("redirect url", "redirect uri"):
            col_map[col] = "redirect_url"
        elif cl in ("content type", "content"):
            col_map.setdefault(col, "content_type")
        elif cl in ("size (bytes)", "size"):
            col_map.setdefault(col, "size_bytes")
        elif cl in ("response time"):
            col_map.setdefault(col, "response_time")
        # Fuzzy
        elif "canonical" in cl:
            col_map.setdefault(col, "canonical")
        elif "redirect" in cl and "url" in cl:
            col_map.setdefault(col, "redirect_url")
        elif "word" in cl and "count" in cl:
            col_map.setdefault(col, "word_count")
        elif "crawl" in cl and "depth" in cl:
            col_map.setdefault(col, "crawl_depth")

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

    # Convert numeric columns
    for col in ["status_code", "word_count", "crawl_depth", "inlinks", "unique_inlinks",
                "outlinks", "unique_outlinks", "title_length", "meta_description_length", "size_bytes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    if "response_time" in df.columns:
        df["response_time"] = pd.to_numeric(df["response_time"], errors="coerce").fillna(0)

    return df


def analyze_crawl_data(pages_df: pd.DataFrame, inlinks_df: pd.DataFrame, site_domain: str = "") -> dict:
    """
    Analyze SF data to find technical SEO issues.
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

    # ── Orphan pages (0 inlinks) ──────────────────────────────────
    if not inlinks_df.empty:
        linked_targets = set(inlinks_df["target"].str.rstrip("/").str.lower())
        html_pages = pages_df[
            (pages_df.get("status_code", pd.Series(dtype=int)).between(200, 299)) |
            (~pages_df.columns.isin(["status_code"]))
        ]
        for _, row in html_pages.iterrows():
            url_norm = row["url"].rstrip("/").lower()
            inlink_count = row.get("unique_inlinks", row.get("inlinks", -1))
            if inlink_count == 0 or (inlink_count == -1 and url_norm not in linked_targets):
                issues["orphan_pages"].append({
                    "url": row["url"],
                    "action": "This page has NO internal links pointing to it — Google may not discover or rank it. Add links from related pages.",
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

    return issues


def build_complete_link_map(inlinks_df: pd.DataFrame) -> dict:
    """
    Build a complete internal link map from SF inlinks data.
    Returns: {
        "links_from": { url: [{"target": ..., "anchor": ..., "status_code": ...}] },
        "links_to": { url: [{"source": ..., "anchor": ...}] },
        "all_anchors": { (source, target): [anchor1, anchor2, ...] },
    }
    """
    links_from = {}  # url -> list of outgoing links
    links_to = {}    # url -> list of incoming links
    all_anchors = {}

    for _, row in inlinks_df.iterrows():
        source = row["source"]
        target = row["target"]
        anchor = row.get("anchor", "")

        # Links FROM source
        if source not in links_from:
            links_from[source] = []
        links_from[source].append({
            "target": target,
            "anchor": str(anchor),
            "status_code": int(row.get("status_code", 200)),
        })

        # Links TO target
        if target not in links_to:
            links_to[target] = []
        links_to[target].append({
            "source": source,
            "anchor": str(anchor),
        })

        # All anchors for each pair
        pair = (source.rstrip("/").lower(), target.rstrip("/").lower())
        if pair not in all_anchors:
            all_anchors[pair] = []
        if anchor and str(anchor).strip():
            all_anchors[pair].append(str(anchor))

    return {
        "links_from": links_from,
        "links_to": links_to,
        "all_anchors": all_anchors,
        "total_links": len(inlinks_df),
        "unique_pages": len(set(list(links_from.keys()) + list(links_to.keys()))),
    }
