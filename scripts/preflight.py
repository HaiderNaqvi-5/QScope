#!/usr/bin/env python3
"""
QSScope Preflight Checks

Verifies that the development environment has required tools and dependencies.
"""

import sys
import subprocess
from pathlib import Path


class Checker:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def check(self, name: str, command: list, min_version: str | None = None) -> bool:
        """Check if a command is available."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                output = result.stdout.strip() or result.stderr.strip()
                if min_version:
                    print(f"✓ {name}: {output}")
                else:
                    print(f"✓ {name}")
                self.passed += 1
                return True
            else:
                print(f"✗ {name}: {result.stderr.strip()}")
                self.failed += 1
                return False
        except FileNotFoundError:
            print(f"✗ {name}: Not found in PATH")
            self.failed += 1
            return False
        except subprocess.TimeoutExpired:
            print(f"⚠ {name}: Check timed out")
            self.warnings += 1
            return False
        except Exception as e:
            print(f"⚠ {name}: {e}")
            self.warnings += 1
            return False

    def check_directory(self, path: str, name: str) -> bool:
        """Check if a directory exists."""
        p = Path(path)
        if p.exists() and p.is_dir():
            print(f"✓ {name} directory exists")
            self.passed += 1
            return True
        else:
            print(f"✗ {name} directory missing: {path}")
            self.failed += 1
            return False

    def check_file(self, path: str, name: str) -> bool:
        """Check if a file exists."""
        p = Path(path)
        if p.exists() and p.is_file():
            print(f"✓ {name} file exists")
            self.passed += 1
            return True
        else:
            print(f"✗ {name} file missing: {path}")
            self.failed += 1
            return False

    def summary(self) -> int:
        """Print summary and return exit code."""
        print(f"\n{'='*50}")
        print(f"Passed: {self.passed}")
        print(f"Warnings: {self.warnings}")
        print(f"Failed: {self.failed}")
        print(f"{'='*50}")
        
        if self.failed == 0:
            print("✅ All checks passed!")
            return 0
        else:
            print("❌ Some checks failed. See above for details.")
            return 1


def main():
    """Run preflight checks."""
    print("🔍 QSScope Preflight Checks\n")
    
    checker = Checker()
    project_root = Path(__file__).parent.parent

    # Check system tools
    print("System Prerequisites:")
    checker.check("Git", ["git", "--version"])
    checker.check("Python 3", ["python3", "--version"])
    checker.check("Node.js", ["node", "--version"])
    
    print("\nRepository Structure:")
    checker.check_directory(project_root / "backend", "Backend")
    checker.check_directory(project_root / "frontend", "Frontend")
    checker.check_directory(project_root / "Doc & prd", "Documentation")
    checker.check_directory(project_root / "scripts", "Scripts")
    checker.check_directory(project_root / ".qsscope", ".qsscope data")
    
    print("\nConfiguration Files:")
    checker.check_file(project_root / ".gitignore", ".gitignore")
    checker.check_file(project_root / ".env.example", ".env.example")
    checker.check_file(project_root / ".editorconfig", ".editorconfig")
    checker.check_file(project_root / "README.md", "README.md")
    checker.check_file(project_root / "LICENSE", "LICENSE")
    
    print("\nBackend Configuration:")
    checker.check_file(project_root / "backend" / "pyproject.toml", "Backend pyproject.toml")
    checker.check_file(project_root / "backend" / "alembic.ini", "Alembic config")
    
    print("\nFrontend Configuration:")
    checker.check_file(project_root / "frontend" / "package.json", "Frontend package.json")
    checker.check_file(project_root / "frontend" / "tsconfig.json", "TypeScript config")
    checker.check_file(project_root / "frontend" / "next.config.ts", "Next.js config")
    checker.check_file(project_root / "frontend" / "tailwind.config.ts", "Tailwind config")
    
    print("\nDocumentation:")
    checker.check_file(project_root / "Doc & prd" / "PRD.md", "PRD")
    checker.check_file(project_root / "Doc & prd" / "PROJECT_RULES.md", "Project Rules")
    checker.check_file(project_root / "Doc & prd" / "IMPLEMENTATION_PLAN.md", "Implementation Plan")
    checker.check_file(project_root / "Doc & prd" / "implementation.md", "Status")
    checker.check_file(project_root / "Doc & prd" / "sessions" / "prd_and_architecture.md", "Architecture Notes")
    
    print("\nDevelopment Scripts:")
    checker.check_file(project_root / "scripts" / "dev.sh", "dev.sh")
    checker.check_file(project_root / "scripts" / "dev.ps1", "dev.ps1")
    
    return checker.summary()


if __name__ == "__main__":
    sys.exit(main())
