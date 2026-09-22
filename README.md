# QSScope — Local Full-Stack Quality, Security & Testing Intelligence Platform

> Understand a project’s quality, test coverage, runtime readiness, and
> security signals with deterministic, local-first analysis.

A local-first, deterministic platform for analyzing software projects. QSScope detects your project's language, frameworks, and test infrastructure, then orchestrates multiple quality and security engines to produce actionable findings and a professional quality report.

## What it does

- Discover languages, frameworks, package manifests, and test tooling
- Run Quick, Standard, or Full Audit scan plans using relevant local tools
- Consolidate code-quality, dependency, runtime, test, and security findings
- Track baselines and regression signals between scans
- Export deterministic JSON, Markdown, HTML, and CycloneDX SBOM reports
- Keep source code local by default, with optional and clearly disclosed AI
  assistance

## Integrated tooling

QSScope detects and prepares locally available tooling for the project being
reviewed. Its workflow covers API specifications and collections, browser-test
readiness, dependency inventory, accessibility and performance evidence, and
local security/load-test tooling.

Some integrations require a local installation or explicit approval before they
run. They are shown as available capabilities when detected; QSScope does not
install tools or transmit source code automatically.

## How it works

1. Add a local project and let QSScope discover its languages, frameworks,
   package manifests, and test tooling.
2. Run a Quick, Standard, or Full Audit with only the locally available tools
   that are relevant to that project.
3. Review normalized findings, evidence, quality scores, baselines, and release
   readiness in the dashboard.
4. Export portable reports for sharing or retaining a deterministic audit trail.

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
├── backend/                # FastAPI Python backend
├── frontend/               # Next.js React frontend
├── scripts/                # Development and deployment scripts
└── .qsscope/              # Runtime data (Git-ignored)
```

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

## Status

The core local-first workflow is implemented and tested: discovery, preflight, scan planning,
safe local execution, localhost API targets with health checks, OpenAPI/GraphQL Schemathesis readiness, Postman/Newman
collection readiness, Playwright browser-test readiness, lockfile and pyproject dependency
inventory, deterministic CycloneDX SBOM export, structured adapters, findings, baselines,
scoring, accessibility/performance readiness and evidence normalization, API test evidence
normalization, history, and JSON/Markdown/HTML
exports, including DOCX, plus approval-gated ZAP/k6/JMeter readiness for detected local
artifacts, local advisory code-hygiene heuristics, optional PDF export when the local
Playwright Chromium renderer is installed, and privacy-safe Groq readiness status. AI actions
remain opt-in and bounded; browser execution expansion and AI review workflows remain planned.

The product is intentionally local-first: source code stays on the machine by
default. Optional AI review is opt-in and constrained to the configured flow.

## License

See LICENSE file for details.
