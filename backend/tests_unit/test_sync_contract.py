"""Unit tests for the sheet column contract. Pure — no DB, no network."""
from datetime import date
from decimal import Decimal

import pytest

from sheet_sync import contract


class TestHeaders:
    def test_build_headers_uses_the_live_sheet_phrasing(self):
        headers = contract.build_headers("Valeria", "Christy")
        assert headers[:8] == [
            "Transaction Date",
            "Description",
            "Amount",
            "Who",
            "What Valeria Owes",
            "What Christy Owes",
            "Notes",
            "Reviewed",
        ]
        assert headers[8:] == [
            "Dispute",
            "Dispute By",
            "Dispute Note",
            "Txn ID",
            "Owner",
            "Carried From",
        ]

    def test_header_index_map_resolves_logical_keys(self):
        headers = contract.build_headers("Valeria", "Christy")
        idx = contract.header_index_map(headers, "Valeria", "Christy")
        assert idx["date"] == 0
        assert idx["owes_1"] == 4
        assert idx["owes_2"] == 5
        assert idx["notes"] == 6
        assert idx["reviewed"] == 7
        assert idx["dispute"] == 8
        assert idx["txn_id"] == 11
        assert idx["owner"] == 12
        assert idx["carried_from"] == 13

    def test_header_index_map_tolerates_reordering(self):
        """Lookup is by name, so a reordered sheet must still resolve."""
        headers = contract.build_headers("Valeria", "Christy")
        swapped = headers[:]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        idx = contract.header_index_map(swapped, "Valeria", "Christy")
        assert idx["description"] == 0
        assert idx["date"] == 1

    def test_header_index_map_tolerates_surrounding_whitespace(self):
        headers = [h + " " for h in contract.build_headers("Valeria", "Christy")]
        idx = contract.header_index_map(headers, "Valeria", "Christy")
        assert idx["amount"] == 2

    def test_missing_required_header_raises(self):
        headers = contract.build_headers("Valeria", "Christy")
        del headers[4]
        with pytest.raises(contract.ContractError) as exc:
            contract.header_index_map(headers, "Valeria", "Christy")
        assert "What Valeria Owes" in str(exc.value)

    def test_duplicate_header_raises(self):
        """A re-run adoption that double-adds a column would otherwise bind the
        contract silently to the second, empty one."""
        headers = contract.build_headers("Valeria", "Christy")
        headers.append("Txn ID")
        with pytest.raises(contract.ContractError) as exc:
            contract.header_index_map(headers, "Valeria", "Christy")
        assert "Txn ID" in str(exc.value)

    def test_blank_trailing_columns_are_not_duplicates(self):
        headers = contract.build_headers("Valeria", "Christy") + ["", "", "  "]
        idx = contract.header_index_map(headers, "Valeria", "Christy")
        assert idx["carried_from"] == 13

    def test_mismatched_person_name_raises(self):
        """The other instance named the column differently — a hard stop."""
        headers = contract.build_headers("Valeria", "Christy")
        with pytest.raises(contract.ContractError):
            contract.header_index_map(headers, "Valeria", "Christina")


class TestParseAmount:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("$456.86", Decimal("456.86")),
            ("51.3", Decimal("51.3")),
            ("26.825", Decimal("26.825")),
            ("$1,234.56", Decimal("1234.56")),
            ("  $80.00  ", Decimal("80.00")),
            ("-$5.00", Decimal("-5.00")),
        ],
    )
    def test_parses_the_formats_the_live_sheet_uses(self, raw, expected):
        assert contract.parse_amount(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_blank_is_none_not_zero(self, raw):
        """Blank means untriaged. Returning 0 would silently settle a debt."""
        assert contract.parse_amount(raw) is None

    def test_unparseable_raises(self):
        with pytest.raises(contract.ContractError):
            contract.parse_amount("about twenty quid")

    def test_returns_decimal_not_float(self):
        assert isinstance(contract.parse_amount("0.1"), Decimal)


class TestFormatAmount:
    def test_formats_two_places(self):
        assert contract.format_amount(Decimal("456.8")) == "456.80"

    def test_none_is_blank(self):
        assert contract.format_amount(None) == ""

    def test_preserves_sub_cent_input_by_rounding_half_up(self):
        assert contract.format_amount(Decimal("26.825")) == "26.83"


class TestParseDate:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("3/31/2026", date(2026, 3, 31)),
            ("03/29/2026", date(2026, 3, 29)),
            ("2026-03-01", date(2026, 3, 1)),
            ("5/6/26", date(2026, 5, 6)),
            ("  4/5/2026 ", date(2026, 4, 5)),
        ],
    )
    def test_parses_every_format_present_in_the_live_sheet(self, raw, expected):
        assert contract.parse_date(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_blank_is_none(self, raw):
        assert contract.parse_date(raw) is None

    def test_unparseable_raises(self):
        with pytest.raises(contract.ContractError):
            contract.parse_date("last tuesday")


class TestFormatDate:
    def test_always_writes_one_canonical_format(self):
        assert contract.format_date(date(2026, 6, 5)) == "06/05/2026"


class TestBools:
    @pytest.mark.parametrize("raw", ["TRUE", "true", "True", "YES", "y", "1", "x"])
    def test_truthy_spellings(self, raw):
        assert contract.parse_bool(raw) is True

    @pytest.mark.parametrize("raw", ["", "   ", "FALSE", "false", "no", "0", None])
    def test_falsy_spellings(self, raw):
        assert contract.parse_bool(raw) is False

    def test_format_bool(self):
        assert contract.format_bool(True) == "TRUE"
        assert contract.format_bool(False) == ""


class TestTxnId:
    def test_round_trips(self):
        owner = "11111111-1111-1111-1111-111111111111"
        tid = contract.make_txn_id(owner, "discover_2026-06-01_-4.5_STARBUCKS")
        assert contract.split_txn_id(tid) == (
            owner,
            "discover_2026-06-01_-4.5_STARBUCKS",
        )

    def test_transaction_ids_containing_colons_survive(self):
        """Split on the FIRST colon only — local ids may contain colons."""
        owner = "11111111-1111-1111-1111-111111111111"
        tid = contract.make_txn_id(owner, "a:b:c")
        assert contract.split_txn_id(tid) == (owner, "a:b:c")

    def test_malformed_raises(self):
        with pytest.raises(contract.ContractError):
            contract.split_txn_id("no-colon-here")


class TestWriterPartition:
    def test_owner_and_disputer_key_sets_are_disjoint(self):
        assert not set(contract.OWNER_KEYS) & set(contract.DISPUTER_KEYS)

    def test_together_they_cover_every_column(self):
        headers = contract.build_headers("Valeria", "Christy")
        idx = contract.header_index_map(headers, "Valeria", "Christy")
        assert set(contract.OWNER_KEYS) | set(contract.DISPUTER_KEYS) == set(idx)

    def test_dispute_columns_belong_to_the_disputer(self):
        assert set(contract.DISPUTER_KEYS) == {"dispute", "dispute_by", "dispute_note"}
