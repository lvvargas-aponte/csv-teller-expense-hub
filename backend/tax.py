"""Tax awareness — what an account's balance is worth after the tax on it.

Deliberately narrow. Nothing here computes tax owed, estimates a refund,
sequences withdrawals or suggests a conversion: those need filing status,
deductions, state rules and per-lot basis the app does not hold, and they are
advice rather than arithmetic. What this module does is label an account's
treatment, and let the rest of the app reason about a pre-tax dollar and an
after-tax dollar as the different things they are.

Inference is a *default shown to the user*, never a silent commitment — a Roth
401(k) and a traditional one carry the same ``subtype`` string, so the only
thing that can tell them apart is the user. ``describe`` therefore reports the
inference alongside whether the user has confirmed it.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

TREATMENTS = ("taxable", "traditional", "roth", "hsa", "education", "other")

# Matched against the subtype with everything but letters and digits removed,
# so "401(k)", "401 k" and "401k" are one key.
_TAXABLE = frozenset({"brokerage", "taxable", "individual", "joint"})
_TRADITIONAL = frozenset({
    "401k", "403b", "457b", "ira", "traditionalira", "rolloverira",
    "sepira", "sep", "simpleira", "simple", "pension",
})


def _normalize(subtype: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (subtype or "").lower())


def infer_treatment(subtype: Optional[str]) -> Optional[str]:
    """The treatment a subtype string implies, or None when it implies nothing.

    ``None`` is a real answer: "investment" and "retirement" are the subtypes
    the app most often has, and neither says whether the money was taxed on
    the way in. Guessing there would put a wrong label on a balance and then
    discount it.
    """
    s = _normalize(subtype)
    if not s:
        return None
    if "roth" in s:
        return "roth"
    if "hsa" in s:
        return "hsa"
    if "529" in s or "coverdell" in s or "esa" == s:
        return "education"
    if s in _TAXABLE:
        return "taxable"
    if s in _TRADITIONAL:
        return "traditional"
    return None


def _field(account: Any, key: str) -> Any:
    if isinstance(account, dict):
        return account.get(key)
    return getattr(account, key, None)


def stored_treatment(account: Any) -> Optional[str]:
    """The treatment the user set on this account, if any."""
    import state

    account_id = _field(account, "id") or _field(account, "account_id")
    if not account_id:
        return None
    details = state.account_details.get(account_id) or {}
    value = (details.get("tax_treatment") or "").strip().lower()
    return value if value in TREATMENTS else None


def effective_treatment(account: Any) -> Optional[str]:
    """What the app should treat this account as. The user's answer wins."""
    return stored_treatment(account) or infer_treatment(_field(account, "subtype"))


def describe(account: Any) -> Dict[str, Any]:
    """``{treatment, inferred, set_by_user}`` — the label plus its provenance.

    The UI needs all three to say "assumed traditional — is that right?"
    instead of quietly presenting a guess as a fact.
    """
    stored = stored_treatment(account)
    inferred = infer_treatment(_field(account, "subtype"))
    return {
        "treatment": stored or inferred,
        "inferred": inferred,
        "set_by_user": stored is not None,
    }


# Treatments whose balances are retirement money rather than general savings.
RETIREMENT_TREATMENTS = frozenset({"traditional", "roth"})


def is_retirement(account: Any) -> bool:
    return effective_treatment(account) in RETIREMENT_TREATMENTS
