"""Tests for gsheet_integration.py"""
import pytest

from gsheet_integration import GoogleSheetsClient, AuthenticationError


# ---------------------------------------------------------------------------
# GoogleSheetsClient authentication
# ---------------------------------------------------------------------------

class TestGoogleSheetsClient:
    def test_raises_auth_error_when_credentials_missing(self, tmp_path):
        """Attempting to authenticate with a missing file must raise AuthenticationError."""
        client = GoogleSheetsClient(credentials_file=str(tmp_path / "does_not_exist.json"))
        with pytest.raises(AuthenticationError, match="credentials file not found"):
            client.get_client()

    def test_raises_auth_error_on_invalid_credentials(self, tmp_path):
        """A file that exists but contains invalid JSON must raise AuthenticationError."""
        bad_creds = tmp_path / "creds.json"
        bad_creds.write_text("{not valid json")
        client = GoogleSheetsClient(credentials_file=str(bad_creds))
        with pytest.raises(AuthenticationError):
            client.get_client()
