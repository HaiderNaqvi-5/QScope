# QSScope — Local Full-Stack Quality, Security & Testing Intelligence Platform

A local-first, deterministic platform for analyzing software projects. QSScope detects your project's language, frameworks, and test infrastructure, then orchestrates multiple quality and security engines to produce actionable findings and a professional quality report.

## Key Features

- **Full-Stack Analysis**: Analyzes frontend, backend, APIs, dependencies, infrastructure, and test suites
- **Local-First**: All source code stays on your machine by default
- **Language-Agnostic**: Support for JavaScript/TypeScript, Python, Java, PHP, Go, C#/.NET, Rust, and more
- **Multiple Scanning Modes**: Quick, Standard, and Full Audit scans
- **Unified Findings Dashboard**: Consolidated results from multiple independent analyzers
- **Regression Baselines**: Track quality improvements between scans
- **Portable Reports**: Export deterministic JSON, Markdown, HTML, and CycloneDX SBOM reports; DOCX/PDF remain planned
- **AI-Assisted Review**: Groq integration is planned and remains optional; no source leaves the machine by default

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm/pnpm
- Git

### Local Development

1. Clone the repository and navigate to it:
   ```bash
   cd /path/to/QSScope
   ```

2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

3. Run the development setup:
   ```bash
   # On Linux/macOS
   ./scripts/dev.sh

   # On Windows PowerShell
   ./scripts/dev.ps1
   ```

4. Open the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API docs: http://localhost:8000/docs

## Repository Structure

```
QSScope/
├── Doc & prd/              # Product requirements, implementation plan, session docs
├── backend/                # FastAPI Python backend
├── frontend/               # Next.js React frontend
├── report_templates/       # DOCX, PDF, HTML report templates
├── scripts/                # Development and deployment scripts
└── .qsscope/              # Runtime data (Git-ignored)
```

For detailed architecture, see `Doc & prd/PRD.md`.

## Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest
```

### Frontend

```bash
cd frontend
pnpm install
pnpm run dev
pnpm run test
```

## Documentation

- **PRD**: `Doc & prd/PRD.md` - Complete product specification
- **Implementation Plan**: `Doc & prd/IMPLEMENTATION_PLAN.md` - Build milestones and tasks
- **Project Rules**: `Doc & prd/PROJECT_RULES.md` - Coding standards and decisions
- **Session Notes**: `Doc & prd/sessions/` - Development notes by milestone

## Status

The core local-first workflow is implemented and tested: discovery, preflight, scan planning,
safe local execution, localhost API targets with health checks, OpenAPI/GraphQL Schemathesis readiness, Postman/Newman
collection readiness, Playwright browser-test readiness, lockfile and pyproject dependency
inventory, deterministic CycloneDX SBOM export, structured adapters, findings, baselines,
scoring, accessibility/performance readiness and evidence normalization, API test evidence
normalization, history, and JSON/Markdown/HTML
exports. Browser execution expansion, AI review, and DOCX/PDF
reporting remain planned. See
`Doc & prd/implementation.md` for the authoritative milestone status.

## License

See LICENSE file for details.

## Contributing

This is a locked-specification project. Before contributing, read `Doc & prd/PROJECT_RULES.md` and the PRD.
