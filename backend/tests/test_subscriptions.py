"""Integration tests for the subscriptions review endpoints."""
from datetime import date, timedelta

import state

# Offsets run from mid-month rather than the real clock. Counted back from
# `date.today()`, a 30-day step lands twice in the same month whenever today
# is early in one — `months_seen` collapses and the detector's "≥ 2 distinct
# months" gate fails, turning the suite red on the 5th of every month for a
# reason unrelated to the code under test.
_ANCHOR = date.today().replace(day=15)


def _add_recurring(tid_prefix, description, amount, category="Entertainment", months=3):
    for i in range(months):
        d = (_ANCHOR - timedelta(days=5 + 30 * i)).isoformat()
        tid = f"{tid_prefix}_{i}"
        state.stored_transactions[tid] = {
            "id": tid, "date": d, "description": description, "amount": amount,
            "category": category, "transaction_type": "debit", "source": "teller",
            "direction": "outflow",
        }


class TestListSubscriptions:
    def test_new_merchant_needs_review(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        data = client.get("/api/subscriptions").json()
        assert len(data["subscriptions"]) == 1
        sub = data["subscriptions"][0]
        assert sub["needs_review"] is True
        assert sub["review"] is None
        assert data["summary"]["needs_review_count"] == 1
        assert data["summary"]["active_monthly_cost"] == 15.49

    def test_reviewed_merchant_is_settled(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        r = client.post(
            "/api/subscriptions/netflix membership/review", json={"decision": "keep"}
        )
        assert r.status_code == 200
        assert r.json()["review"]["reviewed_amount"] == 15.49

        data = client.get("/api/subscriptions").json()
        sub = data["subscriptions"][0]
        assert sub["needs_review"] is False
        assert sub["review"]["decision"] == "keep"
        assert data["summary"]["needs_review_count"] == 0

    def test_price_increase_reprompts(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        client.post(
            "/api/subscriptions/netflix membership/review", json={"decision": "keep"}
        )
        # Price jumps >10% on the newest charge.
        newest = (_ANCHOR - timedelta(days=1)).isoformat()
        state.stored_transactions["nfx_new"] = {
            "id": "nfx_new", "date": newest, "description": "NETFLIX MEMBERSHIP",
            "amount": 18.99, "category": "Entertainment",
            "transaction_type": "debit", "source": "teller", "direction": "outflow",
        }
        data = client.get("/api/subscriptions").json()
        sub = data["subscriptions"][0]
        assert sub["needs_review"] is True
        assert sub["price_change_since_review_pct"] > 10

    def test_cancel_moves_cost_to_savings(self, client):
        _add_recurring("hulu", "HULU SUBSCRIPTION", 12.99)
        client.post(
            "/api/subscriptions/hulu subscription/review", json={"decision": "cancel"}
        )
        data = client.get("/api/subscriptions").json()
        assert data["summary"]["cancel_monthly_savings"] == 12.99
        assert data["summary"]["active_monthly_cost"] == 0.0

    def test_overlap_flagged_for_two_streaming_services(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        _add_recurring("hulu", "HULU SUBSCRIPTION", 12.99)
        data = client.get("/api/subscriptions").json()
        groups = {s["merchant_key"]: s["overlap_group"] for s in data["subscriptions"]}
        assert groups["netflix membership"] == "entertainment"
        assert groups["hulu subscription"] == "entertainment"

    def test_ignored_merchant_never_reprompts(self, client):
        # Category matters now: the endpoint serves commitment_type
        # "subscription" only, so a merchant filed under something else never
        # reaches the review queue at all.
        _add_recurring("gym", "CITY GYM", 40.0, category="Subscriptions")
        client.post("/api/subscriptions/city gym/review", json={"decision": "ignore"})
        data = client.get("/api/subscriptions").json()
        assert data["subscriptions"][0]["needs_review"] is False


class TestStaleness:
    """A charge that stopped arriving is not a live subscription. Staleness is
    measured against the newest transaction on file, never today, so a gap in
    importing never reads as a gap in billing.
    """

    def test_long_silent_merchant_is_dormant(self, client):
        # Monthly, last seen 5 cycles ago.
        for i in range(3):
            d = (_ANCHOR - timedelta(days=150 + 30 * i)).isoformat()
            state.stored_transactions[f"spot_{i}"] = {
                "id": f"spot_{i}", "date": d, "description": "SPOTIFY USA",
                "amount": 19.98, "category": "Subscriptions",
                "transaction_type": "debit", "source": "teller", "direction": "outflow",
            }
        # Something recent from another merchant sets the dataset's horizon.
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)

        data = client.get("/api/subscriptions").json()
        live = [s["merchant_key"] for s in data["subscriptions"]]
        dormant = [s["merchant_key"] for s in data["dormant"]]
        assert "netflix membership" in live
        assert "spotify usa" in dormant
        assert data["summary"]["dormant_count"] == 1
        # A dead charge must not inflate what you spend each month.
        assert data["summary"]["active_monthly_cost"] == 15.49

    def test_staleness_is_measured_from_newest_transaction(self, client):
        # Everything is 6 months old — an import gap, not six cancellations.
        for i in range(3):
            d = (_ANCHOR - timedelta(days=180 + 30 * i)).isoformat()
            state.stored_transactions[f"old_{i}"] = {
                "id": f"old_{i}", "date": d, "description": "NETFLIX MEMBERSHIP",
                "amount": 15.49, "category": "Subscriptions",
                "transaction_type": "debit", "source": "teller", "direction": "outflow",
            }
        data = client.get("/api/subscriptions").json()
        assert data["dormant"] == []
        assert data["subscriptions"][0]["status"] == "active"

    def test_dormant_row_asks_whether_it_ended(self, client):
        for i in range(3):
            d = (_ANCHOR - timedelta(days=150 + 30 * i)).isoformat()
            state.stored_transactions[f"spot_{i}"] = {
                "id": f"spot_{i}", "date": d, "description": "SPOTIFY USA",
                "amount": 19.98, "category": "Subscriptions",
                "transaction_type": "debit", "source": "teller", "direction": "outflow",
            }
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        data = client.get("/api/subscriptions").json()
        assert data["dormant"][0]["open_question"] == "still_active"


class TestDeclaredCadence:
    def test_irregular_merchant_asks_for_cadence(self, client):
        # Two charges 45 days apart fit no billing band.
        for i, days in enumerate((5, 50)):
            d = (_ANCHOR - timedelta(days=days)).isoformat()
            state.stored_transactions[f"cl_{i}"] = {
                "id": f"cl_{i}", "date": d, "description": "CLAUDE.AI SUBSCRIPTION",
                "amount": 107.39, "category": "Subscriptions",
                "transaction_type": "debit", "source": "teller", "direction": "outflow",
            }
        sub = client.get("/api/subscriptions").json()["subscriptions"][0]
        assert sub["cadence"] == "irregular"
        assert sub["open_question"] == "cadence"

    def test_declared_annual_overrides_inference_and_monthly_cost(self, client):
        for i, days in enumerate((5, 50)):
            d = (_ANCHOR - timedelta(days=days)).isoformat()
            state.stored_transactions[f"cl_{i}"] = {
                "id": f"cl_{i}", "date": d, "description": "CLAUDE.AI SUBSCRIPTION",
                "amount": 120.00, "category": "Subscriptions",
                "transaction_type": "debit", "source": "teller", "direction": "outflow",
            }
        # Ask the detector for the key rather than guessing at the
        # normalization — "claude.ai" keeps its dot.
        key = client.get("/api/subscriptions").json()["subscriptions"][0]["merchant_key"]
        r = client.post(
            f"/api/subscriptions/{key}/review",
            json={"decision": "keep", "declared_cadence": "annual"},
        )
        assert r.status_code == 200
        assert r.json()["review"]["declared_cadence"] == "annual"

        sub = client.get("/api/subscriptions").json()["subscriptions"][0]
        assert sub["cadence"] == "annual"
        assert sub["cadence_declared"] is True
        # An annual renewal contributes a twelfth of its price each month.
        assert sub["estimated_monthly_cost"] == round(120.00 / 12, 2)
        # And the question is settled, so it stops being asked.
        assert sub["open_question"] is None

    def test_declared_cadence_survives_a_later_decision(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        client.post(
            "/api/subscriptions/netflix membership/review",
            json={"decision": "keep", "declared_cadence": "annual"},
        )
        # A plain decision with no cadence must not wipe the declared one.
        client.post(
            "/api/subscriptions/netflix membership/review", json={"decision": "cancel"},
        )
        sub = client.get("/api/subscriptions").json()["subscriptions"][0]
        assert sub["cadence"] == "annual"
        assert sub["review"]["decision"] == "cancel"

    def test_invalid_cadence_is_422(self, client):
        r = client.post(
            "/api/subscriptions/whatever/review",
            json={"decision": "keep", "declared_cadence": "fortnightly"},
        )
        assert r.status_code == 422


class TestDeclaringUndetectedMerchants:
    """Detection needs two charges to measure a gap. A yearly renewal inside a
    short history, and a bill that has charged once, are invisible to it — so
    the user has to be able to say so directly.
    """

    def _add_single(self, tid, description, amount, days_ago, category=""):
        d = (_ANCHOR - timedelta(days=days_ago)).isoformat()
        state.stored_transactions[tid] = {
            "id": tid, "date": d, "description": description, "amount": amount,
            "category": category, "transaction_type": "debit", "source": "teller",
            "direction": "outflow",
        }

    def test_single_charge_is_not_detected_but_is_offered(self, client):
        self._add_single("audi", "AUDI FINCL, INC. AUTO DEBIT 0000081", 581.75,
                         days_ago=5, category="Car Payment")
        assert client.get("/api/subscriptions").json()["subscriptions"] == []

        candidates = client.get("/api/subscriptions/candidates").json()["candidates"]
        assert any("AUDI" in c["sample_description"] for c in candidates)

    def test_declaring_a_cadence_promotes_a_single_charge(self, client):
        self._add_single("audi", "AUDI FINCL, INC. AUTO DEBIT 0000081", 581.75,
                         days_ago=5, category="Car Payment")
        key = client.get("/api/subscriptions/candidates").json()["candidates"][0]["merchant_key"]

        client.post(f"/api/subscriptions/{key}/review", json={
            "decision": "keep", "declared_cadence": "monthly", "declared_type": "bill",
        })

        # It is a commitment now, and it left the candidate list.
        from analytics import detect_recurring_charges
        detected = {r["merchant_key"]: r for r in detect_recurring_charges()}
        assert key in detected
        assert detected[key]["cadence"] == "monthly"
        assert detected[key]["commitment_type"] == "bill"
        assert detected[key]["estimated_monthly_cost"] == 581.75

        remaining = client.get("/api/subscriptions/candidates").json()["candidates"]
        assert all(c["merchant_key"] != key for c in remaining)

    def test_declared_annual_prices_at_one_twelfth(self, client):
        self._add_single("dom", "NAMECHEAP RENEWAL", 120.0, days_ago=10,
                         category="Subscriptions")
        key = client.get("/api/subscriptions/candidates").json()["candidates"][0]["merchant_key"]
        client.post(f"/api/subscriptions/{key}/review", json={
            "decision": "keep", "declared_cadence": "annual",
        })
        sub = client.get("/api/subscriptions").json()["subscriptions"][0]
        assert sub["estimated_monthly_cost"] == 10.0
        # A yearly charge seen 10 days ago is not overdue.
        assert sub["status"] == "active"

    def test_card_payments_are_never_offered_as_candidates(self, client):
        self._add_single("boa", "BANK OF AMERICA PAYMENT M10219748875 WEB ID: 9",
                         2243.61, days_ago=5, category="Service")
        self._add_single("chase", "Payment to Chase card ending in 5637 05/08",
                         1722.92, days_ago=6, category="General")
        candidates = client.get("/api/subscriptions/candidates").json()["candidates"]
        assert candidates == []


class TestMerchantAliases:
    """A service that renames itself forks into two merchants, each with half
    the history. Merging folds them back into one.
    """

    def _seed_renamed_service(self):
        # Old name, three months; new name, two more. Neither half alone has
        # the five months of history the pair does.
        for i in range(3):
            d = (_ANCHOR - timedelta(days=95 + 30 * i)).isoformat()
            state.stored_transactions[f"old_{i}"] = {
                "id": f"old_{i}", "date": d, "description": "Google FIBER 9QzC4w 650",
                "amount": 70.0, "category": "Utilities", "transaction_type": "debit",
                "source": "teller", "direction": "outflow",
            }
        for i in range(2):
            d = (_ANCHOR - timedelta(days=5 + 30 * i)).isoformat()
            state.stored_transactions[f"new_{i}"] = {
                "id": f"new_{i}", "date": d, "description": "GFiber Mountain View",
                "amount": 70.0, "category": "Utilities", "transaction_type": "debit",
                "source": "teller", "direction": "outflow",
            }

    def test_merge_folds_history_into_one_merchant(self, client):
        self._seed_renamed_service()
        from analytics import detect_recurring_charges

        before = {r["merchant_key"]: r for r in detect_recurring_charges()}
        assert len(before) == 2

        old_key = next(k for k in before if k.startswith("google fiber"))
        new_key = next(k for k in before if k.startswith("gfiber"))
        r = client.post(f"/api/subscriptions/{old_key}/merge", json={"into": new_key})
        assert r.status_code == 200

        after = {r["merchant_key"]: r for r in detect_recurring_charges()}
        assert list(after) == [new_key]
        merged = after[new_key]
        assert merged["occurrences"] == 5
        assert merged["months_seen"] == 5
        assert merged["merged_from"] == [old_key]
        # The old half was the dormant one; merged, the service is live again.
        assert merged["status"] == "active"

    def test_unmerge_restores_both(self, client):
        self._seed_renamed_service()
        from analytics import detect_recurring_charges

        keys = [r["merchant_key"] for r in detect_recurring_charges()]
        old_key = next(k for k in keys if k.startswith("google fiber"))
        new_key = next(k for k in keys if k.startswith("gfiber"))
        client.post(f"/api/subscriptions/{old_key}/merge", json={"into": new_key})

        r = client.delete(f"/api/subscriptions/{old_key}/merge")
        assert r.status_code == 204
        assert len(detect_recurring_charges()) == 2

    def test_merging_into_itself_is_422(self, client):
        r = client.post("/api/subscriptions/netflix/merge", json={"into": "netflix"})
        assert r.status_code == 422

    def test_merging_into_an_alias_is_422(self, client):
        client.post("/api/subscriptions/a/merge", json={"into": "b"})
        r = client.post("/api/subscriptions/c/merge", json={"into": "a"})
        assert r.status_code == 422
        assert "alias" in r.json()["detail"]

    def test_chained_merge_follows_to_the_new_home(self, client):
        # a→b, then b→c: nothing may be left pointing at b.
        client.post("/api/subscriptions/a/merge", json={"into": "b"})
        client.post("/api/subscriptions/b/merge", json={"into": "c"})
        from db import merchant_aliases_repo
        assert merchant_aliases_repo.list_aliases() == {"a": "c", "b": "c"}

    def test_unmerging_a_merchant_that_is_not_merged_is_404(self, client):
        assert client.delete("/api/subscriptions/nothing/merge").status_code == 404


class TestReviewValidation:
    def test_invalid_decision_is_422(self, client):
        r = client.post("/api/subscriptions/whatever/review", json={"decision": "meh"})
        assert r.status_code == 422

    def test_clear_review(self, client):
        _add_recurring("nfx", "NETFLIX MEMBERSHIP", 15.49)
        client.post(
            "/api/subscriptions/netflix membership/review", json={"decision": "keep"}
        )
        r = client.delete("/api/subscriptions/netflix membership/review")
        assert r.status_code == 204
        assert client.get("/api/subscriptions").json()["subscriptions"][0]["review"] is None

    def test_clear_missing_review_is_404(self, client):
        assert client.delete("/api/subscriptions/nope/review").status_code == 404