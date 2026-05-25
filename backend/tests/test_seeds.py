"""Seeds API — runtime-editable curated reading list.

Covers:
* GET returns the JSON defaults merged with DB rows
* POST adds a custom seed AND auto-allowlists its host
* DELETE on a default id hides it (next GET excludes it)
* DELETE on a custom id removes it
* Restore endpoint un-hides a default
* Adding a duplicate URL rejects with 422
* Effective allowlist (visible via /api/documents/allowed-hosts)
  expands to include custom-seed hosts
"""
from sqlalchemy import text

from db.base import sync_engine

import seed_loader
import url_fetcher


def _custom_count() -> int:
    with sync_engine.connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM seed_custom")).scalar() or 0)


def _removed_count() -> int:
    with sync_engine.connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM seed_removed_defaults")).scalar() or 0)


def _allowlist_count() -> int:
    with sync_engine.connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM allowlist_hosts")).scalar() or 0)


# Clear the lru_cache between tests so a JSON-defaults edit (none here,
# but defensive) doesn't carry across.
def _clear_caches():
    seed_loader._load_defaults_raw.cache_clear()


class TestList:
    def test_returns_default_groups(self, client):
        _clear_caches()
        resp = client.get("/api/seeds")
        assert resp.status_code == 200
        groups = resp.json()
        # The shipped defaults JSON has three groups.
        labels = [g["label"] for g in groups]
        assert "Government & regulators" in labels
        assert "FIRE community" in labels

        # Every default seed has a stable d:... id.
        all_ids = [s["id"] for g in groups for s in g["seeds"]]
        assert any(i == "d:irs-pub-17" for i in all_ids)
        assert all(i.startswith("d:") or i.startswith("c:") for i in all_ids)
        assert all(s["is_custom"] is False
                   for g in groups for s in g["seeds"])


class TestAdd:
    def test_adds_custom_seed_and_allowlists_host(self, client):
        _clear_caches()
        resp = client.post("/api/seeds", json={
            "title": "Vanguard — Lifecycle of a 401(k)",
            "url": "https://investor.vanguard.com/learn/articles/401k",
            "scope": "external",
            "category": "investing",
            "why": "Plain-English 401(k) walkthrough.",
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"].startswith("c:")
        assert body["is_custom"] is True
        assert _custom_count() == 1

        # Host auto-allowlisted.
        hosts = client.get("/api/documents/allowed-hosts").json()
        assert "investor.vanguard.com" in hosts

    def test_duplicate_url_rejected(self, client):
        _clear_caches()
        payload = {
            "title": "Some article",
            "url": "https://www.example.com/x",
            "scope": "external",
            "category": "literacy",
            "why": "",
        }
        # First time succeeds; second time 422.
        first = client.post("/api/seeds", json=payload)
        assert first.status_code == 201
        second = client.post("/api/seeds", json=payload)
        assert second.status_code == 422
        assert "already exists" in second.json()["detail"].lower()

    def test_non_https_rejected(self, client):
        _clear_caches()
        resp = client.post("/api/seeds", json={
            "title": "Insecure",
            "url": "http://www.example.com/x",
            "scope": "external",
            "category": "literacy",
        })
        assert resp.status_code == 422
        assert "https" in resp.json()["detail"].lower()


class TestDelete:
    def test_hide_default_excludes_from_list(self, client):
        _clear_caches()
        resp = client.delete("/api/seeds/d:irs-pub-17")
        assert resp.status_code == 204
        assert _removed_count() == 1

        groups = client.get("/api/seeds").json()
        ids = [s["id"] for g in groups for s in g["seeds"]]
        assert "d:irs-pub-17" not in ids
        # Other IRS defaults are still present.
        assert "d:irs-pub-590a" in ids

    def test_remove_custom_seed(self, client):
        _clear_caches()
        added = client.post("/api/seeds", json={
            "title": "X", "url": "https://www.example.com/y",
            "scope": "external", "category": "literacy",
        }).json()
        assert _custom_count() == 1

        resp = client.delete(f"/api/seeds/{added['id']}")
        assert resp.status_code == 204
        assert _custom_count() == 0

    def test_delete_unknown_returns_404(self, client):
        # Custom id that doesn't exist.
        resp = client.delete("/api/seeds/c:99999")
        assert resp.status_code == 404


class TestHiddenList:
    def test_hidden_endpoint_returns_removed_defaults(self, client):
        _clear_caches()
        # Nothing hidden initially.
        assert client.get("/api/seeds/hidden").json() == []

        client.delete("/api/seeds/d:irs-pub-17")
        client.delete("/api/seeds/d:cfpb-credit-score")

        hidden = client.get("/api/seeds/hidden").json()
        ids = {h["id"] for h in hidden}
        assert ids == {"d:irs-pub-17", "d:cfpb-credit-score"}
        # Each hidden record carries enough to render a row.
        for h in hidden:
            assert h["title"]
            assert h["url"].startswith("https://")
            assert h["group_label"]
            assert h["is_custom"] is False


class TestRestore:
    def test_restore_brings_default_back(self, client):
        _clear_caches()
        client.delete("/api/seeds/d:cfpb-credit-score")
        assert _removed_count() == 1

        resp = client.post("/api/seeds/restore/d:cfpb-credit-score")
        assert resp.status_code == 204
        assert _removed_count() == 0

        ids = [s["id"] for g in client.get("/api/seeds").json() for s in g["seeds"]]
        assert "d:cfpb-credit-score" in ids

    def test_restore_unknown_returns_404(self, client):
        _clear_caches()
        # Default that exists but wasn't hidden -> returns 404 since
        # nothing was removed.
        resp = client.post("/api/seeds/restore/d:irs-pub-17")
        assert resp.status_code == 404


class TestEffectiveAllowlist:
    def test_base_hosts_present_without_custom_seeds(self, client):
        _clear_caches()
        hosts = client.get("/api/documents/allowed-hosts").json()
        for h in url_fetcher.BASE_ALLOWED_HOSTS:
            assert h in hosts

    def test_runtime_addition_visible(self, client):
        _clear_caches()
        client.post("/api/seeds", json={
            "title": "Marketplace article",
            "url": "https://www.marketplace.org/something",
            "scope": "external", "category": "literacy",
        })
        hosts = client.get("/api/documents/allowed-hosts").json()
        assert "www.marketplace.org" in hosts
        # Base hosts still there too.
        assert "www.irs.gov" in hosts
