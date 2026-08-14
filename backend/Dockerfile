FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Optional local root CA (e.g. corporate/antivirus TLS-inspection proxy).
# docker-ca/extra-ca.pem is an empty placeholder by default so this is a
# no-op; populate it locally (not committed) if pip can't reach the
# network due to SSL interception.
COPY docker-ca/extra-ca.pem /usr/local/share/ca-certificates/extra-ca.crt
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# entrypoint.sh runs `alembic upgrade head` before starting uvicorn.
# Invoked via `sh` so the execute bit isn't required (Windows-friendly).
CMD ["sh", "entrypoint.sh"]
