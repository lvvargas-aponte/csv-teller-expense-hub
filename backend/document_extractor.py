"""Plain-text extraction for uploaded knowledge-base documents.

The Knowledge tab accepts PDF / TXT / MD uploads.  Extraction must:

* be pure-Python — no tesseract / poppler system deps;
* never raise on a malformed file (return ``("", {"error": ...})``);
* surface a coarse ``detected_type`` heuristic so the upload form can
  pre-fill category (1040 → tax_return, statement headers → statement,
  W-2 / paystub keywords → paystub, etc.); the user can correct.

OCR for scanned PDFs is deliberately out of scope — see plan deferred
section.  If a PDF returns near-zero text we flag it via
``metadata.detected_type = 'scanned_pdf'`` so the UI can show a hint.
"""
from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, Optional, Tuple

from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

# Reject absurdly large uploads early.  1 GB ceiling on the file body and
# 5000 PDF pages — both are intentionally generous so multi-year tax
# archives or full bank-statement bundles can be ingested in one shot.
# Practical note: embedding a 1 GB doc serially against a local Ollama
# model can take hours and produce hundreds of thousands of chunks.  The
# upload itself is memory-bound (``await file.read()`` materialises the
# whole body) — fine for single-user / local-only, would need streaming
# if this ever serves multiple concurrent uploads.
MAX_BYTES = 1024 * 1024 * 1024        # 1 GB
MAX_PDF_PAGES = 5000
# Below this, a PDF that "extracted cleanly" is almost certainly scanned
# imagery — pypdf returns an empty string per page with no error.
SCANNED_PDF_TEXT_THRESHOLD = 200      # chars across whole doc


class ExtractionError(Exception):
    """Raised when a document is unusable (too large, unsupported type,
    fatally corrupt).  Soft failures (low yield, parse warnings) are
    reported via the metadata dict instead."""


