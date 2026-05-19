"""
Per-language vocabulary for AI prompts and HTML templates.

Used by:
  - utils/ai_generator.py  — language-specific banned words, AI-tell openers,
    transition words, operational-fact GOOD/BAD examples, opinion phrasing
  - utils/templates.py     — customer-facing HTML phrases (FAQ headers,
    buying-guide prefixes, expert-recommendation patterns, etc.)

DESIGN
------
Each lookup function takes an explicit `language` argument (the same value
that is already plumbed through every generator function) and returns the
right vocabulary. No session_state access — keeps generators deterministic
and easy to test.

ADDING A NEW LANGUAGE
---------------------
Add the language name (matching the values in setup.py's `lang_options`,
e.g. "Norwegian", "German") as a key in every dict below. Missing keys
fall back to Swedish defaults so partial coverage is safe.
"""

DEFAULT_LANG = "Swedish"


def _pick(d: dict, language: str):
    """Return d[language] or d[DEFAULT_LANG]. Used by every accessor below."""
    return d.get(language) or d.get(DEFAULT_LANG)


# ── Customer-facing HTML template phrases ───────────────────────────
# These end up verbatim in the generated HTML on the live site, so they
# MUST match the deployment language.

_TEMPLATE_PHRASES = {
    "Swedish": {
        "faq_header": "Vanliga frågor",
        "faq_about_header": "Vanliga frågor om",
        "buying_guide_a": "Hur väljer man",
        "buying_guide_b": "Guide till",
        "expert_rec_pattern": "Välj [product type] om du [benefit]",
        "first_hand_a": "Vi har testat...",
        "first_hand_b": "Vår erfarenhet visar...",
        "experience_phrase_a": "vår erfarenhet visar",
        "experience_phrase_b": "vi har hjälpt tusentals kunder",
        "generic_claim_bad": "vibratorer är bra",
        "specific_claim_good": "en G-punktsvibrator med böjd topp ger mer riktad stimulering",
        "fear_normalizer_a": "det är helt normalt att...",
        "fear_normalizer_b": "många män upplever att...",
        "social_proof_a": "vår mest populära",
        "social_proof_b": "tusentals nöjda kunder",
        "simple_word_a": "använda",
        "complex_word_a": "implementera",
        "simple_word_b": "välja",
        "complex_word_b": "selektera",
        "bad_anchor_a": "klicka här",
        "bad_anchor_b": "läs mer",
        "compound_word_note": "Swedish/Danish compounds",
        "informal_address": "du/dig",
    },
    "Danish": {
        "faq_header": "Ofte stillede spørgsmål",
        "faq_about_header": "Ofte stillede spørgsmål om",
        "buying_guide_a": "Hvordan vælger man",
        "buying_guide_b": "Guide til",
        "expert_rec_pattern": "Vælg [product type] hvis du [benefit]",
        "first_hand_a": "Vi har testet...",
        "first_hand_b": "Vores erfaring viser...",
        "experience_phrase_a": "vores erfaring viser",
        "experience_phrase_b": "vi har hjulpet tusinder af kunder",
        "generic_claim_bad": "vibratorer er gode",
        "specific_claim_good": "en G-punkt vibrator med bøjet top giver mere målrettet stimulation",
        "fear_normalizer_a": "det er helt normalt at...",
        "fear_normalizer_b": "mange mænd oplever at...",
        "social_proof_a": "vores mest populære",
        "social_proof_b": "tusinder af tilfredse kunder",
        "simple_word_a": "bruge",
        "complex_word_a": "implementere",
        "simple_word_b": "vælge",
        "complex_word_b": "selektere",
        "bad_anchor_a": "klik her",
        "bad_anchor_b": "læs mere",
        "compound_word_note": "Danish/Swedish compounds",
        "informal_address": "du/dig",
    },
}


def template_phrase(key: str, language: str = DEFAULT_LANG) -> str:
    """Look up a customer-facing template phrase."""
    return _pick(_TEMPLATE_PHRASES, language).get(key, "")


# ── AI-tell banned openers / closers (target-language specific) ─────
# Phrases the AI loves to start/end paragraphs with in this language.
# Universal-English AI tells (delve, leverage, etc.) live in the
# scaffolding prompt itself.

