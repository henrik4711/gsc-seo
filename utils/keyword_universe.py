"""Unified keyword universe — single source of truth for ALL keywords.

Why this exists
---------------
mshop's own Google Search Console data only contains queries the site
*already ranks for* — roughly 1/5 of what competitors (e.g. Sinful) rank
for. To find real content gaps we union three tagged sources into ONE
keyword universe:

  1. GSC queries          — own, with real impressions / clicks / position
  2. Ahrefs own keywords  — own, adds search volume + difficulty
  3. Ahrefs competitor    — per-competitor CSV upload; volume + which
                            competitor ranks and at what position

Every row is tagged with its source (and competitor domain), so downstream
clustering and gap analysis can treat the whole universe as one dataset
while still knowing where a keyword came from.

CRITICAL — brand stripping
--------------------------
A competitor's export is dominated by their OWN brand terms ("sinful ...",
"sinful rabatkode", ...). mshop can never rank for those, so they are pure
noise. For every competitor the operator supplies the brand name(s); any
keyword containing those tokens is dropped before it enters the universe.
mshop's own brand is kept. The Ahrefs "Branded" column is unreliable across
domains, so we filter on operator-supplied brand names instead.

This module is framework-agnostic (pandas only) — no Streamlit, no NiceGUI.
It is imported by the presentation layer, never the other way around.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import pandas as pd

from utils.ahrefs_import import parse_organic_keywords

# One row per unique keyword. Kept explicit so every consumer sees the same
# schema regardless of which sources were present.
UNIVERSE_COLUMNS = [
    "keyword",                  # display form (first-seen casing)
    "volume",                   # max search volume across sources (0 if unknown)
    "keyword_difficulty",       # max KD across sources (0 if unknown)
    "own_ranks",                # bool: mshop appears for this keyword (GSC or own Ahrefs)
    "own_position",             # mshop position (from GSC, else own Ahrefs); 0 if not ranking
    "own_impressions",          # from GSC (0 if none)
    "own_clicks",               # from GSC (0 if none)
    "competitors",              # sorted list of competitor domains ranking for it
    "n_competitors",            # len(competitors)
    "best_competitor_position", # best (lowest) competitor position; 0 if none
    "is_gap",                   # bool: competitors rank but mshop does not
    "sources",                  # sorted list, e.g. ["ahrefs_own", "competitor", "gsc"]
]


# ── brand stripping ──────────────────────────────────────────────────

def brand_from_domain(domain: str) -> str:
    """Best-effort brand token from a domain, e.g. 'www.sinful.dk' -> 'sinful'.

    Used only to PRE-FILL the brand field in the UI; the operator can edit
    it. Returns '' when nothing sensible can be derived.
    """
    if not domain:
        return ""
    d = str(domain).strip().lower()
    # Accept a full URL or a bare domain.
    if "://" in d:
        d = urlparse(d).netloc or d
    d = d.split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    label = d.split(".")[0] if "." in d else d
    return label.strip()


def _brand_pattern(brand_terms) -> re.Pattern | None:
    """Compile a case-insensitive whole-word matcher for the brand tokens.

    Multi-word brands ("bon jour") match as a sequence with flexible
    whitespace. Empty / blank terms are ignored. Returns None when there is
    nothing to match (so callers can skip filtering entirely).
    """
    terms = []
    for t in brand_terms or []:
        t = str(t).strip().lower()
        if len(t) < 2:  # 1-char "brands" would nuke half the universe
            continue
        # Escape, then allow flexible whitespace between words of a phrase.
        parts = [re.escape(p) for p in t.split()]
        terms.append(r"\s+".join(parts))
    if not terms:
        return None
    # \b word boundaries so "sinful" strips "sinful analplug" but a brand
    # that is a substring of a longer word ("lelo" in "kaleidoscope") does
    # not fire on the inner match.
    return re.compile(r"\b(?:" + "|".join(terms) + r")\b", re.IGNORECASE)


def strip_brand_terms(
    df: pd.DataFrame, brand_terms, keyword_col: str = "keyword"
) -> pd.DataFrame:
    """Drop rows whose keyword contains any supplied brand token.

    Pure and side-effect free — returns a filtered copy. No-op (returns the
    frame unchanged) when df is empty or no usable brand terms are given.
    """
    if df is None or df.empty or keyword_col not in df.columns:
        return df
    pat = _brand_pattern(brand_terms)
    if pat is None:
        return df
    mask = df[keyword_col].astype(str).str.contains(pat, na=False)
    return df[~mask].copy()


# ── loading a competitor export ──────────────────────────────────────

def load_competitor_keywords(
    file_content, competitor: str, brand_terms=None
) -> pd.DataFrame:
    """Parse ONE competitor's Ahrefs 'Organic keywords' CSV and tag it.

    - ``competitor`` is the competitor's domain (used as the tag and to
      pre-derive the brand if ``brand_terms`` is omitted).
    - The competitor's own brand terms are stripped immediately so the
      returned frame is already clean for display and for the universe.

    Returns a DataFrame with the parse_organic_keywords columns plus
    ``source='competitor'`` and ``competitor=<domain>``. Empty frame on a
    file that could not be parsed.
    """
    df = parse_organic_keywords(file_content)
    if df is None or df.empty or "keyword" not in df.columns:
        return pd.DataFrame()

    domain = brand_from_domain(competitor) if competitor else ""
    if brand_terms is None:
        brand_terms = [domain] if domain else []

    df = strip_brand_terms(df, brand_terms)
    df = df.copy()
    df["source"] = "competitor"
    df["competitor"] = (competitor or domain or "").strip().lower()
    return df


# ── building the universe ────────────────────────────────────────────

def _norm_kw(kw) -> str:
    return re.sub(r"\s+", " ", str(kw).strip().lower())


def _gsc_long(gsc_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse GSC (many rows per query/page) to one row per query."""
    if gsc_df is None or getattr(gsc_df, "empty", True) or "query" not in gsc_df.columns:
        return pd.DataFrame()
    agg = (
        gsc_df.groupby("query")
        .agg(
            own_impressions=("impressions", "sum"),
            own_clicks=("clicks", "sum"),
            own_position=("position", "mean"),
        )
        .reset_index()
        .rename(columns={"query": "keyword"})
    )
    agg["source"] = "gsc"
    agg["competitor"] = ""
    agg["volume"] = 0
    agg["keyword_difficulty"] = 0
    return agg


