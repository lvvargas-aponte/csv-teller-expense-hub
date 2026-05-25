# Teller (bank sync)

> Source: `backend/routers/teller.py`, `frontend/src/components/accounts/AccountsModal.js`

[Teller.io](https://teller.io) provides the bank connection used by **Sync Banks** and the **Linked Accounts** modal.

## One-time setup

1. Sign up at [Teller.io](https://teller.io) and create an application.
2. Copy your **Application ID** into `.env`:
   ```bash
   TELLER_APP_ID=your_app_id
   ```
3. Choose your environment:
   ```bash
   TELLER_ENVIRONMENT=sandbox       # sandbox | development | production
   ```
4. **Leave `TELLER_API_KEY` blank** — access tokens are saved automatically when you connect a bank from the UI.

## Environments

| Environment | Real banks? | Certs required? |
|---|---|---|
| `sandbox` | No (test data) | No |
| `development` | Yes (limited) | Yes — mTLS cert + key |
| `production` | Yes | Yes — mTLS cert + key |

For `development` and `production`, place your Teller-issued certificates and set:

```bash
TELLER_CERT_PATH=./certs/certificate.pem
TELLER_KEY_PATH=./certs/private_key.pem
```

In Docker these are mounted read-only at `/app/certs/` (see `docker-compose.yaml`).

## Sandbox credentials

When testing in sandbox, the Teller Connect popup accepts:

- Username: `user_good`
- Password: `pass_good`

## Connecting a bank

See the [Linked Accounts modal](../modals/accounts-modal.md) for the click-by-click flow.

## How tokens are stored

Each connected enrollment creates one access token. Tokens are persisted to the `TELLER_API_KEY` env var (comma-separated) and reloaded on next start. The backend logs a warning at startup if any tokens look like test stubs (`tok_abc…`, `tok_one`, `tok_two`, etc.); run `py backend/scripts/prune_tokens.py` to clean them out.

See also: [Bank sync concept](../concepts/bank-sync.md).
