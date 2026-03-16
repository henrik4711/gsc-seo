"""
AI content generation: meta titles, descriptions, and landing page text
Uses Claude claude-sonnet-4-20250514 via Anthropic API
"""

import os
import anthropic
import streamlit as st
from typing import Optional


def get_client(api_key: str = "") -> anthropic.Anthropic:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("No Anthropic API key provided. Set ANTHROPIC_API_KEY env var or enter key in Setup.")
    return anthropic.Anthropic(api_key=key)


def generate_meta_suggestions(
    client: anthropic.Anthropic,
    page_data: dict,
    target_keywords: list,
    site_context: str = "",
    language: str = "Swedish",
    n_variants: int = 3,
) -> dict:
    """
    Generate optimized meta title and description variants
    """
    current_title = page_data.get("title") or "Ingen title"
    current_desc = page_data.get("meta_description") or "Ingen description"
    url = page_data.get("url", "")
    h1 = page_data.get("h1") or ""
    h2s = page_data.get("h2s", [])[:5]
    
    prompt = f"""Du er en senior SEO-specialist og konverteringsoptimerings-ekspert for en skandinavisk e-commerce webshop der sælger voksenprodukter.

## NUVÆRENDE SITUATION
URL: {url}
Nuværende title: {current_title} ({len(current_title)} tegn)
Nuværende meta description: {current_desc} ({len(current_desc)} tegn)
H1: {h1}
H2'er: {', '.join(h2s) if h2s else 'Ingen'}
Målgruppe-keywords fra GSC: {', '.join(target_keywords)}
Site-kontekst: {site_context}

## OPGAVE
Generer {n_variants} varianter af forbedrede meta title + description.

### KRAV til TITLE (kritisk):
- 50-60 tegn (ALDRIG over 65)
- Primær keyword tidligst muligt (helst ord 1-3)
- Ét konkret benefit eller USP
- Undgå: "Køb", "Bestil" som første ord (Google kan lave det)
- Sproget: {language}

### KRAV til META DESCRIPTION (kritisk):
- 140-160 tegn (ALDRIG over 165)
- Inkluder primær keyword naturligt
- Stærk CTA: fri frakt, hurtig levering, diskret forsendelse, stort udvalg
- Skab nysgerrighed/FOMO eller løs et problem
- Inkluder specifikke detaljer der differentierer
- Sproget: {language}

## OUTPUT FORMAT (kun JSON, ingen markdown-wrapping):
{{
  "analysis": "Kort analyse af hvad der er galt med nuværende meta (2-3 sætninger)",
  "variants": [
    {{
      "title": "...",
      "title_chars": 0,
      "description": "...",
      "description_chars": 0,
      "strategy": "Hvad er strategien bag denne variant (1 sætning)"
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    import json
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    raw = raw.replace("```json", "").replace("```", "").strip()
    
    result = json.loads(raw)
    # Fill in char counts if model didn't
    for v in result.get("variants", []):
        v["title_chars"] = len(v.get("title", ""))
        v["description_chars"] = len(v.get("description", ""))
    
    return result


def generate_content_audit(
    client: anthropic.Anthropic,
    page_data: dict,
    target_keywords: list,
    gsc_queries: list,
) -> dict:
    """
    Analyse existing page content for keyword gaps and SEO opportunities
    """
    body = page_data.get("body_text", "")[:4000]
    url = page_data.get("url", "")
    
    prompt = f"""Du er en SEO content-analytiker. Analysér denne landingpage og dens keyword-dækning.

URL: {url}
GSC-keywords der driver trafik: {', '.join(gsc_queries[:20])}
Target focus keywords: {', '.join(target_keywords)}

NUVÆRENDE INDHOLD (uddrag):
{body}

## OPGAVE: Lav en keyword gap-analyse