def _ahrefs_long(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Normalize an Ahrefs organic-keywords frame to the long shape."""
    if df is None or getattr(df, "empty", True) or "keyword" not in df.columns:
        return pd.DataFrame()
    out = pd.DataFrame({"keyword": df["keyword"].astype(str)})
    out["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    out["keyword_difficulty"] = pd.to_numeric(
        df.get("keyword_difficulty", 0), errors="coerce"
    ).fillna(0)
    out["own_position"] = pd.to_numeric(df.get("position", 0), errors="coerce").fillna(0)
    out["source"] = source
    out["competitor"] = df.get("competitor", "") if source == "competitor" else ""
    out["own_impressions"] = 0
    out["own_clicks"] = 0
    return out


def build_keyword_universe(
    gsc_df: pd.DataFrame | None = None,
    own_keywords_df: pd.DataFrame | None = None,
    competitor_frames: list[pd.DataFrame] | None = None,
    competitor_brands=None,
) -> pd.DataFrame:
    """Union all sources into ONE keyword universe (one row per keyword).

    Parameters
    ----------
    gsc_df
        Raw GSC dataframe (query / page / impressions / clicks / position).
    own_keywords_df
        mshop's own Ahrefs 'Organic keywords' export (optional).
    competitor_frames
        List of frames from ``load_competitor_keywords`` (already tagged).
    competitor_brands
        Union of ALL competitor brand tokens. Applied globally as a final
        safety net so e.g. "sinful" is stripped even if it slipped in via a
        different competitor's export. mshop's own brand is NOT included.

    Returns a DataFrame with :data:`UNIVERSE_COLUMNS`, sorted by volume then
    own_impressions (most valuable first). Empty frame if no source given.
    """
    longs: list[pd.DataFrame] = []
    g = _gsc_long(gsc_df)
    if not g.empty:
        longs.append(g)
    a = _ahrefs_long(own_keywords_df, "ahrefs_own")
    if not a.empty:
        longs.append(a)
    for cf in competitor_frames or []:
        c = _ahrefs_long(cf, "competitor")
        if not c.empty:
            longs.append(c)

    if not longs:
        return pd.DataFrame(columns=UNIVERSE_COLUMNS)

    long = pd.concat(longs, ignore_index=True, sort=False)
    # Ensure every expected column exists before aggregating.
    for col, default in [
        ("volume", 0), ("keyword_difficulty", 0), ("own_position", 0),
        ("own_impressions", 0), ("own_clicks", 0), ("competitor", ""),
    ]:
        if col not in long.columns:
            long[col] = default
    long["keyword"] = long["keyword"].astype(str)
    long["_norm"] = long["keyword"].map(_norm_kw)
    long = long[long["_norm"].str.len() > 0]

    rows = []
    for norm, grp in long.groupby("_norm", sort=False):
        own_grp = grp[grp["source"].isin(("gsc", "ahrefs_own"))]
        own_ranks = not own_grp.empty
        # Prefer GSC position, else own Ahrefs; ignore 0/blank positions.
        own_pos_vals = own_grp.loc[own_grp["own_position"] > 0, "own_position"]
        own_position = round(float(own_pos_vals.min()), 1) if not own_pos_vals.empty else 0.0

        comp_grp = grp[grp["source"] == "competitor"]
        competitors = sorted({str(d).strip().lower() for d in comp_grp["competitor"] if str(d).strip()})
        comp_pos_vals = comp_grp.loc[comp_grp["own_position"] > 0, "own_position"]
        best_comp_pos = round(float(comp_pos_vals.min()), 1) if not comp_pos_vals.empty else 0.0

        rows.append({
            "keyword": grp["keyword"].iloc[0],
            "volume": int(grp["volume"].max()),
            "keyword_difficulty": int(grp["keyword_difficulty"].max()),
            "own_ranks": bool(own_ranks),
            "own_position": own_position,
            "own_impressions": int(grp["own_impressions"].max()),
            "own_clicks": int(grp["own_clicks"].max()),
            "competitors": competitors,
            "n_competitors": len(competitors),
            "best_competitor_position": best_comp_pos,
            "is_gap": bool(competitors) and not own_ranks,
            "sources": sorted(set(grp["source"])),
        })

    universe = pd.DataFrame(rows, columns=UNIVERSE_COLUMNS)

    # Global brand safety net — strip every competitor brand across the
    # whole universe (never mshop's own brand).
    universe = strip_brand_terms(universe, competitor_brands)

    if universe.empty:
        return universe
    return universe.sort_values(
        ["volume", "own_impressions"], ascending=[False, False]
    ).reset_index(drop=True)


# ── summaries for the UI ─────────────────────────────────────────────

def universe_summary(universe_df: pd.DataFrame) -> dict:
    """Headline counts for the import/overview screen."""
    if universe_df is None or universe_df.empty:
        return {"total": 0, "own": 0, "gaps": 0, "with_volume": 0,
                "competitors": 0, "total_volume": 0}
    comps = set()
    for lst in universe_df["competitors"]:
        comps.update(lst or [])
    return {
        "total": int(len(universe_df)),
        "own": int(universe_df["own_ranks"].sum()),
        "gaps": int(universe_df["is_gap"].sum()),
        "with_volume": int((universe_df["volume"] > 0).sum()),
        "competitors": len(comps),
        "total_volume": int(universe_df["volume"].sum()),
    }


def keyword_gaps(universe_df: pd.DataFrame, min_volume: int = 0) -> pd.DataFrame:
    """Keywords competitors rank for but mshop does not — the opportunity list.

    Sorted by volume desc. ``min_volume`` filters out zero/low-volume noise.
    """
    if universe_df is None or universe_df.empty:
        return pd.DataFrame(columns=UNIVERSE_COLUMNS)
    gaps = universe_df[universe_df["is_gap"]]
    if min_volume > 0:
        gaps = gaps[gaps["volume"] >= min_volume]
    return gaps.sort_values("volume", ascending=False).reset_index(drop=True)


# ── state orchestration (the ONE place the universe is assembled) ─────
#
# Everything above is pure (pandas only). The helpers below read/write the
# framework-agnostic app store via state() and persist to disk, so any
# frontend (NiceGUI today, Streamlit still) assembles the universe exactly
# the same way. Keep the "how do the stored inputs become a universe" rule
# here — never re-implement it in a view. See feedback_shared_logic_in_utils.

COMPETITOR_STORE_KEY = "ahrefs_competitor_keywords"  # combined tagged frame
COMPETITOR_META_KEY = "competitor_meta"              # list[{domain, brand_terms, count}]
UNIVERSE_KEY = "keyword_universe"


def _all_competitor_brands(meta) -> list[str]:
    brands: list[str] = []
    for m in meta or []:
        brands.extend(m.get("brand_terms") or [])
    return brands


def refresh_universe():
    """Rebuild the keyword universe from whatever inputs are in the store.

    Reads gsc_data + ahrefs_organic_keywords (own) + the combined competitor
    frame, applies the global competitor-brand strip, writes
    ``keyword_universe`` back to the store and persists it. Returns the
    universe DataFrame. Safe to call whenever an input changes (idempotent).
    """
    from utils.state import state
    from utils.persistence import save

    s = state()
    comp = s.get(COMPETITOR_STORE_KEY)
    comp_frames = [comp] if comp is not None and not getattr(comp, "empty", True) else None
    universe = build_keyword_universe(
        gsc_df=s.get("gsc_data"),
        own_keywords_df=s.get("ahrefs_organic_keywords"),
        competitor_frames=comp_frames,
        competitor_brands=_all_competitor_brands(s.get(COMPETITOR_META_KEY)),
    )
    s[UNIVERSE_KEY] = universe
    try:
        save(UNIVERSE_KEY)
    except Exception:
        pass
    return universe


def add_competitor(file_content, domain: str, brand_terms=None):
    """Import one competitor CSV into the store and rebuild the universe.

    Replaces any previous upload for the same domain (re-upload = refresh).
    Persists the combined competitor frame + meta, then refreshes the
    universe. Returns (n_keywords_added, universe_summary_dict).
    """
    from utils.state import state
    from utils.persistence import save

    domain = (domain or "").strip().lower()
    if brand_terms is None:
        b = brand_from_domain(domain)
        brand_terms = [b] if b else []
    brand_terms = [t.strip() for t in brand_terms if str(t).strip()]

    frame = load_competitor_keywords(file_content, domain, brand_terms)
    if frame is None or frame.empty:
        return 0, universe_summary(state().get(UNIVERSE_KEY))

    s = state()
    existing = s.get(COMPETITOR_STORE_KEY)
    if existing is not None and not getattr(existing, "empty", True):
        # Drop any prior rows for this domain, then append the fresh ones.
        kept = existing[existing.get("competitor", "") != domain]
        combined = pd.concat([kept, frame], ignore_index=True, sort=False)
    else:
        combined = frame
    s[COMPETITOR_STORE_KEY] = combined

    meta = [m for m in (s.get(COMPETITOR_META_KEY) or []) if m.get("domain") != domain]
    meta.append({"domain": domain, "brand_terms": brand_terms, "count": int(len(frame))})
    s[COMPETITOR_META_KEY] = meta

    try:
        save(COMPETITOR_STORE_KEY)
        save(COMPETITOR_META_KEY)
    except Exception:
        pass

    universe = refresh_universe()
    return int(len(frame)), universe_summary(universe)


def remove_competitor(domain: str):
    """Remove one competitor's keywords and rebuild the universe."""
    from utils.state import state
    from utils.persistence import save

    domain = (domain or "").strip().lower()
    s = state()
    existing = s.get(COMPETITOR_STORE_KEY)
    if existing is not None and not getattr(existing, "empty", True):
        s[COMPETITOR_STORE_KEY] = existing[existing.get("competitor", "") != domain].copy()
    s[COMPETITOR_META_KEY] = [
        m for m in (s.get(COMPETITOR_META_KEY) or []) if m.get("domain") != domain
    ]
    try:
        save(COMPETITOR_STORE_KEY)
        save(COMPETITOR_META_KEY)
    except Exception:
        pass
    return refresh_universe()
