"""
Shared UI helpers for consistent next-step guidance across pages.
"""

import streamlit as st
from urllib.parse import urlparse


def stable_hash(text: str) -> str:
    """Deterministic hash that stays the same across process restarts."""
    import hashlib
    return hashlib.md5(text.encode()).hexdigest()[:8]


def show_ai_error(label: str, exc: Exception, context: dict | None = None):
    """
    Detailed AI error display: error class, API status, request ID, credit/rate-limit hint,
    context data, and traceback — so failures aren't silent.
    """
    import json
    import traceback

    err_class = type(exc).__name__
    msg = str(exc)

    status_code = getattr(exc, "status_code", None)
    request_id = getattr(exc, "request_id", None)
    body = getattr(exc, "body", None)

    low_msg = msg.lower()
    hint = ""
    if "no anthropic api key" in low_msg or "anthropic_api_key" in low_msg or "no api key" in low_msg:
        hint = (
            "Anthropic API key is not set. Either set the `ANTHROPIC_API_KEY` env var "
            "(Railway → Variables) and redeploy, OR open **1. Setup & Connect** and paste your key there."
        )
    elif "credit" in low_msg or "insufficient" in low_msg or "balance" in low_msg:
        hint = "Looks like your Anthropic account is out of credits — top up at https://console.anthropic.com/settings/billing."
    elif "rate limit" in low_msg or status_code == 429:
        hint = "Rate limit hit — wait a few seconds and try again. Consider reducing bulk-generation batch size."
    elif "authentication" in low_msg or status_code == 401:
        hint = "API key invalid — re-enter the Anthropic key in Setup."
    elif "overloaded" in low_msg or status_code == 529:
        hint = "Anthropic API is overloaded — retry in a moment."
    elif status_code and status_code >= 500:
        hint = "Anthropic server error — this is on their side, retry shortly."

    st.error(f"**{label} failed** · `{err_class}`: {msg}")
    if hint:
        st.warning(hint)

    lines = []
    if status_code:
        lines.append(f"- **HTTP status:** `{status_code}`")
    if request_id:
        lines.append(f"- **Request ID:** `{request_id}`  *(include when contacting Anthropic)*")
    if body:
        try:
            body_str = json.dumps(body, indent=2, default=str)[:2000]
        except Exception:
            body_str = str(body)[:2000]
        lines.append(f"- **API response body:**\n\n```json\n{body_str}\n```")
    if context:
        lines.append("- **Context:**")
        for k, v in context.items():
            v_str = str(v)
            if len(v_str) > 400:
                v_str = v_str[:400] + "…"
            lines.append(f"  - `{k}` = `{v_str}`")
    tb = traceback.format_exc()
    if tb and tb.strip() != "NoneType: None":
        lines.append(f"- **Traceback:**\n\n```\n{tb[-3000:]}\n```")

    if lines:
        # Use popover (not expander) so this helper works when called
        # from inside another expander — Streamlit forbids nested
        # expanders.
        with st.popover("Full error details (for debugging)"):
            st.markdown("\n".join(lines))


def shorten_url(url: str) -> str:
    """Strip the domain from a URL, returning just the path."""
    parsed = urlparse(url)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def normalize_url(url: str) -> str:
    """
    THE canonical URL normalizer for the entire system.
    Every URL comparison, merge, lookup, and deduplication MUST use this.

    Normalizes:
    - https (never http)
    - Removes www. from netloc
    - Strips ALL query params (? and everything after)
    - Strips fragments (# and everything after)
    - Strips trailing slash
    - Lowercases everything
    - Converts relative paths to absolute using gsc_site
    """
    if not url:
        return ""
    u = str(url).strip()

    # Convert relative to absolute
    if u.startswith("/") and not u.startswith("//"):
        try:
            site = st.session_state.get("gsc_site", "").rstrip("/")
        except Exception:
            site = ""
        if site:
            u = site + u
        else:
            u = "https://example.com" + u

    # Remove fragment
    if "#" in u:
        u = u[:u.index("#")]

    # Remove ALL query params — for matching, params are never meaningful
    if "?" in u:
        u = u[:u.index("?")]

    # Standardize protocol
    u = u.replace("http://", "https://")

    # Remove www from netloc
    u = u.replace("://www.", "://")

    # Strip trailing slash
    u = u.rstrip("/")

    # Lowercase
    u = u.lower()

    return u


