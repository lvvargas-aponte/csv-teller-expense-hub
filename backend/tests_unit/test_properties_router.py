"""HTTP surface for /api/properties and /api/loans."""
import pytest


def _property_payload(**overrides):
    payload = {
        "name": "Maple St Duplex",
        "address": "12 Maple St",
        "property_type": "multi_family",
        "status": "rental",
        "units": 2,
        "monthly_rent": 3000,
        "vacancy_rate_pct": 0,
        "property_tax_annual": 6000,
        "insurance_annual": 1200,
        "maintenance_pct_of_rent": 0,
        "capex_reserve_pct_of_rent": 0,
    }
    payload.update(overrides)
    return payload


def _loan_payload(property_id=None, **overrides):
    payload = {
        "name": "Maple St Mortgage",
        "loan_type": "mortgage",
        "property_id": property_id,
        "original_principal": 240000,
        "interest_rate_pct": 6.0,
        "term_months": 360,
        "origination_date": "2020-01-01",
        "first_payment_date": "2020-02-01",
        "escrow_monthly": 600,
    }
    payload.update(overrides)
    return payload


def _create_property(client, **overrides):
    response = client.post("/api/properties", json=_property_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _create_loan(client, property_id=None, **overrides):
    response = client.post("/api/loans", json=_loan_payload(property_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


class TestPropertyCrud:
    def test_create_returns_economics(self, client):
        body = _create_property(client)
        assert body["name"] == "Maple St Duplex"
        assert body["pro_forma"]["noi"] == 2400.0
        assert body["performance"]["rating"] in {"strong", "watch", "underperforming"}

    def test_list_is_empty_initially(self, client):
        assert client.get("/api/properties").json() == []

    def test_list_returns_created_properties(self, client):
        _create_property(client)
        _create_property(client, name="Oak St")
        names = [p["name"] for p in client.get("/api/properties").json()]
        assert sorted(names) == ["Maple St Duplex", "Oak St"]

    def test_get_one(self, client):
        created = _create_property(client)
        fetched = client.get(f"/api/properties/{created['property_id']}").json()
        assert fetched["property_id"] == created["property_id"]

    def test_get_missing_is_404(self, client):
        assert client.get("/api/properties/nope").status_code == 404

    def test_update_changes_fields_and_recomputes(self, client):
        created = _create_property(client)
        response = client.put(
            f"/api/properties/{created['property_id']}",
            json=_property_payload(name="Renamed", monthly_rent=4000),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed"
        assert body["pro_forma"]["noi"] == 3400.0

    def test_update_missing_is_404(self, client):
        assert client.put(
            "/api/properties/nope", json=_property_payload()
        ).status_code == 404

    def test_delete(self, client):
        created = _create_property(client)
        assert client.delete(
            f"/api/properties/{created['property_id']}"
        ).status_code == 204
        assert client.get("/api/properties").json() == []

    def test_delete_missing_is_404(self, client):
        assert client.delete("/api/properties/nope").status_code == 404

    def test_portfolio_is_not_captured_as_a_property_id(self, client):
        """Route ordering: /properties/portfolio must not hit /{property_id}."""
        response = client.get("/api/properties/portfolio")
        assert response.status_code == 200
        assert "total_equity" in response.json()


class TestPropertyValidation:
    def test_blank_name_rejected(self, client):
        assert client.post(
            "/api/properties", json=_property_payload(name="   ")
        ).status_code == 422

    def test_negative_rent_rejected(self, client):
        assert client.post(
            "/api/properties", json=_property_payload(monthly_rent=-100)
        ).status_code == 422

    def test_percentage_above_100_rejected(self, client):
        assert client.post(
            "/api/properties", json=_property_payload(vacancy_rate_pct=150)
        ).status_code == 422

    def test_zero_units_rejected(self, client):
        assert client.post(
            "/api/properties", json=_property_payload(units=0)
        ).status_code == 422

    def test_unknown_status_rejected_by_the_schema(self, client):
        assert client.post(
            "/api/properties", json=_property_payload(status="wishful")
        ).status_code == 422


class TestValuations:
    def test_purchase_price_seeds_a_valuation(self, client):
        """Equity should work immediately, not wait for a manual entry."""
        created = _create_property(
            client, purchase_price=320000, purchase_date="2021-06-01"
        )
        assert created["current_value"] == 320000.0

        valuations = client.get(
            f"/api/properties/{created['property_id']}/valuations"
        ).json()
        assert len(valuations) == 1
        assert valuations[0]["source"] == "purchase"

    def test_adding_a_newer_valuation_updates_current_value(self, client):
        created = _create_property(
            client, purchase_price=320000, purchase_date="2021-06-01"
        )
        response = client.post(
            f"/api/properties/{created['property_id']}/valuations",
            json={"value": 415000, "as_of": "2026-01-01", "source": "appraisal"},
        )
        assert response.status_code == 201
        assert response.json()["current_value"] == 415000.0

    def test_backfilling_an_older_valuation_does_not_clobber_current(self, client):
        created = _create_property(client)
        pid = created["property_id"]
        client.post(f"/api/properties/{pid}/valuations",
                    json={"value": 415000, "as_of": "2026-01-01"})
        response = client.post(f"/api/properties/{pid}/valuations",
                               json={"value": 250000, "as_of": "2019-01-01"})
        assert response.json()["current_value"] == 415000.0

    def test_non_positive_value_rejected(self, client):
        created = _create_property(client)
        assert client.post(
            f"/api/properties/{created['property_id']}/valuations", json={"value": 0}
        ).status_code == 422

    def test_bad_date_rejected(self, client):
        created = _create_property(client)
        assert client.post(
            f"/api/properties/{created['property_id']}/valuations",
            json={"value": 100, "as_of": "06/01/2021"},
        ).status_code == 422

    def test_valuations_for_missing_property_is_404(self, client):
        assert client.get("/api/properties/nope/valuations").status_code == 404


class TestPortfolio:
    def test_empty(self, client):
        body = client.get("/api/properties/portfolio").json()
        assert body["count"] == 0
        assert body["total_equity"] == 0.0

    def test_aggregates_across_properties(self, client):
        first = _create_property(client)
        client.post(f"/api/properties/{first['property_id']}/valuations",
                    json={"value": 400000})
        _create_loan(client, first["property_id"], current_principal=200000)

        second = _create_property(client, name="Oak St")
        client.post(f"/api/properties/{second['property_id']}/valuations",
                    json={"value": 300000})

        body = client.get("/api/properties/portfolio").json()
        assert body["count"] == 2
        assert body["total_value"] == 700000.0
        assert body["total_debt"] == 200000.0
        assert body["total_equity"] == 500000.0


class TestLoanCrud:
    def test_create_returns_derived_payment(self, client):
        loan = _create_loan(client)
        assert loan["monthly_payment"] == pytest.approx(1438.92, abs=0.01)

    def test_stored_payment_wins_over_derivation(self, client):
        loan = _create_loan(client, payment_amount=1500)
        assert loan["monthly_payment"] == 1500.0

    def test_list_and_filter_by_property(self, client):
        prop = _create_property(client)
        _create_loan(client, prop["property_id"], name="Mortgage")
        _create_loan(client, None, name="Car", loan_type="auto")

        assert len(client.get("/api/loans").json()) == 2
        filtered = client.get(
            "/api/loans", params={"property_id": prop["property_id"]}
        ).json()
        assert [l["name"] for l in filtered] == ["Mortgage"]

    def test_update(self, client):
        loan = _create_loan(client)
        response = client.put(
            f"/api/loans/{loan['id']}", json=_loan_payload(name="Refinanced")
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Refinanced"

    def test_delete(self, client):
        loan = _create_loan(client)
        assert client.delete(f"/api/loans/{loan['id']}").status_code == 204
        assert client.get(f"/api/loans/{loan['id']}").status_code == 404

    def test_missing_loan_is_404(self, client):
        assert client.get("/api/loans/nope").status_code == 404

    def test_equity_and_ltv_from_the_linked_property(self, client):
        prop = _create_property(client)
        client.post(f"/api/properties/{prop['property_id']}/valuations",
                    json={"value": 400000})
        loan = _create_loan(
            client, prop["property_id"], current_principal=300000
        )
        assert loan["asset_value_resolved"] == 400000.0
        assert loan["equity"] == 100000.0
        assert loan["ltv"] == 75.0

    def test_equity_is_none_without_a_valuation(self, client):
        loan = _create_loan(client)
        assert loan["equity"] is None
        assert loan["ltv"] is None


class TestLoanValidation:
    def test_zero_principal_rejected(self, client):
        assert client.post(
            "/api/loans", json=_loan_payload(original_principal=0)
        ).status_code == 422

    def test_zero_term_rejected(self, client):
        assert client.post(
            "/api/loans", json=_loan_payload(term_months=0)
        ).status_code == 422

    def test_negative_rate_rejected(self, client):
        assert client.post(
            "/api/loans", json=_loan_payload(interest_rate_pct=-1)
        ).status_code == 422

    def test_bad_date_format_rejected(self, client):
        assert client.post(
            "/api/loans", json=_loan_payload(origination_date="01/01/2020")
        ).status_code == 422

    def test_unknown_property_id_rejected(self, client):
        assert client.post(
            "/api/loans", json=_loan_payload(property_id="prop_nope")
        ).status_code == 422


class TestCurrentPayment:
    """The endpoint behind 'how much of my payment was interest?'"""

    def test_splits_interest_and_principal(self, client):
        loan = _create_loan(client, payment_amount=1438.92)
        body = client.get(f"/api/loans/{loan['id']}/current-payment").json()

        assert body["period"] >= 1
        assert body["interest"] > 0
        assert body["principal"] > 0
        assert body["interest"] + body["principal"] == pytest.approx(1438.92, abs=0.02)

    def test_escrow_is_reported_separately_from_the_split(self, client):
        loan = _create_loan(client, payment_amount=1438.92, escrow_monthly=600)
        body = client.get(f"/api/loans/{loan['id']}/current-payment").json()
        assert body["escrow"] == 600.0
        assert body["interest"] + body["principal"] < 1438.92 + 600

    def test_reports_cumulative_principal_paid(self, client):
        loan = _create_loan(client, payment_amount=1438.92)
        body = client.get(f"/api/loans/{loan['id']}/current-payment").json()
        assert body["cumulative_principal_paid"] > 0

    def test_missing_loan_is_404(self, client):
        assert client.get("/api/loans/nope/current-payment").status_code == 404


class TestSchedule:
    def test_returns_a_paginated_window_with_whole_loan_totals(self, client):
        loan = _create_loan(client)
        body = client.get(f"/api/loans/{loan['id']}/schedule").json()

        assert len(body["periods"]) == 60          # default page
        assert body["total_periods"] == 360        # but totals span the loan
        assert body["payoff_months"] == 360
        assert body["total_interest"] > 0

    def test_first_period_interest_matches_the_hand_calculation(self, client):
        loan = _create_loan(client, payment_amount=1438.92)
        body = client.get(f"/api/loans/{loan['id']}/schedule").json()
        # 240000 * 0.06 / 12
        assert body["periods"][0]["interest"] == pytest.approx(1200.0)

    def test_paging(self, client):
        loan = _create_loan(client)
        body = client.get(
            f"/api/loans/{loan['id']}/schedule",
            params={"from_period": 100, "limit": 10},
        ).json()
        assert body["periods"][0]["period"] == 100
        assert len(body["periods"]) == 10

    def test_limit_is_capped(self, client):
        loan = _create_loan(client)
        assert client.get(
            f"/api/loans/{loan['id']}/schedule", params={"limit": 5000}
        ).status_code == 422

    def test_missing_loan_is_404(self, client):
        assert client.get("/api/loans/nope/schedule").status_code == 404


class TestWhatIf:
    def test_extra_payment_saves_time_and_interest(self, client):
        loan = _create_loan(client)
        body = client.post(
            f"/api/loans/{loan['id']}/what-if", json={"extra_monthly": 200}
        ).json()

        assert body["months_saved"] > 0
        assert body["interest_saved"] > 0
        assert body["baseline"]["payoff_months"] == 360
        assert body["accelerated"]["payoff_months"] < 360

    def test_zero_extra_is_a_no_op(self, client):
        loan = _create_loan(client)
        body = client.post(
            f"/api/loans/{loan['id']}/what-if", json={"extra_monthly": 0}
        ).json()
        assert body["months_saved"] == 0

    def test_negative_extra_rejected(self, client):
        loan = _create_loan(client)
        assert client.post(
            f"/api/loans/{loan['id']}/what-if", json={"extra_monthly": -50}
        ).status_code == 422

    def test_missing_loan_is_404(self, client):
        assert client.post(
            "/api/loans/nope/what-if", json={"extra_monthly": 100}
        ).status_code == 404


class TestPropertyDeletionKeepsLoans:
    def test_loan_survives_with_property_cleared(self, client):
        """Selling the house must not delete the mortgage record."""
        prop = _create_property(client)
        loan = _create_loan(client, prop["property_id"])

        client.delete(f"/api/properties/{prop['property_id']}")

        survivor = client.get(f"/api/loans/{loan['id']}")
        assert survivor.status_code == 200
        assert survivor.json()["property_id"] is None
