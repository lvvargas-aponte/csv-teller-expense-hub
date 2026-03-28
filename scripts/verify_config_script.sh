#!/bin/bash

# Configuration Verification Script
# Checks if all required files and environment variables are properly set up

echo "🔍 Verifying csv-teller-expense-hub Configuration"
echo "=================================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
ERRORS=0
WARNINGS=0

# Check if backend/.env exists
echo "📁 Checking files..."
if [ -f "backend/.env" ]; then
    echo -e "${GREEN}✓${NC} backend/.env exists"
else
    echo -e "${RED}✗${NC} backend/.env not found"
    echo "   → Copy .env.example to backend/.env and configure it"
    ERRORS=$((ERRORS + 1))
fi

# Check if credentials.json exists
if [ -f "backend/credentials.json" ]; then
    echo -e "${GREEN}✓${NC} backend/credentials.json exists"
else
    echo -e "${RED}✗${NC} backend/credentials.json not found"
    echo "   → Download service account JSON from Google Cloud Console"
    ERRORS=$((ERRORS + 1))
fi

# Check if docker-compose.yaml exists
if [ -f "docker-compose.yaml" ]; then
    echo -e "${GREEN}✓${NC} docker-compose.yaml exists"
else
    echo -e "${RED}✗${NC} docker-compose.yaml not found"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "🔧 Checking environment variables..."

# Source the .env file if it exists
if [ -f "backend/.env" ]; then
    # Check required variables
    if grep -q "^SPREADSHEET_ID=" backend/.env && ! grep -q "^SPREADSHEET_ID=your_google_sheet_id" backend/.env; then
        echo -e "${GREEN}✓${NC} SPREADSHEET_ID is set"
    else
        echo -e "${RED}✗${NC} SPREADSHEET_ID not configured"
        echo "   → Set your Google Sheet ID in backend/.env"
        ERRORS=$((ERRORS + 1))
    fi

    if grep -q "^PERSON_1_NAME=" backend/.env && ! grep -q "^PERSON_1_NAME=Person 1" backend/.env; then
        echo -e "${GREEN}✓${NC} PERSON_1_NAME is customized"
    else
        echo -e "${YELLOW}⚠${NC} PERSON_1_NAME not customized (using default)"
        echo "   → Set to your actual name in backend/.env"
        WARNINGS=$((WARNINGS + 1))
    fi

    if grep -q "^PERSON_2_NAME=" backend/.env && ! grep -q "^PERSON_2_NAME=Person 2" backend/.env; then
        echo -e "${GREEN}✓${NC} PERSON_2_NAME is customized"
    else
        echo -e "${YELLOW}⚠${NC} PERSON_2_NAME not customized (using default)"
        echo "   → Set to your partner's/roommate's name in backend/.env"
        WARNINGS=$((WARNINGS + 1))
    fi

    # Optional Teller.io config
    if grep -q "^TELLER_APP_ID=" backend/.env && ! grep -q "^TELLER_APP_ID=your_app_id" backend/.env; then
        echo -e "${GREEN}✓${NC} Teller.io credentials configured (optional)"
    else
        echo -e "${YELLOW}⚠${NC} Teller.io not configured (optional)"
        echo "   → Only needed if you want to auto-import from connected banks"
    fi
fi

echo ""
echo "📊 Checking Google Sheet..."

# Validate credentials.json format
if [ -f "backend/credentials.json" ]; then
    if command -v jq &> /dev/null; then
        if jq empty backend/credentials.json 2>/dev/null; then
            echo -e "${GREEN}✓${NC} credentials.json is valid JSON"
            
            # Extract service account email
            SERVICE_ACCOUNT=$(jq -r '.client_email' backend/credentials.json 2>/dev/null)
            if [ ! -z "$SERVICE_ACCOUNT" ] && [ "$SERVICE_ACCOUNT" != "null" ]; then
                echo -e "${GREEN}✓${NC} Service account email: $SERVICE_ACCOUNT"
                echo "   → Make sure you shared your Google Sheet with this email!"
            fi
        else
            echo -e "${RED}✗${NC} credentials.json is not valid JSON"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${YELLOW}⚠${NC} jq not installed, skipping JSON validation"
        echo "   Install jq to validate credentials.json: brew install jq (Mac) or apt-get install jq (Linux)"
    fi
fi

echo ""
echo "🐳 Checking Docker..."

if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker is installed"
    
    if docker info &> /dev/null; then
        echo -e "${GREEN}✓${NC} Docker daemon is running"
    else
        echo -e "${RED}✗${NC} Docker daemon is not running"
        echo "   → Start Docker Desktop or docker service"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}✗${NC} Docker is not installed"
    echo "   → Install Docker from https://www.docker.com/get-started"
    ERRORS=$((ERRORS + 1))
fi

if command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker Compose is installed"
else
    echo -e "${YELLOW}⚠${NC} docker-compose command not found"
    echo "   → Try 'docker compose' instead (newer Docker versions)"
fi

echo ""
echo "=================================================="

# Summary
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed! You're ready to run:${NC}"
    echo "   docker-compose up --build"
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  Setup is valid but has $WARNINGS warning(s)${NC}"
    echo "   You can still run: docker-compose up --build"
else
    echo -e "${RED}❌ Found $ERRORS error(s) and $WARNINGS warning(s)${NC}"
    echo "   Fix the errors above before running docker-compose"
    exit 1
fi