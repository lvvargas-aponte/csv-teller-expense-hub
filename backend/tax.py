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


AFTER_TAX_NOTE = (
    "Estimate. Pre-tax balances discounted at your stated marginal rate. "
    "Taxable and Roth balances are left as they are."
)

_RATE_MISSING = (
    "Add your marginal tax rate in Profile & settings to see an after-tax "
    "figure. It is never inferred from your income."
)

_TOGGLE_OFF = "After-tax net worth is turned off in Profile & settings."


def _unavailable(reason: str) -> Dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "headline_net_worth": None,
        "after_tax_net_worth": None,
        "deferred_tax_estimate": None,
        "pre_tax_balance": None,
        "rate_pct": None,
        "rate_source": None,
        "note": AFTER_TAX_NOTE,
    }


def _balance(account: Any) -> float:
    return float(account.available or 0.0) or float(account.ledger or 0.0)


async def after_tax_net_worth() -> Dict[str, Any]:
    """Net worth with the income tax owed on pre-tax balances taken off.

    Only ``traditional`` balances are discounted. A taxable brokerage is left
    alone on purpose: taxing it correctly needs per-lot cost basis and holding
    periods the app does not hold, and applying a flat rate to the whole
    balance rather than the gain would be badly wrong in the user's disfavour.

    Opt-in, and unavailable rather than guessed. The rate is the user's own
    figure — deriving a bracket from income needs filing status, deductions
    and state rules, and a wrong bracket moves this number by five figures.
    """
    import balances_service
    from db import profile_repo

    profile = profile_repo.load_quietly() or {}
    if not profile.get("show_after_tax_net_worth"):
        return _unavailable(_TOGGLE_OFF)

    rate = profile.get("marginal_tax_rate_pct")
    if rate is None:
        return _unavailable(_RATE_MISSING)

    summary = await balances_service.build_summary()
    pre_tax = round(
        sum(
            _balance(a) for a in summary.accounts
            if effective_treatment(a) == "traditional"
        ),
        2,
    )
    deferred = round(pre_tax * float(rate) / 100.0, 2)

    return {
        "available": True,
        "reason": None,
        "headline_net_worth": summary.net_worth,
        "after_tax_net_worth": round(summary.net_worth - deferred, 2),
        "deferred_tax_estimate": deferred,
        "pre_tax_balance": pre_tax,
        "rate_pct": float(rate),
        "rate_source": "profile",
        "note": AFTER_TAX_NOTE,
    }