_BANNED_OPENERS = {
    "Swedish": [
        '"Sammanfattningsvis" / "Avslutningsvis" / "I slutändan"',
        '"Det är viktigt att notera/komma ihåg"',
        '"Oavsett om du ... eller ..."',
        '"Denna guide" / "I denna artikel"',
        '"Utforska vår/vårt" / "Upptäck" as opening word',
        '"Perfekt för dig som..."',
        '"I dagens..." / "I dagens snabba..."',
        '"Faktum är att" as a sentence opener',
        '"Välkommen till"',
        'META-NARRATION openers: "Låt mig förklara", "Här är vad du behöver veta"',
        '"Tänk dig att..." as opener',
    ],
    "Danish": [
        '"Sammenfattende" / "Afsluttende" / "I sidste ende"',
        '"Det er vigtigt at bemærke/huske"',
        '"Uanset om du ... eller ..."',
        '"Denne guide" / "I denne artikel"',
        '"Udforsk vores" / "Opdag" as opening word',
        '"Perfekt for dig som..."',
        '"I dag..." / "I nutidens hurtige..."',
        '"Faktum er at" as a sentence opener',
        '"Velkommen til"',
        'META-NARRATION openers: "Lad mig forklare", "Her er hvad du behøver at vide"',
        '"Forestil dig at..." as opener',
    ],
}


def banned_openers_block(language: str = DEFAULT_LANG) -> str:
    """Return formatted bullet list for the banned-openers prompt section."""
    items = _pick(_BANNED_OPENERS, language)
    return "\n".join(f"- {item}" for item in items)


# ── Banned language-specific AI-tell vocabulary ─────────────────────

_AI_TELL_WORDS = {
    "Swedish": (
        '"skräddarsydd" (figurative), "genomsyrar", '
        '"i sann anda", "i en värld där", "när det kommer till", '
        '"på riktigt", "verkligen", "definitivt" used as filler intensifiers.'
    ),
    "Danish": (
        '"skræddersyet" (figurative), "gennemsyrer", '
        '"i sand ånd", "i en verden hvor", "når det kommer til", '
        '"for alvor", "virkelig", "definitivt" used as filler intensifiers.'
    ),
}


def ai_tell_words(language: str = DEFAULT_LANG) -> str:
    return _pick(_AI_TELL_WORDS, language)


# ── Overused transition / adverb-led openers per language ───────────

_TRANSITION_WORDS = {
    "Swedish": '"Dessutom,", "Dock,", "Emellertid,", "Vidare,", "Likaså,", "Å andra sidan,"',
    "Danish":  '"Derudover,", "Dog,", "Imidlertid,", "Endvidere,", "Ligeledes,", "På den anden side,"',
}


def transition_words(language: str = DEFAULT_LANG) -> str:
    return _pick(_TRANSITION_WORDS, language)


_ADVERB_OPENERS = {
    "Swedish": '"Viktigt,", "Notera att", "Intressant nog,"',
    "Danish":  '"Vigtigt,", "Bemærk at", "Interessant nok,"',
}


def adverb_openers(language: str = DEFAULT_LANG) -> str:
    return _pick(_ADVERB_OPENERS, language)


# ── Operational-fact GOOD/BAD examples ──────────────────────────────
# Used in ANTI_HALLUCINATION_RULES to teach the AI which kinds of facts
# may NOT be invented (specific sender names, return windows, delivery
# times). GOOD = generic statement that is always safe. BAD = specific
# fact that may only be used when explicitly given in site context.

_OPERATIONAL_FACT_EXAMPLES = {
    "Swedish": {
        "good_shipping": "diskret leverans i anonyma kartonger",
        "bad_sender":    "Avsändaren står som 'Mshop'",
        "good_speed":    "snabb leverans",
        "bad_speed":     "leverans inom 24 timmar",
        "good_returns":  "öppet köp enligt svensk konsumentlag",
        "bad_returns":   "30 dagars öppet köp",
    },
    "Danish": {
        "good_shipping": "diskret levering i anonyme kasser",
        "bad_sender":    "Afsenderen står som 'Mshop'",
        "good_speed":    "hurtig levering",
        "bad_speed":     "levering inden for 24 timer",
        "good_returns":  "fortrydelsesret efter dansk forbrugerlovgivning",
        "bad_returns":   "30 dages fortrydelsesret",
    },
}


