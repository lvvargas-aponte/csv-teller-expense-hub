# Teller.io Setup Scripts

These scripts help with initial Teller.io configuration and testing.

## Files:
- `index.js` - Main Teller setup script
- `setup-env.js` - Environment configuration helper
- `teller-connect-app.js` - Teller Connect integration test

## Usage:
These are optional setup scripts. The main application (in `backend/` and `frontend/`)
already includes Teller.io integration.

Only use these if you need to:
1. Test Teller.io credentials
2. Debug Teller Connect flow
3. Manually configure Teller settings

## Running:
```bash
cd scripts/teller
npm install
node index.js