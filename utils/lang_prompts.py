"""
Per-language vocabulary used by utils/cannibalization.py to detect search
intent (informational / listicle / transactional) in user queries.

That is the ONLY job of this module today. The previous design had
per-language banned-word lists and template-phrase dicts so AI prompts
could be localized word-by-word. That approach didn't scale beyond
Swedish + Danish — adding a new language meant hand-curating ~10 dicts
of AI-tell vocabulary in that language.

The new approach: the AI prompt scaffolding in utils/ai_generator.py and
utils/templates.py contains language-AGNOSTIC principles ("avoid AI-tell
openers in {language}", "use the natural {language} equivalent of …"),
and we trust Claude's multilingual knowledge to apply the principles
correctly in any target language. This scales to every language Claude
supports natively — no codebase change needed when going from mshop.dk
to (say) a Norwegian or German deployment.

ADDING A NEW LANGUAGE
---------------------
1. Add the language name to SUPPORTED_LANGUAGES if you want it to show
   in setup.py's dropdown.
2. Add ~10-15 intent-signal words to each of the three lists in
   INTENT_SIGNALS so cannibalization.py can detect search intent in
   that language. ~5 minutes of work; native-speaker review recommended
   but not required (the words are short common search terms).
3. Done. The AI prompt scaffolding picks it up automatically through
   the `language` parameter that is already plumbed through every
   generator function.
"""


# Languages exposed in setup.py's content-language dropdown. The AI
# prompts will accept any string here, but these are the ones the
# system was designed and tested for. Add more as needed.
SUPPORTED_LANGUAGES = [
    "English", "Swedish", "Danish", "Norwegian",
    "German", "French", "Spanish", "Italian",
    "Dutch", "Finnish",
]


# Search-intent signal words used by cannibalization.py. The three lists
# are concatenated across languages because real sites often have queries
# from multiple languages (e.g. a Swedish site gets some English queries
# too), and false positives on intent classification are cheap. Add a new
# language by adding ~10-15 words per intent type.
INTENT_SIGNALS = {
    "informational": [
        # English (universal, kept regardless of target language)
        "how to", "what is", "why ", "when ", "tutorial", "difference between",
        "guide", "explain",
        # Swedish
        "hur ", "vad ", "varför", "när ", "hur man",
        "guide till", "tips", "lär", "förklar", "skillnad mellan",
        # Danish
        "hvordan", "hvad ", "hvorfor", "hvornår", "hvordan man",
        "guide til", "forklar", "lær", "forskel mellem",
        # Norwegian
        "hva ", "hvorfor ", "når ", "hvordan ", "guide til",
        # German
        "wie ", "was ist", "warum ", "wann ", "anleitung",
        "ratgeber", "unterschied zwischen",
        # French
        "comment ", "qu'est-ce que", "pourquoi ", "quand ", "tutoriel",
        "différence entre",
        # Spanish
        "cómo ", "qué es", "por qué", "cuándo ", "guía", "diferencia entre",
        # Italian
        "come ", "cos'è", "perché ", "quando ", "guida", "differenza tra",
        # Dutch
        "hoe ", "wat is", "waarom ", "wanneer ", "gids", "verschil tussen",
        # Finnish
        "kuinka", "mikä on", "miksi", "milloin", "opas", "ero välillä",
    ],
    "listicle": [
        # English
        "best ", "best-", "top ", "top-", "vs ", " vs", "compare",
        "review", "rating",
        # Swedish
        "bäst", "bästa", "topplista", "jämför", "recension", "test",
        # Danish
        "bedst", "bedste", "topliste", "sammenlign", "anmeldelse",
        # Norwegian
        "beste", "topp", "sammenlign", "anmeldelse",
        # German
        "beste", "vergleich", "bewertung", "testbericht",
        # French
        "meilleur", "meilleurs", "comparer", "comparatif", "avis",
        # Spanish
        "mejor", "mejores", "comparar", "comparativa", "reseña", "opinión",
        # Italian
        "migliore", "migliori", "confronto", "recensione",
        # Dutch
        "beste", "vergelijk", "vergelijking", "review", "beoordeling",
        # Finnish
        "paras", "parhaat", "vertaa", "vertailu", "arvostelu",
    ],
    "transactional": [
        # English
        "buy", "cheap", "sale", "discount", "price",
        # Swedish
        "köp", "billig", "rea", "rabatt", "pris",
        # Danish
        "køb", "kob", "billig", "udsalg", "rabat", "pris",
        # Norwegian
        "kjøp", "billig", "salg", "rabatt", "pris",
        # German
        "kaufen", "günstig", "rabatt", "preis", "angebot",
        # French
        "acheter", "pas cher", "soldes", "promo", "prix",
        # Spanish
        "comprar", "barato", "rebajas", "descuento", "precio", "oferta",
        # Italian
        "comprare", "economico", "saldi", "sconto", "prezzo", "offerta",
        # Dutch
        "kopen", "goedkoop", "uitverkoop", "korting", "prijs", "aanbieding",
        # Finnish
        "osta", "halpa", "alennus", "hinta", "tarjous",
    ],
}