def extract(file_bytes: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
    """Return ``(text, metadata)`` for an uploaded file.

    ``metadata`` always contains ``detected_type`` (best-effort heuristic)
    and ``page_count`` (PDF only, else 0).  On a soft failure (empty PDF,
    encoding issues) the text is returned as-is and metadata records the
    issue under ``warning``.
    """
    if len(file_bytes) > MAX_BYTES:
        size_gb = len(file_bytes) / (1024 ** 3)
        cap_gb = MAX_BYTES / (1024 ** 3)
        raise ExtractionError(
            f"File exceeds {cap_gb:.1f} GB limit ({size_gb:.2f} GB)"
        )

    lower = filename.lower()
    if lower.endswith(".pdf"):
        text, meta = _extract_pdf(file_bytes)
    elif lower.endswith((".html", ".htm")):
        text, meta = extract_html(file_bytes)
    elif lower.endswith((".txt", ".md", ".markdown")):
        text, meta = _extract_text(file_bytes)
    else:
        raise ExtractionError(
            f"Unsupported file type: {filename!r} — accepted: .pdf, .html, .txt, .md"
        )

    meta["detected_type"] = _detect_type(text, lower, meta)
    return text, meta


def extract_by_content_type(
    file_bytes: bytes, content_type: str, hint_url: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """Dispatch based on HTTP Content-Type rather than filename.

    Used by the URL-import path where the server tells us the type.  Falls
    back to magic-byte sniffing for ``application/octet-stream`` and
    similar generic types so an IRS publication served without a proper
    MIME type still routes through pypdf.
    """
    ct = (content_type or "").lower()
    head = file_bytes[:4]

    if "pdf" in ct or head == b"%PDF":
        text, meta = _extract_pdf(file_bytes)
    elif "html" in ct or "xml" in ct or head[:1] == b"<":
        text, meta = extract_html(file_bytes)
    elif "text" in ct:
        text, meta = _extract_text(file_bytes)
    else:
        raise ExtractionError(
            f"Unsupported content type for URL import: {content_type!r}"
        )

    meta["detected_type"] = _detect_type(text, (hint_url or "").lower(), meta)
    return text, meta


def _extract_pdf(file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except PdfReadError as e:
        raise ExtractionError(f"PDF parse error: {e}") from e

    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise ExtractionError(
            f"PDF has {page_count} pages; max {MAX_PDF_PAGES}"
        )

    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as e:
            logger.warning(f"[extractor] page {i} extract failed: {e}")
            pages.append("")
    text = "\n\n".join(pages).strip()

    meta: Dict[str, Any] = {"page_count": page_count}
    if len(text) < SCANNED_PDF_TEXT_THRESHOLD:
        # Almost certainly a scan; OCR is deferred.  Caller still gets
        # whatever text we managed so it isn't a hard error.
        meta["warning"] = "low_text_yield"
    return text, meta


# Tags that never carry article content — strip wholesale before grabbing text.
_BOILERPLATE_TAGS = (
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "form", "iframe", "svg",
)


def extract_html(file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """HTML → main-body text.

    Strategy:
    1. Strip boilerplate tags wholesale.
    2. Prefer ``<main>`` / ``<article>`` if present; fall back to ``<body>``.
    3. ``get_text("\\n", strip=True)`` collapses whitespace and joins blocks
       with newlines so the chunker can find paragraph boundaries.

    For trafilatura-grade noise removal we'd swap this implementation; the
    seed-list pages (IRS / Bogleheads / CFPB) are clean enough that this
    20-line approach yields readable, citation-friendly chunks.
    """
    # Decode permissively — utf-8 first, latin-1 fallback for old pages.
    html: str
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            html = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ExtractionError("Could not decode HTML as utf-8 or latin-1")

    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    for tag in soup(_BOILERPLATE_TAGS):
        tag.decompose()

    # WordPress / MediaWiki layouts often wrap content in <main> or <article>.
    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = root.get_text("\n", strip=True)

    # Collapse 3+ blank lines to a single blank line so chunker paragraph
    # splits stay reasonable.
    text = re.sub(r"\n{3,}", "\n\n", text)

    meta: Dict[str, Any] = {"page_count": 0}
    if title:
        meta["html_title"] = title
    if len(text) < 200:
        meta["warning"] = "low_text_yield"
    return text, meta


def _extract_text(file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    # Try utf-8 first, then latin-1 as a permissive fallback so old bank
    # statement TXT exports don't blow up on \xa0 / smart quotes.
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return file_bytes.decode(encoding), {"page_count": 0}
        except UnicodeDecodeError:
            continue
    raise ExtractionError("Could not decode file as utf-8 or latin-1")


# ---------------------------------------------------------------------------
# Detection heuristics — coarse on purpose; the upload form lets the user
# correct the category before submit.  Patterns are matched against the
# first ~4 KB so a 200-page IRS publication doesn't cost a regex sweep
# for every keyword.
# ---------------------------------------------------------------------------

_SAMPLE_HEAD_BYTES = 4_000

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("tax_return",  re.compile(r"\bForm\s+1040\b|U\.S\.\s+Individual\s+Income\s+Tax\s+Return", re.I)),
    ("tax_return",  re.compile(r"\bW-?2\b\s*Wage\s+and\s+Tax\s+Statement", re.I)),
    ("tax_return",  re.compile(r"\b1099-(MISC|NEC|INT|DIV|R|B)\b", re.I)),
    ("tax",         re.compile(r"\bInternal\s+Revenue\s+Service\b|\bIRS\s+Publication\b", re.I)),
    ("paystub",     re.compile(r"\bPay\s+(Stub|Statement)\b|\bEarnings\s+Statement\b", re.I)),
    ("paystub",     re.compile(r"\bGross\s+Pay\b.{0,200}\bNet\s+Pay\b", re.I | re.S)),
    ("statement",   re.compile(r"\bAccount\s+Statement\b|\bStatement\s+Period\b", re.I)),
    ("statement",   re.compile(r"\bPrevious\s+Balance\b.{0,200}\bNew\s+Balance\b", re.I | re.S)),
    ("loan",        re.compile(r"\bAmortization\s+Schedule\b|\bMortgage\s+Statement\b", re.I)),
    ("loan",        re.compile(r"\bLoan\s+Number\b.{0,200}\bPrincipal\s+Balance\b", re.I | re.S)),
    ("investing",   re.compile(r"\b401\(?k\)?\b|\bRoth\s+IRA\b|\bTraditional\s+IRA\b|\bbrokerage\b", re.I)),
    ("credit",      re.compile(r"\bAPR\b|\bcredit\s+utilization\b|\bbalance\s+transfer\b", re.I)),
]


def _detect_type(text: str, filename_lower: str, meta: Dict[str, Any]) -> str:
    """Return one of the category strings the UI knows about, or 'unknown'.

    Filename hints win when text yield was low (scanned PDFs).
    """
    head = text[:_SAMPLE_HEAD_BYTES]
    if head:
        for label, pattern in _PATTERNS:
            if pattern.search(head):
                return label

    if "1040" in filename_lower:
        return "tax_return"
    if "w2" in filename_lower or "w-2" in filename_lower:
        return "tax_return"
    if "paystub" in filename_lower or "pay-stub" in filename_lower:
        return "paystub"
    if "statement" in filename_lower:
        return "statement"
    if "mortgage" in filename_lower or "loan" in filename_lower:
        return "loan"

    if meta.get("warning") == "low_text_yield":
        return "scanned_pdf"
    return "unknown"
