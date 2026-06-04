"""Shared text-cleaning helpers.

Single source of truth for "AI tell" removal, called at BOTH the text
generation source AND the live-push API boundary (mshop_admin_api,
footer_text_api). Enforcing it at the API boundary means NO code path —
inline preview, Fix ALL, Quick Wins, admin push UI, or any future
caller — can send an em-dash to the live shop, regardless of which
generator produced the text.

Keep this module dependency-light (stdlib only) so the API clients can
import it without pulling in the heavy ai_generator module.
"""

import re

# Em/en-dash between two digits is a legitimate numeric range (1–2, 10–15);
# the natural HUMAN form is a plain hyphen, NOT a comma ("1, 2 day" is wrong).
_DASH_RANGE_RE = re.compile(r"(?<=\d)\s*[—–]\s*(?=\d)")
_SPACE_BEFORE_COMMA_RE = re.compile(r"\s+,")
_SPACE_AFTER_COMMA_RE = re.compile(r",\s+")


def strip_ai_dashes(text: str) -> str:
    """Remove em-dashes and en-dashes — a top AI tell — so the text reads
    100% human-written.

    - digit–digit numeric ranges become a plain hyphen ('1–2' → '1-2')
    - every other em/en-dash becomes a comma, with surrounding whitespace
      tidied so the result reads natural

    Idempotent and safe on already-clean text. Returns '' for falsy input.
    """
    if not text or not isinstance(text, str):
        return text or ""
    text = _DASH_RANGE_RE.sub("-", text)
    if "—" not in text and "–" not in text:
        return text
    text = text.replace("—", ",").replace("–", ",")
    text = _SPACE_BEFORE_COMMA_RE.sub(",", text)
    text = _SPACE_AFTER_COMMA_RE.sub(", ", text)
    return text
