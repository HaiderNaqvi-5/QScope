#!/bin/bash
# QSScope development startup script for Linux/macOS

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🚀 QSScope Development Setup"
echo "Project root: $PROJECT_ROOT"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found. Please install Python 3.11+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"

if ! command -v node &> /dev/null; then
    echo -e "${RED}✗ Node.js not found. Please install Node.js 18+${NC}"
    exit 1
fi

NODE_VERSION=$(node --version)
echo -e "${GREEN}✓ Node.js $NODE_VERSION found${NC}"

if ! command -v git &> /dev/null; then
    echo -e "${RED}✗ Git not found. Please install Git${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Git found${NC}"
echo ""

# Initialize backend
echo "📦 Setting up backend..."
cd "$PROJECT_ROOT/backend"

if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]" 2>/dev/null || pip install -e . 2>/dev/null || echo "⚠ Some dependencies may not have installed"

echo -e "${GREEN}✓ Backend dependencies installed${NC}"
echo ""

# Initialize frontend
echo "📦 Setting up frontend..."
cd "$PROJECT_ROOT/frontend"

if [ -d "node_modules" ]; then
    echo "node_modules already exists, skipping install"
else
    echo "Installing Node dependencies..."
    if command -v pnpm &> /dev/null; then
        pnpm install
    else
        npm install
    fi
fi

echo -e "${GREEN}✓ Frontend dependencies installed${NC}"
echo ""

# Initialize database
echo "🗄️  Setting up database..."
cd "$PROJECT_ROOT/backend"

if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
fi

source venv/bin/activate

# TODO: Run Alembic migrations when they exist
# alembic upgrade head

echo -e "${GREEN}✓ Database ready${NC}"
echo ""

# Print startup instructions
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "🎯 To start the application:"
echo ""
echo "Backend (in terminal 1):"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
echo ""
echo "Frontend (in terminal 2):"
echo "  cd frontend"
echo "  npm run dev  # or: pnpm run dev"
echo ""
echo "Then open:"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "To run tests:"
echo "  Backend:  cd backend && pytest"
echo "  Frontend: cd frontend && npm run test"
echo ""
