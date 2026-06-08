-- ============================================================
-- gsc-seo Postgres schema (TRIAL)
-- ============================================================
-- One shared Postgres instance, partitioned by site_code (se/dk/eu).
-- Every page is keyed by (site_code, url) where url is the CANONICAL
-- normalized URL (normalize_url: https, no www, no trailing slash) — the
-- same key the app already uses, so the www/non-www hash bug class is
-- gone for good.
--
-- Idempotent: safe to run repeatedly (CREATE TABLE IF NOT EXISTS).
-- JSONB columns hold the full original blob so nothing is lost while we
-- decide which fields to promote to real columns.
-- ============================================================

-- Reference list of shops (optional, handy for joins/reporting)
CREATE TABLE IF NOT EXISTS sites (
    site_code   TEXT PRIMARY KEY,          -- 'se' | 'dk' | 'eu' | 'de' ...
    domain      TEXT,                       -- e.g. 'mshop.eu'
    language    TEXT,                       -- 'Swedish' | 'Danish' | 'English'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The audited pages (replaces audit_results JSON). One row per page.
CREATE TABLE IF NOT EXISTS pages (
    site_code        TEXT NOT NULL,
    url              TEXT NOT NULL,          -- canonical normalized URL
    page_type        TEXT,                   -- category | product | info | blog | faq | unknown
    word_count       INTEGER,
    title            TEXT,
    meta_description TEXT,
    h1               TEXT,
    intro_text       TEXT,
    bottom_text      TEXT,
    body_text        TEXT,
    audit_json       JSONB,                  -- full original audit row (everything not promoted above)
    scraped_at       TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, url)
);
CREATE INDEX IF NOT EXISTS idx_pages_type ON pages (site_code, page_type);

-- AI content-quality verdicts (replaces _quality_<hash> keys)
CREATE TABLE IF NOT EXISTS page_quality (
    site_code   TEXT NOT NULL,
    url         TEXT NOT NULL,
    verdict     TEXT,                        -- REWRITE | IMPROVE | KEEP
    score       INTEGER,
    summary     TEXT,
    input_hash  TEXT,                         -- staleness check (matches quality_input_hash)
    data_json   JSONB,                         -- main_issues, specific_fixes, etc.
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, url)
);
CREATE INDEX IF NOT EXISTS idx_quality_verdict ON page_quality (site_code, verdict);

-- AI implementation plans (replaces _ai_plan_<hash> keys)
CREATE TABLE IF NOT EXISTS page_plans (
    site_code        TEXT NOT NULL,
    url              TEXT NOT NULL,
    meta_title       TEXT,
    meta_description TEXT,
    plan_json        JSONB,                   -- steps, link suggestions, etc.
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, url)
);

-- Generated editorial text (replaces _bottom_text_/_intro_text_ keys)
CREATE TABLE IF NOT EXISTS page_generated (
    site_code    TEXT NOT NULL,
    url          TEXT NOT NULL,
    bottom_html  TEXT,
    intro_html   TEXT,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pushed_at    TIMESTAMPTZ,                 -- set when pushed live to Mshop
    PRIMARY KEY (site_code, url)
);

-- Topic clusters (replaces topic_clusters JSON)
CREATE TABLE IF NOT EXISTS topic_clusters (
    site_code   TEXT NOT NULL,
    cluster_id  TEXT NOT NULL,
    topic       TEXT,
    data_json   JSONB,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, cluster_id)
);

-- Strategic cluster-health evaluations (replaces _cluster_health_<hash>)
CREATE TABLE IF NOT EXISTS cluster_health (
    site_code   TEXT NOT NULL,
    cluster_key TEXT NOT NULL,
    topic       TEXT,
    data_json   JSONB,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_code, cluster_key)
);
