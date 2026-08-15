FROM node:18-alpine

WORKDIR /app

# Optional local root CA (e.g. corporate/antivirus TLS-inspection proxy).
# docker-ca/extra-ca.pem is an empty placeholder by default so this is a
# no-op; populate it locally (not committed) if npm can't reach the
# network due to SSL interception.
COPY docker-ca/extra-ca.pem /usr/local/share/ca-certificates/extra-ca.pem
ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/extra-ca.pem

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Expose port
EXPOSE 3000

# Start the development server
CMD ["npm", "start"]