def operational_fact_examples_block(language: str = DEFAULT_LANG) -> str:
    """Return the GOOD/BAD operational-fact example block for the prompt."""
    ex = _pick(_OPERATIONAL_FACT_EXAMPLES, language)
    return (
        f"  GOOD: \"{ex['good_shipping']}\"\n"
        f"  BAD:  \"{ex['bad_sender']}\" (only OK if explicitly given)\n"
        f"  GOOD: \"{ex['good_speed']}\"\n"
        f"  BAD:  \"{ex['bad_speed']}\" (only OK if explicitly given)\n"
        f"  GOOD: \"{ex['good_returns']}\"\n"
        f"  BAD:  \"{ex['bad_returns']}\" (only OK if explicitly given)"
    )


# ── "Real opinion" example phrases per language ─────────────────────
# Shown to the AI as examples of how a human writer commits to a position
# instead of hedging. Must read natural in target language or they leak.

_OPINION_PHRASES = {
    "Swedish": (
        '"Vi gillar X för att …" / "Ärligt talat är Y bättre" / '
        '"Honestly, Z is overrated" / "We don\'t recommend …" / '
        '"Hoppa över X om du letar efter Y" / '
        '"Det här är inte värt pengarna om..."'
    ),
    "Danish": (
        '"Vi kan godt lide X fordi …" / "Ærligt talt er Y bedre" / '
        '"Honestly, Z is overrated" / "We don\'t recommend …" / '
        '"Spring X over hvis du leder efter Y" / '
        '"Det er ikke pengene værd hvis..."'
    ),
}


def opinion_phrases(language: str = DEFAULT_LANG) -> str:
    return _pick(_OPINION_PHRASES, language)


# ── Balanced-clause & numbered-list-prose AI-tell examples ──────────

_BALANCED_CLAUSE_EXAMPLE = {
    "Swedish": '"Det är både elegant och funktionellt"',
    "Danish":  '"Det er både elegant og funktionelt"',
}


def balanced_clause_example(language: str = DEFAULT_LANG) -> str:
    return _pick(_BALANCED_CLAUSE_EXAMPLE, language)


_NUMBERED_LIST_PROSE_EXAMPLE = {
    "Swedish": '"Förstens, ..., Andra, ..."',
    "Danish":  '"For det første, ..., For det andet, ..."',
}


def numbered_list_prose_example(language: str = DEFAULT_LANG) -> str:
    return _pick(_NUMBERED_LIST_PROSE_EXAMPLE, language)


# ── Search-intent signal words (used by cannibalization.py) ─────────
# These appear in user queries and indicate informational / listicle /
# transactional intent. Used to bias the cannibalization resolver toward
# the right page type when multiple pages compete for the same query.

INTENT_SIGNALS = {
    "informational": [
        # English (universal — keep regardless of target language)
        "how to", "what is", "why ", "when ", "tutorial", "difference between",
        # Swedish
        "hur ", "vad ", "varför", "när ", "hur man",
        "guide", "guide till", "tips", "lär", "förklar", "skillnad mellan",
        # Danish
        "hvordan", "hvad ", "hvorfor", "hvornår", "hvordan man",
        "guide til", "forklar", "lær", "forskel mellem",
    ],
    "listicle": [
        # English
        "best ", "best-", "top ", "top-", "vs ", " vs", "compare", "review", "rating",
        # Swedish
        "bäst", "bästa", "topplista", "jämför", "recension", "test",
        # Danish
        "bedst", "bedste", "topliste", "sammenlign", "anmeldelse",
    ],
    "transactional": [
        # English
        "buy", "cheap", "sale", "discount", "price",
        # Swedish
        "köp", "billig", "rea", "rabatt", "pris",
        # Danish
        "køb", "kob", "billig", "udsalg", "rabat", "pris",
    ],
}
