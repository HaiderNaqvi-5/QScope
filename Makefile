# QSScope Development Makefile

.PHONY: help install dev backend frontend test lint format clean bootstrap

help:
	@echo "QSScope Development Commands"
	@echo ""
	@echo "make install      - Install dependencies (backend + frontend)"
	@echo "make dev          - Start development servers (requires 2 terminals)"
	@echo "make backend      - Start backend server only"
	@echo "make frontend     - Start frontend server only"
	@echo "make test         - Run all tests"
	@echo "make test-backend - Run backend tests"
	@echo "make test-frontend - Run frontend tests"
	@echo "make lint         - Run linters (backend + frontend)"
	@echo "make lint-backend - Lint backend code"
	@echo "make lint-frontend - Lint frontend code"
	@echo "make format       - Format code (backend + frontend)"
	@echo "make format-backend - Format backend code"
	@echo "make format-frontend - Format frontend code"
	@echo "make clean        - Remove build artifacts and caches"
	@echo "make bootstrap    - Run bootstrap setup"
	@echo "make preflight    - Run preflight checks"

preflight:
	python3 scripts/preflight.py

install: install-backend install-frontend

install-backend:
	cd backend && python3 -m venv venv && source venv/bin/activate && pip install -e ".[dev]"

install-frontend:
	cd frontend && npm install || pnpm install

dev:
	@echo "Starting QSScope development servers..."
	@echo "Backend will run on http://127.0.0.1:8000"
	@echo "Frontend will run on http://127.0.0.1:3000"
	@echo ""
	@echo "Run in separate terminals:"
	@echo "  Terminal 1: make backend"
	@echo "  Terminal 2: make frontend"

backend:
	cd backend && source venv/bin/activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev || pnpm run dev

test: test-backend test-frontend

test-backend:
	cd backend && source venv/bin/activate && pytest -v

test-frontend:
	cd frontend && npm run test || pnpm run test

lint: lint-backend lint-frontend

lint-backend:
	cd backend && source venv/bin/activate && ruff check . && mypy app

lint-frontend:
	cd frontend && npm run lint || pnpm run lint

format: format-backend format-frontend

format-backend:
	cd backend && source venv/bin/activate && ruff format . && ruff check --fix .

format-frontend:
	cd frontend && npm run format || pnpm run format

clean:
	rm -rf backend/venv
	rm -rf backend/.pytest_cache
	rm -rf backend/.mypy_cache
	rm -rf backend/.ruff_cache
	rm -rf backend/__pycache__
	rm -rf backend/**/__pycache__
	rm -rf backend/dist
	rm -rf backend/build
	rm -rf backend/*.egg-info
	rm -rf frontend/node_modules
	rm -rf frontend/.next
	rm -rf frontend/out
	rm -rf frontend/dist
	rm -rf .qsscope/*.db
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete

bootstrap:
	./scripts/dev.sh || powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
