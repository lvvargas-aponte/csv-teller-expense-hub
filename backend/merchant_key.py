"""Single source of truth for collapsing a description into a merchant key.

Three subsystems need the same key or they disagree about what one merchant
is: recurring/subscription detection (``analytics``), the commitments
rollup, and the user's merchant→category rules (``category_rules``). They
all call :func:`normalize`, and :func:`canonical` when the user-declared
``merchant_aliases`` folds should apply too.

The key is deliberately lossy — it exists so the same merchant collapses to
one bucket across months and banks, not to be shown to anyone.
"""
from __future__ import annotations

import logging
import re
from typing import Dict

logger = logging.getLogger(__name__)

# Strip transaction-noise tokens that vary between charges of the same merchant.
# Digits + ``#`` + ``*`` always go; the passes below tackle structured
# tails (WEB ID:, ACH/PMT tokens, state codes) and processor prefixes
# (SQ *, TST*, PP*) so the same merchant collapses to one key across months.
_NOISE_RE = re.compile(r"[\d#*]+")
_WHITESPACE_RE = re.compile(r"[\s\-_/]+")
# Mixed-alphanumeric "session id" tokens like ``F4KP2T``, ``6BVHGR`` that some
# merchants embed in every charge — strip so the same merchant doesn't fork
# into one merchant-key per charge. Gated to tokens 4–10 chars with at least
# one letter AND at least one digit so real words ("4G", "AT&T") survive.
_SESSION_ID_RE = re.compile(
    r"\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]{4,10}\b",
    re.IGNORECASE,
)
_PROCESSOR_PREFIX_RE = re.compile(
    r"^(sq\s*\*|tst\s*\*|pp\s*\*|paypal\s*\*|amzn\s+mktp\s+us\*?)\s*",
    re.IGNORECASE,
)
_ACH_TAIL_RE = re.compile(
    r"\b(web\s*id|ach|pmt|payment|epayment|xfer|pos|recur|aut(?:o|opay)?|mob|olb|mtgpmt|mortg)\b[:\s]*",
    re.IGNORECASE,
)
_STATE_CODE_TAIL_RE = re.compile(r"\s+[a-z]{2}\s*$", re.IGNORECASE)


def normalize(description: str) -> str:
    """Collapse description into a stable merchant key.

    Pipeline:
      1. Lowercase.
      2. Drop processor prefixes (``SQ *``, ``TST*``, ``AMZN MKTP US``).
      3. Strip ACH/wire tail tokens (``WEB ID:``, ``ACH``, ``PMT``…).
      4. Replace remaining digits / ``#`` / ``*`` with spaces.
      5. Drop a trailing 2-letter state code (``... Doral FL`` → ``... doral``).
      6. Collapse whitespace, trim to 40 chars.
    """
    if not description:
        return ""
    cleaned = description.lower()
    cleaned = _PROCESSOR_PREFIX_RE.sub("", cleaned)
    cleaned = _ACH_TAIL_RE.sub(" ", cleaned)
    # Strip mixed-alphanumeric session ids *before* the digit-only sweep so
    # ``F4KP2T`` doesn't survive as ``fkpt``.
    cleaned = _SESSION_ID_RE.sub(" ", cleaned)
    cleaned = _NOISE_RE.sub(" ", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    cleaned = _STATE_CODE_TAIL_RE.sub("", cleaned).strip()
    return cleaned[:40]


def aliases() -> Dict[str, str]:
    """``{alias_key: canonical_key}``, or empty when the table is unreachable.

    Detection must survive a DB hiccup — an unmerged merchant is a worse
    answer than no answer, but it is still an answer.
    """
    try:
        from db import merchant_aliases_repo
        return merchant_aliases_repo.list_aliases()
    except Exception:  # noqa: BLE001
        logger.warning("[merchant_key] could not read merchant aliases", exc_info=True)
        return {}


def canonical(description: str, alias_map: Dict[str, str] | None = None) -> str:
    """:func:`normalize` with the user's alias folds applied.

    ``alias_map`` can be passed in so a caller keying a whole batch reads
    the table once instead of once per row.
    """
    key = normalize(description)
    if not key:
        return ""
    if alias_map is None:
        alias_map = aliases()
    return alias_map.get(key, key)
