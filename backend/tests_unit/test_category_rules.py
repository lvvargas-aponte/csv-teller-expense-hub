"""Standing auto-categorization rules.

The failure mode worth guarding against isn't a rule that doesn't fire — the
user notices that immediately. It's a rule that fires too widely (relabelling
a year of hand-made decisions) or too narrowly (a float comparison quietly
dropping the $1,305.93 match), both of which corrupt spending totals without
any visible error.
"""
import category_rules
import state


def _rule(rule_id="rule_1", **overrides):
    record = {
        "id": rule_id,
        "match": "description_contains",
        "value": "Luz Valeria",
        "category": "Rent",
        "amount": 1305.93,
        "transaction_type": "debit",
        "enabled": True,
        "notes": "",
        "created": "2026-08-17T00:00:00",
        "updated": "2026-08-17T00:00:00",
    }
    record.update(overrides)
    state.category_rules[rule_id] = record
    return record


def _txn(tid="t1", description="Zelle payment to Luz Valeria Vargas-Aponte", **overrides):
    row = {
        "id": tid, "transaction_id": tid, "date": "2026-08-01",
        "description": description, "amount": 1305.93,
        "transaction_type": "debit", "source": "simplefin",
        "institution": "Truist", "category": None,
        "is_shared": False, "reviewed": False,
        "person_1_owes": 0.0, "person_2_owes": 0.0, "notes": "",
    }
    row.update(overrides)
    state.stored_transactions[tid] = row
    return row


class TestMatching:
    def test_matches_description_amount_and_direction(self):
        _rule()
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria Vargas-Aponte", 1305.93, "debit"
        ) == "Rent"

    def test_description_match_is_case_insensitive(self):
        _rule()
        assert category_rules.match_category(
            "ZELLE PAYMENT TO LUZ VALERIA VARGAS-APONTE", 1305.93, "debit"
        ) == "Rent"

    def test_float_noise_within_half_a_cent_still_matches(self):
        # 1305.93 does not survive a float round-trip exactly; an `==`
        # comparison here would silently stop categorizing the rent.
        _rule()
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 1305.9299999999998, "debit"
        ) == "Rent"

    def test_amount_compared_by_magnitude(self):
        """Stores keep amount positive with direction in transaction_type, but
        a signed amount from any other caller must match too."""
        _rule()
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", -1305.93, "debit"
        ) == "Rent"

    def test_different_amount_does_not_match(self):
        _rule()
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 1400.00, "debit"
        ) is None

    def test_different_recipient_does_not_match(self):
        _rule()
        assert category_rules.match_category(
            "Zelle payment to Someone Else", 1305.93, "debit"
        ) is None

    def test_wrong_direction_does_not_match(self):
        _rule()
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 1305.93, "credit"
        ) is None

    def test_amountless_rule_matches_any_amount(self):
        _rule(amount=None)
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 42.00, "debit"
        ) == "Rent"

    def test_typeless_rule_matches_either_direction(self):
        _rule(transaction_type=None)
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 1305.93, "credit"
        ) == "Rent"

    def test_disabled_rule_is_skipped(self):
        _rule(enabled=False)
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 1305.93, "debit"
        ) is None

    def test_merchant_key_match_survives_a_changing_reference_number(self):
        _rule(match="merchant_key", value="ZELLE PAYMENT TO LUZ VALERIA 0421", amount=None,
              transaction_type=None)
        assert category_rules.match_category(
            "ZELLE PAYMENT TO LUZ VALERIA 9987", 1305.93, "debit"
        ) == "Rent"


class TestPrecedence:
    def test_amount_pinned_rule_wins_over_a_broader_one(self):
        # Written second, so insertion order alone would pick the broad rule.
        _rule("rule_specific", amount=1305.93, category="Rent",
              created="2026-08-17T00:00:00")
        _rule("rule_broad", amount=None, category="Gifts and Donations",
              transaction_type=None, created="2026-08-18T00:00:00")
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 1305.93, "debit"
        ) == "Rent"

    def test_broad_rule_still_covers_other_amounts(self):
        _rule("rule_specific", amount=1305.93, category="Rent")
        _rule("rule_broad", amount=None, category="Gifts and Donations",
              transaction_type=None, created="2026-08-18T00:00:00")
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 50.00, "debit"
        ) == "Gifts and Donations"

    def test_same_specificity_ties_break_by_creation_time(self):
        _rule("rule_new", amount=None, category="Newer",
              transaction_type=None, created="2026-08-18T00:00:00")
        _rule("rule_old", amount=None, category="Older",
              transaction_type=None, created="2026-01-01T00:00:00")
        assert category_rules.match_category(
            "Zelle payment to Luz Valeria", 1305.93, "debit"
        ) == "Older"