Returner KUN JSON (ingen markdown):
{{
  "keyword_coverage": [
    {{"keyword": "...", "present": true/false, "context": "Hvor/hvordan det bruges eller mangler"}}
  ],
  "missing_topics": ["Emner der burde dækkes men ikke gør"],
  "thin_content": true/false,
  "content_issues": ["Liste af konkrete indholdsproblemer"],
  "opportunities": ["Konkrete muligheder for at forbedre SEO-indhold"],
  "recommended_structure": {{
    "suggested_h1": "...",
    "suggested_sections": ["H2 sektion 1", "H2 sektion 2", "..."]
  }},
  "overall_score": 0-100,
  "summary": "2-3 sætninger om sidens SEO-indhold status"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    import json
    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def generate_landing_page_text(
    client: anthropic.Anthropic,
    page_data: dict,
    target_keywords: list,
    gsc_queries: list,
    site_context: str = "",
    language: str = "Swedish",
    tone: str = "Professionel men tilgængelig",
) -> dict:
    """
    Generate a full optimized landing page text
    """
    url = page_data.get("url", "")
    h2s = page_data.get("h2s", [])
    existing = page_data.get("body_text", "")[:2000]
    
    prompt = f"""Du er en senior SEO-copywriter specialiseret i e-commerce og voksenprodukter (skandinavisk marked).

## KONTEKST
URL: {url}
Site: {site_context}
Primære keywords: {', '.join(target_keywords[:5])}
Alle GSC-søgeforespørgsler vi rangerer for: {', '.join(gsc_queries[:25])}
Nuværende H2-struktur: {', '.join(h2s) if h2s else 'Ingen'}
Eksisterende indhold (eksempel): {existing[:1000]}
Tone of voice: {tone}
Sprog: {language}

## OPGAVE
Skriv optimeret landingpage-indhold der:
1. Er naturlig og konverterende - IKKE SEO-spam
2. Inkluderer primære keywords naturligt (density ca. 1-2%)
3. Dækker alle relevante LSI-keywords fra GSC-data
4. Har klar struktur med H2/H3
5. Inkluderer sociale beviser, USPs og CTA
6. Er passende for voksenprodukter (diskret, respektfuld tone)

Returner KUN JSON:
{{
  "intro_paragraph": "Kategori-intro tekst (80-120 ord)",
  "sections": [
    {{
      "h2": "Sektions-overskrift",
      "content": "Sektions-indhold (60-100 ord)",
      "h3_subsections": [
        {{"h3": "Evt. underoverskrift", "content": "..."}}
      ]
    }}
  ],
  "buying_guide_snippet": "Kort guide-afsnit der hjælper kunden vælge (80-100 ord)",
  "faq_items": [
    {{"question": "...", "answer": "..."}}
  ],
  "seo_notes": "Noter til redaktøren om keyword-placement (2-3 bullet points)"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    import json
    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def generate_action_plan(
    client: anthropic.Anthropic,
    audit_results: list,
    site_url: str,
) -> dict:
    """
    Generate prioritized action plan from all audit results
    """
    # Build summary of issues
    summary_data = []
    for r in audit_results[:20]:  # Cap for token limit
        summary_data.append({
            "url": r.get("url"),
            "lost_clicks": r.get("lost_clicks_estimate", 0),
            "position": r.get("position"),
            "ctr_gap": r.get("ctr_gap_pct"),
            "meta_score": r.get("meta_score", 100),
            "content_score": r.get("content_score", 100),
            "top_keywords": r.get("target_keywords", [])[:3],
            "issues": r.get("issues", [])[:3],
        })
    
    import json
    prompt = f"""Du er SEO-strateg for {site_url}. Lav en prioriteret handlingsplan baseret på disse audit-resultater:

{json.dumps(summary_data, ensure_ascii=False, indent=2)}

Returner KUN JSON:
{{
  "executive_summary": "3-4 sætninger om den overordnede SEO-situation og potentiale",
  "estimated_monthly_clicks_gain": 0,
  "priority_actions": [
    {{
      "priority": 1,
      "url": "...",
      "action": "Hvad skal gøres",
      "reason": "Hvorfor dette er vigtigt",
      "estimated_impact": "Estimeret klik-gevinst",
      "effort": "Lav/Medium/Høj",
      "type": "meta|content|technical"
    }}
  ],
  "quick_wins": ["Actions der kan gøres på under 30 min"],
  "strategic_recommendations": ["Større strategiske ændringer (1-3 mdr)"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)
