"""Type/subtype inference for SimpleFIN accounts.

SimpleFIN's protocol carries no account-type field, so ``infer_account_bucket``
guesses from the account and institution names. These cases pin the guesses
that matter: a brokerage must not be filed as cash, and a card must stay a
liability even when the institution is a brokerage.
"""
import pytest

from simplefin import infer_account_bucket


@pytest.mark.parametrize("name, org, expected", [
    # Investment wrappers — the reason this classifier grew an investment arm.
    ("Individual Brokerage (9423)", "E*Trade",   ("investment", "brokerage")),
    ("Restricted Stock - NTRA",     "E*Trade",   ("investment", "brokerage")),
    ("NATERA 401(K) PLAN",          "Fidelity",  ("investment", "brokerage")),
    ("Roth IRA",                    "Vanguard",  ("investment", "brokerage")),
    ("Rollover IRA Savings",        "Fidelity",  ("investment", "brokerage")),
    ("HSA",                         "Optum",     ("investment", "brokerage")),
    # Cash and credit keep their old answers.
    ("TOTAL CHECKING (7606)",       "Chase",     ("depository", "checking")),
    ("High Yield Savings 3.30% APY", "Synchrony", ("depository", "savings")),
    ("Amex EveryDay® Card",         "American Express", ("credit", "credit_card")),
    ("Prime Visa",                  "Chase",     ("credit", "credit_card")),
    ("Auto Loan",                   "Ally",      ("credit", "loan")),
])
def test_buckets(name, org, expected):
    assert infer_account_bucket(name, org) == expected


def test_credit_wins_over_investment():
    """A brokerage's own credit card is still a liability, not a holding."""
    assert infer_account_bucket("Brokerage Rewards Card", "Fidelity") == ("credit", "credit_card")


@pytest.mark.parametrize("name", ["Admiral Checking", "Kiran Household", "Miracle Fund Checking"])
def test_short_investment_tokens_do_not_match_inside_words(name):
    """'ira' and friends are matched on word boundaries — a substring match
    would file half the depository accounts in the country as brokerages."""
    assert infer_account_bucket(name, "Some Bank")[0] == "depository"


@pytest.mark.parametrize("subtype", ["home", "vehicle", "other", ""])
def test_asset_type_is_its_own_bucket(subtype):
    """A house is neither spendable cash nor a tradeable holding."""
    from analytics import classify_account_bucket

    assert classify_account_bucket("asset", subtype) == "real_asset"
