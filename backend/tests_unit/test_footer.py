"""The settlement footer written at the bottom of a month worksheet.

The expected shape is taken from the live spreadsheet's own settled months,
which were maintained by hand for three years before sync existed:

    (blank)
                          $640.99   $1,253.26
    (blank)
        Christy pays Valeria via Zelle   $612.27
"""
from decimal import Decimal

from sheet_sync import contract, footer
from sheet_sync.gateway import InMemoryGateway

P1, P2 = "Valeria", "Christy"
HEADERS = contract.build_headers(P1, P2)
INDEX = contract.header_index_map(HEADERS, P1, P2)


def txn(txn_id, owes_1="", owes_2="", who=P1, amount="100"):
    row = [""] * len(HEADERS)
    row[INDEX["date"]] = "06/15/2026"
    row[INDEX["description"]] = "Groceries"
    row[INDEX["amount"]] = amount
    row[INDEX["who"]] = who
    row[INDEX["owes_1"]] = owes_1
    row[INDEX["owes_2"]] = owes_2
    row[INDEX["txn_id"]] = txn_id
    return row


def sheet(*rows):
    return [list(HEADERS), *rows]


def plan(rows, method=None):
    return footer.plan(rows, INDEX, person_1_name=P1, person_2_name=P2, method=method)


class TestArithmetic:
    def test_totals_are_summed_per_owes_column(self):
        f = plan(sheet(txn("a", owes_1="10.00"), txn("b", owes_2="25.50")))

        assert f.owes_1 == Decimal("10.00")
        assert f.owes_2 == Decimal("25.50")

    def test_the_net_is_the_difference_and_names_the_debtor(self):
        # Matches March 2026 on the live sheet: 1253.26 - 640.99 = 612.27.
        f = plan(sheet(txn("a", owes_1="640.99"), txn("b", owes_2="1253.26")))

        assert f.net == Decimal("612.27")
        assert f.debtor == P2
        assert f.creditor == P1

    def test_the_debtor_flips_when_person_one_owes_more(self):
        f = plan(sheet(txn("a", owes_1="200.00"), txn("b", owes_2="50.00")))

        assert f.net == Decimal("150.00")
        assert f.debtor == P1
        assert f.creditor == P2

    def test_rows_without_a_txn_id_are_not_counted(self):
        stray = [""] * len(HEADERS)
        stray[INDEX["owes_1"]] = "999.00"
        f = plan(sheet(txn("a", owes_1="10.00"), stray))

        assert f.owes_1 == Decimal("10.00")


class TestRendering:
    def test_the_sentence_matches_the_sheets_own_wording(self):
        f = plan(sheet(txn("a", owes_2="20.49")))

        assert f.sentence == "Christy pays Valeria via Zelle"

    def test_a_note_supplies_the_method(self):
        f = plan(sheet(txn("a", owes_2="20.49")), method="via Venmo")

        assert f.sentence == "Christy pays Valeria via Venmo"

    def test_money_is_written_the_way_the_sheet_writes_it(self):
        f = plan(sheet(txn("a", owes_1="640.99"), txn("b", owes_2="1253.26")))
        cells = {(u.row, u.col): u.value for u in footer.updates_for(f, INDEX)}

        assert cells[(f.totals_row, INDEX["owes_2"] + 1)] == "$1,253.26"
        assert cells[(f.settlement_row, INDEX["owes_1"] + 1)] == "$612.27"

    def test_only_the_four_convention_cells_are_written(self):
        f = plan(sheet(txn("a", owes_2="10.00")))

        assert len(footer.updates_for(f, INDEX)) == 4


class TestPlacement:
    def test_a_fresh_month_gets_a_blank_row_of_air_then_the_footer(self):
        f = plan(sheet(txn("a", owes_2="10.00"), txn("b", owes_2="5.00")))

        # Header is row 1, transactions 2 and 3.
        assert f.totals_row == 5
        assert f.settlement_row == 7

    def test_an_existing_footer_is_rewritten_in_place(self):
        rows = sheet(txn("a", owes_2="10.00"))
        blank = [""] * len(HEADERS)
        totals = [""] * len(HEADERS)
        totals[INDEX["owes_1"]] = "$0.00"
        totals[INDEX["owes_2"]] = "$10.00"
        settle = [""] * len(HEADERS)
        settle[INDEX["who"]] = "Christy pays Valeria via Zelle"
        settle[INDEX["owes_1"]] = "$10.00"
        rows += [blank, totals, blank, settle]

        f = plan(rows)

        assert (f.totals_row, f.settlement_row) == (4, 6)

    def test_rewriting_never_counts_the_previous_footer_as_transactions(self):
        rows = sheet(txn("a", owes_2="10.00"))
        blank = [""] * len(HEADERS)
        totals = [""] * len(HEADERS)
        totals[INDEX["owes_2"]] = "$10.00"
        settle = [""] * len(HEADERS)
        settle[INDEX["who"]] = "Christy pays Valeria via Zelle"
        settle[INDEX["owes_1"]] = "$10.00"
        rows += [blank, totals, blank, settle]

        f = plan(rows)

        assert f.owes_2 == Decimal("10.00")   # not 20.00

    def test_writing_twice_leaves_one_footer(self):
        gw = InMemoryGateway({"June 2026": sheet(txn("a", owes_2="10.00"))})

        for _ in range(2):
            rows = gw.read_rows("June 2026")
            footer.write(gw, "June 2026", rows, INDEX, person_1_name=P1, person_2_name=P2)

        rows = gw.read_rows("June 2026")
        sentences = [
            r[INDEX["who"]] for r in rows
            if len(r) > INDEX["who"] and "pays" in r[INDEX["who"]]
        ]
        assert len(sentences) == 1


class TestTitles:
    def test_settling_appends_the_pif_suffix(self):
        assert footer.settled_title("June 2026") == "June 2026 - PIF"

    def test_settling_twice_does_not_double_the_suffix(self):
        assert footer.settled_title("June 2026 - PIF") == "June 2026 - PIF"

    def test_reopening_strips_it_again(self):
        assert footer.unsettled_title("June 2026 - PIF") == "June 2026"

    def test_stripping_a_plain_title_is_a_no_op(self):
        assert footer.unsettled_title("June 2026") == "June 2026"

    def test_a_renamed_tab_still_resolves_to_its_period(self):
        from sheet_sync import worksheet

        # The rename must not hide the month from find_worksheet.
        assert worksheet.title_to_period("June 2026 - PIF") == "2026-06"
        assert worksheet.is_settled_title("June 2026 - PIF") is True


class TestRename:
    def test_renaming_moves_the_rows_and_frees_the_old_title(self):
        gw = InMemoryGateway({"June 2026": sheet(txn("a"))})

        gw.rename_worksheet("June 2026", "June 2026 - PIF")

        assert gw.list_worksheets() == ["June 2026 - PIF"]
        assert len(gw.read_rows("June 2026 - PIF")) == 2

    def test_renaming_onto_an_existing_title_is_refused(self):
        import pytest
        from sheet_sync.gateway import WorksheetExists

        gw = InMemoryGateway({"June 2026": sheet(), "June 2026 - PIF": sheet()})

        with pytest.raises(WorksheetExists):
            gw.rename_worksheet("June 2026", "June 2026 - PIF")
