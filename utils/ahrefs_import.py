"""
Ahrefs CSV import and parsing.
Handles three export types:
- Best by links (page-level authority)
- Backlinks (individual inbound links)
- Organic keywords (supplement to GSC)
"""

import pandas as pd
import io
from urllib.parse import urlparse


def parse_best_by_links(file_content) -> pd.DataFrame:
    """
    Parse Ahrefs 'Best by links' CSV export.
    Expected columns vary but typically include:
    - URL / Target URL
    - Referring domains (dofollow)
    - Backlinks (dofollow)
    - DR (Domain Rating) of target
    - Traffic
    """
    df = _read_csv_flexible(file_content)
    if df.empty:
        return df

    # Normalize column names (Ahrefs varies between exports)
    col_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if "url" in col_lower and "source" not in col_lower and "ref" not in col_lower:
            col_map[col] = "page"
        elif "referring" in col_lower and "domain" in col_lower:
            col_map[col] = "referring_domains"
        elif col_lower in ("dofollow", "backlinks", "dofollow backlinks"):
            col_map[col] = "backlinks"
        elif col_lower in ("dr", "domain rating"):
            col_map[col] = "dr"
        elif col_lower in ("traffic", "organic traffic"):
            col_map[col] = "ahrefs_traffic"
        elif col_lower in ("keywords", "organic keywords"):
            col_map[col] = "ahrefs_keywords"

    df = df.rename(columns=col_map)

    # Ensure required columns
    if "page" not in df.columns:
        # Try first column as URL
        df = df.rename(columns={df.columns[0]: "page"})

    # Convert numeric columns
    for col in ["referring_domains", "backlinks", "dr", "ahrefs_traffic", "ahrefs_keywords"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Normalize URLs
    if "page" in df.columns:
        df["page"] = df["page"].str.strip()

    return df


def parse_backlinks(file_content) -> pd.DataFrame:
    """
    Parse Ahrefs 'Backlinks' CSV export.
    Expected columns:
    - Referring page URL / Source URL
    - Target URL
    - Anchor
    - DR
    - Traffic (referring page)
    - Type (dofollow/nofollow)
    """
    df = _read_csv_flexible(file_content)
    if df.empty:
        return df

    col_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if ("source" in col_lower or "referring" in col_lower) and "url" in col_lower:
            col_map[col] = "source_url"
        elif "target" in col_lower and "url" in col_lower:
            col_map[col] = "target_url"
        elif col_lower in ("anchor", "anchor text"):
            col_map[col] = "anchor"
        elif col_lower in ("dr", "domain rating"):
            col_map[col] = "source_dr"
        elif col_lower in ("traffic", "page traffic"):
            col_map[col] = "source_traffic"
        elif col_lower in ("type", "link type"):
            col_map[col] = "link_type"
        elif "first seen" in col_lower:
            col_map[col] = "first_seen"

    df = df.rename(columns=col_map)

    # Extract source domain
    if "source_url" in df.columns:
        df["source_domain"] = df["source_url"].apply(_extract_domain)

    # Convert numeric
    for col in ["source_dr", "source_traffic"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df


def parse_organic_keywords(file_content) -> pd.DataFrame:
    """
    Parse Ahrefs 'Organic keywords' CSV export.
    Supplements GSC with search volume data.
    """
    df = _read_csv_flexible(file_content)
    if df.empty:
        return df

    col_map = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in ("keyword", "query"):
            col_map[col] = "keyword"
        elif col_lower in ("volume", "search volume"):
            col_map[col] = "volume"
        elif col_lower in ("kd", "keyword difficulty"):
            col_map[col] = "keyword_difficulty"
        elif col_lower in ("position", "current position"):
            col_map[col] = "position"
        elif col_lower in ("traffic", "estimated traffic"):
            col_map[col] = "est_traffic"
        elif "url" in col_lower:
            col_map[col] = "page"
        elif col_lower in ("cpc",):
            col_map[col] = "cpc"

    df = df.rename(columns=col_map)

    for col in ["volume", "keyword_difficulty", "position", "est_traffic"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def build_page_authority(
    best_by_links_df: pd.DataFrame = None,
    backlinks_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Build a page-level authority score combining Ahrefs data.
    Returns DataFrame with page URL and authority metrics.
    """
    records = {}

    if best_by_links_df is not None and not best_by_links_df.empty:
        for _, row in best_by_links_df.iterrows():
            page = row.get("page", "")
            if not page:
                continue
            records[page] = {
                "page": page,
                "referring_domains": int(row.get("referring_domains", 0)),
                "backlinks": int(row.get("backlinks", 0)),
                "ahrefs_traffic": int(row.get("ahrefs_traffic", 0)),
            }

    if backlinks_df is not None and not backlinks_df.empty:
        # Aggregate backlinks per target URL
        target_agg = (
            backlinks_df.groupby("target_url")
            .agg(
                backlink_count=("source_url", "count"),
                unique_domains=("source_domain", "nunique"),
                avg_source_dr=("source_dr", "mean"),
                high_dr_links=("source_dr", lambda x: (x >= 50).sum()),
            )
            .reset_index()
        )

        for _, row in target_agg.iterrows():
            page = row["target_url"]
            if page not in records:
                records[page] = {"page": page, "referring_domains": 0, "backlinks": 0, "ahrefs_traffic": 0}

            records[page]["backlink_count_detail"] = int(row["backlink_count"])
            records[page]["unique_domains_detail"] = int(row["unique_domains"])
            records[page]["avg_source_dr"] = round(row["avg_source_dr"], 1)
            records[page]["high_dr_links"] = int(row["high_dr_links"])

    if not records:
        return pd.DataFrame()

    result = pd.DataFrame(records.values())

    # Calculate authority score (0-100)
    if "referring_domains" in result.columns:
        max_rd = result["referring_domains"].max()
        if max_rd > 0:
            result["authority_score"] = (result["referring_domains"] / max_rd * 70).clip(upper=70)
        else:
            result["authority_score"] = 0

        if "high_dr_links" in result.columns:
            max_hdr = result["high_dr_links"].max()
            if max_hdr > 0:
                result["authority_score"] += (result["high_dr_links"] / max_hdr * 30).clip(upper=30)

        result["authority_score"] = result["authority_score"].round(0).astype(int)

    # Risk level: high authority = high risk to change
    if "authority_score" in result.columns:
        result["change_risk"] = result["authority_score"].apply(
            lambda s: "HIGH - do not change URL/structure" if s >= 60
            else "MEDIUM - change with care" if s >= 30
            else "LOW - safe to optimize"
        )

    return result.sort_values("referring_domains", ascending=False).reset_index(drop=True)


def merge_authority_with_gsc(gsc_df: pd.DataFrame, authority_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge page authority data into GSC data.
    Matches on page URL (handles trailing slash differences).
    """
    if authority_df.empty:
        return gsc_df

    # Normalize URLs for matching
    gsc_pages = gsc_df[["page"]].drop_duplicates().copy()
    gsc_pages["page_norm"] = gsc_pages["page"].str.rstrip("/").str.lower()

    auth = authority_df.copy()
    auth["page_norm"] = auth["page"].str.rstrip("/").str.lower()

    merged = gsc_pages.merge(
        auth.drop(columns=["page"]),
        on="page_norm",
        how="left"
    ).drop(columns=["page_norm"])

    # Merge back into full GSC df
    result = gsc_df.merge(
        merged,
        on="page",
        how="left"
    )

    # Fill NaN authority with 0
    for col in ["referring_domains", "backlinks", "authority_score"]:
        if col in result.columns:
            result[col] = result[col].fillna(0).astype(int)

    if "change_risk" in result.columns:
        result["change_risk"] = result["change_risk"].fillna("UNKNOWN - no Ahrefs data")

    return result


def _read_csv_flexible(file_content) -> pd.DataFrame:
    """Read CSV with flexible encoding and separator detection."""
    if isinstance(file_content, bytes):
        content = file_content
    else:
        content = file_content.read()

    # Try different encodings
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            text = content.decode(encoding)
            # Detect separator
            first_line = text.split("\n")[0]
            if "\t" in first_line:
                sep = "\t"
            elif ";" in first_line and "," not in first_line:
                sep = ";"
            else:
                sep = ","

            df = pd.read_csv(io.StringIO(text), sep=sep)
            if len(df.columns) > 1:
                return df
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue

    return pd.DataFrame()


def _extract_domain(url: str) -> str:
    try:
        return urlparse(str(url)).netloc.lower()
    except Exception:
        return ""
