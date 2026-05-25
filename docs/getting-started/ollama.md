# Ollama (AI features)

> Source: `backend/llm_client.py`, `backend/routers/advisor.py`, `backend/routers/insights.py`, `backend/routers/tools.py`

The app uses a **local** Ollama LLM for three features. It runs fine without Ollama — those features show a setup nudge instead of an error.

| Feature | Endpoint | Where it shows up |
|---|---|---|
| Spending Insights | `POST /api/insights/spending-summary` | Finances → Overview |
| AI Payoff Advice | `POST /api/tools/payoff-advice` | Finances → Overview → Payoff Planner |
| Virtual Advisor (chat) | `POST /api/advisor/chat` | Finances → AI Advisor |

## Install

=== "macOS / Linux"
    ```bash
    curl -fsSL https://ollama.com/install.sh | sh
    ```
=== "Windows"
    Download from <https://ollama.com/download>. Installs `ollama` to PowerShell / cmd.

## Pull a model

The default is **`qwen2.5:14b-instruct`** — strong on numeric/finance reasoning, ~10 GB VRAM quantized.

```bash
ollama pull qwen2.5:14b-instruct
```

| Model | VRAM | Best for |
|---|---|---|
| `qwen2.5:14b-instruct` (default) | ~9 GB | RTX 3060 12GB / 4070 / 4080+ |
| `qwen2.5:7b-instruct` | ~5 GB | Lighter, still strong |
| `llama3.1:8b-instruct` | ~5 GB | Proven baseline |
| `llama3.2:3b` | ~2 GB | CPU fallback |

Override per-deployment:

```bash
OLLAMA_MODEL=qwen2.5:7b-instruct        # insights + payoff advice
OLLAMA_CHAT_MODEL=qwen2.5:14b-instruct  # advisor chat (defaults to OLLAMA_MODEL)
```

## Run the server

```bash
ollama serve
```

Default port: **11434**. From Docker the backend reaches it via `host.docker.internal:11434` (set in `docker-compose.yaml`).

## Verify

```bash
ollama list
curl http://localhost:11434/api/tags
```

## When the app can't reach Ollama

- Insights / Payoff Advice show a **"start Ollama" nudge card** instead of failing.
- The advisor chat returns a clear error message.
- See [Troubleshooting](../reference/troubleshooting.md#ai-features-not-working).
