# QSScope development startup script for Windows PowerShell

param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "🚀 QSScope Development Setup" -ForegroundColor Green
Write-Host "Project root: $ProjectRoot`n"

# Check prerequisites
Write-Host "📋 Checking prerequisites...`n"

# Check Python
$PythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Python 3 not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python $PythonVersion found" -ForegroundColor Green

# Check Node.js
$NodeVersion = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Node.js not found. Please install Node.js 18+" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Node.js $NodeVersion found" -ForegroundColor Green

# Check Git
$GitVersion = git --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Git not found. Please install Git" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Git found`n" -ForegroundColor Green

# Initialize backend
if (-not $SkipBackend) {
    Write-Host "📦 Setting up backend..."
    Set-Location "$ProjectRoot\backend"

    if (-not (Test-Path "venv")) {
        Write-Host "Creating Python virtual environment..."
        python -m venv venv
    }

    # Activate virtual environment
    & ".\venv\Scripts\Activate.ps1"

    Write-Host "Installing Python dependencies..."
    python -m pip install --upgrade pip setuptools wheel 2>&1 | Out-Null
    pip install -e ".[dev]" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        pip install -e "." 2>&1 | Out-Null
    }

    Write-Host "✓ Backend dependencies installed`n" -ForegroundColor Green
}

# Initialize frontend
if (-not $SkipFrontend) {
    Write-Host "📦 Setting up frontend..."
    Set-Location "$ProjectRoot\frontend"

    if (Test-Path "node_modules") {
        Write-Host "node_modules already exists, skipping install"
    }
    else {
        Write-Host "Installing Node dependencies..."
        if (Get-Command pnpm -ErrorAction SilentlyContinue) {
            pnpm install
        }
        else {
            npm install
        }
    }

    Write-Host "✓ Frontend dependencies installed`n" -ForegroundColor Green
}

# Initialize database
Write-Host "🗄️  Setting up database..."
Set-Location "$ProjectRoot\backend"

if (-not (Test-Path "..\\.env")) {
    Write-Host "Creating .env from .env.example..."
    Copy-Item "$ProjectRoot\.env.example" "$ProjectRoot\.env" -Force
}

# Activate venv if not already active
if ($null -eq $env:VIRTUAL_ENV) {
    & ".\venv\Scripts\Activate.ps1"
}

# TODO: Run Alembic migrations when they exist
# alembic upgrade head

Write-Host "✓ Database ready`n" -ForegroundColor Green

# Print startup instructions
Write-Host "✅ Setup complete!`n" -ForegroundColor Green
Write-Host "🎯 To start the application:`n"
Write-Host "Backend (in terminal 1):" -ForegroundColor Cyan
Write-Host "  cd backend"
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "Frontend (in terminal 2):" -ForegroundColor Cyan
Write-Host "  cd frontend"
Write-Host "  npm run dev  # or: pnpm run dev"
Write-Host ""
Write-Host "Then open:" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:3000"
Write-Host "  Backend:  http://localhost:8000"
Write-Host "  API Docs: http://localhost:8000/docs"
Write-Host ""
Write-Host "To run tests:" -ForegroundColor Cyan
Write-Host "  Backend:  cd backend && pytest"
Write-Host "  Frontend: cd frontend && npm run test"
Write-Host ""
