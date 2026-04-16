"""
Single source of truth for URL parsing/manipulation across the codebase.

If you find yourself writing urlparse(url).path... or url.split("/")...
in another file — STOP and use a helper from here instead.

Conventions:
- All helpers accept str or any object with __str__ method.
- Paths are returned WITHOUT trailing slash (except for "/" root).
- Comparisons are case-INsensitive on path/host but preserve original
  casing in returned values.
"""

from urllib.parse import urlparse, urlunparse


# ─────────────────────────────────────────────────────────────────────
# PATH EXTRACTION
# ─────────────────────────────────────────────────────────────────────

def url_path(url) -> str:
    """
    Extract the path component from a URL, with trailing slash stripped.
    Returns "/" for root paths.

    >>> url_path("https://example.com/foo/bar/")
    '/foo/bar'
    >>> url_path("https://example.com/")
    '/'
    """
    if not url:
        return "/"
    path = urlparse(str(url)).path.rstrip("/")
    return path or "/"


def url_segments(url) -> list:
    """
    Return the URL path as a list of non-empty segments.

    >>> url_segments("https://example.com/foo/bar/baz")
    ['foo', 'bar', 'baz']
    """
    return [s for s in url_path(url).split("/") if s]


def url_parent_path(url) -> str:
    """
    Return the parent directory of a URL's path.

    >>> url_parent_path("https://example.com/foo/bar/baz")
    '/foo/bar'
    >>> url_parent_path("https://example.com/foo")
    ''
    """
    p = url_path(url)
    if "/" not in p[1:]:
        return ""
    return "/".join(p.split("/")[:-1])


def url_last_segment(url) -> str:
    """
    Return the last path segment (the slug).

    >>> url_last_segment("https://example.com/foo/bar/baz")
    'baz'
    """
    segs = url_segments(url)
    return segs[-1] if segs else ""


# ─────────────────────────────────────────────────────────────────────
# PATH RELATIONSHIPS
# ─────────────────────────────────────────────────────────────────────

def path_is_descendant(child_url, parent_url) -> bool:
    """
    Return True if child_url's path is strictly under parent_url's path.

    >>> path_is_descendant("https://example.com/a/b/c", "https://example.com/a")
    True
    >>> path_is_descendant("https://example.com/a", "https://example.com/a")
    False  # same path is not a descendant
    """
    cp = url_path(child_url)
    pp = url_path(parent_url)
    if not pp or pp == "/":
        return cp != "/"
    return cp != pp and cp.startswith(pp + "/")


def paths_are_siblings(url_a, url_b) -> bool:
    """
    Return True if both URLs share the same parent directory and aren't
    the same URL.

    >>> paths_are_siblings("https://example.com/a/b", "https://example.com/a/c")
    True
    """
    pa = url_parent_path(url_a)
    pb = url_parent_path(url_b)
    return bool(pa) and pa == pb and url_path(url_a) != url_path(url_b)


def shared_top_level(url_a, url_b) -> bool:
    """
    Return True if both URLs share the same top-level segment.

    >>> shared_top_level("https://example.com/blog/foo", "https://example.com/blog/bar")
    True
    """
    sa = url_segments(url_a)
    sb = url_segments(url_b)
    if not sa or not sb:
        return False
    return sa[0] == sb[0]


# ─────────────────────────────────────────────────────────────────────
# SALE / SPECIAL PAGE DETECTION
# ─────────────────────────────────────────────────────────────────────

def is_sale_url(url) -> bool:
    """
    Return True if URL matches a configured sale/discount pattern
    (uses utils.site_patterns.get_sale_patterns).
    """
    if not url:
        return False
    try:
        from utils.site_patterns import get_sale_patterns
        patterns = get_sale_patterns()
    except Exception:
        patterns = ["/rea/", "/sale/", "/udsalg/", "billig"]
    u = str(url).lower()
    return any(p in u for p in patterns)


# ─────────────────────────────────────────────────────────────────────
# DISPLAY HELPERS — short / clean for UI
# ─────────────────────────────────────────────────────────────────────

def shorten_url_path(url, max_len: int = 55) -> str:
    """
    Return URL path with optional truncation. For UI display only —
    keeps the path part without protocol/domain.

    >>> shorten_url_path("https://example.com/foo/bar/baz", 10)
    '/foo/bar/b...'
    """
    p = url_path(url)
    if len(p) > max_len:
        return p[:max_len] + "..."
    return p


# ─────────────────────────────────────────────────────────────────────
# Re-export the existing canonical helpers from ui_helpers for
# convenience — so callers can `from utils.url_helpers import *`
# and get everything URL-related.
# ─────────────────────────────────────────────────────────────────────

from utils.ui_helpers import normalize_url, shorten_url, stable_hash  # noqa: E402,F401
