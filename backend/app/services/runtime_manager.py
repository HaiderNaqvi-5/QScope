"""Manage explicitly approved, loopback-only project service processes."""
from __future__ import annotations

import asyncio
import ipaddress
import os
import signal
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models import RuntimeProfile

MAX_RUNTIME_LOG_BYTES = 1_000_000
_processes: dict[str, asyncio.subprocess.Process] = {}
_logs: dict[str, bytearray] = {}
_drainers: dict[str, asyncio.Task[None]] = {}


def validate_local_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("runtime URL must use http or https")
    hostname = parsed.hostname.lower()
    if hostname != "localhost":
        try:
            if not ipaddress.ip_address(hostname).is_loopback:
                raise ValueError("runtime URL must target localhost or a loopback address")
        except ValueError as exc:
            if "must target" in str(exc):
                raise
            raise ValueError("runtime URL must target localhost or a loopback address") from exc
    return value


def resolve_project_path(root: Path, relative: str, *, require_dir: bool = False) -> Path:
    project_root = root.resolve()
    candidate = (project_root / relative).resolve()
    if candidate != project_root and project_root not in candidate.parents:
        raise ValueError("runtime path escapes project root")
    if require_dir and not candidate.is_dir():
        raise ValueError("runtime working directory does not exist")
    return candidate


def _environment_from_file(root: Path, relative: str | None) -> dict[str, str]:
    environment = os.environ.copy()
    if not relative:
        return environment
    path = resolve_project_path(root, relative)
    if not path.is_file():
        raise ValueError("runtime environment file does not exist")
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key.replace("_", "a").isalnum() and not key[0].isdigit():
            environment[key] = value.strip().strip('"').strip("'")
    return environment


async def _drain(profile_id: str, process: asyncio.subprocess.Process) -> None:
    assert process.stdout is not None
    retained = _logs.setdefault(profile_id, bytearray())
    while chunk := await process.stdout.read(65_536):
        retained.extend(chunk)
        if len(retained) > MAX_RUNTIME_LOG_BYTES:
            del retained[:-MAX_RUNTIME_LOG_BYTES]


async def _set_state(profile_id: str, **values: object) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(RuntimeProfile).where(RuntimeProfile.id == profile_id).values(**values))
        await db.commit()


def _health_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=1) as response:  # noqa: S310 - URL is loopback-validated.
            return response.status < 500
    except Exception:
        return False


async def start_runtime(profile: RuntimeProfile, project_root: Path, *, approved: bool) -> None:
    if profile.id in _processes and _processes[profile.id].returncode is None:
        raise ValueError("runtime is already running")
    if not profile.trusted_default and not approved:
        raise PermissionError("explicit approval is required for this runtime command")
    validate_local_url(profile.local_url)
    health_url = urljoin(profile.local_url.rstrip("/") + "/", (profile.health_endpoint or "").lstrip("/"))
    validate_local_url(health_url)
    working_directory = resolve_project_path(project_root, profile.working_directory, require_dir=True)
    environment = _environment_from_file(project_root, profile.environment_file)
    await _set_state(profile.id, status="STARTING", last_error=None)
    process = await asyncio.create_subprocess_exec(
        *profile.command, cwd=str(working_directory), env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    _processes[profile.id] = process
    _logs[profile.id] = bytearray()
    _drainers[profile.id] = asyncio.create_task(_drain(profile.id, process))
    await _set_state(profile.id, pid=process.pid)
    deadline = asyncio.get_running_loop().time() + profile.startup_timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if process.returncode is not None:
            await _set_state(profile.id, status="FAILED", pid=None, last_error="runtime exited before readiness")
            raise RuntimeError("runtime exited before readiness")
        if await asyncio.to_thread(_health_ready, health_url):
            await _set_state(profile.id, status="READY", pid=process.pid)
            return
        await asyncio.sleep(0.2)
    await stop_runtime(profile.id)
    await _set_state(profile.id, status="FAILED", pid=None, last_error="startup timeout exceeded")
    raise TimeoutError("runtime startup timeout exceeded")


async def stop_runtime(profile_id: str) -> bool:
    process = _processes.get(profile_id)
    if not process or process.returncode is not None:
        await _set_state(profile_id, status="STOPPED", pid=None)
        return False
    await _set_state(profile_id, status="STOPPING")
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        await asyncio.wait_for(process.wait(), timeout=3)
    except (ProcessLookupError, asyncio.TimeoutError):
        if process.returncode is None:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
    drainer = _drainers.pop(profile_id, None)
    if drainer:
        await asyncio.gather(drainer, return_exceptions=True)
    _processes.pop(profile_id, None)
    await _set_state(profile_id, status="STOPPED", pid=None)
    return True


def runtime_log(profile_id: str) -> tuple[str, bool]:
    raw = bytes(_logs.get(profile_id, b""))
    return raw.decode("utf-8", errors="replace"), len(raw) >= MAX_RUNTIME_LOG_BYTES


async def shutdown_runtimes() -> None:
    for profile_id in list(_processes):
        await stop_runtime(profile_id)
