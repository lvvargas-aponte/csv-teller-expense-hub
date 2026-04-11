import pytest
from fastapi.testclient import TestClient

# Must be imported AFTER sys.path is set up by pytest running from backend/
from main import app, stored_transactions


@pytest.fixture(autouse=True)
def clear_storage():
    """Clear in-memory storage before and after every test to prevent state leakage."""
    stored_transactions.clear()
    yield
    stored_transactions.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_discover_csv() -> str:
    return (
        "Trans. Date,Post Date,Description,Amount,Category\n"
        "01/15/2024,01/16/2024,STARBUCKS,-4.50,Restaurants\n"
        "01/16/2024,01/17/2024,AMAZON PRIME,-29.99,Shopping\n"
    )


@pytest.fixture
def sample_barclays_csv() -> str:
    return (
        "Barclays Bank Delaware\n"
        "Account Number: 1234567890123456\n"
        "Account Balance as of 01/31/2024: $1234.56\n"
        "\n"
        "Transaction Date,Description,Category,Amount\n"
        "01/15/2024,WHOLE FOODS,DEBIT,-67.23\n"
        "01/16/2024,NETFLIX,DEBIT,-15.99\n"
    )


@pytest.fixture
def sample_transaction_dict() -> dict:
    return {
        "id": "discover_2024-01-15_-4.5_STARBUCKS",
        "transaction_id": "discover_2024-01-15_-4.5_STARBUCKS",
        "date": "2024-01-15",
        "description": "STARBUCKS",
        "amount": -4.50,
        "source": "discover",
        "is_shared": False,
        "who": None,
        "what": None,
        "person_1_owes": 0.0,
        "person_2_owes": 0.0,
        "notes": "",
    }
