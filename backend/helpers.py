"""Business-logic helpers — pure functions, no HTTP calls, no FastAPI."""
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import TELLER_ENVIRONMENT
from teller import _mask_token

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).parent.parent / ".env"
_LOG_PATH = Path(__file__).parent.parent / "teller-tokens.log"

CSV_ENCODINGS = ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252')


# ---------------------------------------------------------------------------
# Token persistence helpers  (all .env / log I/O lives here)
# ---------------------------------------------------------------------------

def _env_add_token(token: str) -> None:
    """Append an access token to TELLER_API_KEY in .env, creating the entry if absent."""
    try:
        env_text = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""
        if re.search(r"^TELLER_API_KEY=", env_text, re.MULTILINE):
            match = re.search(r"^TELLER_API_KEY=(.*)$", env_text, re.MULTILINE)
            existing = [t.strip() for t in (match.group(1) if match else "").split(",") if t.strip()]
            if token not in existing:
                existing.append(token)
            env_text = re.sub(
                r"^TELLER_API_KEY=.*$",
                "TELLER_API_KEY=" + ",".join(existing),
                env_text,
                flags=re.MULTILINE,
            )
        else:
            sep = "\n" if env_text and not env_text.endswith("\n") else ""
            env_text = env_text + sep + f"\nTELLER_API_KEY={token}\n"
        _ENV_PATH.write_text(env_text, encoding="utf-8")
        logger.info("[Teller] .env updated — token added.")
    except OSError as e:
        logger.error(f"[Teller] Could not write to .env: {e}")


def _env_remove_token(token: str) -> None:
    """Remove a specific access token from TELLER_API_KEY in .env."""
    try:
        if not _ENV_PATH.exists():
            return
        env_text = _ENV_PATH.read_text(encoding="utf-8")
        match = re.search(r"^TELLER_API_KEY=(.*)$", env_text, re.MULTILINE)
        if match:
            remaining = [t.strip() for t in match.group(1).split(",") if t.strip() and t.strip() != token]
            env_text = re.sub(
                r"^TELLER_API_KEY=.*$",
                "TELLER_API_KEY=" + ",".join(remaining),
                env_text,
                flags=re.MULTILINE,
            )
            _ENV_PATH.write_text(env_text, encoding="utf-8")
            logger.info("[Teller] .env updated — token removed.")
    except OSError as e:
        logger.error(f"[Teller] Could not update .env while removing token: {e}")


def _log_token_event(*, token: str, enrollment_id: str, institution: str, note: str = "") -> None:
    """Append an audit line to teller-tokens.log."""
    try:
        ts = datetime.now(timezone.utc).isoformat()
        parts = [
            ts,
            f"Env: {TELLER_ENVIRONMENT}",
            f"Institution: {institution}",
            f"Enrollment: {enrollment_id}",
            f"Token: {_mask_token(token)}",
        ]
        if note:
            parts.append(f"Note: {note}")
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(" | ".join(parts) + "\n")
    except OSError as e:
        logger.warning(f"[Teller] Could not write to teller-tokens.log: {e}")


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


# ---------------------------------------------------------------------------
# Transaction type inference
# ---------------------------------------------------------------------------

def infer_txn_type(
    t: Dict[str, Any],
    raw_amount: float,
    *,
    acct_category: str,
    balance_seq: List[Tuple[str, float]],
    balance_index: Dict[str, int],
) -> str:
    """Infer whether a transaction is a credit or debit from available signals.

    Priority order:
      1. Running-balance delta (depository accounts only, when available)
      2. Teller type + amount sign heuristic (credit accounts)
      3. Amount sign fallback (when running_balance is missing)
    """
    tid = t.get("id")
    idx = balance_index.get(tid)
    teller_type = t.get("type", "")
    desc = t.get("description", "")

    # Depository: balance delta is the most reliable signal.
    if acct_category == "depository" and idx is not None and idx > 0:
        prev_bal = balance_seq[idx - 1][1]
        curr_bal = balance_seq[idx][1]
        result = "credit" if curr_bal > prev_bal else "debit"
        logger.debug(
            f"[CR/DR] DELTA  | {desc!r:50s} | acct={acct_category} teller_type={teller_type!r} "
            f"raw={raw_amount:+.2f} | idx={idx} prev={prev_bal:.2f} curr={curr_bal:.2f} → {result}"
        )
        return result

    # Credit accounts: amount sign + Teller type.
    # card_payment with negative amount = merchant refund; ACH/transfer = bill payment (money out).
    if acct_category == "credit" and raw_amount < 0:
        if teller_type == "card_payment":
            logger.debug(
                f"[CR/DR] CREDIT_REFUND | {desc!r:50s} | acct={acct_category} "
                f"teller_type={teller_type!r} raw={raw_amount:+.2f} → credit"
            )
            return "credit"
        logger.debug(
            f"[CR/DR] CREDIT_PMT   | {desc!r:50s} | acct={acct_category} "
            f"teller_type={teller_type!r} raw={raw_amount:+.2f} → debit"
        )
        return "debit"

    # Fallback: amount sign convention differs by account category.
    if acct_category == "depository":
        result = "debit" if raw_amount < 0 else "credit"
    else:
        result = "credit" if raw_amount < 0 else "debit"
    logger.debug(
        f"[CR/DR] FALLBACK| {desc!r:50s} | acct={acct_category} teller_type={teller_type!r} "
        f"raw={raw_amount:+.2f} idx={idx} → {result}"
    )
    return result
