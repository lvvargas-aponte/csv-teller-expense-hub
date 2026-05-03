"""Persistent stores.

``JsonStore`` is the legacy file-backed store (kept during migration so
``backend/scripts/migrate_json_to_pg.py`` can still read the old sidecar
files). Application code now uses ``PgStore`` — a ``MutableMapping``
backed by the ``json_stores`` table introduced in Alembic migration 0002.

PgStore preserves the live-dict contract ``state.py`` expects:

- ``store[key] = value`` → upserts a row in ``json_stores``
- ``store[key]`` → fetches one row
- ``values()`` / ``items()`` / ``__iter__`` → ``SELECT ... WHERE store_name = :s``
- ``.save()`` / ``.load()`` → no-ops retained for backward compat; writes
  are through.
- ``.data`` → returns ``self`` so legacy ``store.data.update({...})`` /
  ``store.data[k]`` call-sites keep working.
"""
import json
import logging
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Dict, Iterator

from sqlalchemy import text

logger = logging.getLogger(__name__)


class JsonStore:
    """Legacy single-JSON-file store, retained for the JSON → Postgres migration."""

    def __init__(self, path: Path, label: str) -> None:
        self._path = path
        self._label = label
        self.data: Dict[str, Any] = {}

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            self.data = json.loads(self._path.read_text(encoding="utf-8"))
            logger.info(f"[{self._label}] Loaded {len(self.data)} entries from disk")
        except Exception as e:
            logger.warning(f"[{self._label}] Could not load from {self._path}: {e}")
            self.data = {}

    def save(self) -> None:
        try:
            self._path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except OSError as e:
            logger.error(f"[{self._label}] Could not save to {self._path}: {e}")


class PgStore(MutableMapping):
    """Dict-facade backed by ``json_stores(store_name, key, data jsonb)``.

    Every op is write-through: there is no in-memory buffer. ``save()`` is a
    no-op kept only so existing routers that call ``store.save()`` after
    mutations continue to work without editing.
    """

    def __init__(self, store_name: str, label: str) -> None:
        self._name = store_name
        self._label = label

    # Back-compat: JsonStore exposes a ``.data`` dict. Some callers do
    # ``store.data.update({...})`` or ``store.data[k]``. Return self so those
    # expressions resolve to MutableMapping ops on this instance.
    @property
    def data(self) -> "PgStore":
        return self

    def load(self) -> None:
        return

    def save(self) -> None:
        return

    def _engine(self):
        # Imported lazily so ``store.py`` can be imported before
        # ``config.DATABASE_URL`` is resolved at test-collection time.
        from db.base import sync_engine
        return sync_engine

    def __getitem__(self, key: str) -> Any:
        with self._engine().connect() as conn:
            row = conn.execute(
                text("SELECT data FROM json_stores WHERE store_name=:s AND key=:k"),
                {"s": self._name, "k": key},
            ).fetchone()
        if row is None:
            raise KeyError(key)
        return row[0]

    def __setitem__(self, key: str, value: Any) -> None:
        payload = json.dumps(value, default=str)
        with self._engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO json_stores (store_name, key, data, updated_at) "
                    "VALUES (:s, :k, CAST(:d AS JSONB), NOW()) "
                    "ON CONFLICT (store_name, key) DO UPDATE SET "
                    "data = EXCLUDED.data, updated_at = NOW()"
                ),
                {"s": self._name, "k": key, "d": payload},
            )

    def __delitem__(self, key: str) -> None:
        with self._engine().begin() as conn:
            result = conn.execute(
                text("DELETE FROM json_stores WHERE store_name=:s AND key=:k"),
                {"s": self._name, "k": key},
            )
        if result.rowcount == 0:
            raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        with self._engine().connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM json_stores WHERE store_name=:s AND key=:k"),
                {"s": self._name, "k": key},
            ).fetchone()
        return row is not None

    def __iter__(self) -> Iterator[str]:
        with self._engine().connect() as conn:
            rows = conn.execute(
                text("SELECT key FROM json_stores WHERE store_name=:s ORDER BY key"),
                {"s": self._name},
            ).fetchall()
        return iter(r[0] for r in rows)

    def __len__(self) -> int:
        with self._engine().connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) FROM json_stores WHERE store_name=:s"),
                {"s": self._name},
            ).fetchone()
        return int(row[0]) if row else 0

    # Override the MutableMapping defaults for values/items/keys so we don't
    # issue one SELECT per key (N+1). Return materialised lists — analytics
    # iterates these fully; callers that mutate during iteration already hit
    # the same snapshot semantics they had with the previous JSON dict.
    def values(self):  # type: ignore[override]
        with self._engine().connect() as conn:
            rows = conn.execute(
                text("SELECT data FROM json_stores WHERE store_name=:s"),
                {"s": self._name},
            ).fetchall()
        return [r[0] for r in rows]

    def items(self):  # type: ignore[override]
        with self._engine().connect() as conn:
            rows = conn.execute(
                text("SELECT key, data FROM json_stores WHERE store_name=:s"),
                {"s": self._name},
            ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def keys(self):  # type: ignore[override]
        with self._engine().connect() as conn:
            rows = conn.execute(
                text("SELECT key FROM json_stores WHERE store_name=:s ORDER BY key"),
                {"s": self._name},
            ).fetchall()
        return [r[0] for r in rows]

    def clear(self) -> None:  # type: ignore[override]
        with self._engine().begin() as conn:
            conn.execute(
                text("DELETE FROM json_stores WHERE store_name=:s"),
                {"s": self._name},
            )

    def __repr__(self) -> str:
        return f"PgStore(store={self._name!r}, label={self._label!r})"


class InMemoryStore(MutableMapping):
    """Dict-backed drop-in for ``PgStore`` used by unit tests.

    Mirrors PgStore's MutableMapping surface plus the ``.data`` self-alias and
    no-op ``save``/``load`` so call-sites don't change. ``state.configure_for_tests()``
    swaps every PgStore for an instance of this class.
    """

    def __init__(self, store_name: str = "", label: str = "") -> None:
        self._dict: Dict[str, Any] = {}
        self._name = store_name
        self._label = label

    @property
    def data(self) -> "InMemoryStore":
        return self

    def load(self) -> None:
        return

    def save(self) -> None:
        return

    def __getitem__(self, key: str) -> Any:
        return self._dict[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._dict[key] = value

    def __delitem__(self, key: str) -> None:
        del self._dict[key]

    def __contains__(self, key: object) -> bool:
        return key in self._dict

    def __iter__(self) -> Iterator[str]:
        return iter(self._dict)

    def __len__(self) -> int:
        return len(self._dict)

    def values(self):  # type: ignore[override]
        return list(self._dict.values())

    def items(self):  # type: ignore[override]
        return list(self._dict.items())

    def keys(self):  # type: ignore[override]
        return list(self._dict.keys())

    def clear(self) -> None:  # type: ignore[override]
        self._dict.clear()

    def __repr__(self) -> str:
        return f"InMemoryStore(name={self._name!r}, n={len(self._dict)})"