STEP_ORDER = [
    ("gsc_data",          "1. Setup & Connect",    "Connect GSC and add API keys"),
    ("page_authority",    "2. Upload Ahrefs",      "Upload Ahrefs CSV files for backlink data"),
    ("ctr_gaps",          "3. CTR Analysis",       "Click 'Analyze CTR Gaps' to find underperformers"),
    ("cannibalization",   "4. Cannibalization",    "Click 'Analyze Cannibalization' to find keyword conflicts"),
    ("topic_clusters",    "5. Topic Clusters",     "Click 'Build Topic Clusters' to group keywords"),
    ("audit_results",     "6. Page Auditor",       "Click 'Run Audit' to check meta and content"),
    ("linking_fixes",     "7. Internal Linking",   "Review and fix internal linking issues"),
    ("keyword_fixes",     "8. Missing Keywords",   "Fill keyword gaps with AI-generated text"),
    ("new_articles",      "9. New Articles",       "Plan and generate new articles"),
    ("clusters_checked",  "10. Cluster Health",     "AI evaluates topic cluster health"),
    ("generated_content", "11. Content Generator",  "Select a page and generate AI-optimized content"),
    ("sitemap_viewed",    "12. Site Map",             "Export complete site structure + AI validation"),
    ("tasks_viewed",      "13. All Tasks",            "Review unified task list across all analyses"),
    ("action_plan",       "14. Implementation",      "Step-by-step fix guide for every page"),
]


def show_next_step():
    """Show a box at the bottom telling the user what to do next."""
    for state_key, step_name, description in STEP_ORDER:
        if state_key not in st.session_state:
            st.markdown(f"""
            <div style="margin-top:2rem; padding:1rem; background:#0d0d1a; border:1px solid #5533ff; border-radius:8px;">
                <div style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#5533ff; letter-spacing:0.1em; margin-bottom:0.3rem;">
                    NEXT STEP
                </div>
                <div style="font-size:0.9rem; color:#e8e8f0; font-weight:600;">
                    {step_name}
                </div>
                <div style="font-size:0.8rem; color:#9b9bb8; margin-top:0.3rem;">
                    {description}
                </div>
            </div>
            """, unsafe_allow_html=True)
            return
    # All done
    st.markdown("""
    <div style="margin-top:2rem; padding:1rem; background:#0d1a0d; border:1px solid #33dd88; border-radius:8px;">
        <div style="font-size:0.9rem; color:#33dd88; font-weight:600;">
            Pipeline complete! All steps finished.
        </div>
    </div>
    """, unsafe_allow_html=True)


def show_missing_step(step_name: str, description: str):
    """Show a warning that a previous step needs to be completed first."""
    st.warning(f"Go to **{step_name}** first: {description}")


def compute_lix(text: str) -> int:
    """
    Compute Swedish/Danish LIX readability score for plain text.

    LIX = (words / sentences) + (long_words * 100 / words)
    where long_words have >6 characters.

    Scale (Scandinavian norm):
      <30 very easy · 30–40 easy (target) · 40–50 medium ·
      50–60 difficult · >60 very difficult

    Accepts HTML — tags are stripped before counting. Returns 0 when
    there's nothing countable (no words or no sentence punctuation).
    """
    if not text:
        return 0

    # Strip HTML to plain text
    if "<" in text and ">" in text:
        try:
            from bs4 import BeautifulSoup
            text = BeautifulSoup(text, "html.parser").get_text(separator=" ")
        except Exception:
            pass

    import re
    # Count sentences — terminal punctuation .!?
    sentences = len(re.findall(r"[.!?]+", text))
    if sentences == 0:
        return 0

    words = re.findall(r"\b\w+\b", text, flags=re.UNICODE)
    if not words:
        return 0

    long_words = sum(1 for w in words if len(w) > 6)
    lix = (len(words) / sentences) + (long_words * 100 / len(words))
    return int(round(lix))


def lix_badge(lix: int) -> tuple[str, str, str]:
    """
    Map a LIX score to (color_hex, label, severity) for UI display.
    severity is one of: "good", "warn", "bad", "too_simple".
    """
    if lix == 0:
        return "#6b6b8a", "n/a", "warn"
    if lix < 25:
        return "#ffaa33", f"LIX {lix} — very easy (may feel childish)", "too_simple"
    if lix <= 40:
        return "#33dd88", f"LIX {lix} — readable, ideal for e-commerce", "good"
    if lix <= 50:
        return "#ffaa33", f"LIX {lix} — medium difficulty", "warn"
    return "#ff4455", f"LIX {lix} — too difficult, regenerate recommended", "bad"


