"""QSScope's locked local analyzer registry."""
from app.tools.capability import ToolDefinition


def _tool(id: str, name: str, categories: tuple[str, ...], *, ecosystems: tuple[str, ...] = (),
          required: bool = False, guidance: str = "", adapter: str = "universal",
          formats: tuple[str, ...] = ("text",), executable: str | None = None,
          version_args: tuple[str, ...] = ("--version",)) -> ToolDefinition:
    return ToolDefinition(id, name, executable or id, version_args, categories, ecosystems, required,
                          guidance, timeout_seconds=300, output_formats=formats, adapter=adapter)


TOOLS = (
    _tool("git", "Git", ("discovery", "secrets"), guidance="Install Git and ensure it is on PATH."),
    _tool("python", "Python", ("build",), ecosystems=("Python",), required=True,
          guidance="Install Python 3.11 or newer.", adapter="python"),
    _tool("node", "Node.js", ("build",), ecosystems=("JavaScript", "TypeScript"), required=True,
          guidance="Install a supported Node.js LTS release.", adapter="javascript"),
    _tool("npm", "npm", ("build", "tests"), ecosystems=("JavaScript", "TypeScript"),
          guidance="Install npm with Node.js.", adapter="javascript"),
    _tool("pytest", "pytest", ("tests", "coverage"), ecosystems=("Python",), guidance="Install pytest in the project environment.", adapter="python"),
    _tool("ruff", "Ruff", ("quality",), ecosystems=("Python",), guidance="Install Ruff or configure its executable.", adapter="python", formats=("json",)),
    _tool("mypy", "mypy", ("typecheck",), ecosystems=("Python",), guidance="Install mypy when configured by the project.", adapter="python"),
    _tool("eslint", "ESLint", ("quality",), ecosystems=("JavaScript", "TypeScript"), guidance="Install ESLint in the project.", adapter="javascript", executable="npx"),
    _tool("tsc", "TypeScript", ("typecheck",), ecosystems=("TypeScript",), guidance="Install TypeScript in the project.", adapter="javascript", executable="npx"),
    _tool("knip", "Knip", ("dead-code",), ecosystems=("JavaScript", "TypeScript"), guidance="Install Knip in the project.", adapter="javascript", executable="npx"),
    _tool("go", "Go", ("build", "tests"), ecosystems=("Go",), required=True, guidance="Install Go.", adapter="go"),
    _tool("cargo", "Cargo", ("build", "tests"), ecosystems=("Rust",), required=True, guidance="Install Rust/Cargo.", adapter="rust"),
    _tool("mvn", "Maven", ("build", "tests"), ecosystems=("Java",), guidance="Install Maven.", adapter="java"),
    _tool("gradle", "Gradle", ("build", "tests"), ecosystems=("Java",), guidance="Install Gradle.", adapter="java"),
    _tool("staticcheck", "Staticcheck", ("quality",), ecosystems=("Go",), guidance="Install Staticcheck.", adapter="go"),
    _tool("govulncheck", "govulncheck", ("vulnerabilities",), ecosystems=("Go",), guidance="Install govulncheck.", adapter="go"),
    _tool("cargo-audit", "cargo-audit", ("vulnerabilities",), ecosystems=("Rust",), guidance="Install cargo-audit.", adapter="rust"),
    _tool("phpstan", "PHPStan", ("quality",), ecosystems=("PHP",), guidance="Install PHPStan in the project.", adapter="php"),
    _tool("psalm", "Psalm", ("quality",), ecosystems=("PHP",), guidance="Install Psalm in the project.", adapter="php"),
    _tool("php", "PHP", ("build", "tests"), ecosystems=("PHP",), required=True, guidance="Install PHP.", adapter="php"),
    _tool("composer", "Composer", ("dependencies",), ecosystems=("PHP",), guidance="Install Composer.", adapter="php"),
    _tool("dotnet", ".NET SDK", ("build", "tests"), ecosystems=("C#",), required=True, guidance="Install the .NET SDK.", adapter="dotnet"),
    _tool("semgrep", "Semgrep CE", ("sast",), guidance="Install Semgrep Community Edition.", formats=("json", "sarif")),
    _tool("gitleaks", "Gitleaks", ("secrets",), guidance="Install Gitleaks.", formats=("json", "sarif")),
    _tool("osv-scanner", "OSV-Scanner", ("vulnerabilities",), guidance="Install OSV-Scanner.", formats=("json",)),
    _tool("trivy", "Trivy", ("vulnerabilities", "configuration"), guidance="Install Trivy.", formats=("json", "cyclonedx")),
    _tool("syft", "Syft", ("sbom",), guidance="Install Syft for local SBOM generation.", formats=("cyclonedx-json", "spdx-json")),
    _tool("jscpd", "jscpd", ("duplication",), guidance="Install jscpd.", executable="npx", formats=("json",)),
    _tool("lizard", "Lizard", ("complexity",), guidance="Install Lizard.", formats=("csv", "xml")),
    _tool("schemathesis", "Schemathesis", ("api",), guidance="Install Schemathesis.", formats=("json",)),
    _tool("newman", "Newman", ("api",), guidance="Install Newman.", formats=("json",)),
    _tool("playwright", "Playwright", ("browser",), guidance="Install project Playwright and browsers.", executable="npx"),
    _tool("axe", "axe-core", ("accessibility",), guidance="Install @axe-core/playwright in the project.", executable="npx"),
    _tool("lighthouse", "Lighthouse", ("performance",), guidance="Install Lighthouse.", executable="npx", formats=("json",)),
    _tool("zap", "OWASP ZAP", ("dast",), guidance="Install OWASP ZAP.", executable="zap-baseline.py", formats=("json", "html")),
    _tool("k6", "k6", ("load",), guidance="Install k6.", formats=("json",)),
    _tool("jmeter", "Apache JMeter", ("load",), guidance="Install Apache JMeter.", formats=("jtl", "xml")),
)

TOOL_REGISTRY = {tool.id: tool for tool in TOOLS}