class TestApplyToStored:
    def test_categorizes_matching_uncategorized_transactions(self):
        _rule()
        _txn("t1")
        _txn("t2", date="2026-07-01")
        result = category_rules.apply_to_stored()
        assert result["changed"] == 2
        assert state.stored_transactions["t1"]["category"] == "Rent"
        assert state.stored_transactions["t2"]["category"] == "Rent"

    def test_preview_writes_nothing(self):
        _rule()
        _txn("t1")
        result = category_rules.apply_to_stored(dry_run=True)
        assert result["changed"] == 1
        assert state.stored_transactions["t1"]["category"] is None

    def test_leaves_an_existing_category_alone_by_default(self):
        _rule()
        _txn("t1", category="Gifts and Donations")
        result = category_rules.apply_to_stored()
        assert result["matched"] == 1
        assert result["changed"] == 0
        assert state.stored_transactions["t1"]["category"] == "Gifts and Donations"

    def test_overwrite_relabels_a_categorized_transaction(self):
        _rule()
        _txn("t1", category="Gifts and Donations")
        result = category_rules.apply_to_stored(overwrite=True)
        assert result["changed"] == 1
        assert state.stored_transactions["t1"]["category"] == "Rent"

    def test_already_correct_is_matched_but_not_counted_as_a_change(self):
        _rule()
        _txn("t1", category="Rent")
        result = category_rules.apply_to_stored(overwrite=True)
        assert result["matched"] == 1
        assert result["changed"] == 0

    def test_does_not_flip_reviewed(self):
        _rule()
        _txn("t1", reviewed=False)
        category_rules.apply_to_stored()
        assert state.stored_transactions["t1"]["reviewed"] is False

    def test_non_matching_transactions_are_untouched(self):
        _rule()
        _txn("t1", description="AMAZON MKTP", amount=25.00)
        result = category_rules.apply_to_stored()
        assert result["changed"] == 0
        assert state.stored_transactions["t1"]["category"] is None

    def test_scoped_to_a_single_rule(self):
        _rule("rule_rent", value="Luz Valeria", category="Rent", amount=None,
              transaction_type=None)
        _rule("rule_coffee", value="STARBUCKS", category="Coffee", amount=None,
              transaction_type=None)
        _txn("t1")
        _txn("t2", description="STARBUCKS #1234", amount=4.50)
        result = category_rules.apply_to_stored(rule_id="rule_coffee")
        assert result["changed"] == 1
        assert state.stored_transactions["t1"]["category"] is None
        assert state.stored_transactions["t2"]["category"] == "Coffee"

    def test_no_rules_is_a_no_op(self):
        _txn("t1")
        result = category_rules.apply_to_stored()
        assert result == {
            "scanned": 0, "matched": 0, "changed": 0, "changes": [], "truncated": False,
        }


class TestApi:
    def _payload(self, **overrides):
        payload = {
            "match": "description_contains",
            "value": "Luz Valeria",
            "category": "Rent",
            "amount": 1305.93,
            "transaction_type": "debit",
        }
        payload.update(overrides)
        return payload

    def test_create_list_delete_round_trip(self, client):
        created = client.post("/api/category-rules", json=self._payload())
        assert created.status_code == 201
        rule_id = created.json()["id"]

        listed = client.get("/api/category-rules")
        assert [r["id"] for r in listed.json()] == [rule_id]

        assert client.delete(f"/api/category-rules/{rule_id}").status_code == 204
        assert client.get("/api/category-rules").json() == []

    def test_create_rejects_an_empty_value(self, client):
        assert client.post("/api/category-rules", json=self._payload(value="  ")).status_code == 422

    def test_create_rejects_an_empty_category(self, client):
        assert client.post("/api/category-rules", json=self._payload(category="")).status_code == 422

    def test_create_rejects_a_non_positive_amount(self, client):
        assert client.post("/api/category-rules", json=self._payload(amount=0)).status_code == 422

    def test_creating_a_rule_does_not_touch_existing_transactions(self, client):
        """Saving a rule must never relabel history as a side effect — the
        client previews first, then applies."""
        _txn("t1")
        client.post("/api/category-rules", json=self._payload())
        assert state.stored_transactions["t1"]["category"] is None

    def test_update_preserves_created_timestamp(self, client):
        rule_id = client.post("/api/category-rules", json=self._payload()).json()["id"]
        created_at = state.category_rules[rule_id]["created"]
        updated = client.put(
            f"/api/category-rules/{rule_id}", json=self._payload(category="Housing")
        )
        assert updated.status_code == 200
        assert updated.json()["category"] == "Housing"
        assert updated.json()["created"] == created_at

    def test_update_unknown_rule_is_404(self, client):
        assert client.put("/api/category-rules/nope", json=self._payload()).status_code == 404

    def test_delete_unknown_rule_is_404(self, client):
        assert client.delete("/api/category-rules/nope").status_code == 404

    def test_apply_preview_then_apply(self, client):
        _rule()
        _txn("t1")

        preview = client.post("/api/category-rules/apply", json={"mode": "preview"})
        assert preview.json()["changed"] == 1
        assert preview.json()["changes"][0]["to_category"] == "Rent"
        assert state.stored_transactions["t1"]["category"] is None

        applied = client.post("/api/category-rules/apply", json={"mode": "apply"})
        assert applied.json()["changed"] == 1
        assert state.stored_transactions["t1"]["category"] == "Rent"

    def test_apply_with_unknown_rule_id_is_404(self, client):
        assert client.post(
            "/api/category-rules/apply", json={"mode": "apply", "rule_id": "nope"}
        ).status_code == 404


class TestCsvIngest:
    def test_upload_applies_a_rule_to_new_rows(self, client):
        _rule(value="WHOLE FOODS", category="Groceries", amount=None,
              transaction_type=None)
        csv = (
            "Barclays Bank Delaware\n"
            "Account Number: 1234567890123456\n"
            "Account Balance as of 01/31/2024: $1234.56\n"
            "\n"
            "Transaction Date,Description,Category,Amount\n"
            "01/15/2024,WHOLE FOODS,DEBIT,-67.23\n"
            "01/16/2024,NETFLIX,DEBIT,-15.99\n"
        )
        response = client.post(
            "/api/upload-csv",
            files={"file": ("statement.csv", csv, "text/csv")},
        )
        assert response.status_code == 200
        by_description = {
            t["description"]: t for t in response.json()["transactions"]
        }
        assert by_description["WHOLE FOODS"]["category"] == "Groceries"
        assert by_description["NETFLIX"]["category"] is None
