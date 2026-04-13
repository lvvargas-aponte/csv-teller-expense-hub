"""
Tests for the two new Teller Connect endpoints:
  GET  /api/config/teller
  POST /api/teller/register-token
"""
from unittest.mock import patch

# Seed env before importing the app so config reads the test values
import os
os.environ.setdefault("TELLER_APP_ID", "test_app_id")
os.environ.setdefault("TELLER_ENVIRONMENT", "sandbox")
os.environ.setdefault("TELLER_API_KEY", "")

from fastapi.testclient import TestClient
import main as app_module
from main import app, TELLER_ACCESS_TOKENS

client = TestClient(app)


def _clear_tokens():
    TELLER_ACCESS_TOKENS.clear()


# ── GET /api/config/teller ────────────────────────────────────────────────────

class TestGetTellerConfig:
    def test_returns_app_id_and_environment(self):
        with patch.object(app_module, "TELLER_APP_ID", "test_app_id"), \
             patch.object(app_module, "TELLER_ENVIRONMENT", "sandbox"):
            resp = client.get("/api/config/teller")
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == "test_app_id"
        assert data["environment"] == "sandbox"

    def test_503_when_app_id_not_configured(self):
        with patch.object(app_module, "TELLER_APP_ID", None):
            resp = client.get("/api/config/teller")
        assert resp.status_code == 503
        assert "TELLER_APP_ID" in resp.json()["detail"]


# ── POST /api/teller/register-token ──────────────────────────────────────────

class TestRegisterToken:
    def setup_method(self):
        _clear_tokens()

    def _post(self, token="tok_abc123", enrollment_id="enr_1", institution="First Bank"):
        return client.post("/api/teller/register-token", json={
            "access_token": token,
            "enrollment_id": enrollment_id,
            "institution": institution,
        })

    def test_new_token_returns_201_and_registered_true(self, tmp_path):
        env_file = tmp_path / ".env"
        log_file = tmp_path / "teller-tokens.log"

        with patch("main.Path") as MockPath:
            def resolve(base):
                # Called as Path(__file__).parent.parent / ".env" etc.
                # Return tmp paths for .env and .log
                class FakePath:
                    def __truediv__(self, name):
                        if name == ".env":
                            return env_file
                        return log_file
                    def exists(self):
                        return False
                    def read_text(self, **kw):
                        return ""
                    def write_text(self, content, **kw):
                        env_file.write_text(content, **kw)
                    def open(self, mode, **kw):
                        return log_file.open(mode, **kw)
                return FakePath()
            MockPath.return_value = resolve(None)
            MockPath.side_effect = resolve

            resp = self._post()

        assert resp.status_code == 201
        data = resp.json()
        assert data["registered"] is True
        assert data["total_tokens"] == 1
        assert "tok_abc123" in TELLER_ACCESS_TOKENS

    def test_duplicate_token_returns_registered_false(self):
        TELLER_ACCESS_TOKENS.append("tok_existing")
        resp = self._post(token="tok_existing")

        assert resp.status_code == 201
        assert resp.json()["registered"] is False
        assert resp.json()["reason"] == "duplicate"
        assert TELLER_ACCESS_TOKENS.count("tok_existing") == 1

    def test_empty_token_returns_422(self):
        resp = self._post(token="   ")
        assert resp.status_code == 422

    def test_blank_string_token_returns_422(self):
        resp = self._post(token="")
        # Pydantic will flag missing/empty required field
        assert resp.status_code in (422, 400)

    def test_new_token_appended_to_memory_list(self, tmp_path):
        env_file = tmp_path / ".env"
        log_file = tmp_path / "teller-tokens.log"

        with patch("main.Path") as MockPath:
            class FakePath:
                def __truediv__(self, name):
                    if name == ".env":
                        return env_file
                    return log_file
                def exists(self):
                    return False
                def read_text(self, **kw):
                    return ""
                def write_text(self, content, **kw):
                    env_file.write_text(content, **kw)
                def open(self, mode, **kw):
                    return log_file.open(mode, **kw)
            MockPath.return_value = FakePath()
            MockPath.side_effect = lambda *a: FakePath()

            self._post(token="tok_one")
            self._post(token="tok_two")

        assert "tok_one" in TELLER_ACCESS_TOKENS
        assert "tok_two" in TELLER_ACCESS_TOKENS
        assert len(TELLER_ACCESS_TOKENS) == 2
