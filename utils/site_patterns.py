"""
Site-specific URL pattern configuration.

All hardcoded Swedish/English terms used by classifiers live here and can be
overridden per-site via Setup UI.

Defaults are LANGUAGE-AGNOSTIC and UNIVERSAL — they only contain patterns
that work on most e-commerce sites regardless of language.

To add site-specific patterns (like Swedish /sexleksaker/ or Danish /legetoj/),
users configure them in Setup → Site Patterns, which stores them in
st.session_state['site_patterns'] as a dict.
"""

import streamlit as st


# ── Universal defaults (work across languages and domains) ────────

DEFAULT_CATEGORY_PATTERNS = [
    "/kategori/", "/category/", "/categories/", "/collections/",
    "/c/", "/shop/", "/katalog/", "/catalog/",
]

DEFAULT_PRODUCT_PATTERNS = [
    "/products/", "/product/", "/produkt/", "/p/", "/item/",
]

DEFAULT_BLOG_PATTERNS = [
    "/blog/", "/blogg/", "/artikel/", "/article/", "/articles/",
    "/guide/", "/guides/", "/tips/", "/magazine/", "/magazin/",
    "/news/", "/nyheter/", "/post/",
]

DEFAULT_FAQ_PATTERNS = [
    "/faq/", "/faqs/", "/frequently-asked",
]

# Universal corporate/info pages that exist on most sites regardless of language
DEFAULT_INFO_PATTERNS = [
    "/about", "/about-us", "/contact", "/privacy", "/terms",
    "/legal", "/cookie", "/cookies", "/gdpr", "/imprint",
    "/shipping", "/delivery", "/returns", "/refund",
    "/customer-service", "/help", "/support",
    "/career", "/careers", "/jobs",
    "/press", "/media",
    "/newsletter", "/unsubscribe",
    "/gift-card", "/wishlist", "/cart", "/checkout", "/account",
    "/login", "/register", "/sign-in", "/sign-up",
]

# Faceted/paginated Magento + WooCommerce patterns (universal)
DEFAULT_FACETED_QUERY_PARAMS = [
    "dir", "order", "limit", "mode", "p", "SID", "sort", "view",
]

# Empty by default — sites with flat URL structures configure their own
DEFAULT_FLAT_CATEGORY_KEYWORDS: list[str] = []
DEFAULT_LOCAL_PATTERNS: list[str] = []


def _get(key: str, default):
    """Read a site_patterns override from session_state, fall back to default."""
    try:
        cfg = st.session_state.get("site_patterns") or {}
        val = cfg.get(key)
        if val is None:
            return default
        if isinstance(default, list) and not isinstance(val, list):
            return default
        return val
    except Exception:
        return default


def get_category_patterns() -> list:
    return DEFAULT_CATEGORY_PATTERNS + _get("category_patterns_extra", [])


def get_product_patterns() -> list:
    return DEFAULT_PRODUCT_PATTERNS + _get("product_patterns_extra", [])


def get_blog_patterns() -> list:
    return DEFAULT_BLOG_PATTERNS + _get("blog_patterns_extra", [])


def get_faq_patterns() -> list:
    return DEFAULT_FAQ_PATTERNS + _get("faq_patterns_extra", [])


def get_info_patterns() -> list:
    return DEFAULT_INFO_PATTERNS + _get("info_patterns_extra", [])


def get_flat_category_keywords() -> list:
    """Top-level category terms for sites using flat URL structure.
    E.g. for mshop.se: ['sexleksaker', 'bondage', 'glidmedel']
    Empty by default."""
    return _get("flat_category_keywords", DEFAULT_FLAT_CATEGORY_KEYWORDS)


def get_local_patterns() -> list:
    """City/location path fragments for store-locator detection.
    E.g. for Swedish sites: ['/stockholm', '/goteborg', '/malmo']
    Empty by default."""
    return _get("local_patterns", DEFAULT_LOCAL_PATTERNS)


def get_faceted_query_params() -> list:
    return DEFAULT_FACETED_QUERY_PARAMS + _get("faceted_params_extra", [])


# Universal sale/discount path patterns — pages that serve a different purpose
# and should NEVER be 301-redirected to a main category
DEFAULT_SALE_PATTERNS = [
    "/rea/", "/rea-", "/sale/", "/sales/",
    "/outlet/", "/clearance/",
    "/kampanj/", "/campaign/",
    "/tilbud/", "/tilbod/",  # Danish/Norwegian
    "/angebot/", "/angebote/",  # German
    "/promo/", "/promotion/",
    "/rabat/", "/rabatt/",  # Danish/Swedish discount
    "/soldes/",  # French
]


def get_sale_patterns() -> list:
    return DEFAULT_SALE_PATTERNS + _get("sale_patterns_extra", [])


# ── Sample presets for common site types ─────────────────────────

PRESET_SWEDISH_ADULT_ECOMMERCE = {
    "category_patterns_extra": ["/sexleksaker/", "/bondage", "/apotek", "/sexiga-underklader", "/alla/"],
    "info_patterns_extra": [
        "/hjalp", "/kundservice", "/kontakt", "/jobb", "/karriar",
        "/om-oss", "/villkor", "/kopvillkor", "/integritet", "/personuppgift",
        "/leverans", "/frakt", "/retur", "/angerratt", "/betalning",
        "/presentkort", "/nyhetsbrev",
    ],
    "flat_category_keywords": [
        "sexleksaker", "vuxenleksaker", "leksaker", "bondage", "underklader",
        "glidmedel", "kondomer", "apotek",
    ],
    "local_patterns": [
        "/stockholm", "/goteborg", "/malmo", "/uppsala", "/vasteras",
        "/orebro", "/linkoping", "/helsingborg", "/jonkoping", "/norrkoping",
        "/butik", "/butiker", "/vara-butiker",
    ],
}

PRESET_DANISH_ECOMMERCE = {
    "info_patterns_extra": [
        "/hjaelp", "/kundeservice", "/kontakt", "/job", "/karriere",
        "/om-os", "/vilkaar", "/koebsvilkaar", "/handelsbetingelser",
        "/privatliv", "/persondata",
        "/levering", "/fragt", "/retur", "/fortrydelsesret", "/betaling",
        "/gavekort", "/nyhedsbrev",
    ],
    "local_patterns": [
        "/koebenhavn", "/copenhagen", "/aarhus", "/odense", "/aalborg",
        "/esbjerg", "/randers", "/kolding",
        "/butik", "/butikker", "/forretning",
    ],
}

PRESETS = {
    "swedish_adult_ecommerce": PRESET_SWEDISH_ADULT_ECOMMERCE,
    "danish_ecommerce": PRESET_DANISH_ECOMMERCE,
}
