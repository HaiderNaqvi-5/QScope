import hashlib
import re
from pathlib import Path

from app.services.llm.schemas import ContextManifestEntry

DENIED_PARTS = {".git", ".env", "node_modules", "vendor", "dist", "build", ".venv", "venv", "__pycache__"}
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*(['\"]?)[^\s,'\"]+\2"),
    re.compile(r"\b(?:sk|gsk|ghp)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)


def path_allowed(root: Path, candidate: Path) -> bool:
    try:
        relative = candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return not any(part in DENIED_PARTS or part.startswith(".env") for part in relative.parts)


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern in SECRET_PATTERNS:
        text, replaced = pattern.subn("[REDACTED_SECRET:credential]", text)
        count += replaced
    return text, count


def build_context(root: Path, file_path: str | None, line: int | None, radius: int = 40) -> tuple[str, list[ContextManifestEntry]]:
    if not file_path:
        return "", []
    candidate = root / file_path
    if not path_allowed(root, candidate) or not candidate.is_file() or candidate.stat().st_size > 1_000_000:
        return "", []
    try:
        lines = candidate.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return "", []
    target = max(1, line or 1)
    start = max(1, target - radius)
    end = min(len(lines), target + radius, start + 249)
    raw = "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
    safe, count = redact(raw)
    relative = candidate.resolve().relative_to(root.resolve()).as_posix()
    manifest = ContextManifestEntry(path=relative, start_line=start, end_line=end,
        sha256=hashlib.sha256(raw.encode()).hexdigest(), redaction_count=count)
    return f'<source path="{relative}" lines="{start}-{end}">\n{safe}\n</source>', [manifest]
