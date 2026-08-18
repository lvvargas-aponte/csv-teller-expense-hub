"""One-time adoption of the June and July 2026 worksheets."""
import pytest

from sheet_sync import adoption, worksheet
from sheet_sync.gateway import InMemoryGateway

ME = "11111111-1111-1111-1111-111111111111"
PEER = "22222222-2222-2222-2222-222222222222"
P1, P2 = "Valeria", "Christy"
SLOTS = {1: ME, 2: PEER}

LEGACY_HEADERS = [
    "Transaction Date", "Description", "Amount", "Who",
    f"What {P1} Owes", f"What {P2} Owes", "Notes",
]


def legacy_sheet(*rows):
    return {"June 2026": [list(LEGACY_HEADERS), *[list(r) for r in rows]]}


def plan(gw, local=()):
    return adoption.plan_adoption(gw, "2026-06", SLOTS, P1, P2, list(local))


class TestPlan:
    def test_names_the_backup_with_a_leading_underscore(self):
        """Without it the backup resolves to 2026-06 too and sync could write into it."""
        p = plan(InMemoryGateway(legacy_sheet()))

        assert p.backup_title == "_backup June 2026"
        assert worksheet.title_to_period(p.backup_title) is None

    def test_lists_the_missing_headers(self):
        p = plan(InMemoryGateway(legacy_sheet()))

        assert p.header_additions == [
            "Reviewed", "Dispute", "Dispute By", "Dispute Note",
            "Txn ID", "Owner", "Carried From",
        ]

    def test_derives_owner_and_txn_id_from_who(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        row = plan(gw).rows[0]

        assert row.owner == PEER
        assert row.txn_id.startswith(f"{PEER}:")

    def test_a_blank_split_becomes_5050_in_the_non_payers_column(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        row = plan(gw).rows[0]

        assert row.owes_column == f"What {P1} Owes"
        assert row.owes_value == "56.13"

    def test_an_existing_split_is_left_alone(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Dinner", "$113.45", P2, "$37.82", "", ""],
        ))
        row = plan(gw).rows[0]

        assert row.owes_column is None
        assert "split" not in " ".join(row.actions).lower()

    def test_a_row_without_a_usable_who_is_unresolved_not_guessed(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Mystery", "$40.00", "", "", "", ""],
            ["6/2/2026", "Also Mystery", "$40.00", "Mom", "", "", ""],
        ))
        p = plan(gw)

        assert p.rows == []
        assert [r.description for r in p.unresolved] == ["Mystery", "Also Mystery"]

    def test_binds_a_confident_match_to_the_real_transaction(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Groceries", "$112.25", P1, "", "", ""],
        ))
        local = [("t-real", {"date": "06/01/2026", "amount": -112.25,
                             "description": "GROCERIES"})]
        row = plan(gw, local).rows[0]

        assert row.bound_transaction_id == "t-real"
        assert row.manual_only is False
        assert row.txn_id == f"{ME}:t-real"

    def test_an_unmatched_row_gets_a_synthetic_manual_only_id(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Cleaning", "$150.00", P1, "", "", ""],
        ))
        row = plan(gw).rows[0]

        assert row.manual_only is True
        assert "manual" in row.txn_id

    def test_a_row_that_already_carries_a_txn_id_is_skipped(self):
        headers = LEGACY_HEADERS + [
            "Reviewed", "Dispute", "Dispute By", "Dispute Note",
            "Txn ID", "Owner", "Carried From",
        ]
        gw = InMemoryGateway({"June 2026": [
            headers,
            ["6/1/2026", "Done", "$10.00", P1, "", "5.00", "", "TRUE",
             "", "", "", f"{ME}:t9", ME, ""],
        ]})

        assert plan(gw).rows == []


class TestRender:
    def test_prints_every_intended_change(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        text = adoption.render_plan(plan(gw))

        assert "_backup June 2026" in text
        assert "Phone Bill" in text
        assert "56.13" in text
        assert "50/50" in text

    def test_calls_out_the_split_risk(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        assert "uneven" in adoption.render_plan(plan(gw)).lower()

    def test_lists_unresolved_rows_for_the_user(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Mystery", "$40.00", "", "", "", ""],
        ))
        text = adoption.render_plan(plan(gw))

        assert "Mystery" in text
        assert "row 2" in text.lower()


class TestApply:
    def test_planning_alone_writes_nothing(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        before = gw.read_rows("June 2026")
        plan(gw)

        assert gw.read_rows("June 2026") == before
        assert gw.list_worksheets() == ["June 2026"]

    def test_apply_backs_up_first(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        original = [list(r) for r in gw.read_rows("June 2026")]
        adoption.apply_adoption(gw, plan(gw))

        assert gw.read_rows("_backup June 2026") == original

    def test_apply_writes_headers_and_row_values(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        adoption.apply_adoption(gw, plan(gw))

        rows = gw.read_rows("June 2026")
        header = rows[0]
        assert header[-1] == "Carried From"

        row = rows[1]
        assert row[header.index("Owner")] == PEER
        assert row[header.index(f"What {P1} Owes")] == "56.13"
        assert row[header.index(f"What {P2} Owes")] == ""
        assert row[header.index("Reviewed")] == "TRUE"

    def test_apply_leaves_columns_a_to_g_untouched(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Dinner", "$113.45", P2, "$37.82", "", "one third"],
        ))
        adoption.apply_adoption(gw, plan(gw))

        row = gw.read_rows("June 2026")[1]
        assert row[:7] == ["6/1/2026", "Dinner", "$113.45", P2, "$37.82", "", "one third"]

    def test_apply_is_idempotent(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        adoption.apply_adoption(gw, plan(gw))
        after_first = [list(r) for r in gw.read_rows("June 2026")]

        second = adoption.apply_adoption(gw, plan(gw))

        assert second == 0
        assert gw.read_rows("June 2026") == after_first

    def test_apply_does_not_write_unresolved_rows(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Mystery", "$40.00", "", "", "", ""],
        ))
        adoption.apply_adoption(gw, plan(gw))

        row = gw.read_rows("June 2026")[1]
        assert row == ["6/1/2026", "Mystery", "$40.00", "", "", "", ""]

    def test_a_second_backup_does_not_clobber_the_first(self):
        gw = InMemoryGateway(legacy_sheet(
            ["6/1/2026", "Phone Bill", "$112.25", P2, "", "", ""],
        ))
        adoption.apply_adoption(gw, plan(gw))
        first_backup = [list(r) for r in gw.read_rows("_backup June 2026")]

        adoption.apply_adoption(gw, plan(gw))

        assert gw.read_rows("_backup June 2026") == first_backup
