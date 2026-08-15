"""Business-logic helpers — pure functions, no HTTP calls, no FastAPI."""
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).parent.parent / ".env"

CSV_ENCODINGS = ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252')


# ---------------------------------------------------------------------------
# Token persistence helpers  (all .env I/O lives here)
# ---------------------------------------------------------------------------

def _env_add_simplefin_url(access_url: str) -> None:
    """Append an access URL to SIMPLEFIN_ACCESS_URLS in .env, creating the entry if absent."""
    try:
        env_text = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""
        if re.search(r"^SIMPLEFIN_ACCESS_URLS=", env_text, re.MULTILINE):
            match = re.search(r"^SIMPLEFIN_ACCESS_URLS=(.*)$", env_text, re.MULTILINE)
            existing = [u.strip() for u in (match.group(1) if match else "").split(",") if u.strip()]
            if access_url not in existing:
                existing.append(access_url)
            env_text = re.sub(
                r"^SIMPLEFIN_ACCESS_URLS=.*$",
                "SIMPLEFIN_ACCESS_URLS=" + ",".join(existing),
                env_text,
                flags=re.MULTILINE,
            )
        else:
            sep = "\n" if env_text and not env_text.endswith("\n") else ""
            env_text = env_text + sep + f"\nSIMPLEFIN_ACCESS_URLS={access_url}\n"
        _ENV_PATH.write_text(env_text, encoding="utf-8")
        logger.info("[SimpleFIN] .env updated — access URL added.")
    except OSError as e:
        logger.error(f"[SimpleFIN] Could not write to .env: {e}")


def _env_remove_simplefin_url(access_url: str) -> None:
    """Remove a specific access URL from SIMPLEFIN_ACCESS_URLS in .env."""
    try:
        if not _ENV_PATH.exists():
            return
        env_text = _ENV_PATH.read_text(encoding="utf-8")
        match = re.search(r"^SIMPLEFIN_ACCESS_URLS=(.*)$", env_text, re.MULTILINE)
        if match:
            remaining = [u.strip() for u in match.group(1).split(",") if u.strip() and u.strip() != access_url]
            env_text = re.sub(
                r"^SIMPLEFIN_ACCESS_URLS=.*$",
                "SIMPLEFIN_ACCESS_URLS=" + ",".join(remaining),
                env_text,
                flags=re.MULTILINE,
            )
            _ENV_PATH.write_text(env_text, encoding="utf-8")
            logger.info("[SimpleFIN] .env updated — access URL removed.")
    except OSError as e:
        logger.error(f"[SimpleFIN] Could not update .env while removing access URL: {e}")


# ---------------------------------------------------------------------------
# Date / month helpers
# ---------------------------------------------------------------------------

def _previous_month_range() -> Tuple[str, str]:
    """Return (from_date, to_date) strings for the previous calendar month."""
    today = date.today()
    last = date(today.year, today.month, 1) - timedelta(days=1)
    first = date(last.year, last.month, 1)
    return first.isoformat(), last.isoformat()


def _parse_month_key(date_str: str) -> Optional[str]:
    """Return 'YYYY-MM' from a MM/DD/YYYY or YYYY-MM-DD date string, or None."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _decode_csv_bytes(raw: bytes) -> str:
    """Try common encodings in order; latin-1 never raises so it is the safe fallback."""
    for encoding in CSV_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV file — unsupported encoding")
