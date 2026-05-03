"""Interactive helper to remove stale or test Teller tokens from .env.

Usage:
    cd backend && py scripts/prune_tokens.py

Lists every token in the root-level .env's TELLER_API_KEY= line, masks them for
safe display, highlights any that match common test-token patterns
(``tok_abc...``, ``tok_one``, ``tok_two``, ``tok_test...``), and lets you remove
selected ones.  Writes the .env back with the filtered list.  Non-destructive —
each removal requires explicit confirmation.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Script sits under backend/scripts/ → .env is two levels up.
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
_FAKE_PATTERN = re.compile(r"^tok_(abc|one|two|test|fake|dummy)", re.IGNORECASE)


def _mask(token: str) -> str:
    return f"{token[:8]}…{token[-4:]}" if len(token) > 12 else "***"


def _read_tokens() -> list[str]:
    if not _ENV_PATH.exists():
        print(f"No .env file found at {_ENV_PATH}")
        sys.exit(1)
    env_text = _ENV_PATH.read_text(encoding="utf-8")
    match = re.search(r"^TELLER_API_KEY=(.*)$", env_text, re.MULTILINE)
    if not match:
        print("No TELLER_API_KEY line found in .env — nothing to prune.")
        sys.exit(0)
    return [t.strip() for t in match.group(1).split(",") if t.strip()]


def _write_tokens(tokens: list[str]) -> None:
    env_text = _ENV_PATH.read_text(encoding="utf-8")
    env_text = re.sub(
        r"^TELLER_API_KEY=.*$",
        "TELLER_API_KEY=" + ",".join(tokens),
        env_text,
        flags=re.MULTILINE,
    )
    _ENV_PATH.write_text(env_text, encoding="utf-8")


def main() -> None:
    tokens = _read_tokens()
    if not tokens:
        print("TELLER_API_KEY is empty.  Nothing to prune.")
        return

    print(f"\nFound {len(tokens)} Teller token(s) in {_ENV_PATH}:\n")
    for i, tok in enumerate(tokens, start=1):
        flag = "  ⚠ looks synthetic" if _FAKE_PATTERN.match(tok) else ""
        print(f"  [{i}] {_mask(tok)}{flag}")

    print("\nEnter indices to remove (comma-separated, e.g. `1,3`), or press Enter to exit.")
    raw = input("> ").strip()
    if not raw:
        print("No changes made.")
        return

    try:
        indices = sorted({int(x) for x in raw.split(",") if x.strip()}, reverse=True)
    except ValueError:
        print(f"Invalid input: {raw!r}")
        sys.exit(2)

    to_remove = []
    for idx in indices:
        if not (1 <= idx <= len(tokens)):
            print(f"Skipping out-of-range index: {idx}")
            continue
        to_remove.append(tokens[idx - 1])

    if not to_remove:
        print("Nothing to remove.")
        return

    print("\nAbout to remove:")
    for tok in to_remove:
        print(f"  - {_mask(tok)}")
    confirm = input("Proceed? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted — no changes made.")
        return

    remaining = [t for t in tokens if t not in to_remove]
    _write_tokens(remaining)
    print(f"\nDone.  {len(remaining)} token(s) remain in .env.")


if __name__ == "__main__":
    main()
