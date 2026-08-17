"""The hidden _sync worksheet — machine state inside a human's spreadsheet."""
from sheet_sync import sync_sheet
from sheet_sync.gateway import InMemoryGateway
from sheet_sync.guards import Claim

ME = Claim(
    user_id="11111111-1111-1111-1111-111111111111",
    display_name="Valeria",
    person_slot=1,
    contract_version="1.0",
    person_1_name="Valeria",
    person_2_name="Christy",
)
PEER = Claim(
    user_id="22222222-2222-2222-2222-222222222222",
    display_name="Christy",
    person_slot=2,
    contract_version="1.0",
    person_1_name="Valeria",
    person_2_name="Christy",
)


class TestEnsure:
    def test_creates_headers_and_hides_the_worksheet(self):
        gw = InMemoryGateway({"June 2026": [["Transaction Date"]]})
        sync_sheet.ensure_sync_worksheet(gw)

        assert gw.read_rows(sync_sheet.SYNC_TITLE) == [sync_sheet.SYNC_HEADERS]
        assert sync_sheet.SYNC_TITLE in gw.hidden

    def test_is_idempotent_and_preserves_existing_rows(self):
        gw = InMemoryGateway({})
        sync_sheet.ensure_sync_worksheet(gw)
        sync_sheet.write_claim(gw, ME)
        sync_sheet.ensure_sync_worksheet(gw)

        assert len(gw.read_rows(sync_sheet.SYNC_TITLE)) == 2
        assert [c.user_id for c in sync_sheet.read_claims(gw)] == [ME.user_id]

    def test_repairs_a_worksheet_that_exists_without_headers(self):
        gw = InMemoryGateway({sync_sheet.SYNC_TITLE: []})
        sync_sheet.ensure_sync_worksheet(gw)

        assert gw.read_rows(sync_sheet.SYNC_TITLE) == [sync_sheet.SYNC_HEADERS]


class TestClaims:
    def test_round_trips_a_claim(self):
        gw = InMemoryGateway({})
        sync_sheet.ensure_sync_worksheet(gw)
        sync_sheet.write_claim(gw, ME)

        assert sync_sheet.read_claims(gw) == [ME]

    def test_rewriting_a_claim_updates_in_place(self):
        gw = InMemoryGateway({})
        sync_sheet.ensure_sync_worksheet(gw)
        sync_sheet.write_claim(gw, ME)
        renamed = Claim(**{**ME.__dict__, "display_name": "Val"})
        sync_sheet.write_claim(gw, renamed)

        claims = sync_sheet.read_claims(gw)
        assert len(claims) == 1
        assert claims[0].display_name == "Val"

    def test_two_instances_each_keep_their_own_row(self):
        gw = InMemoryGateway({})
        sync_sheet.ensure_sync_worksheet(gw)
        sync_sheet.write_claim(gw, ME)
        sync_sheet.write_claim(gw, PEER)

        assert {c.user_id for c in sync_sheet.read_claims(gw)} == {ME.user_id, PEER.user_id}

    def test_period_rows_are_ignored_by_read_claims(self):
        """Sub-project C writes those; sync must not mistake one for an instance."""
        gw = InMemoryGateway({})
        sync_sheet.ensure_sync_worksheet(gw)
        sync_sheet.write_claim(gw, ME)
        gw.append_rows(sync_sheet.SYNC_TITLE, [["period", "2026-06", PEER.user_id]])

        assert [c.user_id for c in sync_sheet.read_claims(gw)] == [ME.user_id]

    def test_read_claims_on_a_missing_worksheet_is_empty(self):
        assert sync_sheet.read_claims(InMemoryGateway({})) == []

    def test_a_short_row_does_not_crash_the_reader(self):
        gw = InMemoryGateway({})
        sync_sheet.ensure_sync_worksheet(gw)
        gw.append_rows(sync_sheet.SYNC_TITLE, [["claim", "", PEER.user_id, "Christy"]])

        claims = sync_sheet.read_claims(gw)
        assert claims[0].person_slot == 0
        assert claims[0].contract_version == ""
