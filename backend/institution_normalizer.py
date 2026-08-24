"""Single source of truth for institution-name normalization.

Different providers spell the same institution differently — SimpleFIN
reports ``E*Trade`` where SnapTrade reports ``E-Trade`` — which surfaces as
duplicate chips and duplicate groups for one real institution. Every path
that puts an institution name on an ``AccountBalance`` runs it through
``normalize()`` so the whole app agrees on one label.

Only genuine cross-provider collisions belong in ``ALIASES``. Unknown names
pass through untouched: the goal is to reconcile known spelling variants,
not to police what an institution calls itself.
"""
from __future__ import annotations

from typing import Optional

# Lowercased variant -> canonical display name.
ALIASES: dict[str, str] = {
    "e-trade":      "E*Trade",
    "e*trade":      "E*Trade",
    "etrade":       "E*Trade",
    "bank of america": "Bank of America",
    "bofa":         "Bank of America",
    "chase":        "Chase",
    "chase bank":   "Chase",
}


def normalize(name: Optional[str]) -> str:
    """Canonical display name for ``name``; ``""`` for blank input."""
    if not name:
        return ""
    stripped = name.strip()
    if not stripped:
        return ""
    return ALIASES.get(stripped.lower(), stripped)