def render_recommendation_diff(
    label: str,
    current: str,
    recommended: str,
    *,
    kind: str = "title",
    ideal_min: int | None = None,
    ideal_max: int | None = None,
    note: str = "",
):
    """
    Render a high-visibility before → after card for an AI recommendation.

    Use everywhere we suggest a new title, meta description, intro, or any
    short copy change so all views look identical and the user always sees
    the recommendation prominently (not buried in inline code blocks).

    Args:
        label: Visible header, e.g. "META TITLE", "META DESCRIPTION", "INTRO TEXT".
        current: The current copy on the page (may be empty).
        recommended: The AI-generated replacement (may be empty).
        kind: "title" | "description" | "intro" — affects the unit shown
              (chars vs. words) and the default ideal range when not given.
        ideal_min, ideal_max: Override the ideal range for the unit.
        note: Optional small note rendered under the recommended block.

    Renders nothing if both current and recommended are empty.
    """
    current = (current or "").strip()
    recommended = (recommended or "").strip()
    if not current and not recommended:
        return

    if kind == "title":
        unit = "chars"
        cur_count = len(current)
        new_count = len(recommended)
        if ideal_min is None: ideal_min = 30
        if ideal_max is None: ideal_max = 65
    elif kind == "description":
        unit = "chars"
        cur_count = len(current)
        new_count = len(recommended)
        if ideal_min is None: ideal_min = 120
        if ideal_max is None: ideal_max = 165
    else:  # intro / generic body copy — count words
        unit = "words"
        cur_count = len(current.split()) if current else 0
        new_count = len(recommended.split()) if recommended else 0
        if ideal_min is None: ideal_min = 80
        if ideal_max is None: ideal_max = 200

    def _len_color(n: int) -> str:
        if n == 0:
            return "#6b6b8a"
        if n < ideal_min or n > ideal_max:
            return "#ffaa33"
        return "#33dd88"

    import html as _html
    cur_safe = _html.escape(current) if current else "<em style='color:#6b6b8a;'>(empty)</em>"
    new_safe = _html.escape(recommended) if recommended else "<em style='color:#6b6b8a;'>(not generated yet)</em>"

    # Bigger panel for intros — they're long-form text
    rec_font = "1rem" if kind == "intro" else "1.05rem"
    rec_max_height = "none" if kind == "intro" else "none"

    st.markdown(
        f"""
<div style='border:2px solid #33dd88; border-radius:10px; padding:1rem 1.1rem; margin:0.6rem 0 1rem 0; background:linear-gradient(180deg,#0d1a0d 0%, #0a1410 100%);'>
  <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:0.6rem;'>
    <span style='font-family:"IBM Plex Mono",monospace; font-size:0.7rem; color:#33dd88; letter-spacing:0.12em; font-weight:700;'>
      ✨ RECOMMENDED {label.upper()} CHANGE
    </span>
    <span style='font-family:"IBM Plex Mono",monospace; font-size:0.65rem; color:#6b6b8a;'>
      ideal: {ideal_min}–{ideal_max} {unit}
    </span>
  </div>

  <div style='background:#1a0d0d; border-left:3px solid #ff4455; border-radius:4px; padding:0.55rem 0.75rem; margin-bottom:0.5rem;'>
    <div style='font-family:"IBM Plex Mono",monospace; font-size:0.6rem; color:#ff4455; letter-spacing:0.1em; margin-bottom:0.3rem;'>
      CURRENT · <span style='color:{_len_color(cur_count)};'>{cur_count} {unit}</span>
    </div>
    <div style='font-size:0.95rem; color:#d8d8e8; line-height:1.55; word-wrap:break-word;'>{cur_safe}</div>
  </div>

  <div style='background:#0d1a0d; border-left:3px solid #33dd88; border-radius:4px; padding:0.65rem 0.85rem; max-height:{rec_max_height};'>
    <div style='font-family:"IBM Plex Mono",monospace; font-size:0.6rem; color:#33dd88; letter-spacing:0.1em; margin-bottom:0.3rem;'>
      NEW · <span style='color:{_len_color(new_count)};'>{new_count} {unit}</span>
    </div>
    <div style='font-size:{rec_font}; color:#e8e8f0; line-height:1.6; font-weight:500; word-wrap:break-word;'>{new_safe}</div>
    {f"<div style='font-size:0.72rem; color:#9b9bb8; margin-top:0.45rem;'>{_html.escape(note)}</div>" if note else ""}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    if recommended:
        # Popover (not expander) so render_recommendation_diff works
        # when called from inside another expander, e.g. the per-page
        # Meta and Intro cards in views/quick_wins.py.
        with st.popover(f"Copy raw {label.lower()}"):
            st.code(recommended, language="text")


def extract_content_summary(text_data: dict) -> tuple[list, list, list]:
    """
    Pull (keywords, internal_links, products) from a generated-content payload.

    Handles both shapes the AI can produce:
      - new generate_page_content: internal_links is [{anchor, url}, ...]
      - older generators: internal_links_added is ["url", "url", ...]
    Returns three flat lists. Always safe to call .len() on the results.
    """
    if not isinstance(text_data, dict):
        return [], [], []

    keywords = list(text_data.get("keywords_integrated") or [])

    raw_links = text_data.get("internal_links_added")
    if not raw_links:
        raw_links = text_data.get("internal_links") or []
    links: list = []
    for item in raw_links:
        if isinstance(item, dict):
            url = item.get("url") or item.get("href") or ""
            if url:
                links.append(url)
        elif isinstance(item, str) and item:
            links.append(item)

    products = list(text_data.get("products_featured") or [])
    return keywords, links, products
